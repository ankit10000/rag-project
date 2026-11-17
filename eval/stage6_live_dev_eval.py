"""
Stage 6 live development evaluation (real Gemini), written to a NEW directory.

    .venv/bin/python -u -m eval.stage6_live_dev_eval --out eval/results/stage6_live_dev_20261116 [--resume]

Why a separate entry point: eval/phase35/run_eval.py writes to a fixed path and
--fresh deletes the recorded results. This module reuses run_eval's case
runners and frozen scorer UNCHANGED (run_tier1, run_tier2, score_generic,
load_all, split_of) and only adds observation:
  * every Gemini request is counted at the client (kind, model, outcome,
    latency, correction reasons); prompt text is never stored or printed;
  * the answer outcome (attempts, issues) and Tier 2 retrieval_status are captured.
Behaviour of the application is not changed.

Safety: dev split only (Tier 1: 47, Tier 2: 42, ids must equal the recorded
baseline's ids); held-out definitions are read only by the dataset validator
and never run. preflight() first calls bootstrap() (run_eval.bootstrap_execution:
scratch DB switch, then services imports); importing this module has no side
effect. Tier 2 uses the scratch database rag_phase35_eval as it is
(no re-ingestion, verified: 12 documents, 135 chunks). Output files are created
new; an existing output directory is refused unless --resume, which skips
completed ids and logs the resume (no case is re-run silently).
"""
import argparse
import json
import os
import re
import time

from eval.phase35 import run_eval   # import has no side effects since Stage 9 E0
from eval import harness

# Bound by bootstrap(): services.database reads DATABASE_URL at import, so these
# modules are imported only after run_eval.bootstrap_execution() has switched it
# to the scratch database rag_phase35_eval. Importing this module touches no DB.
llm = rag = None

BASELINE_DIR = os.path.join(run_eval.ROOT, "eval", "phase35", "results")
EXPECTED = {1: 47, 2: 42}
PAUSE_SECONDS = 3.0          # run_eval's default pause between cases
REQUESTS = []                # one entry per Gemini request (this process)
CAPTURE = {}


def _kind(prompt):
    if "Classify the user's question" in prompt:
        return "classify"
    if "search query rewriting" in prompt:
        return "rewrite"
    if "<retrieved_documents>" in prompt:
        return "answer_retry" if "CORRECTION REQUIRED" in prompt else "answer"
    return "other"


def instrument_client():
    """Count every request at the Gemini client; re-raise everything unchanged."""
    client = llm.get_client()
    real = client.models.generate_content

    def counted(*args, **kwargs):
        prompt = str(kwargs.get("contents", ""))
        problems = re.search(r"Problems found: ([^.]*)\.", prompt)
        entry = {"kind": _kind(prompt), "model": kwargs.get("model"),
                 "correction": problems.group(1) if problems else None}
        started = time.perf_counter()
        try:
            response = real(*args, **kwargs)
            entry["outcome"] = "ok"
            return response
        except Exception as error:   # recorded, then re-raised unchanged
            entry["outcome"] = f"{type(error).__name__}:{getattr(error, 'code', '')}"
            raise
        finally:
            entry["seconds"] = round(time.perf_counter() - started, 3)
            REQUESTS.append(entry)

    client.models.generate_content = counted


def capture_answers():
    """Record the grounded-answer outcome and Tier 2 retrieval_status (pass-through)."""
    real_answer = run_eval.generate_grounded_answer
    real_ask = rag.ask_question

    def answer(*args, **kwargs):
        out = real_answer(*args, **kwargs)
        CAPTURE["answer"] = {"attempts": out.get("attempts"), "issues": out.get("issues"), "status": out.get("status")}
        return out

    def ask(*args, **kwargs):
        out = real_ask(*args, **kwargs)
        CAPTURE["retrieval_status"] = out.get("retrieval_status")
        return out

    run_eval.generate_grounded_answer = answer      # Tier 1 calls it through run_eval
    rag.generate_grounded_answer = answer           # Tier 2 calls it through rag_service
    rag.ask_question = ask


def bootstrap():
    """Scratch DB switch + provider services (run_eval's own bootstrap), then services imports."""
    global llm, rag
    run_eval.bootstrap_execution()    # use_scratch_database("rag_phase35_eval") before any services import
    import services.llm_service as _llm
    import services.rag_service as _rag
    llm, rag = _llm, _rag


def preflight():
    bootstrap()
    harness.assert_scratch()
    from services.database import get_connection
    with get_connection() as conn:
        name, chunks, docs = conn.execute(
            "SELECT current_database(), count(*), count(DISTINCT document_name) FROM document_chunks").fetchone()
    if (name, chunks, docs) != ("rag_phase35_eval", 135, 12):
        raise RuntimeError(f"unexpected evaluation database state: {(name, chunks, docs)}")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not configured")
    docs, cases = run_eval.load_all()
    selected = {}
    for tier in (1, 2):
        chosen = [c for c in cases if c["split"] == "dev" and (tier == 1 or c["tier"] == "both")]
        recorded = [json.loads(line)["id"] for line in
                    open(os.path.join(BASELINE_DIR, f"tier{tier}_dev.jsonl"), encoding="utf-8") if line.strip()]
        if len(chosen) != EXPECTED[tier] or sorted(c["id"] for c in chosen) != sorted(recorded):
            raise RuntimeError(f"tier {tier}: dev selection does not match the recorded baseline")
        if any(run_eval.split_of(c["id"]) != "dev" for c in chosen):
            raise RuntimeError("a non-dev case was selected")
        selected[tier] = chosen
    return docs, selected


def error_record(case, tier, error):
    """Same shape as run_eval.main's failure record (no rerun, failure kept)."""
    return {"id": case["id"], "category": case["category"], "split": case["split"], "tier": tier,
            "question": case["question"], "answer": f"RUNNER ERROR: {type(error).__name__}", "status": "error",
            "citations": [], "latency_s": 0, "llm_calls": 0, "prompt_tokens": 0, "output_tokens": 0,
            "score": {"correct": False, "correct_lenient": False, "unsupported": False,
                      "citation_correctness": 0.0, "citation_completeness": 0.0, "fabricated": 0,
                      "abstain_ok": None, "fact_recall": 0.0, "forbidden_hits": [],
                      "ungrounded_numbers": [], "partial_ok": None, "conflict_ok": None, "status": "error"}}


def run_tier(tier, cases, docs, out_dir):
    path = os.path.join(out_dir, f"tier{tier}_dev.jsonl")
    done = set()
    if os.path.exists(path):
        done = {json.loads(line)["id"] for line in open(path, encoding="utf-8") if line.strip()}
    todo = [c for c in cases if c["id"] not in done]
    print(f"tier {tier}: {len(cases)} cases selected, {len(done)} already done, {len(todo)} to run", flush=True)
    runner = run_eval.run_tier1 if tier == 1 else run_eval.run_tier2

    for i, case in enumerate(todo, 1):
        CAPTURE.clear()
        first = len(REQUESTS)
        started = time.perf_counter()
        try:
            record = runner(case, docs)
        except Exception as error:   # kept as a failed case, never retried here
            record = error_record(case, tier, error)
        record["stage6"] = {"answer": CAPTURE.get("answer"), "retrieval_status": CAPTURE.get("retrieval_status"),
                            "requests": REQUESTS[first:], "wall_s": round(time.perf_counter() - started, 3)}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        s, a = record["score"], record["stage6"]["answer"] or {}
        print(f"[T{tier} {i}/{len(todo)}] {case['id']} correct={s['correct']} status={record['status']} "
              f"attempts={a.get('attempts')} requests={len(REQUESTS) - first} {record['latency_s']:.1f}s", flush=True)
        time.sleep(PAUSE_SECONDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    if os.path.exists(args.out) and not args.resume:
        raise SystemExit(f"{args.out} already exists; use --resume to continue a stopped run")
    docs, selected = preflight()
    os.makedirs(args.out, exist_ok=args.resume)
    if args.resume:
        print("RESUME: completed case ids are skipped and not re-run", flush=True)
    instrument_client()
    capture_answers()
    print(f"start {time.strftime('%Y-%m-%d %H:%M:%S')} model={llm.MODEL_NAME} fallbacks={llm.FALLBACK_MODELS}", flush=True)
    for tier in (1, 2):
        run_tier(tier, selected[tier], docs, args.out)
    print(f"done {time.strftime('%Y-%m-%d %H:%M:%S')} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
