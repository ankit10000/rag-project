"""Pure citation helpers: extract, strip, validate and build structured citations."""
import re

_MARKER = re.compile(r"\[\s*[Ss]\d+(?:\s*[,;]\s*[Ss]\d+)*\s*\]")
_REF = re.compile(r"[Ss](\d+)")
_PAGE = re.compile(r"\b(?:page|pg|p)\.?\s*(\d+)\b", re.IGNORECASE)
_FILE = re.compile(r"[\w\-.]+\.(?:pdf|docx|txt)\b", re.IGNORECASE)
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_REFUSAL = ("couldn't find", "could not find", "cannot find", "can't find",
            "not enough information", "does not contain", "doesn't contain",
            "no information")


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


def count_uncited_sentences(text):
    """Sentences with >=5 words, no [S#] marker, and not a refusal statement."""
    n = 0
    for sent in _SPLIT.split(_s(text)):
        sent = sent.strip()
        if len(sent.split()) < 5 or _MARKER.search(sent):
            continue
        low = sent.lower().replace("’", "'")
        if any(p in low for p in _REFUSAL):
            continue
        n += 1
    return n


def validate_answer_citations(answer, sources, require_citations=True):
    """Check citations and prose mentions of pages/files against sources."""
    sources = [s for s in (sources or []) if isinstance(s, dict)]
    if not isinstance(answer, str) or not answer.strip():
        return {"valid": False, "cited_refs": [], "invalid_refs": [],
                "issues": ["empty_answer"], "uncited_sentences": 0}
    known = {s.get("ref") for s in sources}
    cited = extract_citation_refs(answer)
    good = [r for r in cited if r in known]
    bad = [r for r in cited if r not in known]
    issues = []
    if bad:
        issues.append("invalid_ref")
    if require_citations and not good:
        issues.append("no_citation")

    prose = _MARKER.sub("", answer)
    pages = {str(s.get("page_number")) for s in sources if s.get("page_number")}
    if any(str(int(p)) not in pages for p in _PAGE.findall(prose)):
        issues.append("unknown_page_mention")
    docs = [str(s.get("document_name")).lower() for s in sources if s.get("document_name")]
    for tok in _FILE.findall(prose):
        t = tok.lower()
        if not any(d == t or d.endswith(t) for d in docs):
            issues.append("unknown_document_mention")
            break
    return {"valid": not issues, "cited_refs": good, "invalid_refs": bad,
            "issues": issues, "uncited_sentences": count_uncited_sentences(answer)}


def answer_with_citations(answer, sources):
    """Answer text with invalid refs removed, structured citations, validation."""
    validation = validate_answer_citations(answer, sources)
    valid = {s.get("ref") for s in (sources or []) if isinstance(s, dict)}
    return {"text": remove_invalid_refs(answer, valid),
            "citations": build_citations(validation["cited_refs"], sources),
            "validation": validation}
