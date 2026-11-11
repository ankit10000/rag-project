"""
Phase 2 benchmark. Usage (from the project root):

    .venv\\Scripts\\python.exe eval\\run_benchmark.py [configs|chunking|noanswer|all]

Runs only against the scratch database rag_phase2_eval.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval import harness  # noqa: E402

harness.use_scratch_database()

from eval.corpus import DOCS as CORE_DOCS, QUERIES, make_distractors  # noqa: E402

N_DISTRACTORS = int(os.getenv("EVAL_DISTRACTORS", "120"))
DOCS = {**CORE_DOCS, **make_distractors(N_DISTRACTORS)}
from services import retrieval_config as cfg  # noqa: E402
from services.chunker import chunk_page  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402
from services.hybrid_search_service import hybrid_search_detailed  # noqa: E402

K = 5
REPEATS = 2
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

ANSWERABLE = [q for q in QUERIES if q[2]]
NOANSWER = [q for q in QUERIES if not q[2]]

CONFIGS = {
    "A vector": dict(use_keyword=False, rerank=False),
    "B bm25": dict(use_vector=False, rerank=False),
    "C vector+bm25 (interleave)": dict(fusion="interleave", rerank=False),
    "D vector+bm25+RRF": dict(rerank=False),
    "E vector+bm25+RRF+rerank": dict(rerank=True),
}

VARIANTS = {
    "B3 bm25 + stopwords removed": dict(use_vector=False, rerank=False, drop_stopwords=True),
    "D3 RRF, bm25 stopwords removed": dict(rerank=False, drop_stopwords=True),
    "E3 RRF(stopwords removed)+rerank": dict(rerank=True, drop_stopwords=True),
    "E3 pool=5 (stopwords removed)": dict(rerank=True, rerank_top_k=5, drop_stopwords=True),
    "B2 postgres FTS": dict(use_vector=False, rerank=False, keyword_backend="fts"),
    "D2 RRF with FTS": dict(rerank=False, keyword_backend="fts"),
    "E2 RRF(FTS)+rerank": dict(rerank=True, keyword_backend="fts"),
    "D k=10": dict(rerank=False, rrf_k=10),
    "D k=30": dict(rerank=False, rrf_k=30),
    "E pool=5": dict(rerank=True, rerank_top_k=5),
    "E pool=20": dict(rerank=True, rerank_top_k=20, rrf_top_k=20, vector_top_k=20, keyword_top_k=20),
}


def run_config(name, kwargs, queries=ANSWERABLE, k=K):
    per_query = []
    stage_ms = {}
    totals = []

    for query, kind, gold, doc_filter in queries:
        scope = [doc_filter] if doc_filter else None
        runs = []

        for _ in range(REPEATS):
            out = hybrid_search_detailed(
                query, k, document_names=scope, **kwargs
            )
            runs.append(out)

        chunks = [r["chunk"] for r in runs[0]["results"]]
        metrics = harness.score_query(chunks, gold, k)
        metrics.update(kind=kind, query=query)
        per_query.append(metrics)

        totals.append(harness.median([r["timings_ms"]["total"] for r in runs]))
        for stage in ("vector", "keyword", "fusion", "rerank"):
            values = [r["timings_ms"][stage] for r in runs if stage in r["timings_ms"]]
            if values:
                stage_ms.setdefault(stage, []).append(harness.median(values))

    by_kind = {}
    for m in per_query:
        by_kind.setdefault(m["kind"], []).append(m["recall"])

    return {
        "config": name,
        "queries": len(per_query),
        "recall": harness.mean([m["recall"] for m in per_query]),
        "precision": harness.mean([m["precision"] for m in per_query]),
        "mrr": harness.mean([m["mrr"] for m in per_query]),
        "ndcg": harness.mean([m["ndcg"] for m in per_query]),
        "hit1": harness.mean([m["hit1"] for m in per_query]),
        "latency_ms_median": harness.median(totals),
        "latency_ms_p95": harness.pct(totals, 95),
        "stage_ms_median": {s: harness.median(v) for s, v in stage_ms.items()},
        "recall_by_kind": {k_: harness.mean(v) for k_, v in by_kind.items()},
        "failures": [
            m["query"] for m in per_query if m["recall"] < 1.0
        ],
    }


def print_table(rows):
    print(f"\n| Configuration | Recall@{K} | Precision@{K} | MRR | nDCG@{K} | Hit@1 | "
          f"median ms | p95 ms | rerank ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        rerank = r["stage_ms_median"].get("rerank")
        print(
            f"| {r['config']} | {r['recall']:.3f} | {r['precision']:.3f} | {r['mrr']:.3f} | "
            f"{r['ndcg']:.3f} | {r['hit1']:.3f} | {r['latency_ms_median']:.1f} | "
            f"{r['latency_ms_p95']:.1f} | {'-' if rerank is None else f'{rerank:.1f}'} |"
        )


def warm_up():
    hybrid_search_detailed("warm up query", 3, rerank=True)
    hybrid_search_detailed("warm up query", 3, rerank=True, keyword_backend="fts")


def section_configs():
    chunks = harness.load_corpus(
        DOCS,
        lambda t: chunk_page(t, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP, cfg.CHUNK_STRATEGY),
        generate_embeddings,
    )
    print(f"Corpus loaded: {len(DOCS)} documents, {chunks} chunks "
          f"(strategy={cfg.CHUNK_STRATEGY}, size={cfg.CHUNK_SIZE}, overlap={cfg.CHUNK_OVERLAP})")
    warm_up()

    main_rows = [run_config(n, kw) for n, kw in CONFIGS.items()]
    var_rows = [run_config(n, kw) for n, kw in VARIANTS.items()]

    print("\n### Main configurations A-E")
    print_table(main_rows)
    print("\n### Variants")
    print_table(var_rows)

    print("\n### Recall by query kind")
    kinds = sorted({q[1] for q in ANSWERABLE})
    print("| Configuration | " + " | ".join(kinds) + " |")
    print("|---|" + "---|" * len(kinds))
    for r in main_rows + var_rows:
        print(f"| {r['config']} | " + " | ".join(
            f"{r['recall_by_kind'].get(k_, float('nan')):.2f}" for k_ in kinds) + " |")

    print("\n### Queries with recall < 1")
    for r in main_rows + var_rows:
        print(f"- {r['config']}: {r['failures']}")

    with open(os.path.join(RESULTS_DIR, "configs.json"), "w") as f:
        json.dump({"main": main_rows, "variants": var_rows}, f, indent=2)


CHUNKINGS = [
    ("words 100/20 (current)", dict(size=100, overlap=20, strategy="words")),
    ("words 50/10", dict(size=50, overlap=10, strategy="words")),
    ("words 60/0 (no overlap)", dict(size=60, overlap=0, strategy="words")),
    ("words 150/30", dict(size=150, overlap=30, strategy="words")),
    ("words 200/40", dict(size=200, overlap=40, strategy="words")),
    ("sentences 60/15", dict(size=60, overlap=15, strategy="sentences")),
    ("sentences 100/20", dict(size=100, overlap=20, strategy="sentences")),
    ("sentences 150/30", dict(size=150, overlap=30, strategy="sentences")),
]


def section_chunking():
    rows = []
    for name, spec in CHUNKINGS:
        n = harness.load_corpus(
            DOCS,
            lambda t, s=spec: chunk_page(t, s["size"], s["overlap"], s["strategy"]),
            generate_embeddings,
        )
        for label, kw in (("D", CONFIGS["D vector+bm25+RRF"]), ("E", CONFIGS["E vector+bm25+RRF+rerank"])):
            r = run_config(f"{name} [{label}] chunks={n}", kw)
            rows.append(r)

    print("\n### Chunking comparison (D = RRF, E = RRF+rerank)")
    print_table(rows)
    with open(os.path.join(RESULTS_DIR, "chunking.json"), "w") as f:
        json.dump(rows, f, indent=2)


def section_noanswer():
    harness.load_corpus(
        DOCS,
        lambda t: chunk_page(t, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP, cfg.CHUNK_STRATEGY),
        generate_embeddings,
    )
    warm_up()

    def clean(queries):
        sims, rr = [], []
        for query, _, _, _ in queries:
            vec = hybrid_search_detailed(query, 1, use_keyword=False, rerank=False)
            sims.append(1 - vec["results"][0]["chunk"][4])
            out = hybrid_search_detailed(query, K, rerank=True)
            rr.append(out["results"][0]["rerank_score"])
        return sims, rr

    a_sim, a_rr = clean(ANSWERABLE)
    n_sim, n_rr = clean(NOANSWER)

    def summary(name, ans, no):
        print(f"- {name}: answerable min={min(ans):.3f} p10={harness.pct(ans,10):.3f} "
              f"median={harness.median(ans):.3f}; no-answer max={max(no):.3f} "
              f"median={harness.median(no):.3f}")
        best = None
        for t in sorted(set(ans + no)):
            tp = sum(1 for v in ans if v >= t) / len(ans)
            tn = sum(1 for v in no if v < t) / len(no)
            score = tp + tn
            if best is None or score > best[0]:
                best = (score, t, tp, tn)
        print(f"  best single threshold {best[1]:.3f}: keeps {best[2]*100:.0f}% of answerable, "
              f"rejects {best[3]*100:.0f}% of no-answer")
        return {"threshold": best[1], "answerable_kept": best[2], "noanswer_rejected": best[3]}

    print("\n### No-answer separation (top-1 score)")
    res = {
        "vector_similarity": summary("vector cosine similarity", a_sim, n_sim),
        "rerank_score": summary("cross-encoder score", a_rr, n_rr),
    }
    print("  no-answer queries:", [q[0] for q in NOANSWER])
    with open(os.path.join(RESULTS_DIR, "noanswer.json"), "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    if which in ("configs", "all"):
        section_configs()
    if which in ("chunking", "all"):
        section_chunking()
    if which in ("noanswer", "all"):
        section_noanswer()
    print(f"\n(done in {time.time() - t0:.0f}s)")
