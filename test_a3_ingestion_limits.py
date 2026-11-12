"""A3: configurable PDF size / page-count limits for ingestion.

Scratch DB only (testsafe), deterministic embedder, small generated PDFs (limits are lowered through config,
no large files are created). Order verified: size check -> open -> page-count check -> text extraction.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import hashlib
import importlib.util
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
import services.pdf_parser as parser
from services import retrieval_config as cfg
from services.database import get_connection
from services.pdf_parser import PDFLimitExceeded

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILURES = []
PREFIX = "a3_"
WORKDIR = tempfile.mkdtemp(prefix="a3_pdf_")
MB = 1024 * 1024


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


def snapshot(name):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, page_number, chunk_id, content, embedding::text FROM document_chunks "
            "WHERE document_name=%s ORDER BY page_number, chunk_id", (name,)).fetchall()


def ingest(path, **cfg_values):
    embed = mock.Mock(side_effect=det_embedder)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(ingestion, "generate_embeddings", embed))
        for key, value in cfg_values.items():
            stack.enter_context(mock.patch.object(cfg, key, value))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        try:
            ingestion.ingest_pdf(path)
            err = None
        except Exception as error:  # noqa: BLE001
            error.__traceback__ = None      # do not keep PyMuPDF frames (and file handles) alive
            err = error
    return err, embed


def load_config_copy(**env):
    with mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location("_a3_cfg_copy", os.path.join(ROOT, "services", "retrieval_config.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def run():
    # ---------------------------------------------------------------- configuration
    clean = {k: v for k, v in os.environ.items() if k not in ("MAX_PDF_SIZE_MB", "MAX_PDF_PAGES")}
    with mock.patch.dict(os.environ, clean, clear=True):
        d = load_config_copy()
    check("[config] default MAX_PDF_SIZE_MB is 50", d.MAX_PDF_SIZE_MB == 50)
    check("[config] default MAX_PDF_PAGES is 500", d.MAX_PDF_PAGES == 500)
    o = load_config_copy(MAX_PDF_SIZE_MB="12.5", MAX_PDF_PAGES="30")
    check("[config] environment overrides MAX_PDF_SIZE_MB (12.5) and MAX_PDF_PAGES (30)",
          o.MAX_PDF_SIZE_MB == 12.5 and o.MAX_PDF_PAGES == 30)
    for var, bad in (("MAX_PDF_SIZE_MB", "abc"), ("MAX_PDF_PAGES", "abc"), ("MAX_PDF_PAGES", "1.5"), ("MAX_PDF_SIZE_MB", "")):
        try:
            load_config_copy(**{var: bad})
            err = None
        except Exception as error:  # noqa: BLE001
            err = error
        check(f"[config] invalid {var}={bad!r} raises ValueError at import (same convention as every other int/float setting)",
              isinstance(err, ValueError))
    check("[config] live module defaults match (50 MB, 500 pages) when no override is present",
          cfg.MAX_PDF_SIZE_MB == 50 and cfg.MAX_PDF_PAGES == 500)

    # ---------------------------------------------------------------- size limit
    name = f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf"
    path = make_pdf(name, [words("sz", 120)])
    size = os.path.getsize(path)
    below, at, above = (size + 1) / MB, size / MB, (size - 1) / MB     # limit values (power-of-two division is exact)
    err, _ = ingest(path, MAX_PDF_SIZE_MB=below)
    check(f"[size] file ({size} bytes) below the limit is ingested", err is None and len(snapshot(name)) == 2)
    err, _ = ingest(path, MAX_PDF_SIZE_MB=at)
    check("[size] file exactly at the limit is accepted (limit is inclusive)", err is None)
    stored = snapshot(name)
    err, embed = ingest(path, MAX_PDF_SIZE_MB=above)
    check("[size] file 1 byte over the limit is rejected with PDFLimitExceeded naming MAX_PDF_SIZE_MB",
          isinstance(err, PDFLimitExceeded) and isinstance(err, ValueError) and "MAX_PDF_SIZE_MB" in str(err))
    check("[size] a rejected file calls neither the parser nor the embedder", embed.call_count == 0)
    check("[size] rejected re-ingest leaves the previously stored rows unchanged", snapshot(name) == stored)

    new_name = f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf"
    new_path = make_pdf(new_name, [words("nw", 120)])
    err, _ = ingest(new_path, MAX_PDF_SIZE_MB=0.0001)
    check("[size] rejected new document creates no rows", isinstance(err, PDFLimitExceeded) and snapshot(new_name) == [])

    # spy: oversize check happens before the PDF is opened/parsed
    with mock.patch.object(ingestion, "extract_text", side_effect=AssertionError("parser must not run")):
        err, _ = ingest(path, MAX_PDF_SIZE_MB=above)
    check("[order] size check runs before parsing (parser never invoked for an oversized file)", isinstance(err, PDFLimitExceeded))

    # ---------------------------------------------------------------- page limit
    pname = f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf"
    ppath = make_pdf(pname, [words(f"p{i}", 30) for i in range(1, 6)])        # 5 pages
    err, _ = ingest(ppath, MAX_PDF_PAGES=6)
    check("[pages] 5-page PDF below a limit of 6 is ingested (5 pages stored)", err is None and [r[1] for r in snapshot(pname)] == [1, 2, 3, 4, 5])
    err, _ = ingest(ppath, MAX_PDF_PAGES=5)
    check("[pages] PDF exactly at the page limit (5 of 5) is accepted (limit is inclusive)", err is None)
    pstored = snapshot(pname)
    with mock.patch.object(pymupdf.Page, "get_text", side_effect=AssertionError("text extraction must not run")):
        err, embed = ingest(ppath, MAX_PDF_PAGES=4)
    check("[pages] PDF over the limit (5 of 4) is rejected with PDFLimitExceeded naming MAX_PDF_PAGES and the page count",
          isinstance(err, PDFLimitExceeded) and "MAX_PDF_PAGES=4" in str(err) and "5 pages" in str(err))
    check("[order] page-count check runs before any page text is extracted (get_text never called)", isinstance(err, PDFLimitExceeded))
    check("[pages] rejected replacement (page limit) leaves the stored document unchanged and embeds nothing",
          snapshot(pname) == pstored and embed.call_count == 0)
    short_replacement = make_pdf(pname, [words("zz", 30) for _ in range(5)])   # same name, would change content
    err, _ = ingest(short_replacement, MAX_PDF_PAGES=3)
    check("[pages] same name, different content, over the page limit: old rows (content, ids, embeddings) intact",
          isinstance(err, PDFLimitExceeded) and snapshot(pname) == pstored)
    err, _ = ingest(short_replacement)
    check("[pages] with the default limit the same replacement is ingested normally (update path unchanged)",
          err is None and snapshot(pname) != pstored and all("zzw" in r[3] for r in snapshot(pname)))

    # ---------------------------------------------------------------- both limits, order, malformed input
    err, _ = ingest(ppath, MAX_PDF_SIZE_MB=0.0001, MAX_PDF_PAGES=1)
    check("[order] when both limits are exceeded the size error is reported first", isinstance(err, PDFLimitExceeded) and "MAX_PDF_SIZE_MB" in str(err))
    bad = os.path.join(WORKDIR, f"{PREFIX}bad.pdf")
    open(bad, "wb").write(b"%PDF-1.4\n" + os.urandom(3000))
    err, embed = ingest(bad)
    check("[malformed] garbage PDF within limits still fails as before (FileDataError), nothing stored, no embedding",
          type(err).__name__ == "FileDataError" and embed.call_count == 0)
    err, _ = ingest(bad, MAX_PDF_SIZE_MB=0.0001)
    check("[malformed] garbage PDF over the size limit is rejected by the size check before parsing", isinstance(err, PDFLimitExceeded))
    err, _ = ingest(os.path.join(WORKDIR, "nope.pdf"))
    check("[malformed] missing file still raises FileNotFoundError", isinstance(err, FileNotFoundError))
    err, _ = ingest(make_pdf(f"{PREFIX}blank.pdf", ["", ""]))
    check("[malformed] blank PDF within limits still raises ValueError('No usable chunks')", isinstance(err, ValueError) and "No usable chunks" in str(err))
    edoc = os.path.join(WORKDIR, f"{PREFIX}enc.pdf")
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 555, 800), words("en", 60), fontsize=9)
    doc.save(edoc, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    doc.close()
    err, _ = ingest(edoc)
    check("[malformed] password-protected PDF still raises ValueError (not a limit error)",
          isinstance(err, ValueError) and not isinstance(err, PDFLimitExceeded))

    # zero / negative limits are used as given (no special-casing invented)
    err, _ = ingest(ppath, MAX_PDF_PAGES=0)
    check("[config edge] MAX_PDF_PAGES=0 rejects every PDF (value used literally)", isinstance(err, PDFLimitExceeded))
    err, _ = ingest(ppath, MAX_PDF_SIZE_MB=0)
    check("[config edge] MAX_PDF_SIZE_MB=0 rejects every non-empty file (value used literally)", isinstance(err, PDFLimitExceeded))

    # defaults leave normal ingestion untouched
    err, _ = ingest(path)
    check("[default] normal ingestion under default limits unchanged", err is None and len(snapshot(name)) == 2)


try:
    run()
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
    import gc; gc.collect()          # release PyMuPDF handles left by the failed-open cases (Windows)
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("[cleanup] no test rows left", left == 0)
check("[cleanup] temp directory removed", not os.path.exists(WORKDIR))
print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
