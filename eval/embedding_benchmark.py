"""
Phase 2.5 / Workstream C: compare 384-d embedding models on the Phase 2 eval set.
SCRATCH DATABASE ONLY (rag_phase2_emb). Nothing in rag_db is read or written and no
service code or default is modified; the query-side embedder is monkey-patched in
this process only.

    .venv\\Scripts\\python.exe eval\\embedding_benchmark.py            (all models)
    .venv\\Scripts\\python.exe eval\\embedding_benchmark.py --fresh    (ignore cached per-model json)

Per-model results are cached in eval/results/phase25_C_cache/<model>.json and a
combined eval/results/phase25_C_embeddings.json is written. Report tables are
printed to stdout. Latency is measured under a file lock (eval/results/.bench.lock)
so it does not overlap with other benchmark workstreams.
"""
import json
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eval import harness  # noqa: E402

harness.use_scratch_database("rag_phase2_emb")

import numpy as np  # noqa: E402
from pgvector import Vector  # noqa: E402

from eval.corpus import DOCS as CORE_DOCS, QUERIES, make_distractors  # noqa: E402
from services import retrieval_config as cfg  # noqa: E402
from services import search_service  # noqa: E402
from services.chunker import chunk_page  # noqa: E402
from services.database import get_connection  # noqa: E402
from services.hybrid_search_service import hybrid_search_detailed  # noqa: E402

DOCS = {**CORE_DOCS, **make_distractors(120)}
ANSWERABLE = [q for q in QUERIES if q[2]]
K = 5
RESULTS_DIR = os.path.join(ROOT, "eval", "results")
CACHE_DIR = os.path.join(RESULTS_DIR, "phase25_C_cache")
LOCK = os.path.join(RESULTS_DIR, ".bench.lock")
os.makedirs(CACHE_DIR, exist_ok=True)

BGE_PREFIX = "Represent this sentence for searching relevant passages: "
# (hf name, query prefix, passage prefix)
MODELS = [
    ("sentence-transformers/all-MiniLM-L6-v2", "", ""),             # production baseline
    ("sentence-transformers/multi-qa-MiniLM-L6-cos-v1", "", ""),
    ("BAAI/bge-small-en-v1.5", BGE_PREFIX, ""),
    ("intfloat/e5-small-v2", "query: ", "passage: "),
    ("sentence-transformers/all-MiniLM-L12-v2", "", ""),
    ("thenlper/gte-small", "", ""),
]
BASELINE = MODELS[0][0]
KINDS = ["semantic", "keyword", "abbrev", "multi", "metadata", "short"]


# ------------------------------------------------------------------- lock ---
def acquire_lock(timeout=1800):
    start = time.time()
    while True:
        try:
            if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) > 1800:
                try:
                    os.remove(LOCK)   # stale
                except OSError:
                    pass
            with open(LOCK, "x") as f:
                f.write(f"phase25_C pid={os.getpid()} t={time.time()}\n")
            return
        except FileExistsError:
            if time.time() - start > timeout:
                raise RuntimeError("could not acquire bench lock")
            print("  waiting for .bench.lock ...", flush=True)
            time.sleep(10)


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


# ---------------------------------------------------------------- helpers ---
def hf_cache_size(name):
    """(whole repo cache bytes, weights-file bytes) from the HF hub cache.
    On Windows without symlinks the snapshot holds real files and blobs/ is empty."""
    from huggingface_hub.constants import HF_HUB_CACHE
    d = os.path.join(HF_HUB_CACHE, "models--" + name.replace("/", "--"))
    seen, total, weights = set(), 0, 0
    for sub in ("blobs", "snapshots"):
        for root, _, files in os.walk(os.path.join(d, sub)):
            for f in files:
                path = os.path.join(root, f)
                real = os.path.realpath(path)
                if real in seen:
                    continue
                seen.add(real)
                size = os.path.getsize(real)
                total += size
                if f in ("model.safetensors", "pytorch_model.bin"):
                    weights = max(weights, size)
    return total, weights


def evaluate(kwargs):
    """Run all answerable queries; return per-query metric dicts (no timing)."""
    out = []
    for query, kind, gold, doc_filter in ANSWERABLE:
        scope = [doc_filter] if doc_filter else None
        res = hybrid_search_detailed(query, K, document_names=scope, **kwargs)
        s = harness.score_query([r["chunk"] for r in res["results"]], gold, K)
        s["kind"] = kind
        out.append(s)
    return out


def summarise(per_query):
    d = {m: harness.mean([s[m] for s in per_query]) for m in ("recall", "precision", "mrr", "ndcg")}
    d["by_kind_recall"] = {
        k: harness.mean([s["recall"] for s in per_query if s["kind"] == k]) for k in KINDS
    }
    return d


def run_model(name, qp, dp, latency_only=False):
    from sentence_transformers import SentenceTransformer
    import torch
    model = SentenceTransformer(name, model_kwargs={"dtype": torch.float32})   # gte-small ships fp16 weights
    dim = model.get_embedding_dimension()
    info = {"model": name, "dim": dim, "max_seq_length": model.max_seq_length,
            "query_prefix": qp, "passage_prefix": dp}
    if dim != cfg.EMBEDDING_DIM:
        info["skipped"] = f"dimension {dim} != {cfg.EMBEDDING_DIM}"
        return info
    info["cache_bytes"], info["weights_bytes"] = hf_cache_size(name)
    queries = [q[0] for q in ANSWERABLE]

    def embed_docs(texts):
        return model.encode([dp + t for t in texts], normalize_embeddings=True, batch_size=64)

    def make_query_embedder(prefix):
        def embed_query(texts):
            return model.encode([prefix + t for t in texts], normalize_embeddings=True)
        return embed_query

    # --- corpus embedding (timed together with chunking-independent encode only) ---
    t = time.perf_counter()
    n = harness.load_corpus(
        DOCS, lambda tx: chunk_page(tx, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP, "words"), embed_docs
    )
    info["chunks"] = n
    info["corpus_embed_and_load_s"] = time.perf_counter() - t

    if not latency_only:
        with get_connection() as conn:
            contents = [r[0] for r in conn.execute("SELECT content FROM document_chunks ORDER BY id").fetchall()]
        # pure encode time (second pass, warm)
        t = time.perf_counter()
        embed_docs(contents)
        info["corpus_encode_s"] = time.perf_counter() - t

        # --- normalisation of raw model output + truncation ---
        raw = model.encode([dp + c for c in contents[:100]], normalize_embeddings=False)
        norms = np.linalg.norm(raw, axis=1)
        info["raw_norm_min"], info["raw_norm_max"] = float(norms.min()), float(norms.max())
        tok = model.tokenizer
        lens = [len(x) for x in tok([dp + c for c in contents], add_special_tokens=True)["input_ids"]]
        info["chunk_tokens_max"] = max(lens)
        info["chunk_tokens_median"] = statistics.median(lens)
        info["chunks_over_max_seq"] = sum(1 for l in lens if l > model.max_seq_length)
        qlens = [len(x) for x in tok([qp + q[0] for q in ANSWERABLE], add_special_tokens=True)["input_ids"]]
        info["query_tokens_max"] = max(qlens)

        # --- quality (no lock needed) ---
        print(f"  [{time.strftime('%H:%M:%S')}] corpus embedded ({n} chunks); evaluating", flush=True)
        search_service.generate_embeddings = make_query_embedder(qp)
        info["vector"] = evaluate(dict(use_keyword=False, rerank=False))
        info["hybrid"] = evaluate(dict(rerank=False))
        info["hybrid_rerank"] = evaluate(dict(rerank=True))
        info["vector_rerank"] = evaluate(dict(use_keyword=False, rerank=True))

        if qp:   # ablation: forget the query prefix (documents unchanged)
            search_service.generate_embeddings = make_query_embedder("")
            info["vector_noprefix"] = evaluate(dict(use_keyword=False, rerank=False))
            info["hybrid_noprefix"] = evaluate(dict(rerank=False))
            search_service.generate_embeddings = make_query_embedder(qp)

    else:
        info.update(measure_latency(make_query_embedder(qp), queries))
    return info


def measure_latency(embed_query, queries):
    acquire_lock()
    try:
        embed_query(["warm up"])
        emb_ms, search_ms = [], []
        vecs = []
        for i in range(30):
            q = queries[i % len(queries)]
            t = time.perf_counter()
            e = embed_query([q])[0]
            emb_ms.append((time.perf_counter() - t) * 1000)
            vecs.append(e)
        for e in vecs:
            vector = Vector(e.tolist())
            t = time.perf_counter()
            with get_connection() as conn:
                conn.execute(
                    "SELECT id FROM document_chunks ORDER BY embedding <=> %s LIMIT 10", (vector,)
                ).fetchall()
            search_ms.append((time.perf_counter() - t) * 1000)
    finally:
        release_lock()
    return {"query_embed_ms_median": statistics.median(emb_ms),
            "pgvector_search_ms_median": statistics.median(search_ms)}


# -------------------------------------------------------------- bootstrap ---
def bootstrap_diff(a, b, n=1000, seed=7):
    """Paired bootstrap of mean(a)-mean(b) over queries; returns (diff, lo, hi)."""
    a, b = np.array(a), np.array(b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n, len(a)))
    d = (a[idx] - b[idx]).mean(axis=1)
    return float((a - b).mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def main():
    fresh = "--fresh" in sys.argv
    results = {}
    # pass 1: quality, corpus embedding stats (no lock)
    for name, qp, dp in MODELS:
        path = os.path.join(CACHE_DIR, name.replace("/", "__") + ".json")
        if os.path.exists(path) and not fresh:
            results[name] = json.load(open(path))
            print(f"cached {name}", flush=True)
            continue
        print(f"=== {name}", flush=True)
        try:
            info = run_model(name, qp, dp)
        except Exception as error:
            info = {"model": name, "skipped": f"{type(error).__name__}: {str(error)[:200]}"}
            print(f"SKIP {name}: {info['skipped']}", flush=True)
        json.dump(info, open(path, "w"), indent=1)
        results[name] = info
        print(f"done {name}", flush=True)

    # pass 2: latency, each model measured alone under the bench lock
    for name, qp, dp in MODELS:
        info = results[name]
        if "skipped" in info or "query_embed_ms_median" in info:
            continue
        print(f"=== latency {name}", flush=True)
        lat = run_model(name, qp, dp, latency_only=True)
        info["query_embed_ms_median"] = lat["query_embed_ms_median"]
        info["pgvector_search_ms_median"] = lat["pgvector_search_ms_median"]
        json.dump(info, open(os.path.join(CACHE_DIR, name.replace("/", "__") + ".json"), "w"), indent=1)
        print(f"latency done {name}", flush=True)

    json.dump(results, open(os.path.join(RESULTS_DIR, "phase25_C_embeddings.json"), "w"), indent=1)
    report(results)


def report(results):
    ok = {n: r for n, r in results.items() if "skipped" not in r}
    for n, r in results.items():
        if "skipped" in r:
            print(f"SKIPPED {n}: {r['skipped']}")
    for n, r in ok.items():
        r['cache_bytes'], r['weights_bytes'] = hf_cache_size(n)
    base = ok.get(BASELINE)
    short = lambda n: n.split("/")[-1]

    print("\n## Model facts")
    print("| Model | dim | max_seq | raw norm min-max | chunks | chunk tokens median/max | chunks > max_seq | "
          "corpus encode s | embed+load s | cache MB (repo) | weights MB | query embed ms (med of 30) | pgvector search ms |")
    print("|" + "---|" * 13)
    for n, r in ok.items():
        print(f"| {short(n)} | {r['dim']} | {r['max_seq_length']} | {r['raw_norm_min']:.3f}-{r['raw_norm_max']:.3f} | "
              f"{r['chunks']} | {r['chunk_tokens_median']:.0f}/{r['chunk_tokens_max']} | {r['chunks_over_max_seq']} | "
              f"{r['corpus_encode_s']:.1f} | {r['corpus_embed_and_load_s']:.1f} | {r['cache_bytes']/1e6:.0f} | "
              f"{r['weights_bytes']/1e6:.0f} | {r['query_embed_ms_median']:.1f} | {r['pgvector_search_ms_median']:.2f} |")

    for mode in ("vector", "hybrid", "hybrid_rerank", "vector_rerank", "vector_noprefix", "hybrid_noprefix"):
        print(f"\n## {mode} (38 answerable queries, K={K})")
        print("| Model | Recall@5 | Precision@5 | MRR | nDCG@5 | " + " | ".join(KINDS) + " |")
        print("|" + "---|" * (5 + len(KINDS)))
        for n, r in ok.items():
            if mode not in r:
                continue
            s = summarise(r[mode])
            print(f"| {short(n)} | {s['recall']:.3f} | {s['precision']:.3f} | {s['mrr']:.3f} | {s['ndcg']:.3f} | "
                  + " | ".join(f"{s['by_kind_recall'][k]:.2f}" for k in KINDS) + " |")

    if not base:
        return
    for mode in ("vector", "hybrid", "hybrid_rerank"):
        print(f"\n## Paired bootstrap vs baseline, {mode} (1000 resamples, seed 7): diff [95% CI]")
        print("| Model | d Recall@5 | d MRR | d nDCG@5 | queries better / worse (recall) | better / worse (MRR) |")
        print("|---|---|---|---|---|---|")
        for n, r in ok.items():
            if n == BASELINE:
                continue
            row = []
            for m in ("recall", "mrr", "ndcg"):
                d, lo, hi = bootstrap_diff([s[m] for s in r[mode]], [s[m] for s in base[mode]])
                row.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
            rb = sum(a["recall"] > b["recall"] for a, b in zip(r[mode], base[mode]))
            rw = sum(a["recall"] < b["recall"] for a, b in zip(r[mode], base[mode]))
            mb = sum(a["mrr"] > b["mrr"] for a, b in zip(r[mode], base[mode]))
            mw = sum(a["mrr"] < b["mrr"] for a, b in zip(r[mode], base[mode]))
            print(f"| {short(n)} | {row[0]} | {row[1]} | {row[2]} | {rb} / {rw} | {mb} / {mw} |")

    for mode in ("vector", "hybrid"):
        print(f"\n## Per-query differences vs baseline, {mode} (only queries where any model differs on recall or MRR)")
        names = [n for n in ok if n != BASELINE]
        print("| # | kind | query | base R/RR | " + " | ".join(f"{short(n)} R/RR" for n in names) + " |")
        print("|" + "---|" * (4 + len(names)))
        for i, (q, kind, gold, _) in enumerate(ANSWERABLE):
            b = base[mode][i]
            cells, differs = [], False
            for n in names:
                s = ok[n][mode][i]
                cells.append(f"{s['recall']:.2f}/{s['mrr']:.2f}")
                if abs(s["recall"] - b["recall"]) > 1e-9 or abs(s["mrr"] - b["mrr"]) > 1e-9:
                    differs = True
            if differs:
                print(f"| {i} | {kind} | {q[:60]} | {b['recall']:.2f}/{b['mrr']:.2f} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
