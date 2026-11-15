"""Conversational-memory evaluation interfaces and metrics (pure).

Each memory evaluation case states a DETERMINISTIC expected outcome; an
evaluator (future, not run) records the observed outcome; this module scores
them. Dimensions are kept separate so a provenance failure can never be hidden
by a good extraction score.

Dimensions and the fields compared
  extraction   expected_memories (list of required substrings per memory),
               forbidden_memories (substrings that must NOT be stored),
               expected_categories {memory_substring: category}
  provenance   expected_sources {memory_substring: [user message ids]} — exact set match;
               any non-user / foreign / missing source in observed sources is a failure
  dedup        expected_action per step: NEW|DUPLICATE|UPDATE|UNCERTAIN|SKIPPED + preserved_details
  update       same as dedup (decision accuracy) + old_fact_retained flag
  conflict     expected_relation per pair: EXPLICIT_UPDATE|TEMPORARY_STATE|TIME_DEPENDENT|
               DETAIL_CHANGE|UNRESOLVED
  context      expected_included_ids / expected_excluded_ids for assemble_memory_context
  lifecycle    expected_absent_ids after deletion, checkpoint_advanced flag,
               deleted facts that must not reappear in summary/context text

A semantically similar memory is NOT counted as correct: matching is by the
required substrings / exact ids / exact source sets defined in the case.
"""

from dataclasses import dataclass, field

DIMENSIONS = ("extraction", "provenance", "dedup", "update", "conflict", "context", "lifecycle")


@dataclass
class MemoryCase:
    id: str
    dimension: str
    description: str
    expected: dict
    tags: list = field(default_factory=list)


def _contains(text, needle):
    return isinstance(text, str) and needle.lower() in text.lower()


def score_extraction(expected: dict, observed: dict) -> dict:
    stored = observed.get("stored_memories") or []      # list of texts
    req = expected.get("expected_memories") or []        # list of substring lists (all must appear in ONE memory)
    found = [any(all(_contains(m, s) for s in group) for m in stored) for group in req]
    forbidden = [f for f in expected.get("forbidden_memories") or [] if any(_contains(m, f) for m in stored)]
    cats = expected.get("expected_categories") or {}
    observed_cats = observed.get("categories") or {}     # memory text -> category
    cat_ok = [any(_contains(t, key) and c == cat for t, c in observed_cats.items()) for key, cat in cats.items()]
    return {
        "recall": (sum(found) / len(found)) if found else None,
        "missing": [req[i] for i, ok in enumerate(found) if not ok],
        "unsupported_created": forbidden,
        "category_accuracy": (sum(cat_ok) / len(cat_ok)) if cat_ok else None,
        "passed": all(found) and not forbidden and all(cat_ok),
    }


def score_provenance(expected: dict, observed: dict) -> dict:
    exp = {k: set(v) for k, v in (expected.get("expected_sources") or {}).items()}
    obs = observed.get("sources") or {}                  # memory text -> [{"id", "role", "conversation_ok"}]
    problems = []
    for key, want in exp.items():
        match = [srcs for text, srcs in obs.items() if _contains(text, key)]
        if not match:
            problems.append(f"memory {key!r} not stored")
            continue
        srcs = match[0]
        got = {s["id"] for s in srcs}
        if got != want:
            problems.append(f"{key!r}: sources {sorted(got)} != expected {sorted(want)}")
        bad = [s["id"] for s in srcs if s.get("role") != "user" or not s.get("conversation_ok", False)]
        if bad:
            problems.append(f"{key!r}: non-user or foreign sources {bad}")
    rejected_ok = observed.get("rejected_invalid_batch") == expected.get("expect_batch_rejected", False)
    if not rejected_ok:
        problems.append("invalid-provenance batch handling differs from expectation")
    return {"passed": not problems, "problems": problems}


def score_decisions(expected: dict, observed: dict) -> dict:
    """dedup / update: per-step action accuracy + detail and old-fact preservation."""
    exp_steps, obs_steps = expected.get("steps") or [], observed.get("steps") or []
    rows = []
    for i, step in enumerate(exp_steps):
        got = obs_steps[i] if i < len(obs_steps) else {}
        ok = got.get("action") == step.get("action")
        details = all(_contains(got.get("stored_text", ""), d) for d in step.get("preserved_details") or [])
        old = (got.get("old_fact_retained") == step["old_fact_retained"]) if "old_fact_retained" in step else True
        sources = (set(got.get("source_ids") or []) == set(step["source_ids"])) if "source_ids" in step else True
        rows.append({"step": i, "action_ok": ok, "details_ok": details, "old_fact_ok": old, "sources_ok": sources})
    passed = bool(rows) and all(all(v for k, v in r.items() if k != "step") for r in rows)
    acc = (sum(r["action_ok"] for r in rows) / len(rows)) if rows else None
    return {"action_accuracy": acc, "steps": rows, "passed": passed}


def score_conflict(expected: dict, observed: dict) -> dict:
    exp, obs = expected.get("relations") or [], observed.get("relations") or []
    ok = [i < len(obs) and obs[i] == e for i, e in enumerate(exp)]
    return {"accuracy": (sum(ok) / len(ok)) if ok else None, "passed": bool(ok) and all(ok)}


def score_context(expected: dict, observed: dict) -> dict:
    inc = set(observed.get("included_ids") or [])
    want_in, want_out = set(expected.get("expected_included_ids") or []), set(expected.get("expected_excluded_ids") or [])
    leaked = sorted(inc & want_out)
    missing = sorted(want_in - inc)
    bounded = len(inc) <= expected.get("max_memories", len(inc))
    return {"missing": missing, "leaked": leaked, "bounded": bounded,
            "passed": not missing and not leaked and bounded}


def score_lifecycle(expected: dict, observed: dict) -> dict:
    present = set(observed.get("present_ids") or [])
    resurfaced = [t for t in expected.get("deleted_facts") or []
                  if any(_contains(txt, t) for txt in observed.get("context_texts") or [])]
    still = sorted(present & set(expected.get("expected_absent_ids") or []))
    cp_ok = observed.get("checkpoint_advanced") == expected.get("checkpoint_advanced") \
        if "checkpoint_advanced" in expected else True
    return {"still_present": still, "resurfaced": resurfaced, "checkpoint_ok": cp_ok,
            "passed": not still and not resurfaced and cp_ok}


SCORERS = {
    "extraction": score_extraction, "provenance": score_provenance, "dedup": score_decisions,
    "update": score_decisions, "conflict": score_conflict, "context": score_context,
    "lifecycle": score_lifecycle,
}


def score_case(case: MemoryCase, observed: dict) -> dict:
    if case.dimension not in SCORERS:
        raise ValueError(f"unknown memory dimension {case.dimension!r}")
    result = SCORERS[case.dimension](case.expected, observed or {})
    return {"id": case.id, "dimension": case.dimension, **result}


def aggregate(results: list) -> dict:
    by_dim = {}
    for r in results:
        by_dim.setdefault(r["dimension"], []).append(r)
    return {
        "overall": {"cases": len(results), "passed": sum(1 for r in results if r["passed"])},
        "by_dimension": {d: {"cases": len(rs), "passed": sum(1 for r in rs if r["passed"])}
                         for d, rs in sorted(by_dim.items())},
    }
