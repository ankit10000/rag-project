"""Answer-quality aggregation over EXISTING per-case scores (pure).

The per-case scoring semantics stay exactly those of
eval/phase35/run_eval.py:score_generic (fields stored in each result row's
"score"). This module never re-scores, never changes a rule and never treats a
structurally valid citation as semantic support.

Per-case fields consumed (from row["score"]):
  correct, correct_lenient, fact_recall, forbidden_hits, abstain_ok, partial_ok,
  conflict_ok, citation_correctness, citation_completeness, fabricated,
  ungrounded_numbers, unsupported, status
  (+ Tier 2: retrieval_page_recall, retrieval_first_gold_rank)

Metric mapping (what each reported metric means):
  correctness            share of cases with score.correct
  completeness           mean fact_recall (share of gold fact groups present)
  citation_correctness   mean structural citation correctness (cited chunks that are
                         gold pages) — NOT semantic support
  citation_completeness  mean share of gold pages cited
  unsupported_claims     share of cases flagged unsupported (forbidden hit, missed
                         abstention, fabricated citation or ungrounded number) —
                         a heuristic, separate from missing citations
  abstention_correctness share of abstention-expected cases with abstain_ok
  conflict_handling      share of conflict cases with conflict_ok
  partial_handling       share of partial cases with partial_ok
  injection_resistance   share of prompt_injection cases with no forbidden hit
NOT computable from current fields (reported as unavailable, never invented):
  semantic groundedness (needs claim-level human/judge labels),
  answer relevance (no relevance labels exist).
"""

UNAVAILABLE = {
    "semantic_groundedness": "requires claim-level human or judge labels; not present in the datasets",
    "answer_relevance": "no relevance labels exist in the datasets",
}


def _share(values):
    values = [bool(v) for v in values]
    return {"rate": (sum(values) / len(values)) if values else None, "n": len(values)}


def _mean(values):
    values = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {"mean": (sum(values) / len(values)) if values else None, "n": len(values)}


def case_issues(row: dict) -> list:
    """Human-readable explanation of why a case is not correct (from its score)."""
    s = row.get("score") or {}
    issues = []
    if s.get("fact_recall") is not None and s["fact_recall"] < 1.0:
        issues.append(f"fact recall {s['fact_recall']:.2f} (missing gold facts)")
    if s.get("forbidden_hits"):
        issues.append(f"forbidden content present: {s['forbidden_hits']}")
    for key, label in (("abstain_ok", "abstention expectation not met"),
                       ("partial_ok", "partial-answer expectation not met"),
                       ("conflict_ok", "conflict not surfaced / not all sides cited")):
        if s.get(key) is False:
            issues.append(label)
    if s.get("fabricated"):
        issues.append(f"{s['fabricated']} fabricated citation(s)")
    if s.get("ungrounded_numbers"):
        issues.append(f"ungrounded numbers: {s['ungrounded_numbers']}")
    if s.get("retrieval_page_recall") is not None and s["retrieval_page_recall"] < 1.0:
        issues.append(f"retrieval page recall {s['retrieval_page_recall']:.2f}")
    if str(row.get("answer", "")).startswith("RUNNER ERROR"):
        issues.append("runner/provider error")
    return issues


def aggregate(rows: list, cases_by_id: dict) -> dict:
    def block(rs):
        scores = [r.get("score") or {} for r in rs]
        cases = [cases_by_id.get(r["id"], {}) for r in rs]
        inj = [s for s, r in zip(scores, rs) if r.get("category") == "prompt_injection"]
        return {
            "cases": len(rs),
            "correct": sum(1 for s in scores if s.get("correct")),
            "correctness": _share([s.get("correct") for s in scores]),
            "correctness_lenient": _share([s.get("correct_lenient") for s in scores]),
            "completeness": _mean([s.get("fact_recall") for s in scores]),
            "citation_correctness": _mean([s.get("citation_correctness") for s in scores]),
            "citation_completeness": _mean([s.get("citation_completeness") for s in scores]),
            "unsupported_claims": _share([s.get("unsupported") for s in scores]),
            "abstention_correctness": _share([s.get("abstain_ok") for s, c in zip(scores, cases)
                                              if c.get("expect_abstain")]),
            "conflict_handling": _share([s.get("conflict_ok") for s in scores if s.get("conflict_ok") is not None]),
            "partial_handling": _share([s.get("partial_ok") for s in scores if s.get("partial_ok") is not None]),
            "injection_resistance": _share([not s.get("forbidden_hits") for s in inj]),
            "status_counts": _count(r.get("status") for r in rs),
        }

    by_category = {}
    for r in rows:
        by_category.setdefault(r.get("category"), []).append(r)
    return {
        "overall": block(rows),
        "by_category": {c: block(rs) for c, rs in sorted(by_category.items(), key=lambda x: str(x[0]))},
        "unavailable_metrics": dict(UNAVAILABLE),
        "per_case": [{"id": r["id"], "category": r.get("category"), "status": r.get("status"),
                      "correct": bool((r.get("score") or {}).get("correct")), "issues": case_issues(r)}
                     for r in sorted(rows, key=lambda r: r["id"])],
    }


def _count(values):
    out = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))
