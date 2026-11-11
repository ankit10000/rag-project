"""
Phase 2.5 workstreams A, D, E (scratch DB rag_phase2_eval only).

    .venv\\Scripts\\python.exe eval\\phase25_ab.py main  [--seed 7]   # A + D: configs, latency (takes the bench lock)
    .venv\\Scripts\\python.exe eval\\phase25_ab.py lost  [--seed 7]   # E: vector-only hit lost from RRF top 5 (no latency)

Quality metrics are deterministic; latency is only recorded in `main`.
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval import harness  # noqa: E402

harness.use_scratch_database()

from eval.corpus import DOCS as CORE_DOCS, QUERIES, make_distractors  # noqa: E402
from services import retrieval_config as cfg  # noqa: E402
from services.chunker import chunk_page  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402
from services.hybrid_search_service import hybrid_search_detailed, keyword_search  # noqa: E402
from services.search_service import semantic_search  # noqa: E402
from services.rrf_service import reciprocal_rank_fusion  # noqa: E402
from services.reranker_service import rerank_results  # noqa: E402

K = 5
REPEATS = 2
N_DISTRACTORS = 120
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
LOCK = os.path.join(RESULTS_DIR, ".bench.lock")
ANSWERABLE = [q for q in QUERIES if q[2]]

CONFIGS = {
    "A vector": dict(use_keyword=False, rerank=False),
    "B bm25": dict(use_vector=False, rerank=False),
    "C interleave": dict(fusion="interleave", rerank=False),
    "D RRF (k=60)": dict(rerank=False),
    "E RRF+rerank (pool 10)": dict(rerank=True),
    # RRF k
    "D k=10": dict(rerank=False, rrf_k=10),
    "D k=30": dict(rerank=False, rrf_k=30),
    "D k=100": dict(rerank=False, rrf_k=100),
    "E k=10": dict(rerank=True, rrf_k=10),
    "E k=30": dict(rerank=True, rrf_k=30),
    "E k=100": dict(rerank=True, rrf_k=100),
    # rerank pool
    "E pool=5": dict(rerank=True, rerank_top_k=5),
    "E pool=20 (fused 20, lists 10)": dict(rerank=True, rerank_top_k=20, rrf_top_k=20),
    "E pool=20 (lists 20)": dict(rerank=True, rerank_top_k=20, rrf_top_k=20,
                                  vector_top_k=20, keyword_top_k=20),
    # FTS
    "B2 postgres FTS": dict(use_vector=False, rerank=False, keyword_backend="fts"),
    "D2 RRF + FTS": dict(rerank=False, keyword_backend="fts"),
    "E2 RRF(FTS)+rerank": dict(rerank=True, keyword_backend="fts"),
    # stopwords (workstream D)
    "B3 bm25 stopwords removed": dict(use_vector=False, rerank=False, drop_stopwords=True),
    "D3 RRF stopwords removed": dict(rerank=False, drop_stopwords=True),
    "E3 rerank stopwords removed": dict(rerank=True, drop_stopwords=True),
    "E3 pool=5 stopwords removed": dict(rerank=True, rerank_top_k=5, drop_stopwords=True),
}

# Pre-IDF-fix figures supplied with the task (recall, mrr, ndcg). HISTORICAL.
HIST = {
    "A vector": (0.842, 0.785, 0.776),
    "B bm25": (0.921, 0.908, 0.888),
    "C interleave": (0.974, 0.922, 0.914),
    "D RRF (k=60)": (0.974, 0.889, 0.890),
    "E RRF+rerank (pool 10)": (0.947, 0.926, 0.911),
    "E pool=5": (0.974, 0.939, 0.927),
    "B2 postgres FTS": (0.803, 0.734, 0.724),
}


# ------------------------------------------------------------------ lock ---
def acquire_lock():
    while True:
        try:
            with open(LOCK, "x") as f:
                f.write(f"phase25_AD_E pid={os.getpid()} t={time.time()}\n")
            return
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > 1800:
                    os.remove(LOCK)
                    continue
            except OSError:
                pass
            time.sleep(10)


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


# ---------------------------------------------------------------- helpers ---
def load(seed):
    docs = {**CORE_DOCS, **make_distractors(N_DISTRACTORS, seed=seed)}
    n = harness.load_corpus(
        docs,
        lambda t: chunk_page(t, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP, cfg.CHUNK_STRATEGY),
        generate_embeddings,
    )
    print(f"Corpus: seed={seed} docs={len(docs)} chunks={n} "
          f"(strategy={cfg.CHUNK_STRATEGY} {cfg.CHUNK_SIZE}/{cfg.CHUNK_OVERLAP}) K={K}", flush=True)
    return n, len(docs)


def bootstrap_ci(values, n=1000, seed=12345):
    rng = random.Random(seed)
    m = len(values)
    means = sorted(sum(values[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def paired_ci(a, b, n=1000, seed=12345):
    return bootstrap_ci([x - y for x, y in zip(a, b)], n, seed)


def run_config(kwargs):
    per_query, totals, stage = [], [], {}
    for query, kind, gold, doc_filter in ANSWERABLE:
        scope = [doc_filter] if doc_filter else None
        runs = [hybrid_search_detailed(query, K, document_names=scope, **kwargs)
                for _ in range(REPEATS)]
        chunks = [r["chunk"] for r in runs[0]["results"]]
        m = harness.score_query(chunks, gold, K)
        m.update(kind=kind, query=query, top=[c[0] for c in chunks])
        per_query.append(m)
        totals.append(harness.median([r["timings_ms"]["total"] for r in runs]))
        for s in ("vector", "keyword", "fusion", "rerank"):
            vals = [r["timings_ms"][s] for r in runs if s in r["timings_ms"]]
            if vals:
                stage.setdefault(s, []).append(harness.median(vals))
    by_kind = {}
    for m in per_query:
        by_kind.setdefault(m["kind"], []).append(m["recall"])
    return {
        "recall": harness.mean([m["recall"] for m in per_query]),
        "precision": harness.mean([m["precision"] for m in per_query]),
        "mrr": harness.mean([m["mrr"] for m in per_query]),
        "ndcg": harness.mean([m["ndcg"] for m in per_query]),
        "hit1": harness.mean([m["hit1"] for m in per_query]),
        "lat_med": harness.median(totals),
        "lat_p95": harness.pct(totals, 95),
        "rerank_ms": harness.median(stage["rerank"]) if "rerank" in stage else None,
        "by_kind": {k: harness.mean(v) for k, v in by_kind.items()},
        "per_query": per_query,
    }


def warm_up():
    hybrid_search_detailed("warm up query", 3, rerank=True)
    hybrid_search_detailed("warm up query", 3, rerank=True, keyword_backend="fts")
    hybrid_search_detailed("warm up query", 3, rerank=True, drop_stopwords=True)


def section_main(seed):
    n_chunks, n_docs = load(seed)
    warm_up()
    quick = "--quick" in sys.argv   # quality-only: 1 repeat, no lock, latency not meaningful
    global REPEATS
    if quick:
        REPEATS = 1
    else:
        acquire_lock()
    t0 = time.time()
    try:
        results = {}
        for name, kw in CONFIGS.items():
            results[name] = run_config(kw)
            print(f"  done {name} ({time.time() - t0:.0f}s)", flush=True)
    finally:
        if not quick:
            release_lock()

    out = {"seed": seed, "chunks": n_chunks, "docs": n_docs, "K": K, "repeats": REPEATS,
           "results": results}
    for name, r in results.items():
        r["recall_ci"] = bootstrap_ci([m["recall"] for m in r["per_query"]])
        r["mrr_ci"] = bootstrap_ci([m["mrr"] for m in r["per_query"]])
    with open(os.path.join(RESULTS_DIR, f"phase25_main_seed{seed}{'_quick' if quick else ''}.json"), "w") as f:
        json.dump(out, f, indent=1)

    # ---- tables
    print(f"\n#### Main table (seed {seed}, {n_chunks} chunks, 38 queries)")
    print("| Config | R@5 | P@5 | MRR | nDCG@5 | Hit@1 | med ms | p95 ms | rerank ms | "
          "pre-IDF R/MRR/nDCG | delta R/MRR/nDCG |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, r in results.items():
        h = HIST.get(name)
        hs = f"{h[0]:.3f}/{h[1]:.3f}/{h[2]:.3f}" if h else "-"
        ds = (f"{r['recall']-h[0]:+.3f}/{r['mrr']-h[1]:+.3f}/{r['ndcg']-h[2]:+.3f}") if h else "-"
        rr = "-" if r["rerank_ms"] is None else f"{r['rerank_ms']:.0f}"
        print(f"| {name} | {r['recall']:.3f} | {r['precision']:.3f} | {r['mrr']:.3f} | "
              f"{r['ndcg']:.3f} | {r['hit1']:.3f} | {r['lat_med']:.0f} | {r['lat_p95']:.0f} | "
              f"{rr} | {hs} | {ds} |")

    print("\n#### Bootstrap 95% CI (1000 resamples, seed 12345)")
    print("| Config | Recall@5 [CI] | MRR [CI] |")
    print("|---|---|---|")
    for name, r in results.items():
        print(f"| {name} | {r['recall']:.3f} [{r['recall_ci'][0]:.3f}, {r['recall_ci'][1]:.3f}] | "
              f"{r['mrr']:.3f} [{r['mrr_ci'][0]:.3f}, {r['mrr_ci'][1]:.3f}] |")

    kinds = sorted({q[1] for q in ANSWERABLE})
    print("\n#### Recall@5 by kind (counts: " + ", ".join(
        f"{k}={sum(1 for q in ANSWERABLE if q[1] == k)}" for k in kinds) + ")")
    print("| Config | " + " | ".join(kinds) + " |")
    print("|---|" + "---|" * len(kinds))
    for name, r in results.items():
        print(f"| {name} | " + " | ".join(f"{r['by_kind'].get(k, float('nan')):.2f}" for k in kinds) + " |")

    pairs = [
        ("B bm25", "D RRF (k=60)"), ("A vector", "D RRF (k=60)"), ("C interleave", "D RRF (k=60)"),
        ("D RRF (k=60)", "E RRF+rerank (pool 10)"), ("E RRF+rerank (pool 10)", "E pool=5"),
        ("E RRF+rerank (pool 10)", "E pool=20 (fused 20, lists 10)"),
        ("D RRF (k=60)", "D k=10"), ("D RRF (k=60)", "D k=100"),
        ("B bm25", "B3 bm25 stopwords removed"), ("D RRF (k=60)", "D3 RRF stopwords removed"),
        ("E RRF+rerank (pool 10)", "E3 rerank stopwords removed"),
        ("B bm25", "B2 postgres FTS"), ("D RRF (k=60)", "D2 RRF + FTS"),
    ]
    print("\n#### Paired per-query changes (first -> second; recall/mrr deltas; bootstrap CI of mean MRR delta)")
    for a, b in pairs:
        ra, rb = results[a]["per_query"], results[b]["per_query"]
        diffs = []
        for x, y in zip(ra, rb):
            if abs(x["recall"] - y["recall"]) > 1e-9 or abs(x["mrr"] - y["mrr"]) > 1e-9:
                diffs.append(f"    - `{x['query']}` [{x['kind']}]: recall {x['recall']:.2f}->{y['recall']:.2f}, "
                             f"MRR {x['mrr']:.2f}->{y['mrr']:.2f}")
        lo, hi = paired_ci([m["mrr"] for m in rb], [m["mrr"] for m in ra])
        rlo, rhi = paired_ci([m["recall"] for m in rb], [m["recall"] for m in ra])
        print(f"- {a} -> {b}: {len(diffs)} queries changed; dRecall CI [{rlo:+.3f},{rhi:+.3f}], "
              f"dMRR CI [{lo:+.3f},{hi:+.3f}]")
        print("\n".join(diffs))

    print("\n#### Queries with recall < 1")
    for name, r in results.items():
        print(f"- {name}: {[m['query'] for m in r['per_query'] if m['recall'] < 1]}")


# -------------------------------------------------------------- workstream E ---
def gather(seed):
    """Cache raw candidate lists (top 20) per query."""
    cache = {}
    for query, kind, gold, doc_filter in ANSWERABLE:
        scope = [doc_filter] if doc_filter else None
        cache[query] = {
            "vec": semantic_search(query, top_k=20, document_names=scope),
            "kw": keyword_search(query, 20, scope, None, "memory", False),
            "kw_sw": keyword_search(query, 20, scope, None, "memory", True),
        }
    return cache


_rr_cache = {}


def rerank_scores(query, items):
    need = [it for it in items if (query, it["chunk"][0]) not in _rr_cache]
    if need:
        out = rerank_results(query, need, top_k=len(need))
        for o in out:
            _rr_cache[(query, o["chunk"][0])] = o["rerank_score"]
    return [{**it, "rerank_score": _rr_cache[(query, it["chunk"][0])]} for it in items]


def fuse(c, kw_key="kw", k=60, weights=(1.0, 1.0), kw_frac=None, vec_n=10, kw_n=10, pool=10):
    kw = c[kw_key][:kw_n]
    if kw_frac is not None and kw:
        best = kw[0][4]
        kw = [x for x in kw if x[4] >= kw_frac * best]
    vec = c["vec"][:vec_n]
    return reciprocal_rank_fusion([kw, vec], k=k, top_k=pool, weights=list(weights))


def eval_variant(cache, name, rerank_pool=None, **fkw):
    per = []
    for query, kind, gold, doc_filter in ANSWERABLE:
        fused = fuse(cache[query], **fkw)
        if rerank_pool:
            res = rerank_scores(query, fused[:rerank_pool])
            res = sorted(res, key=lambda x: x["rerank_score"], reverse=True)
        else:
            res = fused
        chunks = [r["chunk"] for r in res[:K]]
        m = harness.score_query(chunks, gold, K)
        m.update(kind=kind, query=query)
        per.append(m)
    return {"name": name, "per_query": per,
            "recall": harness.mean([m["recall"] for m in per]),
            "mrr": harness.mean([m["mrr"] for m in per]),
            "ndcg": harness.mean([m["ndcg"] for m in per]),
            "hit1": harness.mean([m["hit1"] for m in per])}


def rank_of(lst, gold_item):
    for i, c in enumerate(lst, start=1):
        if harness.covers(c, gold_item):
            return i
    return None


def section_lost(seed):
    n_chunks, _ = load(seed)
    cache = gather(seed)

    print(f"\n### Vector-hit-lost analysis (seed {seed}, default k=60, lists of 10, fused top 10)")
    lost = []
    for query, kind, gold, doc_filter in ANSWERABLE:
        c = cache[query]
        vec10, kw10 = c["vec"][:10], c["kw"][:10]
        fused = reciprocal_rank_fusion([kw10, vec10], k=60, top_k=10)
        fl = [f["chunk"] for f in fused]
        for gi, g in enumerate(gold):
            rv, rk, rf = rank_of(vec10, g), rank_of(kw10, g), rank_of(fl, g)
            if rv is not None and (rf is None or rf > K):
                score = None
                if rf is not None:
                    score = fused[rf - 1]["rrf_score"]
                lost.append({
                    "query": query, "kind": kind, "gold": g[1][:40], "vec_rank": rv,
                    "kw_rank": rk, "fused_rank": rf, "rrf_score": score,
                    "in_pool10": rf is not None,
                    "displacers": [{"doc": f["chunk"][1], "rrf": round(f["rrf_score"], 5),
                                    "vec": rank_of([f["chunk"]], g) and None,
                                    "vec_rank": next((i for i, x in enumerate(vec10, 1) if x[0] == f["chunk"][0]), None),
                                    "kw_rank": next((i for i, x in enumerate(kw10, 1) if x[0] == f["chunk"][0]), None),
                                    "gold_other": any(harness.covers(f["chunk"], gg) for gg in gold)}
                                   for f in fused[:K]],
                })
    print(f"Gold items in vector top-10 but not in fused top-5: {len(lost)}")
    for l in lost:
        dis = "; ".join(f"{d['doc']}(rrf {d['rrf']}, v{d['vec_rank']}, k{d['kw_rank']})" for d in l["displacers"])
        print(f"- `{l['query']}` [{l['kind']}] gold={l['gold']}: vec rank {l['vec_rank']}, "
              f"kw rank {l['kw_rank']}, fused rank {l['fused_rank']}"
              f"{'' if l['rrf_score'] is None else f' (rrf {l['rrf_score']:.5f})'}, "
              f"in pool10={l['in_pool10']}; top5: {dis}")
    vec5_lost = [l for l in lost if l["vec_rank"] <= 5]
    print(f"Of which vector rank<=5: {len(vec5_lost)}")

    # all fused ranks incl. what rerank does to them
    print("\n### Interventions (all 38 queries; D = fused top 5, E = rerank of fused top-pool)")
    base = {}
    variants = []

    def add(name, **kw):
        variants.append((name, kw))

    add("baseline D (k=60, w=[1,1])")
    add("w=[1,1.5] (kw,vec)", weights=(1.0, 1.5))
    add("w=[1,2]", weights=(1.0, 2.0))
    add("w=[0.5,1]", weights=(0.5, 1.0))
    add("stopwords removed", kw_key="kw_sw")
    add("stopwords + w=[1,1.5]", kw_key="kw_sw", weights=(1.0, 1.5))
    add("kw filter >=0.3*best", kw_frac=0.3)
    add("kw filter >=0.5*best", kw_frac=0.5)
    add("kw filter >=0.7*best", kw_frac=0.7)
    add("kw filter 0.5 + w=[1,1.5]", kw_frac=0.5, weights=(1.0, 1.5))
    add("k=10", k=10)
    add("k=30", k=30)
    add("k=100", k=100)

    rows = []
    for name, kw in variants:
        d = eval_variant(cache, "D " + name, pool=10, **kw)
        rows.append(d)
    base_d = rows[0]
    print("\nD (no rerank): fused top 5")
    print("| Variant | R@5 | MRR | nDCG | Hit@1 | fixed (queries recall/MRR up) | hurt | dRecall CI | dMRR CI |")
    print("|---|---|---|---|---|---|---|---|---|")

    def cmp_rows(base, r):
        fixed, hurt = [], []
        for x, y in zip(base["per_query"], r["per_query"]):
            up = (y["recall"] - x["recall"]) + (y["mrr"] - x["mrr"])
            if y["recall"] > x["recall"] + 1e-9 or (y["recall"] >= x["recall"] - 1e-9 and y["mrr"] > x["mrr"] + 1e-9):
                fixed.append(x["query"])
            elif y["recall"] < x["recall"] - 1e-9 or y["mrr"] < x["mrr"] - 1e-9:
                hurt.append(x["query"])
        rlo, rhi = paired_ci([m["recall"] for m in r["per_query"]], [m["recall"] for m in base["per_query"]])
        mlo, mhi = paired_ci([m["mrr"] for m in r["per_query"]], [m["mrr"] for m in base["per_query"]])
        return fixed, hurt, (rlo, rhi), (mlo, mhi)

    detail = []
    for r in rows:
        fixed, hurt, rc, mc = cmp_rows(base_d, r)
        print(f"| {r['name']} | {r['recall']:.3f} | {r['mrr']:.3f} | {r['ndcg']:.3f} | {r['hit1']:.3f} | "
              f"{len(fixed)} | {len(hurt)} | [{rc[0]:+.3f},{rc[1]:+.3f}] | [{mc[0]:+.3f},{mc[1]:+.3f}] |")
        detail.append((r["name"], fixed, hurt))
    for n, f, h in detail[1:]:
        print(f"- {n}: improved {f}; worsened {h}")

    print("\nE (cross-encoder rerank over fused top-pool)")
    erows = []
    for pool in (5, 10, 20):
        for name, kw in variants:
            if "k=" in name and pool != 10:
                continue
            kw2 = dict(kw)
            if pool == 20:
                kw2.update(pool=20)
            else:
                kw2.update(pool=pool)
            erows.append(eval_variant(cache, f"E pool={pool} " + name, rerank_pool=pool, **kw2))
    # pool 20 with lists of 20
    for name, kw in variants[:7]:
        kw2 = dict(kw)
        kw2.update(pool=20, vec_n=20, kw_n=20)
        erows.append(eval_variant(cache, "E pool=20 lists=20 " + name, rerank_pool=20, **kw2))
    base_e = next(r for r in erows if r["name"].startswith("E pool=10 baseline"))
    print("| Variant | R@5 | MRR | nDCG | Hit@1 | improved | worsened | dRecall CI | dMRR CI |")
    print("|---|---|---|---|---|---|---|---|---|")
    edetail = []
    for r in erows:
        fixed, hurt, rc, mc = cmp_rows(base_e, r)
        print(f"| {r['name']} | {r['recall']:.3f} | {r['mrr']:.3f} | {r['ndcg']:.3f} | {r['hit1']:.3f} | "
              f"{len(fixed)} | {len(hurt)} | [{rc[0]:+.3f},{rc[1]:+.3f}] | [{mc[0]:+.3f},{mc[1]:+.3f}] |")
        edetail.append((r["name"], fixed, hurt))
    for n, f, h in edetail:
        if f or h:
            print(f"- {n}: improved {f}; worsened {h}")

    with open(os.path.join(RESULTS_DIR, f"phase25_lost_seed{seed}.json"), "w") as f:
        json.dump({"seed": seed, "lost": lost,
                   "D": [{k: v for k, v in r.items()} for r in rows],
                   "E": [{k: v for k, v in r.items()} for r in erows]}, f, indent=1, default=str)


if __name__ == "__main__":
    which = sys.argv[1]
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 7
    t = time.time()
    {"main": section_main, "lost": section_lost}[which](seed)
    print(f"\n(done in {time.time() - t:.0f}s)")
