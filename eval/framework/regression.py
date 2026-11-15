"""Baseline vs current comparison (pure; reads result rows, writes nothing).

Rows are dicts with at least "id" and a correctness signal. By default the
signal is row["score"]["correct"] (eval/phase35 format); pass ``correct_fn``
for other formats. Inputs are never modified.

Per-case outcome classes
  FIXED                 baseline wrong  -> current correct   (improvement)
  REGRESSED             baseline correct -> current wrong     (regression)
  UNCHANGED_PASS        correct in both
  UNCHANGED_FAILURE     wrong in both
  NEW_CASE / MISSING    present only in current / only in baseline
Also reports status changes (e.g. answered -> abstained) and numeric metric deltas.
"""


def _default_correct(row):
    return bool((row.get("score") or {}).get("correct"))


def compare(baseline_rows, current_rows, correct_fn=_default_correct, metric_keys=()):
    base = {r["id"]: r for r in baseline_rows}
    cur = {r["id"]: r for r in current_rows}
    if len(base) != len(baseline_rows) or len(cur) != len(current_rows):
        raise ValueError("duplicate case ids in the inputs")

    cases = []
    for cid in sorted(set(base) | set(cur)):
        b, c = base.get(cid), cur.get(cid)
        if b is None:
            outcome = "NEW_CASE"
        elif c is None:
            outcome = "MISSING"
        else:
            bc, cc = correct_fn(b), correct_fn(c)
            outcome = {(False, True): "FIXED", (True, False): "REGRESSED",
                       (True, True): "UNCHANGED_PASS", (False, False): "UNCHANGED_FAILURE"}[(bc, cc)]
        entry = {"id": cid, "outcome": outcome,
                 "category": (c or b).get("category"),
                 "status_before": b.get("status") if b else None,
                 "status_after": c.get("status") if c else None}
        if b and c:
            deltas = {}
            for key in metric_keys:
                vb, vc = (b.get("score") or {}).get(key), (c.get("score") or {}).get(key)
                if isinstance(vb, (int, float)) and isinstance(vc, (int, float)) \
                        and not isinstance(vb, bool) and not isinstance(vc, bool) and vb != vc:
                    deltas[key] = vc - vb
            if deltas:
                entry["metric_deltas"] = deltas
        cases.append(entry)

    counts = {}
    for e in cases:
        counts[e["outcome"]] = counts.get(e["outcome"], 0) + 1
    both = [e for e in cases if e["outcome"] not in ("NEW_CASE", "MISSING")]
    return {
        "counts": dict(sorted(counts.items())),
        "baseline_correct": sum(1 for r in baseline_rows if correct_fn(r)),
        "current_correct": sum(1 for r in current_rows if correct_fn(r)),
        "compared_cases": len(both),
        "status_changes": [e for e in both if e["status_before"] != e["status_after"]],
        "regressions": [e["id"] for e in cases if e["outcome"] == "REGRESSED"],
        "improvements": [e["id"] for e in cases if e["outcome"] == "FIXED"],
        "unchanged_failures": [e["id"] for e in cases if e["outcome"] == "UNCHANGED_FAILURE"],
        "cases": cases,
    }
