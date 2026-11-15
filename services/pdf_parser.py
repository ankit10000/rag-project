
import pymupdf

from services import retrieval_config as cfg


class PDFLimitExceeded(ValueError):
    """The PDF is larger (bytes or pages) than the configured ingestion limits."""


class UnsupportedFileTypeError(ValueError):
    """The input file is not a PDF (only the .pdf extension is supported)."""


class InvalidPDFError(ValueError):
    """The file cannot be read as a PDF: empty, corrupt, not a PDF, or password-protected.

    Stage 4: PyMuPDF's own open errors (FileDataError / EmptyFileError, which are
    RuntimeErrors) are re-raised as this ValueError so callers can treat them as
    invalid user input. For safe internal diagnostics the original exception
    TYPE is kept in ``cause_type``; the message never contains the file path or
    document text.

    The original exception object is deliberately NOT chained (__cause__/
    __context__): its traceback keeps the half-opened PyMuPDF document alive,
    which holds the file open on Windows, so the caller could not delete or
    restore the uploaded file while handling the error.
    """

    def __init__(self, message: str, cause_type: str | None = None):
        super().__init__(message)
        self.cause_type = cause_type


def extract_text(pdf_path: str) -> list[dict]:

    pages = []

    open_error = None
    try:
        # filetype="pdf": always parse as PDF, never guess another format from the content.
        document = pymupdf.open(pdf_path, filetype="pdf")
    except pymupdf.FileDataError as error:          # includes EmptyFileError
        open_error = type(error).__name__
    # Raised outside the except block so the PyMuPDF exception (and the file handle
    # its traceback keeps open) is released first.
    if open_error is not None:
        raise InvalidPDFError(f"not a readable PDF ({open_error})", cause_type=open_error)

    with document:

        # An unopened password-protected PDF cannot be read (owner-password-only
        # PDFs open without a password and are read normally).
        if document.needs_pass:
            raise InvalidPDFError("password-protected PDF", cause_type="needs_pass")

        if document.is_repaired:
            # MuPDF reconstructed a damaged file; whatever text it recovered is used.
            print("Warning: the PDF was damaged and repaired while opening; some content may be missing.")

        # Cheap check before any text is extracted.
        if document.page_count > cfg.MAX_PDF_PAGES:
            raise PDFLimitExceeded(
                f"PDF has {document.page_count} pages, exceeding "
                f"MAX_PDF_PAGES={cfg.MAX_PDF_PAGES}"
            )

        for page in document:

            text = page.get_text(sort=True)

            if text.strip():

                pages.append({
                    "page_number": page.number + 1,
                    "text": text
                })

    return pages
