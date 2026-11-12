"""Pure citation helpers: extract, strip, validate and build structured citations."""
import re

_MARKER = re.compile(r"\[\s*[Ss]\d+(?:\s*[,;]\s*[Ss]\d+)*\s*\]")
_REF = re.compile(r"[Ss](\d+)")
_PAGE = re.compile(r"\b(?:page|pg|p)\.?\s*(\d+)\b", re.IGNORECASE)
_FILE = re.compile(r"[\w\-.]+\.(?:pdf|docx|txt)\b", re.IGNORECASE)
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_LEADING_MARKERS = re.compile(r"^((?:\s*\[\s*[Ss]\d+(?:\s*[,;]\s*[Ss]\d+)*\s*\])+)")

# One shared list of insufficiency / abstention phrases (used by the citation
# coverage check here and by answer_service). Phrase matching is a heuristic.
ABSTAIN_PHRASES = (
    "couldn't find", "could not find", "cannot find", "can't find",
    "not enough information", "insufficient information", "does not contain",
    "doesn't contain", "do not contain", "don't contain", "no information",
    "not mentioned", "not available", "not provided", "not stated",
    "do not say", "does not say", "not specified", "do not mention",
    "does not mention", "don't mention", "doesn't mention", "no mention",
)
_REFUSAL = ABSTAIN_PHRASES

# Meta statements about disagreement between sources ("the two passages
# disagree on ...") are not document claims of their own.
_CONFLICT_WORDS = ("disagree", "conflict", "differ", "inconsistent", "contradict")
_SOURCE_WORDS = ("source", "passage", "document", "report", "file")


def _s(x):
    return x if isinstance(x, str) else ""


def _refs_in(marker):
    return [f"S{int(n)}" for n in _REF.findall(marker)]


def _tidy(text):
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def extract_citation_refs(text):
    """Unique refs (S<n>) in first-appearance order."""
    out = []
    for m in _MARKER.finditer(_s(text)):
        for r in _refs_in(m.group(0)):
            if r not in out:
                out.append(r)
    return out


def strip_citations(text):
    """Remove all citation markers and tidy whitespace."""
    return _tidy(_MARKER.sub("", _s(text)))


def remove_invalid_refs(text, valid_refs):
    """Remove refs not in valid_refs from markers; drop emptied markers."""
    valid = {str(r).upper() for r in (valid_refs or [])}

    def fix(m):
        refs = _refs_in(m.group(0))
        keep = [r for r in refs if r in valid]
        if len(keep) == len(refs):
            return m.group(0)
        return "[" + ", ".join(keep) + "]" if keep else ""

    return _tidy(_MARKER.sub(fix, _s(text)))


def build_citations(refs, sources):
    """Structured citation dicts for refs that exist in sources."""
    idx = {s.get("ref"): s for s in (sources or []) if isinstance(s, dict)}
    out = []
    for r in refs or []:
        s = idx.get(r)
        if s is None:
            continue
        out.append({"ref": r, "document": s.get("document_name"),
                    "page": s.get("page_number") or None, "chunk_id": s.get("chunk_id")})
    return out


def split_sentences(text):
    """
    Sentence segments of an answer. A citation marker written AFTER the full
    stop ("Fact. [S1] Next fact.") belongs to the preceding sentence, so
    leading markers are moved back to the previous segment.
    """
    out = []
    for seg in _SPLIT.split(_s(text)):
        seg = seg.strip()
        if not seg:
            continue
        lead = _LEADING_MARKERS.match(seg)
        if lead and out:
            out[-1] = out[-1] + " " + lead.group(1).strip()
            seg = seg[lead.end():].strip()
            if not seg:
                continue
        out.append(seg)
    return out


def _is_claim_without_citation(sent):
    """A sentence that states something (>=5 words) but carries no [S#]."""
    if len(sent.split()) < 5 or _MARKER.search(sent):
        return False
    if sent.rstrip().endswith(":"):                       # list / section intro
        return False
    low = sent.lower().replace("’", "'")
    if any(p in low for p in ABSTAIN_PHRASES):
        return False
    if any(w in low for w in _CONFLICT_WORDS) and any(w in low for w in _SOURCE_WORDS):
        return False
    return True


def uncited_claim_sentences(text):
    """Sentences that need a citation but have none (heuristic, see docs)."""
    return [s for s in split_sentences(text) if _is_claim_without_citation(s)]


def count_uncited_sentences(text):
    """Number of sentences with >=5 words, no [S#] marker, not an abstention/meta statement."""
    return len(uncited_claim_sentences(text))


def drop_uncited_claims(text):
    """Remove uncited claim sentences (used only by the repair fallback)."""
    kept = [s for s in split_sentences(text) if not _is_claim_without_citation(s)]
    return _tidy(" ".join(kept))


def validate_answer_citations(answer, sources, require_citations=True):
    """Check citations, claim coverage and prose mentions of pages/files against sources."""
    sources = [s for s in (sources or []) if isinstance(s, dict)]
    if not isinstance(answer, str) or not answer.strip():
        return {"valid": False, "cited_refs": [], "invalid_refs": [],
                "issues": ["empty_answer"], "uncited_sentences": 0}
    by_ref = {s.get("ref"): s for s in sources}
    known = set(by_ref)
    cited = extract_citation_refs(answer)
    good = [r for r in cited if r in known]
    bad = [r for r in cited if r not in known]
    uncited = count_uncited_sentences(answer)
    issues = []
    if bad:
        issues.append("invalid_ref")
    if require_citations and not good:
        issues.append("no_citation")
    if require_citations and uncited:
        issues.append("uncited_claim")

    # Page mentions: a sentence that cites sources may only mention pages of the
    # sources it cites; an uncited sentence may mention any retrieved page.
    all_pages = {str(s.get("page_number")) for s in sources if s.get("page_number")}
    prose = _MARKER.sub("", answer)
    if any(str(int(p)) not in all_pages for p in _PAGE.findall(prose)):
        issues.append("unknown_page_mention")
    for sent in ([] if "unknown_page_mention" in issues else split_sentences(answer)):
        refs = [r for r in extract_citation_refs(sent) if r in known]
        allowed = ({str(by_ref[r].get("page_number")) for r in refs if by_ref[r].get("page_number")}
                   if refs else all_pages)
        if any(str(int(p)) not in allowed for p in _PAGE.findall(_MARKER.sub("", sent))):
            issues.append("unknown_page_mention")
            break

    docs = {str(s.get("document_name")).lower() for s in sources if s.get("document_name")}
    for tok in _FILE.findall(prose):
        if tok.lower() not in docs:                       # exact file name only
            issues.append("unknown_document_mention")
            break
    return {"valid": not issues, "cited_refs": good, "invalid_refs": bad,
            "issues": issues, "uncited_sentences": uncited}


def answer_with_citations(answer, sources):
    """Answer text with invalid refs removed, structured citations, validation."""
    validation = validate_answer_citations(answer, sources)
    valid = {s.get("ref") for s in (sources or []) if isinstance(s, dict)}
    return {"text": remove_invalid_refs(answer, valid),
            "citations": build_citations(validation["cited_refs"], sources),
            "validation": validation}
