"""Phase 4 evaluation framework — pure unit checks.

WRITTEN BUT NOT EXECUTED: testing/evaluation is disabled by user instruction until
explicitly authorized. No database, no model, no network, no evaluation run.
"""
import testsafe
testsafe.require_scratch_db()

import os
import sys
import tempfile

from eval.framework import memory_metrics, regression, reporting, retrieval_metrics as rm, safety
from eval.framework.integrity import runner_split_logic_matches, split_of
from eval.framework.memory_cases_proposal import CASES as MEMORY_CASES

FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


# retrieval metrics
ret, rel = ["a", "b", "a", "c", None, "d"], {"a", "d"}
check("duplicates/None collapsed", rm.dedupe_ranked(ret) == ["a", "b", "c", "d"])
check("recall@2", rm.recall_at_k(ret, rel, 2) == 0.5)
check("precision@3 (fixed K)", rm.precision_at_k(ret, rel, 3) == 1 / 3)
check("MRR first hit at rank 1", rm.reciprocal_rank(ret, rel) == 1.0)
check("MRR no hit -> 0.0", rm.reciprocal_rank(["x"], rel) == 0.0)
check("empty relevant -> recall/MRR/nDCG None", rm.recall_at_k(ret, set(), 3) is None
      and rm.reciprocal_rank(ret, set()) is None and rm.ndcg_at_k(ret, set(), 3) is None)
check("perfect ranking nDCG = 1", abs(rm.ndcg_at_k(["a", "d"], rel, 2) - 1.0) < 1e-12)
try:
    rm.recall_at_k(ret, rel, 0)
    check("k=0 rejected", False)
except ValueError:
    check("k=0 rejected", True)
m = rm.case_metrics([("D1", 1), ("D2", 3), ("D1", 2)], {("D1", 2), ("D3", 1)}, ks=(1, 3))
check("page and document recall", m["page_recall"] == 0.5 and m["document_recall"] == 0.5)
agg = rm.aggregate([{"id": "x", "category": "c", "metrics": {"mrr": None, "recall@1": 1.0}},
                    {"id": "y", "category": "c", "metrics": {"mrr": 0.5, "recall@1": 0.0}}], group_key="category")
check("aggregate excludes undefined values", agg["overall"]["mrr"] == {"mean": 0.5, "n": 1})

# regression
base = [{"id": "a", "score": {"correct": True}}, {"id": "b", "score": {"correct": False}},
        {"id": "c", "score": {"correct": True}}]
cur = [{"id": "a", "score": {"correct": False}}, {"id": "b", "score": {"correct": True}},
       {"id": "d", "score": {"correct": True}}]
r = regression.compare(base, cur)
check("regression classes", r["regressions"] == ["a"] and r["improvements"] == ["b"]
      and r["counts"] == {"FIXED": 1, "MISSING": 1, "NEW_CASE": 1, "REGRESSED": 1})

# safety gates and frozen thresholds
check("frozen thresholds", safety.FROZEN_THRESHOLDS[("heldout", 1)]["min_correct"] == 97
      and safety.FROZEN_THRESHOLDS[("heldout", 2)]["min_correct"] == 69)
check("96/113 fails (no rounding)", safety.threshold_result("heldout", 1, 96, 113)["status"] == "FAIL")
check("97/113 passes", safety.threshold_result("heldout", 1, 97, 113)["status"] == "PASS")
check("partial run is INCOMPLETE", safety.threshold_result("dev", 1, 41, 40)["status"] == "INCOMPLETE")
with tempfile.TemporaryDirectory() as tmp:
    existing = os.path.join(tmp, "exists.json")
    open(existing, "w").close()
    req = safety.RunRequest(mode="heldout", splits=["heldout"], tiers=[1], output_paths=[existing],
                            allow_live_provider=True)
    problems = safety.check_run_request(req)
    check("held-out blocked without approval / manifests; existing output refused",
          any("approval" in p for p in problems) and any("never overwritten" in p for p in problems))
    req = safety.RunRequest(mode="development", splits=["dev"], tiers=[1],
                            output_paths=[os.path.join(tmp, "new.jsonl")], allow_live_provider=False)
    check("live provider needs explicit opt-in", any("opt-in" in p for p in safety.check_run_request(req)))

# integrity (static only)
check("split rule duplicate matches the runner source (ast)", runner_split_logic_matches())
check("split_of deterministic", split_of("A-direct-01") == split_of("A-direct-01"))

# reporting evidence labels
try:
    reporting.build_report(evidence_class="INDEPENDENT_VALIDATION", human_review_status="AI_ASSISTED_ONLY",
                           manifest={}, run_info={})
    check("AI-assisted review cannot be labelled independent validation", False)
except ValueError:
    check("AI-assisted review cannot be labelled independent validation", True)

# memory metrics
ctx = memory_metrics.score_context({"expected_included_ids": [1, 3], "expected_excluded_ids": [2], "max_memories": 5},
                                   {"included_ids": [1, 3]})
check("context scoring", ctx["passed"])
check("proposed memory cases cover all dimensions",
      {c.dimension for c in MEMORY_CASES} == set(memory_metrics.DIMENSIONS))

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
