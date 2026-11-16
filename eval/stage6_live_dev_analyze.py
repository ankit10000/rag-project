"""
Summarize the Stage 6 live dev run against the recorded Stage B dev baseline (both read-only).

    .venv/bin/python -m eval.stage6_live_dev_analyze --run eval/results/stage6_live_dev_20261116

Scores are the frozen run_eval.score_generic values stored in each record; nothing
is re-scored. Writes <run>/summary.json (new file, never overwritten) and prints it.
A case "triggered the safeguard" when any answer request carried numeric feedback
(unsupported_number) or the repair dropped a number sentence.
"""
import argparse
import json
import os
import statistics
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_DIR = os.path.join(ROOT, "eval", "phase35", "results")


def read(path):
    return {r["id"]: r for r in (json.loads(line) for line in open(path, encoding="utf-8") if line.strip())}


def latency(rows):
    values = sorted(r["latency_s"] for r in rows)
    if not values:
        return {}
    return {"median": round(statistics.median(values), 2), "p90": round(values[int(0.9 * (len(values) - 1))], 2),
            "max": round(values[-1], 2), "total": round(sum(values), 1)}


def triggered(record):
    s6 = record.get("stage6") or {}
    issues = (s6.get("answer") or {}).get("issues") or []
    corrections = [q.get("correction") or "" for q in s6.get("requests", [])]
    return any("unsupported_number" in c for c in corrections) or any("unsupported_number" in i for i in issues)


def requests_summary(rows):
    reqs = [q for r in rows for q in (r.get("stage6") or {}).get("requests", [])]
    errors = [q["outcome"] for q in reqs if q["outcome"] != "ok"]
    return {"total": len(reqs), "by_kind": dict(Counter(q["kind"] for q in reqs)),
            "by_model": dict(Counter(q["model"] for q in reqs)), "errors": dict(Counter(errors)),
            "rate_limited_429": sum(1 for e in errors if e.endswith(":429")),
            "timeouts": sum(1 for e in errors if "Timeout" in e),
            "corrections": dict(Counter(q["correction"] for q in reqs if q.get("correction")))}


def tier_summary(new, base):
    rows = [new[i] for i in sorted(new)]
    answers = [(r.get("stage6") or {}).get("answer") or {} for r in rows]
    issues = [i for a in answers for i in (a.get("issues") or [])]
    changes = {"correct_gained": [], "correct_lost": [], "status_changed": [], "same_answer_text": 0}
    for r in rows:
        b = base[r["id"]]
        if r["score"]["correct"] and not b["score"]["correct"]:
            changes["correct_gained"].append({"id": r["id"], "safeguard": triggered(r)})
        if b["score"]["correct"] and not r["score"]["correct"]:
            changes["correct_lost"].append({"id": r["id"], "safeguard": triggered(r)})
        if r["status"] != b["status"]:
            changes["status_changed"].append(f"{r['id']}: {b['status']}->{r['status']}")
        changes["same_answer_text"] += r["answer"] == b["answer"]
    return {
        "cases": len(rows), "runner_errors": sum(1 for r in rows if str(r["answer"]).startswith("RUNNER ERROR")),
        "correct": sum(r["score"]["correct"] for r in rows), "baseline_correct": sum(b["score"]["correct"] for b in base.values()),
        "correct_lenient": sum(r["score"]["correct_lenient"] for r in rows),
        "unsupported_scorer": sum(r["score"]["unsupported"] for r in rows),
        "baseline_unsupported_scorer": sum(b["score"]["unsupported"] for b in base.values()),
        "status": dict(Counter(r["status"] for r in rows)), "baseline_status": dict(Counter(b["status"] for b in base.values())),
        "attempts": dict(Counter(a.get("attempts") for a in answers)),
        "baseline_attempts": dict(Counter(b.get("attempts") for b in base.values())),
        "regenerated_cases": sum(1 for a in answers if (a.get("attempts") or 0) > 1),
        "safeguard_cases": [r["id"] for r in rows if triggered(r)],
        "repaired": sum(1 for i in issues if i.startswith("repaired:")),
        "dropped_unsupported_number_sentences": sum(1 for i in issues if i.startswith("dropped_unsupported_number")),
        "dropped_uncited_sentences": sum(1 for i in issues if i.startswith("dropped_uncited")),
        "retrieval_status": dict(Counter((r.get("stage6") or {}).get("retrieval_status") for r in rows)),
        "requests": requests_summary(rows),
        "llm_calls_recorded": sum(r["llm_calls"] for r in rows), "baseline_llm_calls": sum(b["llm_calls"] for b in base.values()),
        "tokens": {"prompt": sum(r["prompt_tokens"] for r in rows), "output": sum(r["output_tokens"] for r in rows)},
        "baseline_tokens": {"prompt": sum(b["prompt_tokens"] for b in base.values()),
                            "output": sum(b["output_tokens"] for b in base.values())},
        "latency_s": latency(rows), "baseline_latency_s": latency(list(base.values())),
        "changes": changes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    summary = {}
    for tier in (1, 2):
        new = read(os.path.join(args.run, f"tier{tier}_dev.jsonl"))
        base = read(os.path.join(BASELINE_DIR, f"tier{tier}_dev.jsonl"))
        if set(new) != set(base):
            raise SystemExit(f"tier {tier}: case ids differ from the baseline ({len(new)} vs {len(base)})")
        summary[f"tier{tier}"] = tier_summary(new, base)
    with open(os.path.join(args.run, "summary.json"), "x", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
