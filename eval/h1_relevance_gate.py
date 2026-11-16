"""
Stage 5 H.1: development-only evaluation of the no-rerank relevance gate.
Retrieval only: no LLM call, no answer generation, no default changed.

    .venv/bin/python -m eval.h1_relevance_gate --output eval/results/h1_relevance_gate_dev.json
        [--no-ingest]

Data: eval/phase35 dataset, DEV split only (run_eval.split_of), Tier 2 cases
(tier == "both"). The corpus is written as PDFs and ingested with the real
ingest_pdf into the scratch database rag_phase35_eval (run_eval's builder).
Queries are the raw case questions (no LLM rewrite).

Configurations, all in the no-rerank path that has no gate today:
  E   existing  : RRF([keyword, vector]) -> first FINAL_TOP_K (= hybrid_search_detailed(rerank=False))
  (a) threshold : vector list filtered at T (existing SIMILARITY_THRESHOLD semantics) and every
                  fused candidate, keyword-only ones included, needs cosine similarity >= T
  (b) stopwords : BM25 with drop_stopwords=True (existing BM25_DROP_STOPWORDS path)
  a+b combined
T is swept over a grid; the calibration rule is fixed before looking at the results:
the largest T whose relevant-retrieval rate and page recall equal the T=None value.
The default reranked path (with rag_service's margin gate) is measured as a reference.
"""
import argparse
import json
import statistics
import time

from eval.phase35.run_eval import build_scratch_corpus, load_all  # noqa: E402 (sets the scratch DB)
from eval import harness
from eval.framework import retrieval_metrics as RM
from services import retrieval_config as cfg
from services.context_assembly_service import assemble_context
from services.database import get_connection
from services.embedding_service import generate_embeddings
from services.hybrid_search_service import hybrid_search_detailed, keyword_search
from services.rrf_service import reciprocal_rank_fusion
from services.search_service import semantic_search
from pgvector import Vector

GRID = [round(0.05 * i, 2) for i in range(15)]   # 0.00 .. 0.70
SCRATCH_DB = "rag_phase35_eval"


def prepare(no_ingest):
    harness.assert_scratch()
    with get_connection() as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        if name != SCRATCH_DB:
            raise RuntimeError(f"connected to {name!r}, expected {SCRATCH_DB!r}")
        chunks = conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
    docs, cases = load_all()
    if not no_ingest:
        chunks = build_scratch_corpus(docs)
    if not chunks:
        raise RuntimeError("scratch corpus is empty; run without --no-ingest")
    dev = [c for c in cases if c["split"] == "dev" and c["tier"] == "both"]
    return dev, chunks


def similarities(query, ids):
    if not ids:
        return {}
    vector = Vector(generate_embeddings([query])[0].tolist())
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, 1 - (embedding <=> %s) FROM document_chunks WHERE id = ANY(%s)",
            (vector, list(ids)),
        ).fetchall()
    return {cid: float(sim) for cid, sim in rows}


def collect(case, drop_stopwords):
    """One retrieval per case and stopword setting; every T is derived from it."""
    q = case["question"]
    vec = semantic_search(q, top_k=cfg.VECTOR_TOP_K, similarity_threshold=None)
    t = time.perf_counter()
    kw = keyword_search(q, cfg.BM25_TOP_K, backend="memory", drop_stopwords=drop_stopwords)
    kw_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    sims = similarities(q, {r[0] for r in vec} | {r[0] for r in kw})
    sim_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    app = hybrid_search_detailed(q, top_k=cfg.FINAL_TOP_K, rerank=False,
                                 keyword_backend="memory", drop_stopwords=drop_stopwords)
    total_ms = (time.perf_counter() - t) * 1000
    return {"vec": vec, "kw": kw, "sims": sims, "app_ids": [r["chunk"][0] for r in app["results"]],
            "kw_ms": kw_ms, "sim_ms": sim_ms, "nogate_total_ms": total_ms}


def final_for(data, threshold, backfill=True):
    """backfill=True gates the RRF pool, then keeps FINAL_TOP_K (removed chunks are replaced);
    backfill=False keeps FINAL_TOP_K, then gates (like rag_service's margin gate: no refill)."""
    vec, kw, sims = data["vec"], data["kw"], data["sims"]
    if threshold is not None:
        vec = [r for r in vec if (1 - r[4]) >= threshold]
    lists = [l for l in (kw, vec) if l]           # same order as hybrid_search_detailed
    pool = reciprocal_rank_fusion(lists, k=cfg.RRF_K, top_k=cfg.RRF_TOP_K)
    if not backfill:
        pool = pool[:cfg.FINAL_TOP_K]
    if threshold is not None:
        pool = [item for item in pool if sims[item["chunk"][0]] >= threshold]
    return assemble_context(pool[:cfg.FINAL_TOP_K])["sources"]


def score_case(case, sources, data):
    gold = {(s["document"], s["page"]) for s in case["gold_sources"]}
    pages = [(s["document_name"], s["page_number"]) for s in sources]
    vec_ids = {r[0] for r in data["vec"]}
    return {
        "id": case["id"], "category": case["category"], "answerable": bool(gold),
        "ids": [s["chunk_id"] for s in sources],
        "gold_flags": [p in gold for p in pages],
        "keyword_only": [s["chunk_id"] not in vec_ids for s in sources],
        "first_gold_rank": next((i for i, p in enumerate(pages, 1) if p in gold), None),
        "metrics": RM.case_metrics(pages, gold, ks=(1, 3, 5)),
    }


def summarize(rows, base_rows):
    ans = [r for r in rows if r["answerable"]]
    noans = [r for r in rows if not r["answerable"]]
    returned = sum(len(r["ids"]) for r in rows)
    gold_returned = sum(sum(r["gold_flags"]) for r in rows)
    agg = RM.aggregate([{"metrics": r["metrics"]} for r in ans])["overall"]
    base = {r["id"]: r for r in base_rows}
    removed = lost = 0
    for r in rows:
        b = base[r["id"]]
        for cid, kwo, g in zip(b["ids"], b["keyword_only"], b["gold_flags"]):
            if kwo and cid not in r["ids"]:
                removed += 1
                lost += int(g)
    return {
        "relevant_retrieval_rate": sum(1 for r in ans if any(r["gold_flags"])) / len(ans),
        "irrelevant_retrieval_rate": (returned - gold_returned) / returned if returned else 0.0,
        "page_recall": agg["page_recall"]["mean"], "recall@5": agg["recall@5"]["mean"],
        "precision@5": agg["precision@5"]["mean"], "mrr": agg["mrr"]["mean"], "ndcg@5": agg["ndcg@5"]["mean"],
        "precision_returned": gold_returned / returned if returned else None,
        "chunks_returned": returned, "irrelevant_chunks": returned - gold_returned,
        "answerable_empty": sum(1 for r in ans if not r["ids"]),
        "no_answer_cases_with_context": sum(1 for r in noans if r["ids"]),
        "no_answer_chunks": sum(len(r["ids"]) for r in noans),
        "keyword_only_returned": sum(sum(r["keyword_only"]) for r in rows),
        "keyword_only_removed_vs_T_none": removed, "relevant_keyword_only_lost_vs_T_none": lost,
    }


def ranking_changes(rows, ref_rows):
    ref = {r["id"]: r for r in ref_rows}
    out = {"order_changed": 0, "set_changed": 0, "first_gold_better": 0, "first_gold_worse": 0}
    for r in rows:
        b = ref[r["id"]]
        out["order_changed"] += r["ids"] != b["ids"]
        out["set_changed"] += set(r["ids"]) != set(b["ids"])
        x, y = r["first_gold_rank"] or 99, b["first_gold_rank"] or 99
        out["first_gold_better"] += x < y
        out["first_gold_worse"] += x > y
    return out


def calibrate(sweep, ans_ids):
    """Largest T with no loss of relevant retrieval (rate and page recall) vs T=None."""
    def ok(rows_t, rows_0, ids):
        for cid in ids:
            a, b = rows_t[cid], rows_0[cid]
            if any(b["gold_flags"]) and not any(a["gold_flags"]):
                return False
            if (a["metrics"]["page_recall"] or 0) < (b["metrics"]["page_recall"] or 0):
                return False
        return True

    by_t = {t: {r["id"]: r for r in rows} for t, rows in sweep.items()}
    base = by_t[None]

    def best(ids):
        return max((t for t in GRID if ok(by_t[t], base, ids)), default=None)

    loo = {cid: best([i for i in ans_ids if i != cid]) for cid in ans_ids}
    first_loss = {t: sorted(cid for cid in ans_ids if not ok(by_t[t], base, [cid])) for t in GRID}
    return {"t_cal": best(ans_ids), "loo_min": min(loo.values()), "loo_max": max(loo.values()),
            "loo_cases_changing_t": sorted(c for c, t in loo.items() if t != best(ans_ids)),
            "cases_losing_relevance_by_t": {str(t): v for t, v in first_loss.items() if v}}


def sim_distribution(dev, collected):
    gold, other = [], []
    for case in dev:
        g = {(s["document"], s["page"]) for s in case["gold_sources"]}
        data = collected[case["id"]]
        pool = {r[0]: r for r in data["vec"] + data["kw"]}
        for cid, row in pool.items():
            (gold if (row[1], row[2]) in g else other).append(data["sims"][cid])

    def q(v):
        v = sorted(v)
        return {"n": len(v), "min": v[0], "p10": v[len(v) // 10], "median": statistics.median(v),
                "p90": v[(9 * len(v)) // 10], "max": v[-1]} if v else {"n": 0}
    return {"gold_page_candidates": q(gold), "other_candidates": q(other)}


def reranked_reference(dev):
    """Default production path: reranked results + rag_service's margin/min-score gate."""
    rows, ms = [], []
    for case in dev:
        t = time.perf_counter()
        res = hybrid_search_detailed(case["question"], top_k=cfg.FINAL_TOP_K, keyword_backend="memory",
                                     drop_stopwords=False)
        ms.append((time.perf_counter() - t) * 1000)
        results = res["results"]
        if results and "rerank_score" in results[0]:      # mirrors services/rag_service.py step 3
            best = results[0]["rerank_score"]
            if cfg.RERANK_MIN_SCORE is not None and best < cfg.RERANK_MIN_SCORE:
                results = []
            results = [i for i in results if i["rerank_score"] >= best - cfg.RERANK_SCORE_MARGIN]
        data = {"vec": semantic_search(case["question"], top_k=cfg.VECTOR_TOP_K, similarity_threshold=None)}
        rows.append(score_case(case, assemble_context(results)["sources"], data))
        rows[-1]["rerank_status"] = res["rerank_status"]
    return rows, statistics.median(ms)


def run_setting(dev, drop_stopwords):
    hybrid_search_detailed("warm up", rerank=False, drop_stopwords=drop_stopwords)
    collected = {c["id"]: collect(c, drop_stopwords) for c in dev}
    sweeps = {}
    for backfill in (True, False):
        sweeps[backfill] = {t: [score_case(c, final_for(collected[c["id"]], t, backfill), collected[c["id"]])
                                for c in dev] for t in [None] + GRID}
    mismatches = [c["id"] for c, r in zip(dev, sweeps[True][None]) if r["ids"] != collected[c["id"]]["app_ids"]]
    return collected, sweeps, mismatches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--no-ingest", action="store_true")
    args = ap.parse_args()

    dev, chunks = prepare(args.no_ingest)
    ans_ids = [c["id"] for c in dev if c["gold_sources"]]
    report = {"database": SCRATCH_DB, "chunks": chunks, "dev_cases": len(dev), "answerable": len(ans_ids),
              "config": {k: getattr(cfg, k) for k in ("VECTOR_TOP_K", "BM25_TOP_K", "RRF_K", "RRF_TOP_K",
                                                      "FINAL_TOP_K", "CONTEXT_MAX_CHUNKS", "RERANK_SCORE_MARGIN",
                                                      "RERANK_MIN_SCORE", "SIMILARITY_THRESHOLD",
                                                      "BM25_DROP_STOPWORDS", "BM25_BACKEND", "EMBEDDING_MODEL")},
              "grid": GRID, "settings": {}}
    sweeps = {}
    for sw in (False, True):
        collected, both, mismatches = run_setting(dev, sw)
        sweep = sweeps[sw] = both[True]
        report["settings"][f"drop_stopwords={sw}"] = {
            "simulation_mismatches_vs_app": mismatches,
            "summary_by_T": {str(t): summarize(rows, sweep[None]) for t, rows in sweep.items()},
            "calibration": calibrate(sweep, ans_ids),
            "no_backfill": {
                "summary_by_T": {str(t): summarize(rows, both[False][None]) for t, rows in both[False].items()},
                "calibration": calibrate(both[False], ans_ids),
                "ranking_vs_E_by_T": {str(t): ranking_changes(rows, both[False][None])
                                      for t, rows in both[False].items()}},
            "similarity_distribution": sim_distribution(dev, collected),
            "latency_ms_median": {k: statistics.median(d[k] for d in collected.values())
                                  for k in ("kw_ms", "sim_ms", "nogate_total_ms")},
            "keyword_lists_changed_vs_stopwords_off": None,
        }
        report["settings"][f"drop_stopwords={sw}"]["ranking_vs_E_by_T"] = {
            str(t): ranking_changes(rows, sweeps[False][None]) for t, rows in sweep.items()}
        report["settings"][f"drop_stopwords={sw}"]["_kw"] = {c: [r[0] for r in d["kw"]] for c, d in collected.items()}
    off, on = (report["settings"][f"drop_stopwords={s}"].pop("_kw") for s in (False, True))
    report["settings"]["drop_stopwords=True"]["keyword_lists_changed_vs_stopwords_off"] = {
        "order": sum(off[c] != on[c] for c in off), "set": sum(set(off[c]) != set(on[c]) for c in off)}
    ref_rows, ref_ms = reranked_reference(dev)
    report["reranked_reference"] = {"summary": summarize(ref_rows, ref_rows), "latency_ms_median": ref_ms,
                                    "rerank_status": sorted({r["rerank_status"] for r in ref_rows}),
                                    "ranking_vs_E": ranking_changes(ref_rows, sweeps[False][None])}
    report["per_case_E"] = [{k: r[k] for k in ("id", "category", "ids", "gold_flags", "keyword_only")}
                            for r in sweeps[False][None]]
    with open(args.output, "x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    print(f"written {args.output}")


if __name__ == "__main__":
    main()
