"""A2: re-ingesting a document removes its obsolete chunks, atomically.

Scratch DB only (testsafe), deterministic embedder (patched at ingestion_service.generate_embeddings),
generated PDFs. Failure injection for database errors uses a proxy around the real connection/cursor so the
real PostgreSQL transaction semantics (commit/rollback) are what is verified. Cleanup removes only a2_* rows.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
import uuid
from unittest import mock

import numpy as np
import pymupdf

import services.ingestion_service as ingestion
from services import retrieval_config as cfg
from services.chunker import chunk_text
from services.database import get_connection

FAILURES = []
PREFIX = "a2_"
WORKDIR = tempfile.mkdtemp(prefix="a2_pdf_")
REAL_GET_CONNECTION = ingestion.get_connection


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def words(tag, n):
    return " ".join(f"{tag}w{i:03d}" for i in range(1, n + 1))


def make_pdf(filename, pages):
    path = os.path.join(WORKDIR, filename)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            assert page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=9) >= 0
    doc.save(path)
    doc.close()
    return path


def det_embedder(texts):
    out = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        v = np.random.default_rng(seed).normal(size=cfg.EMBEDDING_DIM)
        out.append(v / np.linalg.norm(v))
    return np.array(out)


def snapshot(doc_name):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, page_number, chunk_id, content, embedding::text FROM document_chunks "
            "WHERE document_name=%s ORDER BY page_number, chunk_id", (doc_name,)).fetchall()


def foreign_snapshot(prefix_owner_names):
    with get_connection() as conn:
        return conn.execute(
            "SELECT count(*), coalesce(md5(string_agg(d::text, '|' ORDER BY d.id)), '') FROM document_chunks d "
            "WHERE document_name <> ALL(%s) AND document_name NOT LIKE %s", (prefix_owner_names, PREFIX + "%")).fetchone()


class Cursor:
    def __init__(self, real, rule, counter):
        self.real, self.rule, self.counter = real, rule, counter

    def execute(self, sql, params=None):
        self.counter.append(sql.strip().split()[0].upper())
        if self.rule(sql.strip().split()[0].upper(), self.counter.count(sql.strip().split()[0].upper())):
            raise RuntimeError("injected database failure")
        return self.real.execute(sql, params)

    def __getattr__(self, item):
        return getattr(self.real, item)


class CursorContext:
    def __init__(self, ctx, rule, counter):
        self.ctx, self.rule, self.counter = ctx, rule, counter

    def __enter__(self):
        return Cursor(self.ctx.__enter__(), self.rule, self.counter)

    def __exit__(self, *exc):
        return self.ctx.__exit__(*exc)


class Connection:
    def __init__(self, real, rule, counter):
        self.real, self.rule, self.counter = real, rule, counter

    def __enter__(self):
        self.real.__enter__()
        return self

    def __exit__(self, *exc):
        return self.real.__exit__(*exc)

    def cursor(self):
        return CursorContext(self.real.cursor(), self.rule, self.counter)

    def __getattr__(self, item):
        return getattr(self.real, item)


def ingest(path, embedder=det_embedder, extract=None, db_rule=None):
    counter = []
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(ingestion, "generate_embeddings", side_effect=embedder))
        if extract is not None:
            stack.enter_context(mock.patch.object(ingestion, "extract_text", side_effect=extract))
        if db_rule is not None:
            stack.enter_context(mock.patch.object(
                ingestion, "get_connection", side_effect=lambda: Connection(REAL_GET_CONNECTION(), db_rule, counter)))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        try:
            ingestion.ingest_pdf(path)
            return None
        except Exception as error:  # noqa: BLE001
            return error


def expected_chunks(text):
    return chunk_text(text, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)


def run():
    fname = f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf"
    other = f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf"
    sibling = fname + ".old.pdf"                   # a name that starts with fname (kept .pdf for A4)
    outside_before = foreign_snapshot([])

    v_long, v_mid, v_short = words("lg", 330), words("md", 130), words("sh", 40)
    check("[setup] chunk counts: long 4, mid 2, short 1",
          [len(expected_chunks(t)) for t in (v_long, v_mid, v_short)] == [4, 2, 1])

    # isolation fixtures: another document and a name-prefix sibling, same page/chunk ids
    for n in (other, sibling):
        assert ingest(make_pdf(n, [words("ot", 330)])) is None
    other_snap, sibling_snap = snapshot(other), snapshot(sibling)

    # ---- longer re-ingest
    assert ingest(make_pdf(fname, [v_mid])) is None
    first = snapshot(fname)
    check("[longer] initial 2 chunks", len(first) == 2)
    assert ingest(make_pdf(fname, [v_long])) is None
    longer = snapshot(fname)
    check("[longer] 2 -> 4 chunks, exactly the new version, earlier ids kept",
          [r[3] for r in longer] == expected_chunks(v_long) and [r[0] for r in longer][:2] == [r[0] for r in first])

    # ---- shorter re-ingest (the A2 case)
    assert ingest(make_pdf(fname, [v_short])) is None
    shorter = snapshot(fname)
    check("[shorter] 4 -> 1: exactly the current chunk remains, no obsolete chunk",
          [r[3] for r in shorter] == expected_chunks(v_short) and len(shorter) == 1)
    check("[shorter] the surviving chunk keeps its row id (updated in place, not recreated)", shorter[0][0] == longer[0][0])
    check("[isolation] another document and a name-prefix sibling are untouched by the shrink",
          snapshot(other) == other_snap and snapshot(sibling) == sibling_snap)

    # ---- multi-page shrink removes whole pages
    assert ingest(make_pdf(fname, [words("pa", 40), words("pb", 40), words("pc", 40)])) is None
    check("[pages] 3 pages stored", [r[1] for r in snapshot(fname)] == [1, 2, 3])
    assert ingest(make_pdf(fname, [words("pa", 40)])) is None
    check("[pages] shrinking to 1 page removes the chunks of pages 2 and 3", [r[1] for r in snapshot(fname)] == [1])
    assert ingest(make_pdf(fname, ["", words("pz", 40)])) is None
    check("[pages] a document whose only text is now on page 2 loses the old page-1 chunk",
          [(r[1], r[2]) for r in snapshot(fname)] == [(2, 1)])

    # ---- same number of chunks, changed content
    assert ingest(make_pdf(fname, [v_mid])) is None
    base = snapshot(fname)
    assert ingest(make_pdf(fname, [words("ch", 130)])) is None
    changed = snapshot(fname)
    check("[same count] changed content: same ids, new content and embeddings, no extra rows",
          [r[0] for r in changed] == [r[0] for r in base] and len(changed) == len(base)
          and all(c[3] != b[3] and c[4] != b[4] for c, b in zip(changed, base)))

    # ---- repeated identical ingestion
    assert ingest(make_pdf(fname, [v_long])) is None
    stable = snapshot(fname)
    assert ingest(make_pdf(fname, [v_long])) is None
    assert ingest(make_pdf(fname, [v_long])) is None
    check("[repeat] identical re-ingestion leaves rows, ids, content and embeddings unchanged", snapshot(fname) == stable)

    # ---- failures after a successful stored version: previous state must be preserved exactly
    prev = snapshot(fname)
    new_pdf = make_pdf(fname, [v_short])       # a shorter version that WOULD trigger deletion if it succeeded

    def preserved(label, error, expected=None):
        ok = error is not None and snapshot(fname) == prev
        if expected is not None:
            ok = ok and expected(error)
        check(f"[failure preserves state] {label}", ok)

    preserved("blank/empty PDF -> ValueError('No usable chunks')",
              ingest(make_pdf(fname, ["", ""])), lambda e: isinstance(e, ValueError))
    garbage = os.path.join(WORKDIR, fname)
    open(garbage, "wb").write(os.urandom(500))
    preserved("invalid (garbage) PDF bytes", ingest(garbage))
    new_pdf = make_pdf(fname, [v_short])
    preserved("parser failure", ingest(new_pdf, extract=RuntimeError("parser exploded")),
              lambda e: isinstance(e, RuntimeError))

    def boom(texts):
        raise ConnectionError("embedding down")
    preserved("embedding failure", ingest(new_pdf, embedder=boom), lambda e: isinstance(e, ConnectionError))
    preserved("embedding dimension mismatch", ingest(new_pdf, embedder=lambda t: np.zeros((len(t), 7))),
              lambda e: isinstance(e, ValueError) and "EMBEDDING_DIM" in str(e))
    preserved("embedding count mismatch (too few)", ingest(make_pdf(fname, [v_long]), embedder=lambda t: det_embedder(t)[:-1]),
              lambda e: isinstance(e, ValueError) and "Embedding count" in str(e))
    new_pdf = make_pdf(fname, [v_short])

    # database failure during insertion (2nd INSERT of a longer new version, with changed content)
    changed_long = make_pdf(fname, [words("zz", 330)])
    preserved("database failure during insertion (injected on the 2nd INSERT)",
              ingest(changed_long, db_rule=lambda verb, n: verb == "INSERT" and n == 2),
              lambda e: "injected" in str(e))

    def nan_second(texts):
        v = det_embedder(texts)
        v[1][0] = float("nan")
        return v
    preserved("real database error during insertion (NaN vector in chunk 2)", ingest(changed_long, embedder=nan_second))

    # database failure during stale deletion: the new (shorter) version has already been upserted in the transaction
    new_pdf = make_pdf(fname, [v_short])       # same path as before: re-create the shorter version
    preserved("database failure during stale-chunk deletion (injected on DELETE)",
              ingest(new_pdf, db_rule=lambda verb, n: verb == "DELETE"), lambda e: "injected" in str(e))
    check("[atomicity] after the failed deletion the upsert of chunk 1 was rolled back too (old content still there)",
          snapshot(fname) == prev and not snapshot(fname)[0][3].startswith("shw"))

    # sanity: the same shorter file now succeeds and cleans up
    assert ingest(new_pdf) is None
    final = snapshot(fname)
    check("[recovery] after the failures the shorter version ingests and removes the obsolete chunks",
          [r[3] for r in final] == expected_chunks(v_short))

    check("[isolation] other documents unchanged through the whole run", snapshot(other) == other_snap and snapshot(sibling) == sibling_snap)
    check("[isolation] no row outside a2_* documents was touched", foreign_snapshot([]) == outside_before)


try:
    run()
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("[cleanup] no test rows left", left == 0)
check("[cleanup] temp directory removed", not os.path.exists(WORKDIR))
print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
