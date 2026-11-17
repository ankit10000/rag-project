"""Mechanical source lookup for reviewers (read-only).

For a (document, page, span) reference it reports WHERE the evidence is: the PDF
file, whether the page exists, the line of that page in source_pages.md, and
whether the span text occurs on that page (in the PDF text and in the dataset
page text, comparing case-insensitively with whitespace collapsed), plus other
pages where the same text occurs.

It does NOT judge whether the evidence supports a gold fact, and it never
recommends a decision. A span that is found may still be the wrong evidence;
a span that is not found is a lookup problem for the reviewer to inspect.
"""

import os
import re

from eval.framework.integrity import ROOT

PDF_DIR = os.path.join(ROOT, "docs", "remediation", "heldout_review", "source_pdfs")
SOURCE_PAGES = os.path.join(ROOT, "docs", "remediation", "heldout_review", "source_pages.md")
DISCLAIMER = ("Mechanical lookup only: it locates text; it does not decide whether the "
              "evidence supports the expected fact or how the case should be judged.")
_PAGE_HEADING = re.compile(r"^### (.+?): page (\d+)\s*$")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


class SourceIndex:
    """Page texts from the dataset, source_pages.md and the PDFs (loaded lazily)."""

    def __init__(self, docs: dict, pdf_dir: str = PDF_DIR, source_pages: str = SOURCE_PAGES):
        self.docs = docs                    # {document: [page text, ...]} from the dataset
        self.pdf_dir = pdf_dir
        self.md_lines = self._md_page_lines(source_pages)
        self._pdf_pages = {}

    @staticmethod
    def _md_page_lines(path) -> dict:
        lines = {}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    match = _PAGE_HEADING.match(line)
                    if match:
                        lines[(match.group(1), int(match.group(2)))] = number
        return lines

    def pdf_pages(self, document: str):
        """List of page texts, or None if the PDF is missing/unreadable."""
        if document not in self._pdf_pages:
            path = os.path.join(self.pdf_dir, document)
            pages = None
            if os.path.isfile(path):
                import pymupdf
                try:
                    with pymupdf.open(path) as pdf:
                        pages = [page.get_text() for page in pdf]
                except (RuntimeError, ValueError):
                    pages = None
            self._pdf_pages[document] = pages
        return self._pdf_pages[document]

    def locate(self, document, page, span) -> dict:
        pdf = self.pdf_pages(document) if isinstance(document, str) else None
        dataset_pages = self.docs.get(document)
        result = {
            "document": document, "page": page,
            "pdf_path": os.path.relpath(os.path.join(self.pdf_dir, str(document)), ROOT),
            "pdf_found": pdf is not None, "pdf_page_count": len(pdf) if pdf else None,
            "document_in_dataset": dataset_pages is not None,
            "page_valid": isinstance(page, int) and not isinstance(page, bool) and pdf is not None
                          and 1 <= page <= len(pdf),
            "source_pages_md_line": self.md_lines.get((document, page)),
            "span_on_pdf_page": None, "span_on_dataset_page": None, "span_also_on": [],
        }
        needle = normalize(span)
        if not needle:
            result["problem"] = "empty span"
            return result
        if result["page_valid"]:
            result["span_on_pdf_page"] = needle in normalize(pdf[page - 1])
        if dataset_pages is not None and isinstance(page, int) and 1 <= page <= len(dataset_pages):
            result["span_on_dataset_page"] = needle in normalize(dataset_pages[page - 1])
        result["span_also_on"] = [(doc, n) for doc, pages in sorted(self.docs.items())
                                  for n, text in enumerate(pages, 1)
                                  if (doc, n) != (document, page) and needle in normalize(text)]
        result["problem"] = _problem(result)
        return result


def _problem(r: dict):
    if not r["pdf_found"]:
        return "PDF not found"
    if not r["document_in_dataset"]:
        return "document not in the dataset"
    if not r["page_valid"]:
        return "page out of range"
    if not r["span_on_pdf_page"] or not r["span_on_dataset_page"]:
        return "span text not found on the stated page"
    return None


def case_sources(row: dict) -> list:
    """(document, page, span) triples from a workbook row's expected_sources_json."""
    import json
    try:
        sources = json.loads(row.get("expected_sources_json") or "[]")
    except json.JSONDecodeError:
        return [("<invalid JSON>", None, None)]
    return [(s.get("document"), s.get("page"), s.get("span", s.get("gold_span"))) for s in sources]


def check_book_sources(book, index: SourceIndex) -> dict:
    """Locate every reference in a workbook; report counts and problems only (no text)."""
    total, problems = 0, []
    for row in book.cases:
        for document, page, span in case_sources(row):
            total += 1
            found = index.locate(document, page, span)
            if found["problem"]:
                problems.append({"case_id": row.get("case_id"), "document": document, "page": page,
                                 "problem": found["problem"]})
    return {"references": total, "problems": problems, "note": DISCLAIMER}
