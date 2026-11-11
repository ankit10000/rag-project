"""P2-01: end-to-end PDF ingestion verification.

PDF (generated with PyMuPDF) -> services.pdf_parser.extract_text -> chunker -> embeddings ->
ingestion_service.ingest_pdf -> PostgreSQL document_chunks (scratch database).

Embeddings: the HAPPY-PATH test uses the REAL all-MiniLM-L6-v2 model loaded from the local
cache (HF offline, no network). Only the tests that need a controlled vector (update-on-
conflict proof, dimension mismatch) swap in a DETERMINISTIC substitute at
ingestion_service.generate_embeddings; each such check says so in its label.
No Gemini, no downloads, rag_db never touched (testsafe guard).
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import math
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
from services.embedding_service import generate_embeddings
from services.pdf_parser import extract_text

FAILURES = []
PREFIX = "p2_01_"
WORKDIR = tempfile.mkdtemp(prefix="p2_01_pdf_")


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def words(page_no, count, tag="w"):
    return [f"p{page_no}{tag}{i:03d}" for i in range(1, count + 1)]


def make_pdf(name, pages):
    """pages: list of strings ('' = blank page). Returns the file path."""
    path = os.path.join(WORKDIR, name)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            rc = page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=9)
            assert rc >= 0, "test PDF text did not fit on the page"
    doc.save(path)
    doc.close()
    return path


def rows_for(name):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, page_number, chunk_id, content, vector_dims(embedding), embedding::text "
            "FROM document_chunks WHERE document_name=%s ORDER BY page_number, chunk_id", (name,)).fetchall()


def other_rows_fingerprint():
    with get_connection() as conn:
        return conn.execute(
            "SELECT count(*), coalesce(md5(string_agg(d::text, '|' ORDER BY d.id)), '') "
            "FROM document_chunks d WHERE document_name NOT LIKE %s", (PREFIX + "%",)).fetchone()


def cleanup():
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))


def expected_chunks(page_texts):
    """Independent expectation: chunk each page's words with the configured sizes, ids from 1."""
    out = []
    for page_no, text in page_texts:
        for idx, content in enumerate(chunk_text(text, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP), start=1):
            out.append((page_no, idx, content))
    return out


def unit(v):
    return v / np.linalg.norm(v)


def run():
    baseline = other_rows_fingerprint()
    print(f"INFO | config: chunk_size={cfg.CHUNK_SIZE} overlap={cfg.CHUNK_OVERLAP} strategy={cfg.CHUNK_STRATEGY} "
          f"dim={cfg.EMBEDDING_DIM}")
    check("[config] default chunk strategy is 'words' (test expectations assume word chunks)",
          cfg.CHUNK_STRATEGY == "words")

    # ------------------------------------------------------------------ fixture
    # page 1: 250 words, page 2: 120 words, page 3: blank (no text), page 4: 150 words, page 5: only 6 words
    p1, p2, p4, p5 = words(1, 250), words(2, 120), words(4, 150), words(5, 6)
    name = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    pdf = make_pdf(name, [" ".join(p1), " ".join(p2), "", " ".join(p4), " ".join(p5)])
    print(f"INFO | fixture {name}: 5 PDF pages (250 / 120 / blank / 150 / 6 words), "
          f"{os.path.getsize(pdf)} bytes")

    # --------------------------------------------------------------- 1. parsing
    parsed = extract_text(pdf)
    check("[parse] PDF parsed: pages with text are 1, 2, 4, 5 (blank page 3 skipped)",
          [p["page_number"] for p in parsed] == [1, 2, 4, 5])
    by_page = {p["page_number"]: p["text"] for p in parsed}
    check("[parse] extracted text is correct (word-for-word) for pages 1, 2, 4, 5",
          by_page[1].split() == p1 and by_page[2].split() == p2 and by_page[4].split() == p4
          and by_page[5].split() == p5)
    check("[parse] page numbers preserved across the blank page (content of page 4 is page_number 4)",
          by_page[4].split()[0] == "p4w001")

    # ------------------------------------------------------------ 2. chunking
    exp = expected_chunks([(1, " ".join(p1)), (2, " ".join(p2)), (4, " ".join(p4))])
    check("[chunk] expected chunk count: 250w->3, 120w->2, 150w->2 = 7 (page 5 has < 10 words, skipped)",
          len(exp) == 7 and [e[:2] for e in exp] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (4, 1), (4, 2)])

    # ------------------------------------------- 3. real-embedding ingestion
    try:
        quiet(ingestion.ingest_pdf, pdf)
        raised = None
    except Exception as error:  # noqa: BLE001
        raised = error
    check(f"[ingest, REAL embeddings] ingest_pdf completes without error" + (f" (raised {raised!r})" if raised else ""),
          raised is None)
    rows = rows_for(name)
    check("[db] exactly 7 rows inserted for the document (no unexpected rows)", len(rows) == 7)
    check("[db] (page, chunk_id) identities are exactly the expected ones",
          [(r[1], r[2]) for r in rows] == [(e[0], e[1]) for e in exp])
    check("[db] stored content equals the independently computed chunks",
          [r[3] for r in rows] == [e[2] for e in exp])
    check("[db] each page's metadata: document_name column, page numbers 1/2/4 only (not 3, not 5)",
          {r[1] for r in rows} == {1, 2, 4})
    check("[db] every embedding has the configured dimension (vector_dims == EMBEDDING_DIM == 384)",
          all(r[4] == cfg.EMBEDDING_DIM == 384 for r in rows))
    vectors = [np.array([float(x) for x in r[5].strip("[]").split(",")]) for r in rows]
    check("[db] stored embeddings are the model's normalised vectors (norm = 1.0 +- 1e-3)",
          all(abs(np.linalg.norm(v) - 1.0) < 1e-3 for v in vectors))
    fresh = generate_embeddings([r[3] for r in rows])
    check("[db] stored vectors match a fresh real-model encoding of the stored content (cos > 0.999)",
          all(float(np.dot(unit(v), unit(f))) > 0.999 for v, f in zip(vectors, fresh)))
    check("[db] different chunks got different vectors (not a constant placeholder)",
          len({tuple(np.round(v, 4)) for v in vectors}) == 7)
    check("[db] no rows from other documents were added or changed", other_rows_fingerprint() == baseline)

    # ------------------------------------------- 4. duplicate ingestion (existing behaviour)
    ids_before = [r[0] for r in rows]
    quiet(ingestion.ingest_pdf, pdf)
    again = rows_for(name)
    check("[dup, REAL embeddings] re-ingesting the same PDF creates no extra rows (still 7)", len(again) == 7)
    check("[dup] same row ids and identities kept (upsert on document/page/chunk, not delete+insert)",
          [r[0] for r in again] == ids_before and [(r[1], r[2]) for r in again] == [(r[1], r[2]) for r in rows])
    check("[dup] content unchanged after re-ingestion", [r[3] for r in again] == [r[3] for r in rows])

    # existing behaviour = DO UPDATE: prove it with a deterministic substitute embedder
    marker = np.zeros(cfg.EMBEDDING_DIM)
    marker[7] = 1.0

    def fixed_embedder(texts):
        return np.tile(marker, (len(texts), 1))

    with mock.patch.object(ingestion, "generate_embeddings", side_effect=fixed_embedder):
        quiet(ingestion.ingest_pdf, pdf)
    updated = rows_for(name)
    check("[dup, DETERMINISTIC embedder] conflict path UPDATES the embedding of the existing rows "
          "(row count and ids unchanged)",
          len(updated) == 7 and [r[0] for r in updated] == ids_before
          and all(r[5].strip("[]").split(",")[7] == "1" for r in updated)
          and all(r[5] != o[5] for r, o in zip(updated, rows)))

    # same text repeated on two pages of one document is stored once (digest dedupe)
    same = " ".join(words(9, 120, "r"))
    dname = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    dpdf = make_pdf(dname, [same, same])
    with mock.patch.object(ingestion, "generate_embeddings", side_effect=fixed_embedder):
        quiet(ingestion.ingest_pdf, dpdf)
    drows = rows_for(dname)
    check("[dup, DETERMINISTIC embedder] identical text on two pages: stored once, from page 1 only "
          "(2 chunks of page 1, none from page 2)",
          [(r[1], r[2]) for r in drows] == [(1, 1), (1, 2)])

    # existing behaviour pin: shrinking a re-ingested document leaves stale chunks behind
    sname = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    big = make_pdf(sname, [" ".join(words(1, 250, "s"))])
    with mock.patch.object(ingestion, "generate_embeddings", side_effect=fixed_embedder):
        quiet(ingestion.ingest_pdf, big)
        n_big = len(rows_for(sname))
        small_path = make_pdf(sname + ".tmp", [" ".join(words(1, 40, "t"))])
        # same document_name, fewer chunks: ingest_pdf derives the name from the path
        os.replace(small_path, big)
        quiet(ingestion.ingest_pdf, big)
    srows = rows_for(sname)
    print(f"INFO | shrink re-ingest: {n_big} chunks first, {len(srows)} rows after re-ingesting a smaller file")
    check("[dup, existing behaviour PINNED] re-ingesting a shorter version updates chunk 1 but leaves the "
          "old extra chunks (stale rows are not removed)",
          n_big == 3 and len(srows) == 3 and srows[0][3].startswith("p1t001"))

    # ----------------------------------------------------------- 5. failure cases
    before_fail = other_rows_fingerprint()
    # 5a empty extracted text: all pages blank
    ename = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    epdf = make_pdf(ename, ["", ""])
    check("[fail] parser returns no pages for a PDF with only blank pages", extract_text(epdf) == [])
    try:
        quiet(ingestion.ingest_pdf, epdf)
        err = None
    except Exception as error:  # noqa: BLE001
        err = error
    check("[fail] empty extracted text -> ValueError('No usable chunks found in PDF'), no rows",
          isinstance(err, ValueError) and "No usable chunks" in str(err) and rows_for(ename) == [])

    # 5b only short pages (< 10 words)
    shname = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    shpdf = make_pdf(shname, ["only six words on this page"])
    try:
        quiet(ingestion.ingest_pdf, shpdf)
        err = None
    except Exception as error:  # noqa: BLE001
        err = error
    check("[fail] a page with fewer than 10 words is not ingested -> ValueError, no rows",
          isinstance(err, ValueError) and rows_for(shname) == [])

    # 5c embedding dimension mismatch (DETERMINISTIC embedder returning the wrong size)
    mname = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    mpdf = make_pdf(mname, [" ".join(words(1, 60, "m"))])
    with mock.patch.object(ingestion, "generate_embeddings",
                           side_effect=lambda texts: np.zeros((len(texts), 3))):
        try:
            quiet(ingestion.ingest_pdf, mpdf)
            err = None
        except Exception as error:  # noqa: BLE001
            err = error
    check("[fail, DETERMINISTIC embedder] 3-dimensional embeddings -> ValueError mentioning EMBEDDING_DIM, "
          "nothing written",
          isinstance(err, ValueError) and "EMBEDDING_DIM" in str(err) and rows_for(mname) == [])

    # 5d invalid PDF input (not a PDF) and a missing file
    bname = f"{PREFIX}{uuid.uuid4().hex[:10]}.pdf"
    bpath = os.path.join(WORKDIR, bname)
    with open(bpath, "w", encoding="utf-8") as handle:
        handle.write("this is plain text, not a PDF " * 20)
    for label, path, name_ in (("text file named .pdf", bpath, bname),
                               ("missing file", os.path.join(WORKDIR, PREFIX + "missing.pdf"), PREFIX + "missing.pdf")):
        try:
            quiet(ingestion.ingest_pdf, path)
            err = None
        except Exception as error:  # noqa: BLE001
            err = error
        print(f"INFO | {label}: ingest_pdf raised {type(err).__name__ if err else 'nothing'}")
        check(f"[fail] {label} -> an exception is raised (not silently ingested), no rows written",
              err is not None and rows_for(name_) == [])

    # 5e document_name is the file's base name, for both separators
    with get_connection() as conn:
        names = conn.execute("SELECT DISTINCT document_name FROM document_chunks WHERE document_name LIKE %s "
                             "AND document_name LIKE %s", (PREFIX + "%", "%" + name[len(PREFIX):])).fetchall()
    check("[meta] document_name stored is the file's base name (no directory part)",
          names == [(name,)] and os.sep not in name and "/" not in name)

    check("[isolation] failure cases changed nothing outside this test's documents",
          other_rows_fingerprint() == before_fail == baseline)


try:
    run()
finally:
    cleanup()
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("[cleanup] no test rows left in document_chunks", left == 0)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
