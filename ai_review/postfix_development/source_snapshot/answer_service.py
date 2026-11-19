"""
Grounded answer generation: prompt -> Gemini -> parse -> citation validation
-> bounded regeneration -> safe fallback. Citations are kept as structured
data next to the prose so they can be validated against the retrieval result.
"""
import re

from services import retrieval_config as cfg
from services.answer_prompt import REFUSAL_MESSAGE, build_answer_prompt
from services.citation_service import (
    ABSTAIN_PHRASES,
    answer_with_citations,
    drop_uncited_claims,
    evidence_profile,
    remove_invalid_refs,
    uncited_claim_sentences,
    validate_answer_citations,
)
from services.context_assembly_service import source_index
from services.grounding_service import drop_unsupported_number_sentences, unsupported_numbers

UNVERIFIED_MESSAGE = (
    "I found related passages in your documents, but I couldn't produce an "
    "answer I can verify against them, so I won't guess. Please rephrase or "
    "ask about a more specific part."
)

ERROR_MESSAGE = (
    "I couldn't generate a reliable answer right now. Please try again."
)

_TAG_RE = re.compile(r"^\s*\[(DOCUMENT|MEMORY|MIXED)\]\s*", re.I)

_ABSTAIN_PHRASES = ABSTAIN_PHRASES      # single shared list (citation_service)
_CONFLICT_PHRASES = ("disagree", "conflict", "differ", "inconsistent", "contradict")


def has_abstention_language(text: str) -> bool:
    return evidence_profile(text)[0] > 0


def classify_status(answer: str, cited_docs: set, has_citations: bool, sources=None) -> str:
    """Report pure insufficiency separately from cited negative facts and partials."""
    missing, facts = evidence_profile(answer, sources)

    lowered = answer.lower()

    if has_citations and len(cited_docs) >= 2 and any(p in lowered for p in _CONFLICT_PHRASES):
        return "conflict"
    if missing:
        return "partial" if facts else "abstained"
    return "answered"


def _result(answer, status, tag=None, citations=None, validation=None,
            attempts=0, issues=None):
    citations = citations or []
    return {
        "answer": answer,
        "status": status,
        "tag": tag,
        "citations": citations,
        # backward compatible shape used by main.py: document + page (+ extras)
        "sources": [
            {"document": c["document"], "page": c["page"],
             "chunk_id": c["chunk_id"], "ref": c["ref"]}
            for c in citations
        ],
        "validation": validation,
        "attempts": attempts,
        "issues": issues or [],
    }


def _parse(raw):
    """Return (tag, body) or (None, '') for empty/malformed model output."""
    if not isinstance(raw, str) or not raw.strip():
        return None, ""

    text = raw.strip()
    match = _TAG_RE.match(text)

    if match:
        return match.group(1).upper(), text[match.end():].strip()

    return None, text


def generate_grounded_answer(
    question: str,
    bundle: dict,
    question_type: str,
    generate_fn,
    history: list | None = None,
    memory_summary: str = "",
) -> dict:
    sources = bundle.get("sources", [])
    context_text = bundle.get("context_text", "")

    # Nothing retrieved for a document question: never ask the model to
    # "answer anyway" (that is where general knowledge leaks in).
    if question_type == "DOCUMENT" and not sources:
        return _result(REFUSAL_MESSAGE, "abstained", tag="DOCUMENT")

    attempts = 1 + max(0, cfg.ANSWER_MAX_RETRIES)
    feedback = None
    last_issues = []
    last_body, last_tag = "", None

    for attempt in range(1, attempts + 1):
        prompt = build_answer_prompt(
            question, sources, context_text, history, memory_summary, feedback
        )

        try:
            raw = generate_fn(prompt)
        except Exception as error:   # retry/fallback already happened inside generate_answer
            last_issues = [f"generation_error: {type(error).__name__}"]
            feedback = None
            continue

        tag, body = _parse(raw)

        if not body:
            last_issues = ["empty_answer"]
            feedback = "Your previous reply was empty. Reply with a tag and an answer."
            continue

        last_tag, last_body = tag, body
        is_refusal = body.strip() == REFUSAL_MESSAGE
        # A DOCUMENT/MIXED question with retrieved sources needs citations,
        # whatever tag the model chose (a [MEMORY] tag must not bypass grounding).
        needs_citations = bool(sources) and question_type != "MEMORY" and not is_refusal

        # Nothing was retrieved, yet the reply claims document facts: reject.
        if (not sources and tag == "DOCUMENT" and not is_refusal
                and not (has_abstention_language(body) and not uncited_claim_sentences(body))):
            last_issues = ["document_claim_without_sources"]
            feedback = (
                "Problems found: document_claim_without_sources. No document passages "
                "were retrieved, so you cannot state document facts. Answer only from "
                "memory/conversation with the [MEMORY] tag, or say the documents do not "
                "contain the answer."
            )
            continue

        checked = answer_with_citations(body, sources)
        # Numbers are checked whenever document grounding applies, including in
        # an abstention that the next rule exempts from needing a citation.
        check_uncited_numbers = needs_citations

        # A pure abstention / insufficiency statement needs no citation.
        # Only when EVERY sentence is an insufficiency statement; a factual
        # sentence that merely contains "not available" still needs a citation.
        if (needs_citations and not checked["citations"]
                and has_abstention_language(body)
                and validate_answer_citations(body, sources, require_citations=False)["uncited_sentences"] == 0):
            needs_citations = False

        validation = validate_answer_citations(body, sources, require_citations=needs_citations)

        # Stage 6: every number must be written in the passage it cites (or in the question).
        ungrounded = unsupported_numbers(body, sources, question, check_uncited=check_uncited_numbers)
        if ungrounded:
            validation = {**validation, "valid": False,
                          "issues": validation["issues"] + ["unsupported_number"]}

        if validation["valid"]:
            cited_docs = {c["document"] for c in checked["citations"]}
            status = classify_status(body, cited_docs, bool(checked["citations"]), sources)
            final_tag = tag or ("DOCUMENT" if checked["citations"] else "MEMORY")
            return _result(checked["text"], status, final_tag,
                           checked["citations"], validation, attempt)

        last_issues = validation["issues"]
        feedback = (
            "Problems found: " + ", ".join(validation["issues"]) +
            f". Cite only these references: {', '.join(s['ref'] for s in sources) or 'none'}. "
            "Do not write page numbers or filenames. If the passages do not "
            "contain the answer, say so instead of guessing."
        )
        if ungrounded:
            numbers = sorted({n for _, missing in ungrounded for n in missing})
            feedback += (
                f" These numbers are not written in the passages you cited: {', '.join(numbers)}. "
                "Use only numbers that appear in the cited passage; do not calculate, "
                "estimate or carry over numbers from elsewhere."
            )

    # ---- bounded retries exhausted: safe fallback ---------------------------
    if last_body:
        return _fallback(last_body, last_tag, last_issues, sources, question, attempts)

    return _result(ERROR_MESSAGE, "error", None, [], None, attempts, last_issues)


def _fallback(last_body, last_tag, last_issues, sources, question, attempts):
    """Repair the last reply, accept a pure abstention, or return UNVERIFIED."""
    # Repair: drop invalid refs, then drop every sentence left without a
    # citation (including a claim whose only citation was fabricated) and
    # every sentence with a number its evidence does not contain. Keep the
    # answer only if valid citations remain and nothing fabricated was
    # written in prose.
    without_bad_refs = remove_invalid_refs(last_body, set(source_index(sources)))
    dropped = uncited_claim_sentences(without_bad_refs)
    repaired = drop_uncited_claims(without_bad_refs) if dropped else without_bad_refs
    number_dropped = unsupported_numbers(repaired, sources, question)
    if number_dropped:
        repaired = drop_unsupported_number_sentences(repaired, sources, question)
    v = validate_answer_citations(repaired, sources, require_citations=True)
    issues_blocking = [i for i in v["issues"] if i != "invalid_ref"]

    if v["valid"] and not issues_blocking:
        checked = answer_with_citations(repaired, sources)
        cited_docs = {c["document"] for c in checked["citations"]}
        repair_issues = ["repaired:" + ",".join(last_issues)]
        if dropped:
            repair_issues.append(f"dropped_uncited_sentences:{len(dropped)}")
        if number_dropped:
            repair_issues.append(f"dropped_unsupported_number_sentences:{len(number_dropped)}")
        return _result(checked["text"],
                       classify_status(repaired, cited_docs, True, sources),
                       last_tag or "DOCUMENT", checked["citations"], v,
                       attempts, issues=repair_issues)

    if has_abstention_language(last_body) and not any(
        i.startswith(("unknown_", "invalid")) for i in last_issues
    ) and validate_answer_citations(
        last_body, sources, require_citations=False
    )["uncited_sentences"] == 0 and not unsupported_numbers(last_body, sources, question):
        return _result(last_body, "abstained", last_tag, [], None, attempts, last_issues)

    return _result(UNVERIFIED_MESSAGE, "unverified", last_tag, [], None, attempts, last_issues)
