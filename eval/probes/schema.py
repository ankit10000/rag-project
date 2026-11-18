"""Probe record schema shared by the probe data modules."""

CONTEXT_MODES = ("gold", "tier1")
CITATION_MODES = ("all_gold", "none")
STATUSES = ("answered", "abstained", "unverified", "error", "partial")
T, F = True, False


def S(correct, fact_recall, forbidden_hits, abstain_ok, partial_ok, conflict_ok, fabricated=0, **extra) -> dict:
    """Expected v1 sub-signals, positional in score_generic's order; ``extra`` adds e.g.
    citation_completeness or ungrounded_numbers where a probe is about them."""
    return {"correct": correct, "fact_recall": fact_recall, "forbidden_hits": list(forbidden_hits),
            "abstain_ok": abstain_ok, "partial_ok": partial_ok, "conflict_ok": conflict_ok,
            "fabricated": fabricated, **extra}


def probe(pid, limitation, target, answer, truth, v1, v2, classification, reason, *, v2_reason=None,
          status="answered", citations="all_gold", context="gold", extra_context=(), annotations=None,
          phase_d_change=None, v2_signals=None) -> dict:
    """One probe. ``v2`` is the intended v2 ``correct`` (True/False) or None when it cannot be stated
    yet; None requires ``v2_reason``. ``phase_d_change`` records how a Phase D probe was corrected."""
    if v2 is None and not v2_reason:
        raise ValueError(f"{pid}: an undecided v2 expectation needs a v2_reason")
    if context not in CONTEXT_MODES or status not in STATUSES:
        raise ValueError(f"{pid}: bad context {context!r} or status {status!r}")
    if not isinstance(citations, list) and citations not in CITATION_MODES:
        raise ValueError(f"{pid}: bad citations {citations!r}")
    if extra_context and context != "gold":
        raise ValueError(f"{pid}: extra_context only applies to the gold context")
    return {"id": pid, "limitation": limitation, "target": target, "answer": answer, "truth": truth,
            "v1": v1, "v2": v2, "v2_reason": v2_reason, "classification": classification, "reason": reason,
            "status": status, "citations": citations, "context": context,
            "extra_context": [tuple(e) for e in extra_context], "annotations": dict(annotations or {}),
            "phase_d_change": phase_d_change, "v2_signals": dict(v2_signals or {})}
