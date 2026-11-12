"""A4: ingest_pdf accepts only .pdf files (case-insensitive) and rejects everything else first.

Scratch DB only (testsafe), deterministic embedder, small generated files. Spies prove the type check runs
before os.path.getsize, parsing/text extraction, embedding and any database connection.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import gc
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
from services.database import get_connection
from services.pdf_parser import PDFLimitExceeded, UnsupportedFileTypeError

FAILURES = []
PREFIX = "a4_"
WORKDIR = tempfile.mkdtemp(prefix="a4_files_")


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


def all_test_rows():
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, document_name, page_number, chunk_id, content, embedding::text FROM document_chunks "
            "WHERE document_name LIKE %s ORDER BY id", (PREFIX + "%",)).fetchall()


def ingest(path, **cfg_values):
    """Run ingest_pdf with spies on every later stage; returns (error, spies)."""
    spies = {
        "getsize": mock.Mock(side_effect=os.path.getsize),
        "extract_text": mock.Mock(side_effect=ingestion.extract_text),
        "embed": mock.Mock(side_effect=det_embedder),
        "db": mock.Mock(side_effect=ingestion.get_connection),
        "page_open": mock.Mock(side_effect=pymupdf.open),
    }
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(ingestion.os.path, "getsize", spies["getsize"]))
        stack.enter_context(mock.patch.object(ingestion, "extract_text", spies["extract_text"]))
        stack.enter_context(mock.patch.object(ingestion, "generate_embeddings", spies["embed"]))
        stack.enter_context(mock.patch.object(ingestion, "get_connection", spies["db"]))
        stack.enter_context(mock.patch("services.pdf_parser.pymupdf.open", spies["page_open"]))
        for key, value in cfg_values.items():
            stack.enter_context(mock.patch.object(cfg, key, value))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        try:
            ingestion.ingest_pdf(path)
            err = None
        except Exception as error:  # noqa: BLE001
            error.__traceback__ = None
            err = error
    return err, spies


def nothing_ran(spies):
    return all(spy.call_count == 0 for spy in spies.values())


def run():
    body = [words("ok", 120)]

    # ---------------------------------------------------------------- accepted
    lower = f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf"
    err, spies = ingest(make_pdf(lower, body))
    check("[accept] normal .pdf is ingested (2 chunks)", err is None and len(snapshot(lower)) == 2)
    check("[accept] .pdf goes through size check, parsing, embedding and the database",
          all(spies[k].call_count >= 1 for k in ("getsize", "extract_text", "embed", "db")))
    upper = f"{PREFIX}{uuid.uuid4().hex[:8]}.PDF"
    err, _ = ingest(make_pdf(upper, body))
    check("[accept] uppercase .PDF is ingested (document_name kept as given)", err is None and len(snapshot(upper)) == 2)
    mixed = f"{PREFIX}{uuid.uuid4().hex[:8]}.Pdf"
    err, _ = ingest(make_pdf(mixed, body))
    check("[accept] mixed-case .Pdf is ingested", err is None and len(snapshot(mixed)) == 2)
    dotted = f"{PREFIX}report.v2.final.pdf"
    err, _ = ingest(make_pdf(dotted, body))
    check("[accept] a name with several dots ending in .pdf is ingested", err is None and len(snapshot(dotted)) == 2)

    # ---------------------------------------------------------------- rejected
    before = all_test_rows()
    rejected = {
        ".txt": f"{PREFIX}{uuid.uuid4().hex[:8]}.txt",
        ".docx": f"{PREFIX}{uuid.uuid4().hex[:8]}.docx",
        ".png": f"{PREFIX}{uuid.uuid4().hex[:8]}.png",
        "no extension": f"{PREFIX}{uuid.uuid4().hex[:8]}",
        ".pdf.bak": f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf.bak",
        ".pdfx": f"{PREFIX}{uuid.uuid4().hex[:8]}.pdfx",
        "trailing dot": f"{PREFIX}{uuid.uuid4().hex[:8]}.pdf.",
    }
    for label, fname in rejected.items():
        # real PDF bytes under the wrong name: the extension alone decides
        path = make_pdf(fname, body) if label != "trailing dot" else os.path.join(WORKDIR, fname)
        err, spies = ingest(path)
        check(f"[reject] {label} -> UnsupportedFileTypeError (a ValueError) with a descriptive message",
              isinstance(err, UnsupportedFileTypeError) and isinstance(err, ValueError)
              and "only .pdf files" in str(err) and fname.split("\\")[-1] in str(err))
        check(f"[reject] {label}: rejected before getsize, PDF open, text extraction, embedding and any DB connection",
              nothing_ran(spies))
    err, _ = ingest(os.path.join(WORKDIR, rejected["no extension"]))
    check("[reject] extensionless message says '(no extension)'", "(no extension)" in str(err))
    check("[reject] rejected new files create no database rows (all a4_* rows identical before/after)",
          all_test_rows() == before)
    err, spies = ingest(os.path.join(WORKDIR, "does_not_exist.txt"))
    check("[reject] a missing non-PDF path is rejected by type (no filesystem access at all)",
          isinstance(err, UnsupportedFileTypeError) and nothing_ran(spies))

    # rejected 'replacement' of an existing document: same stem, wrong type -> stored document untouched
    stored = snapshot(lower)
    stem = lower[:-4]
    for bad in (stem + ".txt", lower + ".bak", stem + ".docx"):
        err, spies = ingest(make_pdf(bad, [words("new", 300)]))
        check(f"[replacement] {bad[-9:]!r} for an existing document is rejected; stored rows (ids, content, embeddings) unchanged",
              isinstance(err, UnsupportedFileTypeError) and snapshot(lower) == stored and nothing_ran(spies))
    check("[replacement] no rows exist under the rejected names", all(snapshot(n) == [] for n in (stem + ".txt", lower + ".bak", stem + ".docx")))

    # ---------------------------------------------------------------- existing behaviour preserved for .pdf
    bad_pdf = os.path.join(WORKDIR, f"{PREFIX}garbage.pdf")
    with open(bad_pdf, "wb") as handle:
        handle.write(b"this is plain text, not a pdf " * 60)      # deterministic invalid content
    err, spies = ingest(bad_pdf)
    print(f"INFO | invalid .pdf content -> {type(err).__name__}: {str(err)[:60]!r}")
    check("[malformed] .pdf with invalid content still fails in PyMuPDF (FileDataError), after the type and size checks",
          type(err).__name__ == "FileDataError" and spies["getsize"].call_count >= 1 and spies["embed"].call_count == 0)
    bad_upper = os.path.join(WORKDIR, f"{PREFIX}garbage2.PDF")
    with open(bad_upper, "wb") as handle:
        handle.write(b"not a pdf at all " * 50)
    err, _ = ingest(bad_upper)
    check("[malformed] .PDF with invalid content -> FileDataError (not a type error)", type(err).__name__ == "FileDataError")
    err, _ = ingest(os.path.join(WORKDIR, f"{PREFIX}missing.pdf"))
    check("[missing] a missing .pdf still raises FileNotFoundError", isinstance(err, FileNotFoundError))
    enc = os.path.join(WORKDIR, f"{PREFIX}enc.pdf")
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 555, 800), words("en", 60), fontsize=9)
    doc.save(enc, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    doc.close()
    err, _ = ingest(enc)
    check("[encrypted] password-protected .pdf still raises ValueError (not a type error)",
          isinstance(err, ValueError) and not isinstance(err, UnsupportedFileTypeError))
    err, _ = ingest(make_pdf(f"{PREFIX}blank.pdf", ["", ""]))
    check("[blank] blank .pdf still raises ValueError('No usable chunks')", isinstance(err, ValueError) and "No usable chunks" in str(err))

    # ---------------------------------------------------------------- A3 limits still apply to .pdf / .PDF
    path = os.path.join(WORKDIR, lower)
    err, _ = ingest(path, MAX_PDF_SIZE_MB=0.0001)
    check("[A3] size limit still enforced for a .pdf", isinstance(err, PDFLimitExceeded) and "MAX_PDF_SIZE_MB" in str(err))
    err, _ = ingest(os.path.join(WORKDIR, upper), MAX_PDF_PAGES=0)
    check("[A3] page limit still enforced for a .PDF", isinstance(err, PDFLimitExceeded) and "MAX_PDF_PAGES" in str(err))
    err, _ = ingest(os.path.join(WORKDIR, rejected[".txt"]), MAX_PDF_SIZE_MB=0.0001)
    check("[order] a non-PDF that would also exceed the size limit reports the type error first",
          isinstance(err, UnsupportedFileTypeError))
    check("[A3] the stored .pdf is unchanged by the limit rejections", snapshot(lower) == stored)


try:
    run()
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
    gc.collect()                      # release PyMuPDF handles from failed opens (Windows)
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("[cleanup] no test rows left", left == 0)
check("[cleanup] temp directory removed", not os.path.exists(WORKDIR))
print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
