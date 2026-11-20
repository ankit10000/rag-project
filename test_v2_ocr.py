"""Deterministic extraction guards plus opt-in actual local OCR benchmark.

Predeclared benchmark: a clean synthetic image-only page must recover at least
95% normalized word recall, both numeric facts, and original page 2 in a mixed
document. This is a fixture-quality gate, not a claim about arbitrary scans.
Run actual backend: RAG_OCR_REAL=1 .venv/bin/python -B test_v2_ocr.py
"""
import os
from pathlib import Path
import re
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import pymupdf

from services.ocr_service import (
    OCROptions, OCRError, OCRCancelled, OCRTimeout, OCRUnavailable,
    PDFLimitExceeded, InvalidPDFError, UnsupportedFileTypeError,
    extract_pages, _run_tesseract,
)
from services.pdf_parser import extract_text


NATIVE = "Native document text is preserved exactly with original page numbers and no duplicate indexing."
SCANNED = ("Lumen Observatory visitor policy\n"
           "A visitor permit costs 71 tokens.\n"
           "The permit is valid for 23 days.\n"
           "Visitors must keep the permit during each visit.")


def make_pdf(path, kinds):
    doc = pymupdf.open()
    for kind in kinds:
        page = doc.new_page(width=612, height=792)
        if kind == "native":
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 300), NATIVE, fontsize=16)
        elif kind == "scan":
            source = pymupdf.open()
            source_page = source.new_page(width=612, height=792)
            source_page.insert_textbox(pymupdf.Rect(50, 80, 562, 600), SCANNED, fontsize=20)
            png = source_page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
            page.insert_image(page.rect, stream=png)
            source.close()
    doc.save(path)
    doc.close()


class OCRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.pdf"

    def tearDown(self):
        self.temp.cleanup()

    def test_native_path_matches_existing_text_parser_without_ocr(self):
        make_pdf(self.path, ["native", "native"])
        def unexpected(*args):
            self.fail("native page unnecessarily sent to OCR")
        pages = extract_pages(self.path, recognize=unexpected)
        self.assertEqual([{k: p[k] for k in ("page_number", "text")} for p in pages], extract_text(str(self.path)))
        self.assertEqual([p["method"] for p in pages], ["native", "native"])

    def test_mixed_page_numbers_no_duplicate_text_and_progress(self):
        make_pdf(self.path, ["native", "scan", "native"])
        calls, progress = [], []
        def recognize(png, options, deadline, cancelled):
            calls.append(png[:8])
            return SCANNED, .98
        pages = extract_pages(self.path, recognize=recognize, progress=lambda *a: progress.append(a))
        self.assertEqual([p["page_number"] for p in pages], [1, 2, 3])
        self.assertEqual(calls, [b"\x89PNG\r\n\x1a\n"])
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertEqual(pages[1]["text"], SCANNED)
        self.assertEqual(pages[1]["quality"]["mean_confidence"], .98)

    def test_retry_is_pure_and_idempotent(self):
        make_pdf(self.path, ["scan"])
        fn = lambda *a: (SCANNED, .99)
        before = self.path.read_bytes()
        self.assertEqual(extract_pages(self.path, recognize=fn), extract_pages(self.path, recognize=fn))
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_and_encrypted_rejected(self):
        self.path.write_bytes(b"not a pdf")
        with self.assertRaises(InvalidPDFError):
            extract_pages(self.path)
        doc = pymupdf.open()
        doc.new_page()
        doc.save(self.path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="secret", user_pw="password")
        doc.close()
        with self.assertRaises(InvalidPDFError):
            extract_pages(self.path)

    def test_extension_and_byte_budget(self):
        make_pdf(self.path, ["native"])
        with self.assertRaises(PDFLimitExceeded):
            extract_pages(self.path, options=OCROptions(max_upload_bytes=10))
        with self.assertRaises(UnsupportedFileTypeError):
            extract_pages(self.path.with_suffix(".png"))

    def test_page_and_pixel_budgets(self):
        make_pdf(self.path, ["native", "scan"])
        with self.assertRaises(PDFLimitExceeded):
            extract_pages(self.path, options=OCROptions(max_pages=1))
        with self.assertRaises(PDFLimitExceeded):
            extract_pages(self.path, options=OCROptions(max_page_pixels=10))

    def test_cancel_before_work(self):
        make_pdf(self.path, ["scan"])
        with self.assertRaises(OCRCancelled):
            extract_pages(self.path, cancelled=lambda: True)

    def test_cancel_after_native_page_does_not_return_partial_results(self):
        make_pdf(self.path, ["native", "scan"])
        state = []
        with self.assertRaises(OCRCancelled):
            extract_pages(self.path, cancelled=lambda: bool(state), progress=lambda *a: state.append(a))

    def test_ocr_failure_and_empty_output_raise_instead_of_false_completion(self):
        make_pdf(self.path, ["scan"])
        with self.assertRaises(OCRError):
            extract_pages(self.path, recognize=lambda *a: ("", None))
        def failing(*args):
            raise OCRError("local OCR processing failed")
        with self.assertRaises(OCRError):
            extract_pages(self.path, recognize=failing)

    def test_page_timeout_checked_after_backend_return(self):
        make_pdf(self.path, ["scan"])
        with patch("services.ocr_service.time.monotonic", side_effect=[0, 0, 0, 0, 2]):
            with self.assertRaises(OCRTimeout):
                extract_pages(self.path, options=OCROptions(page_timeout_seconds=1),
                              recognize=lambda *a: (SCANNED, .9))

    def test_missing_local_backend_fails_without_network_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OCRUnavailable):
                _run_tesseract(b"", OCROptions(), float("inf"), None)

    def test_backend_cancellation_kills_and_reaps_real_subprocess(self):
        processes = []
        original_popen = subprocess.Popen
        def sleeper(*args, **kwargs):
            process = original_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            processes.append(process)
            return process
        calls = []
        def cancel():
            calls.append(1)
            return len(calls) >= 2
        with patch("services.ocr_service.subprocess.Popen", side_effect=sleeper), \
             patch("services.ocr_service._tessdata_path", return_value="/fake/tessdata"):
            with self.assertRaises(OCRCancelled):
                _run_tesseract(b"", OCROptions(), time.monotonic() + 10, cancel)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].returncode)

    def test_backend_timeout_kills_and_reaps_real_subprocess(self):
        processes = []
        original_popen = subprocess.Popen
        def sleeper(*args, **kwargs):
            process = original_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            processes.append(process)
            return process
        with patch("services.ocr_service.subprocess.Popen", side_effect=sleeper), \
             patch("services.ocr_service._tessdata_path", return_value="/fake/tessdata"):
            with self.assertRaises(OCRTimeout):
                _run_tesseract(b"", OCROptions(), time.monotonic() + .1, None)
        self.assertIsNotNone(processes[0].returncode)

    def test_invalid_options_fail_closed(self):
        for kw in ({"dpi": 400}, {"max_pages": 0}, {"min_confidence": 2},
                   {"languages": ("xx",)}, {"backend": "cloud"}, {"page_timeout_seconds": float("nan")}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                OCROptions(**kw)

    @unittest.skipUnless(os.getenv("RAG_OCR_REAL") == "1", "actual local OCR benchmark opt-in")
    def test_actual_scanned_and_mixed_quality_predeclared_95_percent(self):
        make_pdf(self.path, ["native", "scan"])
        with pymupdf.open(self.path) as doc:
            self.assertFalse(doc[1].get_text().strip(), "fixture must be truly image-only")
        pages = extract_pages(self.path, options=OCROptions(page_timeout_seconds=120))
        words = lambda s: re.findall(r"[a-z0-9]+", s.lower())
        expected, actual = words(SCANNED), words(pages[1]["text"])
        recall = sum(w in actual for w in expected) / len(expected)
        self.assertGreaterEqual(recall, .95)
        self.assertIn("71", actual)
        self.assertIn("23", actual)
        self.assertEqual(pages[1]["page_number"], 2)
        self.assertEqual(pages[0]["method"], "native")
        self.assertEqual(pages[1]["method"], "pymupdf-tesseract-fast-4.1.0")
        self.assertIsNone(pages[1]["quality"]["mean_confidence"])
        print(f"Actual Tesseract OCR benchmark: word_recall={recall:.3f}, numeric_facts=2/2, original_page=2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
