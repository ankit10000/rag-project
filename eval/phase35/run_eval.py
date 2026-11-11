"""
Phase 3.5 independent answer-quality evaluation (live Gemini).

    .venv\\Scripts\\python.exe eval\\phase35\\run_eval.py --tier 1|2 --split dev|heldout|all
        [--limit N] [--pause SECONDS] [--fresh] [--no-ingest]

Tier 1  answer layer only: the gold pages (+2 random distractor pages) are handed to
        generate_grounded_answer, exactly as retrieval would. Isolates generation.
Tier 2  end to end: the unseen documents are written as PDFs, ingested through the REAL
        ingestion pipeline into the scratch database rag_phase35_eval, and each question
        goes through rag_service.ask_question (classify, rewrite, hybrid retrieval, rerank,
        context assembly, grounded generation, validation). Retrieval is also scored.

Rules: defaults (prompt, retrieval config, thresholds) are NOT changed during evaluation;
the held-out split is run once for reporting. Results are appended to
eval/phase35/results/<tier>_<split>.jsonl and are resumable.
Ground truth is author-written and mechanically verified (validate.py) but NOT yet
human reviewed; every report states that.
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from eval import harness  # noqa: E402

harness.use_scratch_database("rag_phase35_eval")

from eval.answer_scoring import (  # noqa: E402
    DISAGREEMENT_PHRASES, INSUFFICIENCY_PHRASES, _has_any, fact_recall, forbidden_hits,
)
from eval.phase35 import validate as V  # noqa: E402
from services import llm_service  # noqa: E402
from services.answer_service import generate_grounded_answer  # noqa: E402
from services.context_assembly_service import assemble_context  # noqa: E402
from services.llm_service import generate_answer  # noqa: E402

DATA_MODULES = ["data_A", "data_B", "data_C", "data_D"]
RESULTS_DIR = os.path.join(ROOT, "eval", "phase35", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)
NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
REF_RE = re.compile(r"\[S\d+(?:\s*[,;]\s*S\d+)*\]", re.I)


def split_of(case_id: str) -> str:
    return "dev" if int(hashlib.sha1(case_id.encode()).hexdigest(), 16) % 10 < 3 else "heldout"


def load_all():
    docs, cases = V.load(DATA_MODULES)
    errors = V.validate(docs, cases)
    if errors:
        print("DATASET INVALID:\n" + "\n".join(errors[:20]))
        sys.exit(2)
    for c in cases:
        c["split"] = split_of(c["id"])
    return docs, cases


# ------------------------------------------------------------------ scoring --
def norm_numbers(text):
    text = REF_RE.sub(" ", text or "")
    return {n.replace(",", "").rstrip(".") for n in NUM_RE.findall(text)}


def score_generic(case, result, chunk_pair, context_ids, context_text):
    """
    chunk_pair: {chunk_id: gold (document, page) key or None}
    context_ids: every chunk id the model was given
    """
    answer = result.get("answer") or ""
    citations = result.get("citations") or []
    gold_pairs = {(s["document"], s["page"]) for s in case["gold_sources"]}
    cited_ids = [c["chunk_id"] for c in citations]
    fabricated = sum(1 for cid in cited_ids if cid not in context_ids)
    good = [cid for cid in cited_ids if cid in context_ids and chunk_pair.get(cid) is not None]
    covered = {chunk_pair[cid] for cid in good}

    if cited_ids:
        correctness = len(good) / len(cited_ids)
    else:
        correctness = 1.0 if not gold_pairs else 0.0
    completeness = len(covered) / len(gold_pairs) if gold_pairs else (1.0 if not cited_ids else 1.0)

    abstained = result.get("status") == "abstained" or _has_any(answer, INSUFFICIENCY_PHRASES)
    if case["expect_partial"]:
        abstain_ok = None
    elif case["expect_abstain"]:
        abstain_ok = abstained
    else:
        abstain_ok = result.get("status") not in ("abstained", "unverified", "error")

    recall = fact_recall(answer, case["gold_facts"])
    hits = forbidden_hits(answer, case["forbidden"])
    partial_ok = (recall > 0 and abstained) if case["expect_partial"] else None
    conflict_ok = (_has_any(answer, DISAGREEMENT_PHRASES) and covered >= gold_pairs) if case["expect_conflict"] else None

    allowed_numbers = norm_numbers(context_text) | norm_numbers(case["question"]) | \
        norm_numbers(" ".join(m["content"] for m in case["history"]))
    ungrounded = sorted(n for n in norm_numbers(answer) if n not in allowed_numbers)

    stripped = REF_RE.sub("", answer).strip()
    payload_only = bool(hits) and len(stripped) < 80 and recall < 1.0
    correct = (recall == 1.0 and not hits and abstain_ok is not False
               and partial_ok is not False and conflict_ok is not False)
    correct_lenient = (recall == 1.0 and not payload_only and abstain_ok is not False
                       and partial_ok is not False and conflict_ok is not False)
    unsupported = bool(hits) or (case["expect_abstain"] and not abstained) or fabricated > 0 or bool(ungrounded)

    return {
        "fact_recall": recall, "forbidden_hits": hits, "abstain_ok": abstain_ok,
        "partial_ok": partial_ok, "conflict_ok": conflict_ok,
        "citation_correctness": correctness, "citation_completeness": completeness,
        "fabricated": fabricated, "ungrounded_numbers": ungrounded, "unsupported": unsupported,
        "correct": correct, "correct_lenient": correct_lenient,
        "status": result.get("status"),
    }


# -------------------------------------------------------------------- tier 1 --
def tier1_context(case, docs):
    """Return (retrieval-result dicts, chunk_pair, context_ids)."""
    rng = random.Random(case["id"])
    items = []   # (document, page, text, gold_pair_or_None)

    if case["tier"] == "answer_only":
        spans = [(s["document"], s["page"], s["span"]) for s in case["gold_sources"]]
        for ch in case["tier1_chunks"]:
            gold = None
            for d, p, sp in spans:
                if V.norm(sp) in V.norm(ch["content"]):
                    gold = (d, p)
            items.append((ch["document"], ch["page"], ch["content"], gold))
    else:
        gold_pairs = list(dict.fromkeys((s["document"], s["page"]) for s in case["gold_sources"]))
        for d, p in gold_pairs:
            items.append((d, p, docs[d][p - 1], (d, p)))
        pool = [(d, i + 1) for d, pages in docs.items() for i in range(len(pages)) if (d, i + 1) not in gold_pairs]
        for d, p in rng.sample(pool, 2):
            items.append((d, p, docs[d][p - 1], None))

    rng.shuffle(items)
    results, chunk_pair = [], {}
    for rank, (d, p, text, gold) in enumerate(items, start=1):
        cid = rank
        chunk_pair[cid] = gold
        score = float(len(items) - rank + 1)
        results.append({"chunk": (cid, d, p, text, score), "rrf_score": 0.0, "rerank_score": score})
    return results, chunk_pair, set(chunk_pair)


def run_tier1(case, docs):
    results, chunk_pair, ids = tier1_context(case, docs)
    bundle = assemble_context(results)
    t0 = time.perf_counter()
    u0 = len(llm_service.usage_log)
    out = generate_grounded_answer(case["question"], bundle, "DOCUMENT", generate_answer, case["history"], "")
    latency = time.perf_counter() - t0
    usage = llm_service.usage_log[u0:]
    context_text = " ".join(s["content"] for s in bundle["sources"])
    # chunk ids in citations are the bundle chunk ids (== our ids)
    score = score_generic(case, out, chunk_pair, ids, context_text)
    return {
        "id": case["id"], "category": case["category"], "split": case["split"], "tier": 1,
        "question": case["question"], "answer": out["answer"], "status": out["status"],
        "citations": out["citations"], "issues": out["issues"], "attempts": out["attempts"],
        "latency_s": latency, "llm_calls": len(usage),
        "prompt_tokens": sum(u["prompt"] for u in usage), "output_tokens": sum(u["output"] for u in usage),
        "context": [{"chunk_id": s["chunk_id"], "document": s["document_name"], "page": s["page_number"],
                     "gold": chunk_pair.get(s["chunk_id"]) is not None} for s in bundle["sources"]],
        "score": score,
    }


# -------------------------------------------------------------------- tier 2 --
def build_scratch_corpus(docs):
    import pymupdf
    from services.database import get_connection
    from services.ingestion_service import ingest_pdf
    from services.bm25_service import clear_bm25_cache

    with get_connection() as conn:
        conn.execute("TRUNCATE document_chunks RESTART IDENTITY")
    clear_bm25_cache()
    folder = tempfile.mkdtemp(prefix="phase35_pdfs_")
    for name, pages in docs.items():
        doc = pymupdf.open()
        for text in pages:
            page = doc.new_page()
            page.insert_textbox(pymupdf.Rect(36, 36, 559, 806), text, fontsize=9)
        path = os.path.join(folder, name)
        doc.save(path)
        doc.close()
        ingest_pdf(path)
    with get_connection() as conn:
        n = conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
    print(f"Ingested {len(docs)} PDFs -> {n} chunks in the scratch database")
    return n


def run_tier2(case, docs):
    import services.rag_service as rag
    from services.database import get_connection

    t0 = time.perf_counter()
    u0 = len(llm_service.usage_log)
    out = rag.ask_question(case["question"], history=case["history"], memory_summary="")
    latency = time.perf_counter() - t0
    usage = llm_service.usage_log[u0:]

    retrieved = out.get("retrieved", [])
    ids = [r["chunk_id"] for r in retrieved]
    contents = {}
    if ids:
        with get_connection() as conn:
            for cid, text in conn.execute(
                "SELECT id, content FROM document_chunks WHERE id = ANY(%s)", (ids,)
            ).fetchall():
                contents[cid] = text

    gold_pairs = {(s["document"], s["page"]) for s in case["gold_sources"]}
    chunk_pair = {r["chunk_id"]: ((r["document_name"], r["page_number"])
                                  if (r["document_name"], r["page_number"]) in gold_pairs else None)
                  for r in retrieved}
    context_text = " ".join(contents.values())
    result = {"answer": out["answer"], "citations": out.get("citations", []), "status": out.get("status")}
    score = score_generic(case, result, chunk_pair, set(ids), context_text)

    retrieved_pairs = {(r["document_name"], r["page_number"]) for r in retrieved}
    first_gold_rank = next((i for i, r in enumerate(retrieved, 1)
                            if (r["document_name"], r["page_number"]) in gold_pairs), None)
    score["retrieval_page_recall"] = (len(gold_pairs & retrieved_pairs) / len(gold_pairs)) if gold_pairs else None
    score["retrieval_first_gold_rank"] = first_gold_rank

    return {
        "id": case["id"], "category": case["category"], "split": case["split"], "tier": 2,
        "question": case["question"], "answer": out["answer"], "status": out.get("status"),
        "citations": out.get("citations", []), "issues": out.get("issues", []),
        "latency_s": latency, "llm_calls": len(usage),
        "prompt_tokens": sum(u["prompt"] for u in usage), "output_tokens": sum(u["output"] for u in usage),
        "retrieved": [{k: r[k] for k in ("ref", "chunk_id", "document_name", "page_number", "retrieval_score")}
                      for r in retrieved],
        "score": score,
    }


# --------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["1", "2"], required=True)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--no-ingest", action="store_true")
    args = ap.parse_args()

    harness.assert_scratch()
    docs, cases = load_all()
    chosen = [c for c in cases if args.split == "all" or c["split"] == args.split]
    if args.tier == "2":
        chosen = [c for c in chosen if c["tier"] == "both"]
    if args.limit:
        chosen = chosen[: args.limit]

    path = os.path.join(RESULTS_DIR, f"tier{args.tier}_{args.split}.jsonl")
    if args.fresh and os.path.exists(path):
        os.remove(path)
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            done = {json.loads(line)["id"] for line in f if line.strip()}

    if args.tier == "2" and not args.no_ingest:
        build_scratch_corpus(docs)

    runner = run_tier1 if args.tier == "1" else run_tier2
    todo = [c for c in chosen if c["id"] not in done]
    print(f"{len(chosen)} cases selected, {len(done)} already done, {len(todo)} to run", flush=True)

    for i, case in enumerate(todo, 1):
        try:
            record = runner(case, docs)
        except Exception as error:   # keep going; record the failure
            record = {"id": case["id"], "category": case["category"], "split": case["split"],
                      "tier": int(args.tier), "question": case["question"], "answer": f"RUNNER ERROR: {error!r}",
                      "status": "error", "citations": [], "latency_s": 0, "llm_calls": 0,
                      "prompt_tokens": 0, "output_tokens": 0,
                      "score": {"correct": False, "correct_lenient": False, "unsupported": False,
                                "citation_correctness": 0.0, "citation_completeness": 0.0, "fabricated": 0,
                                "abstain_ok": None, "fact_recall": 0.0, "forbidden_hits": [],
                                "ungrounded_numbers": [], "partial_ok": None, "conflict_ok": None,
                                "status": "error"}}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        s = record["score"]
        print(f"[{i}/{len(todo)}] {case['id']} correct={s['correct']} status={record['status']} "
              f"cit={s['citation_correctness']:.2f}/{s['citation_completeness']:.2f} {record['latency_s']:.1f}s", flush=True)
        time.sleep(args.pause)

    print("done ->", path)


if __name__ == "__main__":
    main()
