"""Deterministic numeric grounding (Stage 6). Pure: no DB, no LLM, no network.

A number (amount, date part, time, count, percentage, version digit) written in
an answer must appear in the evidence it relies on:
  * a sentence with valid [S#] citations -> the text of the CITED passages
    (so a fact cited to the wrong passage is caught when it carries a number);
  * an uncited sentence (only checked when citations are required) -> the text
    of ANY retrieved passage;
  * numbers that appear in the user's question are always allowed.
Numbers are compared by value ("07" = "7", "14.50" = "14.5", "1,200" = "1200").

This is factual verification of numbers only; it is not semantic grounding.
Names, paraphrases, hedging ("may" -> "will"), spelled-out numbers and derived
numbers that are not written in the evidence are outside its reach (see
docs/remediation/BATCH2_STAGE6_ANSWER_REPORT.md).
"""
import re
from decimal import Decimal, InvalidOperation

from services.citation_service import _FILE, _PAGE, extract_citation_refs, split_sentences, strip_citations

# Answer side: same pattern as eval/phase35/run_eval.py (NUM_RE), digits not glued
# to a word or a decimal point. Evidence side: every digit run, so "v4.0", "PR-7" or
# "A4" in a passage supports "version 4.0", "form 7" or "4" in the answer (the
# answer-side pattern alone would see no number in "v4.0": a false positive).
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_EVIDENCE_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _canonical(token):
    token = token.replace(",", "").rstrip(".")
    try:
        return str(Decimal(token).normalize())
    except InvalidOperation:
        return token


def _text(value):
    return strip_citations(value if isinstance(value, str) else "")


def numbers_in(text):
    """
    Canonical numbers an ANSWER states, ignoring [S#] citation markers and
    page / file-name mentions ("page 3", "report_2025.pdf"): those are checked
    against the source metadata by citation_service (unknown_page_mention,
    unknown_document_mention), not against the passage text.
    """
    prose = _FILE.sub(" ", _PAGE.sub(" ", _text(text)))
    return {_canonical(n) for n in _NUMBER.findall(prose)}


def evidence_numbers(text):
    """Canonical numbers present anywhere in evidence text (permissive)."""
    return {_canonical(n) for n in _EVIDENCE_NUMBER.findall(_text(text))}


def unsupported_numbers(answer, sources, question="", check_uncited=True):
    """
    [(sentence, [numbers...]), ...] for every sentence whose numbers are not in
    its evidence. Empty list = every number is grounded.
    """
    # Evidence of a passage: its text plus its document name (shown to the model in the header).
    by_ref = {s.get("ref"): evidence_numbers(s.get("content")) | evidence_numbers(s.get("document_name"))
              for s in (sources or []) if isinstance(s, dict)}
    everything = set().union(*by_ref.values()) if by_ref else set()
    asked = evidence_numbers(question)
    problems = []

    for sentence in split_sentences(answer if isinstance(answer, str) else ""):
        refs = [r for r in extract_citation_refs(sentence) if r in by_ref]
        if refs:
            allowed = set().union(*(by_ref[r] for r in refs))
        elif check_uncited:
            allowed = everything
        else:
            continue
        missing = sorted(numbers_in(sentence) - allowed - asked)
        if missing:
            problems.append((sentence, missing))

    return problems


def drop_unsupported_number_sentences(answer, sources, question="", check_uncited=True):
    """Remove the sentences reported by unsupported_numbers (repair fallback only)."""
    bad = {sentence for sentence, _ in unsupported_numbers(answer, sources, question, check_uncited)}
    kept = [s for s in split_sentences(answer) if s not in bad]
    return " ".join(kept).strip()
