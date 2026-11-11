"""Deterministic answer-quality scorers (pure Python, no network).

result = {"answer": str, "citations": [{"ref","document","page","chunk_id"}], "status": str}
"""

INSUFFICIENCY_PHRASES = [
    "couldn't find", "could not find", "can't find", "cannot find",
    "not enough information", "insufficient information", "does not contain",
    "doesn't contain", "do not contain", "no information", "not available",
    "cannot answer", "can't answer", "unable to answer", "not mentioned",
    "not specified", "not provided", "not stated", "isn't mentioned",
    "is not included", "not covered", "no mention",
]

DISAGREEMENT_PHRASES = [
    "differ", "conflict", "disagree", "inconsistent", "however", "whereas", "while",
]


def _text(result):
    return (result or {}).get("answer") or ""


def _has_any(text, phrases):
    low = text.lower()
    return any(p in low for p in phrases)


def _norm_ref(v):
    if v is None or v == "":
        return None
    if isinstance(v, str):
        v = v.strip()
        if v.isdigit():
            return int(v)
        return v.lower()
    return v


def fact_recall(answer, expected_facts):
    if not expected_facts:
        return 1.0
    low = (answer or "").lower()
    hit = sum(1 for alts in expected_facts if any(a.lower() in low for a in alts))
    return hit / len(expected_facts)


def forbidden_hits(answer, forbidden):
    low = (answer or "").lower()
    return [f for f in (forbidden or []) if f.lower() in low]


def _is_abstention(result):
    return (result or {}).get("status") == "abstained" or _has_any(_text(result), INSUFFICIENCY_PHRASES)


def abstention_ok(case, result):
    if case.get("expect_partial"):
        return None
    if case.get("expect_abstain"):
        return _is_abstention(result)
    return (result or {}).get("status") != "abstained"


def _citation_validity(case, result):
    """Return list of (cited chunk_id, fabricated: bool, valid: bool)."""
    chunks = {c["chunk_id"]: c for c in case["chunks"]}
    unexpected = set(case.get("unexpected_sources", []))
    out = []
    for cit in (result or {}).get("citations") or []:
        cid = cit.get("chunk_id")
        ch = chunks.get(cid)
        if ch is None:
            out.append((cid, True, False))
            continue
        meta_ok = (_norm_ref(cit.get("document")) == _norm_ref(ch.get("document_name"))
                   and _norm_ref(cit.get("page")) == _norm_ref(ch.get("page_number")))
        out.append((cid, not meta_ok, meta_ok and cid not in unexpected))
    return out


def citation_scores(case, result):
    items = _citation_validity(case, result)
    expected = [s["chunk_id"] for s in case.get("expected_sources", [])]
    if items:
        correctness = sum(1 for _, _, v in items if v) / len(items)
    else:
        correctness = 1.0 if not expected else 0.0
    cited_ids = {cid for cid, _, _ in items}
    completeness = (sum(1 for e in expected if e in cited_ids) / len(expected)) if expected else 1.0
    fabricated = sum(1 for _, f, _ in items if f)
    return {"correctness": correctness, "completeness": completeness, "fabricated": fabricated}


def unsupported_claim_flag(case, result):
    if forbidden_hits(_text(result), case.get("forbidden", [])):
        return True
    if case.get("expect_abstain") and not _is_abstention(result):
        return True
    return citation_scores(case, result)["fabricated"] > 0


def partial_ok(case, result):
    if not case.get("expect_partial"):
        return None
    text = _text(result)
    facts = case.get("expected_facts") or []
    got_one = any(any(a.lower() in text.lower() for a in alts) for alts in facts)
    return got_one and _has_any(text, INSUFFICIENCY_PHRASES)


def conflict_ok(case, result):
    if not case.get("expect_conflict"):
        return None
    if not _has_any(_text(result), DISAGREEMENT_PHRASES):
        return False
    cited = {cid for cid, _, _ in _citation_validity(case, result)}
    return all(s["chunk_id"] in cited for s in case.get("expected_sources", []))


def score_case(case, result):
    text = _text(result)
    recall = fact_recall(text, case.get("expected_facts", []))
    hits = forbidden_hits(text, case.get("forbidden", []))
    abst = abstention_ok(case, result)
    cit = citation_scores(case, result)
    part = partial_ok(case, result)
    conf = conflict_ok(case, result)
    correct = (recall == 1.0 and not hits and abst is not False
               and part is not False and conf is not False)
    return {
        "id": case["id"],
        "category": case["category"],
        "fact_recall": recall,
        "forbidden_hits": hits,
        "abstention_ok": abst,
        "citation_correctness": cit["correctness"],
        "citation_completeness": cit["completeness"],
        "fabricated": cit["fabricated"],
        "unsupported": unsupported_claim_flag(case, result),
        "partial_ok": part,
        "conflict_ok": conf,
        "correct": correct,
    }


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def aggregate(scores):
    n = len(scores)
    unsupported_rate = (sum(1 for s in scores if s["unsupported"]) / n) if n else 0.0
    abst = [s["abstention_ok"] for s in scores if s["abstention_ok"] is not None]
    per_cat = {}
    for s in scores:
        per_cat.setdefault(s["category"], []).append(1.0 if s["correct"] else 0.0)
    return {
        "answer_correctness": _mean([1.0 if s["correct"] else 0.0 for s in scores]),
        "faithfulness": 1.0 - unsupported_rate,
        "unsupported_claim_rate": unsupported_rate,
        "citation_correctness": _mean([s["citation_correctness"] for s in scores]),
        "citation_completeness": _mean([s["citation_completeness"] for s in scores]),
        "abstention_accuracy": _mean([1.0 if a else 0.0 for a in abst]),
        "fabricated_citations_total": sum(s["fabricated"] for s in scores),
        "per_category": {k: _mean(v) for k, v in per_cat.items()},
    }


def _expected_behaviour(case):
    parts = []
    if case.get("expect_abstain"):
        parts.append("abstain (information unavailable)")
    if case.get("expect_partial"):
        parts.append("answer available part and flag the missing part")
    if case.get("expect_conflict"):
        parts.append("state that sources disagree and cite both")
    if case.get("expected_facts"):
        parts.append("facts: " + "; ".join("/".join(a) for a in case["expected_facts"]))
    if case.get("forbidden"):
        parts.append("forbidden: " + ", ".join(case["forbidden"]))
    if case.get("citation_note"):
        parts.append("citations: " + case["citation_note"])
    return " | ".join(parts)


def format_report(cases, results, scores):
    agg = aggregate(scores)
    lines = ["# Answer quality report", "",
             "| Metric | Value |", "|---|---|"]
    for k in ("answer_correctness", "faithfulness", "unsupported_claim_rate",
              "citation_correctness", "citation_completeness", "abstention_accuracy"):
        lines.append(f"| {k} | {agg[k]:.3f} |")
    lines.append(f"| fabricated_citations_total | {agg['fabricated_citations_total']} |")
    lines += ["", "| Category | Correctness |", "|---|---|"]
    for k, v in agg["per_category"].items():
        lines.append(f"| {k} | {v:.3f} |")
    failed = [(c, r, s) for c, r, s in zip(cases, results, scores) if not s["correct"]]
    lines += ["", f"## Failed cases ({len(failed)})"]
    for c, r, s in failed:
        chunks = "; ".join(
            f"[{ch['chunk_id']}] {ch['document_name']} p{ch['page_number']}: {ch['content'][:60]}"
            for ch in c["chunks"]) or "(none)"
        lines += ["", f"### {c['id']} ({c['category']})",
                  f"- Question: {c['question']}",
                  f"- Retrieved: {chunks}",
                  f"- Answer: {(r or {}).get('answer', '')}",
                  f"- Status: {(r or {}).get('status')}",
                  f"- Expected: {_expected_behaviour(c)}",
                  f"- Score: recall={s['fact_recall']:.2f} forbidden={s['forbidden_hits']} "
                  f"abstention_ok={s['abstention_ok']} partial_ok={s['partial_ok']} conflict_ok={s['conflict_ok']}"]
    return "\n".join(lines)
