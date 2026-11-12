"""P2-04: PDF ingestion edge cases (extends P2-01; the ingestion code is NOT modified).

Generated PDFs + the scratch database + a DETERMINISTIC substitute embedder (content-derived unit
vectors patched in at ingestion_service.generate_embeddings; the real model is never asked).
No Gemini, no network, rag_db never touched (testsafe guard). Cleanup removes only p2_04_* rows and
this test's temp files.

Convention: check() = asserted behaviour (existing contract or deliberately PINNED current behaviour);
finding() = a reproducible defect or gap that is REPORTED, not asserted away and not fixed here.
"""
import testsafe  # refuses to run against anything but a scratch database
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
from services.chunker import chunk_text, chunk_text_sentences
from services.database import get_connection
from services.pdf_parser import extract_text

FAILURES = []
FINDINGS = []
PREFIX = "p2_04_"
WORKDIR = tempfile.mkdtemp(prefix="p2_04_pdf_")
ARIAL = r"C:\Windows\Fonts\arial.ttf"
NIRMALA = r"C:\Windows\Fonts\Nirmala.ttc"


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def finding(label, detail):
    FINDINGS.append(label)
    print(f"FINDING | {label} | {detail}")


def name(ext=".pdf", tag=""):
    return f"{PREFIX}{tag}{uuid.uuid4().hex[:10]}{ext}"


def words(tag, count):
    return [f"{tag}w{i:03d}" for i in range(1, count + 1)]


def make_pdf(filename, pages, **textbox):
    """pages: list of strings ('' = blank page). Extra kwargs go to insert_textbox (fonts)."""
    path = os.path.join(WORKDIR, filename)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            kwargs = dict(fontsize=9)
            kwargs.update(textbox)
            rc = page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, **kwargs)
            assert rc >= 0, "test PDF text did not fit on the page"
    doc.save(path)
    doc.close()
    return path


def det_embedder(texts):
    """Content-derived, normalised 384-d vectors: same text -> same vector, different text -> different vector."""
    out = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        v = np.random.default_rng(seed).normal(size=cfg.EMBEDDING_DIM)
        out.append(v / np.linalg.norm(v))
    return np.array(out)


def rows_for(doc_name):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, page_number, chunk_id, content, embedding::text FROM document_chunks "
            "WHERE document_name=%s ORDER BY page_number, chunk_id", (doc_name,)).fetchall()


def foreign_fingerprint():
    with get_connection() as conn:
        return conn.execute(
            "SELECT count(*), coalesce(md5(string_agg(d::text, '|' ORDER BY d.id)), '') FROM document_chunks d "
            "WHERE document_name NOT LIKE %s", (PREFIX + "%",)).fetchone()


def ingest(path, embedder=det_embedder, **patches):
    """Run ingest_pdf with the deterministic embedder; return the exception (or None)."""
    stack = contextlib.ExitStack()
    with stack:
        stack.enter_context(mock.patch.object(ingestion, "generate_embeddings", side_effect=embedder))
        for target, value in patches.items():
            stack.enter_context(mock.patch.object(ingestion, target, value) if target != "extract_text"
                                else mock.patch.object(ingestion, "extract_text", side_effect=value))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        try:
            ingestion.ingest_pdf(path)
            return None
        except Exception as error:  # noqa: BLE001
            return error


def etype(error):
    return type(error).__name__ if error is not None else None


def run():
    baseline = foreign_fingerprint()
    ok_text = " ".join(words("ok", 60))
    good_name = name()
    good = make_pdf(good_name, [ok_text])
    good_bytes = open(good, "rb").read()

    # ============================================================ 1. malformed / unreadable inputs
    print("INFO | --- 1. malformed and unreadable inputs ---")
    cases = []
    for label, data, allowed in (
        ("%PDF header + random bytes", b"%PDF-1.4\n" + os.urandom(2000), {"FileDataError"}),
        ("zero-byte file", b"", {"EmptyFileError"}),
        ("plain text saved as .pdf", b"this is plain text, not a pdf " * 30, {"FileDataError"}),
        ("PDF truncated to half its size", good_bytes[: len(good_bytes) // 2], {"ValueError"}),
        ("PDF with 200 bytes overwritten", good_bytes[:200] + b"A" * 200 + good_bytes[400:], {"ValueError"}),
    ):
        fname = name()
        path = os.path.join(WORKDIR, fname)
        with open(path, "wb") as handle:
            handle.write(data)
        error = ingest(path)
        print(f"INFO | {label}: ingest_pdf raised {etype(error)}: {str(error)[:70]!r}")
        check(f"[unreadable] {label} -> exception ({'/'.join(sorted(allowed))}), nothing stored",
              error is not None and etype(error) in allowed and rows_for(fname) == [])

    # truncated tail: PyMuPDF repairs it and the text survives -> ingestion succeeds (pinned, not an error)
    fname = name()
    path = os.path.join(WORKDIR, fname)
    open(path, "wb").write(good_bytes[:-60])
    error = ingest(path)
    check("[unreadable, PINNED] PDF with its last 60 bytes cut off is repaired by PyMuPDF and ingested normally",
          error is None and len(rows_for(fname)) == len(chunk_text(ok_text, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)))

    missing = os.path.join(WORKDIR, name())
    error = ingest(missing)
    check("[unreadable] missing file -> FileNotFoundError, nothing stored",
          etype(error) == "FileNotFoundError" and rows_for(os.path.basename(missing)) == [])
    error = ingest(WORKDIR)
    check("[unreadable, A4] a directory path without a .pdf extension -> UnsupportedFileTypeError", etype(error) == "UnsupportedFileTypeError")
    pdf_dir = os.path.join(WORKDIR, name())
    os.mkdir(pdf_dir)
    check("[unreadable] a directory whose name ends in .pdf -> FileDataError (as before)", etype(ingest(pdf_dir)) == "FileDataError")

    enc_name = name()
    enc_path = os.path.join(WORKDIR, enc_name)
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 555, 800), ok_text, fontsize=9)
    doc.save(enc_path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()
    error = ingest(enc_path)
    check("[unreadable] password-protected PDF -> ValueError (no password support), nothing stored",
          etype(error) == "ValueError" and "encrypted" in str(error) and rows_for(enc_name) == [])

    # valid PDFs with nothing to ingest
    for label, make in (
        ("only blank pages", lambda f: make_pdf(f, ["", "", ""])),
        ("only whitespace text", None),
        ("image-only page (no OCR)", None),
    ):
        fname = name()
        if label == "only whitespace text":
            path = os.path.join(WORKDIR, fname)
            doc = pymupdf.open()
            doc.new_page().insert_text((50, 50), "      ", fontsize=9)
            doc.save(path); doc.close()
        elif label.startswith("image-only"):
            path = os.path.join(WORKDIR, fname)
            doc = pymupdf.open()
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
            pix.clear_with(200)
            doc.new_page().insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=pix)
            doc.save(path); doc.close()
        else:
            path = make(fname)
        error = ingest(path)
        check(f"[valid, no text] {label} -> parser returns [], ingest raises ValueError('No usable chunks'), nothing stored",
              extract_text(path) == [] and etype(error) == "ValueError" and "No usable chunks" in str(error)
              and rows_for(fname) == [])

    # non-PDF files: rejected by the A4 extension check (supersedes the P2-04 pin that a .txt was ingested)
    txt_name = name(".txt")
    txt_path = os.path.join(WORKDIR, txt_name)
    open(txt_path, "w", encoding="utf-8").write(" ".join(words("txt", 150)))
    error = ingest(txt_path)
    check("[non-PDF, A4] a plain .txt file is rejected with UnsupportedFileTypeError (ValueError), nothing stored",
          etype(error) == "UnsupportedFileTypeError" and isinstance(error, ValueError) and rows_for(txt_name) == [])

    # ============================================================ 2. unusual but valid content
    print("INFO | --- 2. unusual but valid content ---")
    n9, n10 = " ".join(words("nine", 9)), " ".join(words("ten", 10))
    fname = name()
    error = ingest(make_pdf(fname, [n9, n10, n9]))
    got = rows_for(fname)
    check("[short pages] boundary: 9-word pages are skipped, a 10-word page is ingested (page numbers kept: page 2 only)",
          error is None and [(r[1], r[2]) for r in got] == [(2, 1)] and got[0][3] == n10)
    fname = name()
    error = ingest(make_pdf(fname, [n9, n9]))
    check("[short pages] a document made only of 9-word pages -> ValueError, nothing stored",
          etype(error) == "ValueError" and rows_for(fname) == [])

    ws_pdf = os.path.join(WORKDIR, name())
    doc = pymupdf.open()
    contents = [" ".join(words("pa", 40)), None, "ws", " ".join(words("pd", 40)), n9, " ".join(words("pf", 40))]
    for text in contents:
        page = doc.new_page()
        if text == "ws":
            page.insert_text((50, 50), "     ", fontsize=9)
        elif text:
            page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=9)
    doc.save(ws_pdf); doc.close()
    fname = os.path.basename(ws_pdf)
    error = ingest(ws_pdf)
    check("[mixed pages] text / blank / whitespace / text / 9 words / text -> pages 1, 4, 6 stored with their real page numbers",
          error is None and [r[1] for r in rows_for(fname)] == [1, 4, 6])

    # unicode
    def unicode_case(label, text, **font):
        fname_ = name()
        try:
            path = make_pdf(fname_, [text], fontsize=11, **font)
        except Exception as error:  # noqa: BLE001
            print(f"SKIP | unicode {label}: could not build the PDF here ({type(error).__name__})")
            return
        extracted = extract_text(path)
        error = ingest(path)
        got = rows_for(fname_)
        expected_words = text.split()
        stored_words = " ".join(r[3] for r in got).split()
        check(f"[unicode] {label}: text extracted, stored and read back from PostgreSQL intact (no mojibake, no loss)",
              error is None and bool(got) and extracted[0]["text"].split() == expected_words
              and set(stored_words) == set(expected_words)
              and all(r[3] == chunk_text(extracted[0]["text"], cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)[i] for i, r in enumerate(got)))

    if os.path.exists(ARIAL):
        unicode_case("Cyrillic (Arial)", " ".join(["Привет мир это тест документа"] * 4), fontfile=ARIAL, fontname="arialx")
        unicode_case("Latin accents (Arial)", " ".join(["Café crème über naïve señor"] * 4), fontfile=ARIAL, fontname="arialx")
    else:
        print("SKIP | Arial not available: Cyrillic/accent cases skipped")
    if os.path.exists(NIRMALA):
        unicode_case("Devanagari (Nirmala UI)", " ".join(["यह एक परीक्षण दस्तावेज़ है"] * 4), fontfile=NIRMALA, fontname="nirx")
    else:
        print("SKIP | Nirmala not available: Devanagari case skipped")
    unicode_case("CJK with spaces (built-in japan font)", " ".join(["日本語のテスト"] * 12), fontname="japan")

    # CJK written without spaces counts as very few "words" -> page skipped by the 10-word minimum (PINNED gap)
    fname = name()
    path = make_pdf(fname, ["日本語のテスト文書です。" * 12], fontsize=11, fontname="japan")
    error = ingest(path)
    extracted = extract_text(path)
    print(f"INFO | CJK without spaces: {len(extracted[0]['text'].split())} whitespace-separated token(s) on the page")
    check("[unicode, PINNED] unspaced CJK text (a few whitespace tokens) is skipped by the 10-word page minimum -> ValueError",
          etype(error) == "ValueError" and rows_for(fname) == [])
    finding("unspaced CJK pages are silently skipped",
            "the 'fewer than 10 whitespace words' page rule and the word-based chunkers assume space-separated text; "
            "a full page of Japanese/Chinese without spaces yields 'No usable chunks'. Undefined by the contract (limitation)")

    unicode_name = f"{PREFIX}документ é {uuid.uuid4().hex[:6]}.pdf"
    path = make_pdf(unicode_name, [ok_text])
    check("[names] a Unicode file name with spaces is stored unchanged as document_name",
          ingest(path) is None and len(rows_for(unicode_name)) == len(chunk_text(ok_text, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)) == 1)
    for sep in ("/", "\\"):
        with mock.patch.object(ingestion, "generate_embeddings", side_effect=det_embedder), \
                mock.patch.object(ingestion, "extract_text", side_effect=lambda p: [{"page_number": 1, "text": ok_text}]), \
                mock.patch.object(ingestion.os.path, "getsize", return_value=1), \
                contextlib.redirect_stdout(io.StringIO()):
            leaf = name()
            ingestion.ingest_pdf(f"C:{sep}some{sep}dir with space{sep}{leaf}")
        check(f"[names] path with '{sep}' separators -> document_name is just the file name", len(rows_for(leaf)) == 1)

    # long text
    long_pages = [" ".join(words(f"L{p}", 600)) for p in range(1, 9)]
    fname = name()
    error = ingest(make_pdf(fname, long_pages, fontsize=7))
    exp = [(p, i, c) for p, t in enumerate(long_pages, 1) for i, c in enumerate(chunk_text(t, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP), 1)]
    got = rows_for(fname)
    check(f"[long] 8 pages x 600 words -> {len(exp)} chunks stored, identities and content exactly as chunked",
          error is None and [(r[1], r[2], r[3]) for r in got] == exp and all(len(r[3].split()) <= cfg.CHUNK_SIZE for r in got))
    one_long = " ".join(words("sx", 400))      # a single 400-word 'sentence' (no punctuation) on one page
    fname = name()
    error = ingest(make_pdf(fname, [one_long]))
    check("[long sentence, words strategy] 400 unpunctuated words -> word chunks of <= chunk_size",
          error is None and [r[3] for r in rows_for(fname)] == chunk_text(one_long, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP))
    fname = name()
    with mock.patch.object(cfg, "CHUNK_STRATEGY", "sentences"):
        error = ingest(make_pdf(fname, [one_long]))
    got = rows_for(fname)
    check("[long sentence, sentences strategy] the oversized sentence is split by words: every chunk <= chunk_size, "
          "equals chunk_text_sentences, no repeated trailing window",
          error is None and [r[3] for r in got] == chunk_text_sentences(one_long, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)
          and all(len(r[3].split()) <= cfg.CHUNK_SIZE for r in got))

    # ============================================================ 3. duplicate / repeated ingestion
    print("INFO | --- 3. duplicate and repeated ingestion ---")
    page_text = " ".join(words("du", 230))
    fname = name()
    path = make_pdf(fname, [page_text])
    ingest(path)
    first = rows_for(fname)
    for _ in range(2):
        ingest(path)
    again = rows_for(fname)
    check("[repeat] same file ingested 3 times: same rows, same ids, same content and embeddings (idempotent)",
          len(first) == len(again) == 3 and again == first)

    other_name = name()
    other = make_pdf(other_name, [page_text])
    ingest(other)
    a, b = rows_for(fname), rows_for(other_name)
    check("[same content, other filename] stored as a second, independent document (no cross-document dedupe): "
          "same chunks, different row ids", len(b) == 3 and [r[3] for r in a] == [r[3] for r in b]
          and not ({r[0] for r in a} & {r[0] for r in b}))

    changed = make_pdf(fname + ".v2.pdf", [" ".join(words("ch", 230))])
    os.replace(changed, path)                   # same file name, different content, same chunk layout
    ingest(path)
    updated = rows_for(fname)
    check("[changed content, same filename] rows are updated in place (same ids and positions, new content and embeddings)",
          [r[0] for r in updated] == [r[0] for r in first] and [r[3] for r in updated] != [r[3] for r in first]
          and all("chw" in r[3] for r in updated) and all(u[4] != f[4] for u, f in zip(updated, first)))
    check("[changed content, same filename] no old text remains for the positions that were rewritten",
          not any("duw" in r[3] for r in updated))
    grown = make_pdf(fname + ".v3.pdf", [" ".join(words("gr", 330))])
    os.replace(grown, path)
    ingest(path)
    check("[changed content, more chunks] the extra chunks are inserted (4 rows), earlier ids kept",
          len(rows_for(fname)) == 4 and [r[0] for r in rows_for(fname)][:3] == [r[0] for r in first])
    shrunk = make_pdf(fname + ".v4.pdf", [" ".join(words("sh", 30))])
    os.replace(shrunk, path)
    ingest(path)
    left = rows_for(fname)
    check("[changed content, fewer chunks, A2] chunk 1 is updated and the obsolete chunks are removed (1 row; "
          "superseded the earlier pin that kept 4 rows)",
          len(left) == 1 and left[0][3].startswith("shw001"))

    # ============================================================ 4. failure handling
    print("INFO | --- 4. failure handling ---")
    f_name = name()
    f_path = make_pdf(f_name, [" ".join(words("fa", 230))])

    error = ingest(f_path, extract_text=RuntimeError("parser exploded"))
    check("[failure] parser failure propagates (RuntimeError) and nothing is stored",
          etype(error) == "RuntimeError" and rows_for(f_name) == [])

    def boom(texts):
        raise ConnectionError("embedding service down")
    error = ingest(f_path, embedder=boom)
    check("[failure] embedding failure propagates (ConnectionError) and nothing is stored",
          etype(error) == "ConnectionError" and rows_for(f_name) == [])

    error = ingest(f_path, embedder=lambda t: np.zeros((len(t), 5)))
    check("[failure] embedding dimension mismatch -> ValueError mentioning EMBEDDING_DIM, nothing stored",
          etype(error) == "ValueError" and "EMBEDDING_DIM" in str(error) and rows_for(f_name) == [])

    for label, emb, allowed in (("a Python list instead of an ndarray", lambda t: [[0.1] * cfg.EMBEDDING_DIM] * len(t), {"AttributeError"}),
                                ("a 1-D array", lambda t: np.zeros(cfg.EMBEDDING_DIM), {"IndexError"}),
                                ("None", lambda t: None, {"AttributeError"})):
        error = ingest(f_path, embedder=emb)
        check(f"[failure] embedder returning {label} -> {'/'.join(sorted(allowed))} (not validated, but nothing is stored)",
              etype(error) in allowed and rows_for(f_name) == [])

    # embedder returns FEWER vectors than chunks: dimension is right, row count is wrong
    def short_embedder(texts):
        return det_embedder(texts)[:-1]
    error = ingest(f_path, embedder=short_embedder)
    stored = rows_for(f_name)
    expected_chunks = len(chunk_text(" ".join(words("fa", 230)), cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP))
    print(f"INFO | embedder returned {expected_chunks - 1} vectors for {expected_chunks} chunks: raised {etype(error)}, "
          f"{len(stored)} rows stored")
    check("[failure] embedder returning too few vectors -> ValueError (count mismatch) and nothing is stored",
          etype(error) == "ValueError" and "Embedding count" in str(error) and stored == [])
    def long_embedder(texts):
        return np.vstack([det_embedder(texts), det_embedder(["extra"])])
    error = ingest(f_path, embedder=long_embedder)
    check("[failure] embedder returning too many vectors -> ValueError (count mismatch) and nothing is stored",
          etype(error) == "ValueError" and "Embedding count" in str(error) and rows_for(f_name) == [])
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name=%s", (f_name,))

    # database write failure: NaN vector in the 2nd chunk -> the INSERT fails after chunk 1 was executed
    def nan_second(texts):
        v = det_embedder(texts)
        v[1][0] = float("nan")
        return v
    error = ingest(f_path, embedder=nan_second)
    print(f"INFO | NaN vector in chunk 2: raised {etype(error)}: {str(error)[:70]!r}")
    check("[failure, DB write] a failing INSERT (NaN in chunk 2) raises and the whole document is rolled back: 0 rows "
          "(one transaction, no partial document)", error is not None and rows_for(f_name) == [])

    ingest(f_path)
    before = rows_for(f_name)
    error = ingest(make_pdf(f_name + ".bad.pdf", [" ".join(words("zz", 230))]), embedder=nan_second)
    os.replace(os.path.join(WORKDIR, f_name + ".bad.pdf"), f_path)
    error = ingest(f_path, embedder=nan_second)
    check("[failure, DB write] a failing re-ingest (same filename, NaN in chunk 2) leaves the previously stored rows untouched",
          error is not None and rows_for(f_name) == before)

    # ============================================================ 5. resource boundaries
    print("INFO | --- 5. resource and input boundaries ---")
    src = open(os.path.join(os.path.dirname(os.path.abspath(ingestion.__file__)), "ingestion_service.py"), encoding="utf-8").read()
    src += open(os.path.join(os.path.dirname(os.path.abspath(ingestion.__file__)), "pdf_parser.py"), encoding="utf-8").read()
    has_limit = any(token in src.lower() for token in ("max_pages", "max_size", "getsize", "st_size", "page_count", "len(document)", "max_bytes"))
    check("[limits, A3] ingestion now enforces configurable file-size and page-count limits (superseded the earlier 'no limit' gap; "
          "behaviour covered by test_a3_ingestion_limits.py)",
          has_limit is True and cfg.MAX_PDF_SIZE_MB == 50 and cfg.MAX_PDF_PAGES == 500)
    finding("no total-chunk limit in ingestion",
            "file size and page count are limited since A3, but the total chunk count is not; all embeddings are computed "
            "in memory in one call and inserted in one transaction. Documented gap; no huge file created")
    pages40 = [" ".join(words(f"q{p:02d}", 12)) for p in range(1, 41)]
    fname = name()
    error = ingest(make_pdf(fname, pages40))
    check("[limits] a modest 40-page document is ingested completely (40 pages -> 40 rows, pages 1..40)",
          error is None and [r[1] for r in rows_for(fname)] == list(range(1, 41)))

    check("[isolation] no rows outside this test's p2_04_ documents were added, changed or removed",
          foreign_fingerprint() == baseline)


try:
    run()
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("[cleanup] no test rows left in document_chunks", left == 0)
check("[cleanup] temp directory removed", not os.path.exists(WORKDIR))

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
