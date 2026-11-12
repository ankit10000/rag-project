
import pymupdf

from services import retrieval_config as cfg


class PDFLimitExceeded(ValueError):
    """The PDF is larger (bytes or pages) than the configured ingestion limits."""


class UnsupportedFileTypeError(ValueError):
    """The input file is not a PDF (only the .pdf extension is supported)."""


def extract_text(pdf_path: str) -> list[dict]:

    pages = []

    with pymupdf.open(pdf_path) as document:

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
