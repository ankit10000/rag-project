"""
Stage 8 P3 live development check: rewrite-first question classification.

    .venv/bin/python -u -m eval.stage8_p3_live_dev_eval --out eval/results/stage8_p3_live_dev_20261116

Six Tier 2 DEV cases named by the Phase A audit (the two cases classified
MEMORY and the four classified MIXED in the Stage B / Stage 6 runs). Each case
runs once through the unchanged run_eval.run_tier2 (real retrieval on the
scratch database rag_phase35_eval, real Gemini, frozen scorer). Reuses the
Stage 6 live-eval preflight (dev-only, database check) and client request
counter; adds pass-through recorders for rewrite_query and classify_question.
No prompt text is stored. The output directory must not exist.
"""
import argparse
import json
import os
import time

from eval import stage6_live_dev_eval as s6   # noqa: E402 (sets the scratch DB via run_eval)
from eval.phase35 import run_eval
import services.llm_service as llm
import services.rag_service as rag

CASES = ["D-follow_up-04", "C-direct-05", "A-multipage-03", "B-follow-03", "D-multi_page-03", "D-multi_page-04"]
TRACE = {}


def record_rewrite_and_classify():
    real_rewrite, real_classify = rag.rewrite_query, rag.classify_question

    def rewrite(query, history, memory_summary):
        TRACE["raw_query"] = query
        try:
            out = real_rewrite(query=query, history=history, memory_summary=memory_summary)
            TRACE["rewritten_query"] = out
            return out
        except Exception as error:   # recorded, re-raised unchanged
            TRACE["rewrite_error"] = type(error).__name__
            raise

    def classify(text):
        TRACE["classifier_input"] = text
        try:
            TRACE["classification"] = real_classify(text)
            return TRACE["classification"]
        except Exception as error:
            TRACE["classify_error"] = type(error).__name__
            raise

    rag.rewrite_query, rag.classify_question = rewrite, classify


def summarize(record, case):
    gold = {(s["document"], s["page"]) for s in case["gold_sources"]}
    retrieved = {(r["document_name"], r["page_number"]) for r in record.get("retrieved", [])}
    reqs = record["stage6"]["requests"]
    return {
        "id": case["id"], "category": case["category"], "history_turns": len(case["history"]),
        "raw_query": TRACE.get("raw_query"), "rewritten_query": TRACE.get("rewritten_query"),
        "classifier_input": TRACE.get("classifier_input"), "classification": TRACE.get("classification"),
        "errors": {k: v for k, v in TRACE.items() if k.endswith("_error")},
        "retrieval_status": record["stage6"].get("retrieval_status"),
        "retrieval_ran": record["stage6"].get("retrieval_status") not in (None, "not_run"),
        "gold_pages": sorted(gold), "gold_pages_retrieved": sorted(gold & retrieved),
        "page_recall": record["score"].get("retrieval_page_recall"),
        "status": record["status"], "correct": record["score"]["correct"],
        "answer": record["answer"],
        "requests": [(q["kind"], q["model"], q["outcome"]) for q in reqs],
        "prompt_tokens": record["prompt_tokens"], "output_tokens": record["output_tokens"],
        "latency_s": record["latency_s"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if os.path.exists(args.out):
        raise SystemExit(f"{args.out} already exists")
    docs, selected = s6.preflight()          # dev-only selection + database checks
    by_id = {c["id"]: c for c in selected[2]}
    cases = [by_id[i] for i in CASES]        # KeyError if a case is not a Tier 2 dev case
    os.makedirs(args.out)
    s6.instrument_client()
    s6.capture_answers()
    record_rewrite_and_classify()
    print(f"start {time.strftime('%H:%M:%S')} model={llm.MODEL_NAME} fallbacks={llm.FALLBACK_MODELS}", flush=True)
    rows = []
    for case in cases:
        TRACE.clear()
        s6.CAPTURE.clear()
        first = len(s6.REQUESTS)
        try:
            record = run_eval.run_tier2(case, docs)
        except Exception as error:   # kept as a failed case, never retried
            record = s6.error_record(case, 2, error)
        record["stage6"] = {"answer": s6.CAPTURE.get("answer"), "retrieval_status": s6.CAPTURE.get("retrieval_status"),
                            "requests": s6.REQUESTS[first:]}
        row = summarize(record, case)
        rows.append(row)
        print(f"{row['id']}: class={row['classification']} retrieval={row['retrieval_status']} "
              f"gold={len(row['gold_pages_retrieved'])}/{len(row['gold_pages'])} correct={row['correct']} "
              f"requests={len(row['requests'])}", flush=True)
        time.sleep(s6.PAUSE_SECONDS)
    with open(os.path.join(args.out, "cases.json"), "x", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, default=str)
    print(f"done {time.strftime('%H:%M:%S')} total requests={len(s6.REQUESTS)}", flush=True)


if __name__ == "__main__":
    main()
