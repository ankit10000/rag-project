"""Phase 3 — deduplication, detail preservation and conflict analysis (pure).

No database, no model. These helpers make the existing NEW / DUPLICATE /
UPDATE / UNCERTAIN flow safer; they never delete, merge or rewrite stored
memories themselves, and they never change persisted text (the Phase 1
trim-only normalization contract is untouched: the keys below are for
COMPARISON only and are never stored or embedded).

Material details are the facts most easily lost by an over-eager
"duplicate" or "update": numbers, amounts, percentages, times, dates, years
and version strings. Two memories whose material details differ are never
treated as duplicates, and an update that drops a detail of the new
statement is not applied as a replacement.
"""

import re

from services.memory_classification_service import is_temporary_statement

# Comparison results
EXACT_DUPLICATE = "EXACT_DUPLICATE"
SAME_DETAILS = "SAME_DETAILS"
DETAILS_DIFFER = "DETAILS_DIFFER"

# Conflict / change relations between an existing and a new statement
EXPLICIT_UPDATE = "EXPLICIT_UPDATE"        # new text signals a change ("no longer", "switched to", ...)
DETAIL_CHANGE = "DETAIL_CHANGE"            # same kind of fact, different material details
TIME_DEPENDENT = "TIME_DEPENDENT"          # both carry different dates/years: may both be true
TEMPORARY_STATE = "TEMPORARY_STATE"        # new text describes a short-lived state
UNRESOLVED = "UNRESOLVED"                  # no deterministic evidence either way

_MATERIAL = re.compile(
    r"""
    \b\d{4}-\d{2}-\d{2}\b                      # ISO date
  | \b\d{1,2}:\d{2}\b                          # time
  | \bv?\d+(?:\.\d+){1,3}\b                    # version / decimal (v1.2, 3.11, 4.99)
  | [$€£₹]\s?\d[\d,]*(?:\.\d+)?                # currency amount
  | \b\d[\d,]*(?:\.\d+)?\s?%                   # percentage
  | \b\d[\d,]*\b                               # plain number / year
    """,
    re.VERBOSE,
)
_YEAR_OR_DATE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{4}-\d{2}-\d{2}\b")
_CHANGE_MARKERS = re.compile(
    r"\b(?:no longer|not any ?more|anymore|stopped|switched(?: to)?|changed(?: to)?|"
    r"moved to|now (?:uses?|works?|lives?|prefers?|is|am)|instead of|replaced|"
    r"used to|formerly|previously|quit|left)\b",
    re.IGNORECASE,
)


def duplicate_key(text) -> str:
    """Comparison-only key: casefold, collapse whitespace, drop trailing .!?"""
    if not isinstance(text, str):
        return ""
    collapsed = re.sub(r"\s+", " ", text).strip().casefold()
    return re.sub(r"[.!?]+$", "", collapsed).strip()


def material_details(text) -> frozenset:
    """Numbers, amounts, %, times, dates, years, versions found in the text."""
    if not isinstance(text, str):
        return frozenset()
    return frozenset(re.sub(r"[\s,]", "", m.group(0)).lower() for m in _MATERIAL.finditer(text))


def compare_memories(existing_text, new_text) -> str:
    """EXACT_DUPLICATE | SAME_DETAILS | DETAILS_DIFFER (comparison only)."""
    if duplicate_key(existing_text) and duplicate_key(existing_text) == duplicate_key(new_text):
        return EXACT_DUPLICATE
    if material_details(existing_text) == material_details(new_text):
        return SAME_DETAILS
    return DETAILS_DIFFER


_STATUS_DETAILS = re.compile(
    r"\b(?:no longer|not|never|without|completed|cancelled|canceled|paused|"
    r"pending|finished|stopped|quit|failed|active|inactive)\b", re.IGNORECASE
)


def new_details_preserved(new_text, candidate_text) -> bool:
    """Keep numeric details and require consistent status/negation evidence.

    A semantic similarity score must not turn a completed project into an
    active one, or discard a positive statement against an existing negation.
    For updates callers compare the new statement with its proposed replacement,
    so changing the old fact remains allowed when the replacement is faithful.
    """
    def statuses(text):
        return {match.group(0).casefold() for match in _STATUS_DETAILS.finditer(text or "")}
    return (material_details(new_text) <= material_details(candidate_text)
            and statuses(new_text) == statuses(candidate_text))


def find_exact_duplicate(new_text, candidates):
    """Return the id of a candidate whose duplicate_key equals new_text's, else None.

    candidates: iterable of (memory_id, memory_text). Lowest id wins for determinism.
    """
    key = duplicate_key(new_text)
    if not key:
        return None
    matches = sorted(mid for mid, text in candidates if duplicate_key(text) == key)
    return matches[0] if matches else None


def analyze_relation(existing_text, new_text) -> str:
    """Deterministic, auditable relation of a new statement to an existing one.

    Precedence: TEMPORARY_STATE, EXPLICIT_UPDATE, TIME_DEPENDENT, DETAIL_CHANGE,
    UNRESOLVED. It is evidence for the caller, not a decision by itself.
    """
    if is_temporary_statement(new_text):
        return TEMPORARY_STATE
    if isinstance(new_text, str) and _CHANGE_MARKERS.search(new_text):
        return EXPLICIT_UPDATE
    old_dates = set(_YEAR_OR_DATE.findall(existing_text or ""))
    new_dates = set(_YEAR_OR_DATE.findall(new_text or ""))
    if old_dates and new_dates and old_dates != new_dates:
        return TIME_DEPENDENT
    if material_details(existing_text) != material_details(new_text):
        return DETAIL_CHANGE
    return UNRESOLVED
