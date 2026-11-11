import time

from services import retrieval_config as cfg
from services.bm25_service import bm25_search
from services.fts_service import fts_search
from services.search_service import semantic_search
from services.rrf_service import reciprocal_rank_fusion
from services.reranker_service import rerank_results


def _interleave(result_lists, top_k):
    """Naive merge without scores: round-robin, de-duplicated by chunk id."""
    merged, seen = [], set()
    longest = max((len(r) for r in result_lists), default=0)

    for i in range(longest):
        for results in result_lists:
            if i < len(results) and results[i][0] not in seen:
                seen.add(results[i][0])
                merged.append({"chunk": results[i], "rrf_score": 0.0})

    return merged[:top_k]


def keyword_search(query, top_k, document_names=None, pages=None, backend=None,
                   drop_stopwords=None):
    backend = backend or cfg.BM25_BACKEND

    if backend == "fts":
        return fts_search(query, top_k, document_names, pages)

    return bm25_search(query, top_k, document_names, pages, drop_stopwords)


def hybrid_search_detailed(
    query: str,
    top_k: int | None = None,
    *,
    document_names=None,
    pages=None,
    use_vector: bool = True,
    use_keyword: bool = True,
    fusion: str = "rrf",             # "rrf" | "interleave"
    rerank: bool | None = None,
    vector_top_k: int | None = None,
    keyword_top_k: int | None = None,
    rrf_k: int | None = None,
    rrf_top_k: int | None = None,
    rerank_top_k: int | None = None,
    keyword_backend: str | None = None,
    drop_stopwords: bool | None = None,
):
    """
    Run the retrieval pipeline and return {"results", "timings_ms", "counts"}.
    Each result is {"chunk": (id, document, page, content, raw_score),
    "rrf_score": float, "rerank_score": float (only when reranked)}.
    """
    top_k = top_k or cfg.FINAL_TOP_K
    rerank = cfg.RERANK_ENABLED if rerank is None else rerank
    timings = {}

    started = time.perf_counter()
    vector_results, keyword_results = [], []

    if use_vector:
        t = time.perf_counter()
        vector_results = semantic_search(
            query, top_k=vector_top_k or cfg.VECTOR_TOP_K,
            document_names=document_names, pages=pages,
        )
        timings["vector"] = (time.perf_counter() - t) * 1000

    if use_keyword:
        t = time.perf_counter()
        keyword_results = keyword_search(
            query, keyword_top_k or cfg.BM25_TOP_K,
            document_names, pages, keyword_backend, drop_stopwords,
        )
        timings["keyword"] = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    lists = [l for l in (keyword_results, vector_results) if l]
    pool = rrf_top_k or cfg.RRF_TOP_K

    if fusion == "interleave":
        fused = _interleave(lists, pool)
    else:
        fused = reciprocal_rank_fusion(
            lists, k=rrf_k or cfg.RRF_K, top_k=pool
        )
    timings["fusion"] = (time.perf_counter() - t) * 1000

    if rerank:
        t = time.perf_counter()
        results = rerank_results(
            query, fused[: rerank_top_k or cfg.RERANK_TOP_K], top_k=top_k
        )
        timings["rerank"] = (time.perf_counter() - t) * 1000
    else:
        results = fused[:top_k]

    timings["total"] = (time.perf_counter() - started) * 1000

    return {
        "results": results,
        "timings_ms": timings,
        "counts": {
            "vector": len(vector_results),
            "keyword": len(keyword_results),
            "fused": len(fused),
        },
    }


def hybrid_search(query: str, top_k: int = 5, document_names=None, pages=None):
    """Backward compatible entry point used by rag_service."""
    return hybrid_search_detailed(
        query, top_k, document_names=document_names, pages=pages
    )["results"]
