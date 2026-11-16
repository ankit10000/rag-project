"""
Stage 6: offline replay of the RECORDED dev answers through the answer layer,
before (git HEAD) and after (working tree) the Stage 6 change. No LLM call:
a fake model returns the recorded answer on every attempt.

    .venv/bin/python -m eval.stage6_answer_replay --output eval/results/stage6_answer_replay_dev.json

Inputs (read-only): eval/phase35/results/tier1_dev.jsonl and tier2_dev.jsonl
(dev split only, recorded live Gemini output). Tier 1 contexts are rebuilt with
run_eval.tier1_context (same seed); Tier 2 passages are read by chunk id from
the scratch database rag_phase35_eval and checked against the recorded
document/page. run_eval's helpers are loaded with ast (importing run_eval
would switch DATABASE_URL), exactly as in the B4 replay.
"""
import argparse
import ast
import json
import os
import random
import re
import subprocess
import sys
import types
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eval import harness  # noqa: E402

SCRATCH_DB = "rag_phase35_eval"
RESULTS = os.path.join(ROOT, "eval", "phase35", "results")
HELPERS = ("NUM_RE", "REF_RE", "norm_numbers", "score_generic", "tier1_context")


def load_run_eval_helpers():
    from eval import answer_scoring
    from eval.phase35 import validate as V
    tree = ast.parse(open(os.path.join(ROOT, "eval", "phase35", "run_eval.py"), encoding="utf-8").read())
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name in HELPERS)
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in HELPERS for t in n.targets))]
    module = types.ModuleType("run_eval_helpers")
    module.__dict__.update(re=re, random=random, V=V, **{k: getattr(answer_scoring, k) for k in (
        "DISAGREEMENT_PHRASES", "INSUFFICIENCY_PHRASES", "_has_any", "fact_recall", "forbidden_hits")})
    exec(compile(ast.Module(body=keep, type_ignores=[]), "run_eval_helpers", "exec"), module.__dict__)
    return module


def load_head_answer_service():
    """services/answer_service.py as committed at HEAD (before Stage 6)."""
    source = subprocess.run(["git", "show", "HEAD:services/answer_service.py"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout
    module = types.ModuleType("answer_service_head")
    exec(compile(source, "answer_service_head", "exec"), module.__dict__)
    return module


def replay(service, question, bundle, recorded, history):
    def fake(prompt):
        return recorded
    return service.generate_grounded_answer(question, bundle, "DOCUMENT", fake, history)


def tier1_bundles(helpers, docs, cases, rows):
    from services.context_assembly_service import assemble_context
    for row in rows:
        case = cases[row["id"]]
        results, chunk_pair, ids = helpers.tier1_context(case, docs)
        yield row, case, assemble_context(results), chunk_pair, ids


def tier2_bundles(cases, rows):
    from services.context_assembly_service import assemble_context
    from services.database import get_connection
    with get_connection() as conn:
        if conn.execute("SELECT current_database()").fetchone()[0] != SCRATCH_DB:
            raise RuntimeError("not connected to the scratch database")
        chunks = {r[0]: r for r in conn.execute(
            "SELECT id, document_name, page_number, content FROM document_chunks").fetchall()}
    for row in rows:
        case = cases[row["id"]]
        results = []
        for r in row["retrieved"]:
            cid, doc, page, content = chunks[r["chunk_id"]]
            if (doc, page) != (r["document_name"], r["page_number"]):
                raise RuntimeError(f"{row['id']}: chunk {cid} is {doc} p.{page} here, recorded differently")
            results.append({"chunk": (cid, doc, page, content, 0.0), "rrf_score": 0.0, "rerank_score": 1.0})
        bundle = assemble_context(results)
        gold = {(s["document"], s["page"]) for s in case["gold_sources"]}
        pair = {s["chunk_id"]: ((s["document_name"], s["page_number"])
                                if (s["document_name"], s["page_number"]) in gold else None) for s in bundle["sources"]}
        yield row, case, bundle, pair, set(pair)


def compare(helpers, head, new, items):
    out = []
    for row, case, bundle, pair, ids in items:
        context_text = " ".join(s["content"] for s in bundle["sources"])
        before = replay(head, case["question"], bundle, row["answer"], case["history"])
        after = replay(new, case["question"], bundle, row["answer"], case["history"])
        scores = [helpers.score_generic(case, r, pair, ids, context_text) for r in (before, after)]
        out.append({"id": row["id"], "category": case["category"],
                    "status": [before["status"], after["status"]],
                    "answer_changed": before["answer"] != after["answer"],
                    "issues_after": after["issues"],
                    "correct": [s["correct"] for s in scores],
                    "ungrounded_numbers": [s["ungrounded_numbers"] for s in scores],
                    "unsupported": [s["unsupported"] for s in scores]})
    return out


def summarize(rows):
    return {"cases": len(rows),
            "correct_before": sum(r["correct"][0] for r in rows), "correct_after": sum(r["correct"][1] for r in rows),
            "unsupported_before": sum(r["unsupported"][0] for r in rows),
            "unsupported_after": sum(r["unsupported"][1] for r in rows),
            "status_transitions": dict(Counter(f"{a}->{b}" for a, b in (r["status"] for r in rows))),
            "answers_changed": [r["id"] for r in rows if r["answer_changed"]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    harness.use_scratch_database(SCRATCH_DB)
    harness.assert_scratch()
    from services import answer_service as new
    from eval.phase35 import validate as V
    from eval.framework.integrity import split_of

    helpers, head = load_run_eval_helpers(), load_head_answer_service()
    docs, case_list = V.load(["data_A", "data_B", "data_C", "data_D"])
    cases = {c["id"]: c for c in case_list}
    report = {}
    for tier, name, make in ((1, "tier1_dev.jsonl", lambda rows: tier1_bundles(helpers, docs, cases, rows)),
                             (2, "tier2_dev.jsonl", lambda rows: tier2_bundles(cases, rows))):
        rows = [json.loads(line) for line in open(os.path.join(RESULTS, name), encoding="utf-8") if line.strip()]
        if any(split_of(r["id"]) != "dev" for r in rows):
            raise RuntimeError(f"{name} contains a non-dev case")
        per_case = compare(helpers, head, new, make(rows))
        report[f"tier{tier}"] = {"summary": summarize(per_case), "per_case": per_case}
    with open(args.output, "x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    for tier in ("tier1", "tier2"):
        print(tier, json.dumps(report[tier]["summary"]))


if __name__ == "__main__":
    main()
