"""Bounded, local-only page extraction for tenant-owned ingestion workers.

The native text path uses the same PyMuPDF sorted extraction as pdf_parser.
Only pages below the configured text threshold are rasterized for OCR; native
and OCR text are never concatenated, so a page cannot be indexed twice.

The local backend is Tesseract embedded in pinned PyMuPDF 2.0, with hash-pinned
tessdata_fast 4.1.0 English data installed explicitly. No download occurs during
request processing and no cloud OCR or external model/provider is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import hashlib
import os
import sys
import subprocess
import tempfile
import time
from typing import Callable

import pymupdf

from services.pdf_parser import InvalidPDFError, PDFLimitExceeded, UnsupportedFileTypeError


class OCRError(ValueError):
    """Safe ingestion error; never includes document text or paths."""


class OCRUnavailable(OCRError):
    pass


class OCRCancelled(OCRError):
    pass


class OCRTimeout(OCRError):
    pass


@dataclass(frozen=True)
class OCROptions:
    languages: tuple[str, ...] = ("en-US",)
    max_upload_bytes: int = 30 * 1024 * 1024
    max_pages: int = 100
    dpi: int = 180
    max_page_pixels: int = 15_000_000
    native_min_characters: int = 30
    page_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 300.0
    min_confidence: float = 0.0
    backend: str = "pymupdf-tesseract-fast-4.1.0"
    tessdata_dir: str | None = None

    def __post_init__(self):
        if self.backend != "pymupdf-tesseract-fast-4.1.0":
            raise ValueError("unsupported local OCR backend")
        if not self.languages or any(language != "en-US" for language in self.languages):
            raise ValueError("this release supports only en-US OCR")
        for value in (self.max_upload_bytes, self.max_pages, self.max_page_pixels,
                      self.native_min_characters):
            if type(value) is not int or value < 1:
                raise ValueError("OCR size and page limits must be positive integers")
        if not 72 <= self.dpi <= 300:
            raise ValueError("OCR dpi must be between 72 and 300")
        if self.min_confidence != 0:
            raise ValueError("the selected OCR backend does not expose confidence filtering")
        if (not math.isfinite(self.page_timeout_seconds)
                or not math.isfinite(self.total_timeout_seconds)
                or self.page_timeout_seconds <= 0 or self.total_timeout_seconds <= 0):
            raise ValueError("OCR timeouts must be finite positive values")


TESSDATA_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
TESSDATA_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata"

_TESSERACT_PYTHON = r'''
import json, sys
import pymupdf
pixmap = pymupdf.Pixmap(sys.argv[1])
pdf = pixmap.pdfocr_tobytes(language="eng", tessdata=sys.argv[2])
with pymupdf.open(stream=pdf, filetype="pdf") as document:
    text = document[0].get_text(sort=True)
print(json.dumps({"text": text}))
'''


def _check(cancelled, deadline):
    if cancelled is not None and cancelled():
        raise OCRCancelled("document processing cancelled")
    if time.monotonic() >= deadline:
        raise OCRTimeout("document processing time budget exceeded")


def _tessdata_path(options):
    configured = options.tessdata_dir or os.getenv("RAG_OCR_TESSDATA")
    if not configured:
        raise OCRUnavailable("local OCR requires configured pinned English language data")
    directory = Path(configured)
    try:
        digest = hashlib.sha256((directory / "eng.traineddata").read_bytes()).hexdigest()
    except OSError:
        raise OCRUnavailable("local OCR language data is unavailable") from None
    if digest != TESSDATA_SHA256:
        raise OCRUnavailable("local OCR language data does not match the pinned release")
    return str(directory.resolve())


def _run_tesseract(png: bytes, options: OCROptions, deadline: float,
                   cancelled: Callable[[], bool] | None) -> tuple[str, float | None]:
    tessdata = _tessdata_path(options)
    with tempfile.TemporaryDirectory(prefix="rag-ocr-") as directory:
        directory = Path(directory)
        image = directory / "page.png"
        image.write_bytes(png)
        # stderr is never exposed: runtime diagnostics may contain file paths.
        # A private file avoids pipe deadlock; output and raster sizes are bounded.
        with (directory / "output.json").open("w+b") as output:
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", _TESSERACT_PYTHON, str(image), tessdata],
                stdout=output, stderr=subprocess.DEVNULL,
            )
            try:
                while process.poll() is None:
                    _check(cancelled, deadline)
                    if output.tell() > 2_000_000:
                        raise OCRError("OCR output exceeds resource budget")
                    time.sleep(0.05)
                _check(cancelled, deadline)
                if process.returncode:
                    raise OCRError("local OCR processing failed")
                output.seek(0)
                raw = output.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise OCRError("OCR output exceeds resource budget")
                try:
                    result = json.loads(raw)
                    text = result["text"]
                    if not isinstance(text, str):
                        raise ValueError()
                    # MuPDF's PDF OCR interface does not expose word confidence.
                    return text, None
                except (ValueError, TypeError, KeyError):
                    raise OCRError("local OCR returned invalid output") from None
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()


def extract_pages(pdf_path: str | Path, *, options: OCROptions | None = None,
                  cancelled: Callable[[], bool] | None = None,
                  progress: Callable[[int, int], None] | None = None,
                  recognize: Callable | None = None) -> list[dict]:
    """Return original-page records, or raise without publishing partial results.

    `cancelled` must check a worker's lease/deletion/cancellation fence. Callers
    must recheck that fence in their publication transaction too. Retrying this
    pure extraction operation has no persistence or indexing side effects.
    `recognize` is a deterministic test seam; production uses local Tesseract.
    """
    options = options or OCROptions()
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        raise UnsupportedFileTypeError("only PDF documents are supported")
    if path.stat().st_size > options.max_upload_bytes:
        raise PDFLimitExceeded("PDF exceeds upload byte budget")
    deadline = time.monotonic() + options.total_timeout_seconds
    _check(cancelled, deadline)
    try:
        document = pymupdf.open(path, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError):
        raise InvalidPDFError("not a readable PDF") from None
    with document:
        if document.needs_pass:
            raise InvalidPDFError("password-protected PDF", cause_type="needs_pass")
        if document.page_count > options.max_pages:
            raise PDFLimitExceeded("PDF exceeds page budget")
        if not document.page_count:
            raise InvalidPDFError("PDF contains no pages")
        result = []
        for page in document:
            _check(cancelled, deadline)
            text = page.get_text(sort=True)
            method, confidence = "native", None
            if len("".join(text.split())) < options.native_min_characters:
                scale = options.dpi / 72
                pixels = math.ceil(page.rect.width * scale) * math.ceil(page.rect.height * scale)
                if pixels > options.max_page_pixels:
                    raise PDFLimitExceeded("PDF page exceeds OCR pixel budget")
                # RGB on white avoids alpha artifacts and an extra preprocessing dependency.
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                         colorspace=pymupdf.csRGB, alpha=False)
                page_deadline = min(deadline, time.monotonic() + options.page_timeout_seconds)
                text, confidence = (recognize or _run_tesseract)(
                    pixmap.tobytes("png"), options, page_deadline, cancelled)
                _check(cancelled, page_deadline)
                if not text.strip():
                    raise OCRError("no searchable text recognized on a PDF page")
                method = options.backend
            _check(cancelled, deadline)
            result.append({"page_number": page.number + 1, "text": text, "method": method,
                           "quality": {"mean_confidence": confidence, "languages": list(options.languages)
                                       if method != "native" else [], "language_data_sha256": TESSDATA_SHA256 if method != "native" else None}})
            if progress:
                progress(page.number + 1, document.page_count)
        return result
