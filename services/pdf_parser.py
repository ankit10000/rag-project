
import pymupdf


def extract_text(pdf_path: str) -> list[dict]:

    pages = []

    with pymupdf.open(pdf_path) as document:

        for page in document:

            text = page.get_text(sort=True)

            if text.strip():

                pages.append({
                    "page_number": page.number + 1,
                    "text": text
                })

    return pages
