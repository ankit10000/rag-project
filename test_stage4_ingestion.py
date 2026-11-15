"""Batch 2 / Stage 4: PDF ingestion pipeline verification (service level).

Scratch database only (testsafe; run via run_tests.py, e.g. --db rag_ingestion_test).
Generated PDFs only. Embeddings: the REAL configured model (offline, from the local
Hugging Face cache) for the embedding and persistence checks; a deterministic
fake embedder elsewhere. Failure injection wraps the real connection so real
PostgreSQL commit/rollback semantics are what is verified.
Cleanup removes only s4_* documents. No document text is printed.
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
from unittest import mock

import numpy as np
import pymupdf

import services.ingestion_service as ingestion
import services.embedding_service as embedding_service
from services import retrieval_config as cfg
from services.chunker import chunk_page
from services.database import get_connection
from services.pdf_parser import InvalidPDFError, PDFLimitExceeded, extract_text

FAILURES = []
PREFIX = "s4_"
WORKDIR = tempfile.mkdtemp(prefix="s4_pdf_")
ROOT = os.path.dirname(os.path.abspath(__file__))


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def words(tag, n):
    return " ".join(f"{tag}w{i:03d}" for i in range(1, n + 1))


def make_pdf(filename, pages, directory=WORKDIR, metadata=None, fontname="helv", **save):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            assert page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=8, fontname=fontname) >= 0
    if metadata:
        doc.set_metadata(metadata)
    doc.save(path, **save)
    doc.close()
    return path


def det_embedder(texts):
    out = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        v = np.random.default_rng(seed).normal(size=cfg.EMBEDDING_DIM)
        out.append(v / np.linalg.norm(v))
    return np.array(out)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def ingest(path, embedder=det_embedder):
    """Run ingest_pdf; return the exception (or None)."""
    try:
        with mock.patch.object(ingestion, "generate_embeddings", side_effect=embedder):
            quiet(ingestion.ingest_pdf, path)
        return None
    except Exception as error:  # noqa: BLE001
        return error


def rows(document_name):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, page_number, chunk_id, md5(content), vector_dims(embedding), embedding::text "
            "FROM document_chunks WHERE document_name = %s ORDER BY page_number, chunk_id",
            (document_name,),
        ).fetchall()


def cleanup():
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))


cleanup()
try:
    # ------------------------------------------------------------- 4.2/4.3 validation
    valid = make_pdf("s4_valid.pdf", [words("p1", 150), "", words("p3", 60)])
    check("[validate] valid multi-page PDF ingests", ingest(valid) is None and len(rows("s4_valid.pdf")) > 0)

    zero = os.path.join(WORKDIR, "s4_zero.pdf"); open(zero, "wb").close()
    textpdf = os.path.join(WORKDIR, "s4_text.pdf")
    with open(textpdf, "w") as f:
        f.write("plain text renamed to .pdf\n" * 20)
    garbage = os.path.join(WORKDIR, "s4_garbage.pdf")
    with open(garbage, "wb") as f:
        f.write(os.urandom(4096))
    header_only = os.path.join(WORKDIR, "s4_header.pdf")
    with open(header_only, "wb") as f:
        f.write(b"%PDF-1.7\n" + os.urandom(800))
    encrypted = make_pdf("s4_encrypted.pdf", [words("enc", 50)],
                         encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    for label, path in [("zero-byte", zero), ("non-PDF renamed to .pdf", textpdf), ("random bytes", garbage),
                        ("PDF header + garbage", header_only), ("user-password encrypted", encrypted)]:
        err = ingest(path)
        check(f"[validate] {label} -> InvalidPDFError (a ValueError), nothing stored",
              isinstance(err, InvalidPDFError) and isinstance(err, ValueError)
              and rows(os.path.basename(path)) == [])
        check(f"[diagnostics] {label}: message has no path; original error type kept in cause_type",
              WORKDIR not in str(err) and bool(getattr(err, "cause_type", None)))
        try:
            probe = os.path.join(WORKDIR, "s4_lockprobe.pdf")
            shutil.copy(path, probe)
            try:
                extract_text(probe)
            except InvalidPDFError:
                pass
            os.remove(probe)                  # must not be locked on Windows
            unlocked = True
        except PermissionError:
            unlocked = False
        check(f"[resources] {label}: the file is released after the error (can be deleted)", unlocked)

    owner_only = make_pdf("s4_owner_only.pdf", [words("own", 50)],
                          encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="")
    check("[validate] owner-password-only PDF (opens without a password) still ingests", ingest(owner_only) is None)

    blank = make_pdf("s4_blank.pdf", ["", ""])
    err = ingest(blank)
    check("[validate] PDF with no extractable text -> ValueError('No usable chunks'), nothing stored",
          isinstance(err, ValueError) and "No usable chunks" in str(err) and rows("s4_blank.pdf") == [])

    with mock.patch.object(cfg, "MAX_PDF_SIZE_MB", 0.0001):
        err = ingest(valid)
    check("[validate] oversized PDF -> PDFLimitExceeded before parsing", isinstance(err, PDFLimitExceeded))

    meta = make_pdf("s4_meta.pdf", [words("meta", 40)],
                    metadata={"title": "Ünïcødé — " + "x" * 2000, "author": "", "producer": None,
                              "keywords": "\u0000‮"})
    check("[validate] PDF with unusual metadata ingests", ingest(meta) is None and len(rows("s4_meta.pdf")) == 1)

    # ------------------------------------------------------------- 4.4 extraction
    pages = extract_text(valid)
    check("[extract] page numbers preserved and ordered; empty page skipped", [p["page_number"] for p in pages] == [1, 3])
    check("[extract] page text belongs to its page", "p1w001" in pages[0]["text"] and "p3w060" in pages[1]["text"])
    many = make_pdf("s4_many.pdf", [words(f"pg{i}", 12) for i in range(1, 8)])
    check("[extract] 7-page document keeps order 1..7", [p["page_number"] for p in extract_text(many)] == list(range(1, 8)))
    latin = make_pdf("s4_latin.pdf", ["café naïve über señor façade jalapeño déjà Ålborg " * 3])
    cjk = make_pdf("s4_cjk.pdf", ["中文测试 文本 提取 " * 6], fontname="china-s")
    lt, ct = extract_text(latin)[0]["text"], extract_text(cjk)[0]["text"]
    check("[extract] accented Latin text is extracted intact", all(w in lt for w in ("café", "naïve", "über", "Ålborg")))
    check("[extract] CJK text is extracted (Unicode preserved)", "中文测试" in ct)
    truncated = os.path.join(WORKDIR, "s4_truncated.pdf")
    with open(many, "rb") as src, open(truncated, "wb") as dst:
        data = src.read(); dst.write(data[: len(data) // 2])
    try:
        recovered = extract_text(truncated); trunc_err = None
    except Exception as e:  # noqa: BLE001
        recovered, trunc_err = [], e
    check("[extract] truncated PDF is either repaired (partial pages) or rejected as InvalidPDFError, never a crash",
          trunc_err is None or isinstance(trunc_err, InvalidPDFError))
    print(f"INFO | truncated 7-page PDF: recovered pages {[p['page_number'] for p in recovered]}")

    # ------------------------------------------------------------- 4.5 chunking
    print(f"INFO | effective chunking: CHUNK_SIZE={cfg.CHUNK_SIZE} words, CHUNK_OVERLAP={cfg.CHUNK_OVERLAP}, "
          f"CHUNK_STRATEGY={cfg.CHUNK_STRATEGY}")
    chunk_fn = lambda t: chunk_page(t, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP, cfg.CHUNK_STRATEGY)  # noqa: E731
    short = ingestion.build_chunks("d", [{"page_number": 1, "text": words("s", 30)}], chunk_fn)
    check("[chunk] short page -> exactly one chunk", len(short) == 1 and short[0]["chunk_id"] == 1)
    long_text = words("L", 450)
    long_chunks = ingestion.build_chunks("d", [{"page_number": 2, "text": long_text}], chunk_fn)
    sizes = [len(c["content"].split()) for c in long_chunks]
    check("[chunk] every chunk <= CHUNK_SIZE words and none empty", all(0 < s <= cfg.CHUNK_SIZE for s in sizes))
    if cfg.CHUNK_STRATEGY == "words":
        first, second = long_chunks[0]["content"].split(), long_chunks[1]["content"].split()
        check("[chunk] consecutive chunks overlap by exactly CHUNK_OVERLAP words",
              first[-cfg.CHUNK_OVERLAP:] == second[:cfg.CHUNK_OVERLAP])
    covered = set(w for c in long_chunks for w in c["content"].split())
    check("[chunk] every word of a long paragraph is covered (boundaries lose nothing)", covered == set(long_text.split()))
    check("[chunk] chunk_ids are 1..n in order and carry the page number",
          [c["chunk_id"] for c in long_chunks] == list(range(1, len(long_chunks) + 1))
          and {c["page_number"] for c in long_chunks} == {2})
    multi = ingestion.build_chunks("d", [{"page_number": 1, "text": words("a", 120)},
                                         {"page_number": 2, "text": "too few words"},
                                         {"page_number": 3, "text": words("b", 30)}], chunk_fn)
    check("[chunk] multi-page: chunk_id restarts per page, pages under MIN_PAGE_WORDS skipped, order kept",
          [(c["page_number"], c["chunk_id"]) for c in multi] == [(1, 1), (1, 2), (3, 1)])
    para = "The same repeated paragraph appears on every page of this report for testing."
    repeated = ingestion.build_chunks("d", [{"page_number": n, "text": para} for n in (1, 2, 3)], chunk_fn)
    check("[chunk] repeated paragraph across pages is stored once (dedupe)", len(repeated) == 1)
    uni = ingestion.build_chunks("d", [{"page_number": 1, "text": "naïve café " * 20}], chunk_fn)
    check("[chunk] Unicode text survives chunking unchanged", "naïve café" in uni[0]["content"])
    again = ingestion.build_chunks("d", [{"page_number": 2, "text": long_text}], chunk_fn)
    check("[chunk] chunk identifiers are stable for identical input",
          [(c["chunk_id"], c["content"]) for c in again] == [(c["chunk_id"], c["content"]) for c in long_chunks])

    # ------------------------------------------------------------- 4.6 embeddings (real model, offline)
    model_a = embedding_service.get_model()
    model_b = embedding_service.get_model()
    check("[embed] the configured model is loaded once and reused", model_a is model_b)
    texts = ["first chunk text", "second chunk text", "third"]
    batch = embedding_service.generate_embeddings(texts)
    single = embedding_service.generate_embeddings([texts[1]])
    check(f"[embed] batch shape is (3, EMBEDDING_DIM={cfg.EMBEDDING_DIM})", batch.shape == (3, cfg.EMBEDDING_DIM))
    check("[embed] all values finite", bool(np.isfinite(batch).all()))
    check("[embed] vectors are L2-normalised", bool(np.allclose(np.linalg.norm(batch, axis=1), 1.0, atol=1e-4)))
    check("[embed] batch and single encoding agree", bool(np.allclose(batch[1], single[0], atol=1e-5)))
    empty = embedding_service.generate_embeddings([])
    check("[embed] empty input returns no vectors (ingest_pdf never embeds an empty list)", len(empty) == 0)
    print(f"INFO | configured EMBEDDING_MODEL={cfg.EMBEDDING_MODEL!r}, "
          f"model dim={model_a.get_sentence_embedding_dimension()}")
    check("[embed] model output dimension equals EMBEDDING_DIM",
          model_a.get_sentence_embedding_dimension() == cfg.EMBEDDING_DIM)

    # ------------------------------------------------------------- 4.7 persistence (real embeddings)
    doc = make_pdf("s4_persist.pdf", [words("q1", 150), words("q2", 40), words("q3", 5)])
    expected = ingestion.build_chunks("s4_persist.pdf", extract_text(doc), chunk_fn)
    check("[persist] ingest with the REAL embedding model succeeds",
          ingest(doc, embedder=embedding_service.generate_embeddings) is None)
    stored = rows("s4_persist.pdf")
    check("[persist] chunk count equals the chunker's output", len(stored) == len(expected) > 0)
    check("[persist] every stored vector has EMBEDDING_DIM dimensions", {r[4] for r in stored} == {cfg.EMBEDDING_DIM})
    check("[persist] page references and chunk ids match the chunker",
          [(r[1], r[2]) for r in stored] == [(c["page_number"], c["chunk_id"]) for c in expected])
    check("[persist] content stored exactly", [r[3] for r in stored]
          == [hashlib.md5(c["content"].encode()).hexdigest() for c in expected])
    check("[persist] page under MIN_PAGE_WORDS (page 3) produced no rows", 3 not in {r[1] for r in stored})

    # re-ingest: identical file -> same rows, same ids (upsert, no duplicates)
    before = rows("s4_persist.pdf")
    check("[re-ingest] identical re-ingest succeeds", ingest(doc, embedder=embedding_service.generate_embeddings) is None)
    check("[re-ingest] identical re-ingest keeps the same rows and ids", rows("s4_persist.pdf") == before)

    # changed file (shorter) -> stale chunks removed in the same transaction
    make_pdf("s4_persist.pdf", [words("q1", 60)])
    check("[re-ingest] shorter version ingests", ingest(doc) is None)
    after = rows("s4_persist.pdf")
    check("[re-ingest] stale chunks of the old version are gone (only page 1, 1 chunk)",
          [(r[1], r[2]) for r in after] == [(1, 1)])

    # failures keep the previous valid version
    snapshot = rows("s4_persist.pdf")
    make_pdf("s4_persist.pdf", [words("new", 300), words("new2", 80)])

    def failing_embedder(texts):
        raise RuntimeError("simulated embedding failure")
    err = ingest(doc, embedder=failing_embedder)
    check("[failure] embedding failure propagates and leaves the previous version untouched",
          isinstance(err, RuntimeError) and rows("s4_persist.pdf") == snapshot)

    real_write = ingestion.write_document_chunks

    def write_then_fail(cursor, *args, **kwargs):
        real_write(cursor, *args, **kwargs)           # all upserts + stale delete executed ...
        raise RuntimeError("simulated persistence failure before commit")
    with mock.patch.object(ingestion, "write_document_chunks", side_effect=write_then_fail):
        err = ingest(doc)
    check("[failure] persistence failure after all writes rolls back everything (previous version intact)",
          isinstance(err, RuntimeError) and rows("s4_persist.pdf") == snapshot)

    calls = {"n": 0}
    real_conn = ingestion.get_connection

    class FailingCursor:
        def __init__(self, cur): self._cur = cur
        def __enter__(self): self._cur.__enter__(); return self
        def __exit__(self, *a): return self._cur.__exit__(*a)
        def execute(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("simulated failure on the 3rd statement")
            return self._cur.execute(*a, **k)

    class ConnProxy:
        def __init__(self, conn): self._conn = conn
        def __enter__(self): self._conn.__enter__(); return self
        def __exit__(self, *a): return self._conn.__exit__(*a)
        def cursor(self, *a, **k): return FailingCursor(self._conn.cursor(*a, **k))
        def __getattr__(self, name): return getattr(self._conn, name)

    with mock.patch.object(ingestion, "get_connection", side_effect=lambda: ConnProxy(real_conn())):
        err = ingest(doc)
    check("[failure] a database error mid-way leaves no partial rows (previous version intact)",
          isinstance(err, RuntimeError) and rows("s4_persist.pdf") == snapshot)

    # ------------------------------------------------------------- 4.8 identity
    a_dir, b_dir = os.path.join(WORKDIR, "a"), os.path.join(WORKDIR, "b")
    one = make_pdf("s4_same_name.pdf", [words("first", 40)], directory=a_dir)
    two = make_pdf("s4_same_name.pdf", [words("second", 40)], directory=b_dir)
    ingest(one); first_rows = rows("s4_same_name.pdf")
    ingest(two); second_rows = rows("s4_same_name.pdf")
    check("[identity] ingest_pdf identifies a document by its file basename "
          "(a different file with the same basename REPLACES it; the API blocks this with 409 unless replace=true)",
          len(first_rows) == len(second_rows) == 1 and first_rows[0][3] != second_rows[0][3])
    renamed = os.path.join(WORKDIR, "s4_renamed_copy.pdf"); shutil.copy(valid, renamed)
    ingest(renamed)
    check("[identity] the same file under another name is a separate document (original untouched)",
          len(rows("s4_renamed_copy.pdf")) == len(rows("s4_valid.pdf")) > 0)
    valid_before = rows("s4_valid.pdf")
    similar = make_pdf("s4_similar.pdf", [words("p1", 150), "", words("p3", 59)])
    ingest(similar)
    check("[identity] a different file with similar content is a separate document; the original is unchanged",
          len(rows("s4_similar.pdf")) > 0 and rows("s4_valid.pdf") == valid_before)

    # ------------------------------------------------------------- 4.9 harness uses the shared implementation
    # (runs last: load_corpus TRUNCATEs the scratch table by design)
    import eval.harness as harness
    corpus = {"s4_h1.txt": [words("h", 130), "short page", words("h", 130)], "s4_h2.txt": [words("k", 20)]}
    with mock.patch.object(ingestion, "build_chunks", wraps=ingestion.build_chunks) as b_spy, \
            mock.patch.object(ingestion, "validate_embeddings", wraps=ingestion.validate_embeddings) as v_spy, \
            mock.patch.object(ingestion, "write_document_chunks", wraps=ingestion.write_document_chunks) as w_spy:
        n = harness.load_corpus(corpus, chunk_fn, det_embedder)
    check("[harness] load_corpus runs through the shared build_chunks / validate_embeddings / write_document_chunks",
          b_spy.call_count == 2 and v_spy.call_count == 1 and w_spy.call_count == 2)
    with get_connection() as conn:
        stored_h = conn.execute("SELECT document_name, page_number, chunk_id FROM document_chunks "
                                "ORDER BY id").fetchall()
    check("[harness] benchmark semantics kept: short pages are NOT skipped (min_words=0), repeated page deduped, "
          "ids in insertion order", n == len(stored_h)
          and [(d, p) for d, p, _ in stored_h if d == "s4_h1.txt"].count(("s4_h1.txt", 2)) == 1
          and not any(p == 3 for d, p, _ in stored_h if d == "s4_h1.txt"))
    src = open(os.path.join(ROOT, "eval", "harness.py"), encoding="utf-8").read()
    check("[harness] load_corpus imports build_chunks / validate_embeddings / write_document_chunks "
          "from services.ingestion_service and has no INSERT of its own",
          "from services.ingestion_service import build_chunks, validate_embeddings, write_document_chunks" in src
          and "INSERT INTO document_chunks" not in src)
    check("[harness] ingest_pdf uses the same shared functions",
          all(name in open(os.path.join(ROOT, "services", "ingestion_service.py"), encoding="utf-8").read()
              .split("def ingest_pdf", 1)[1] for name in ("build_chunks(", "validate_embeddings(", "write_document_chunks(")))
finally:
    cleanup()
    shutil.rmtree(WORKDIR, ignore_errors=True)
    check("[cleanup] no s4_* rows remain", rows("s4_valid.pdf") == [] and rows("s4_persist.pdf") == [])

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
