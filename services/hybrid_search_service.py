import time

from services import retrieval_config as cfg
from services.bm25_service import bm25_search
from services.fts_service import fts_search
from services.search_service import semantic_search
from services.rrf_service import reciprocal_rank_fusion
from services.reranker_service import rerank_results
from services.evidence_trace import trace_candidates, trace_event


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
    Run the retrieval pipeline and return
    {"results", "timings_ms", "counts", "rerank_status"}.
    Each result is {"chunk": (id, document, page, content, raw_score),
    "rrf_score": float, "rerank_score": float (only when reranked)}.

    Failure behaviour (Stage 5):
      * a retriever that raises (database or embedding failure) propagates its
        exception: a failed retrieval is never reported as an empty result;
      * the reranker is optional: if it fails to load or score, the fused (RRF)
        order is kept, a type-only diagnostic is printed, and rerank_status is
        "failed:<ExceptionType>"; other values are "ok", "disabled", "skipped";
      * a blank query returns no results without querying anything.
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be a string, not {type(query).__name__}")

    # None -> configured default; an explicit 0 (or negative) means "no results".
    top_k = cfg.FINAL_TOP_K if top_k is None else max(0, top_k)
    rerank = cfg.RERANK_ENABLED if rerank is None else rerank
    timings = {}

    if not query.strip():
        return {
            "results": [],
            "timings_ms": {"total": 0.0},
            "counts": {"vector": 0, "keyword": 0, "fused": 0},
            "rerank_status": "skipped",
        }

    started = time.perf_counter()
    trace_event('retrieval_scope', metadata={'document_names': document_names,
                'pages': pages, 'top_k': top_k}, raw={'search_query': query})
    vector_results, keyword_results = [], []

    if use_vector:
        t = time.perf_counter()
        vector_results = semantic_search(
            query, top_k=vector_top_k or cfg.VECTOR_TOP_K,
            document_names=document_names, pages=pages,
        )
        timings["vector"] = (time.perf_counter() - t) * 1000
        trace_candidates('vector_candidates', vector_results)

    if use_keyword:
        t = time.perf_counter()
        keyword_results = keyword_search(
            query, keyword_top_k or cfg.BM25_TOP_K,
            document_names, pages, keyword_backend, drop_stopwords,
        )
        timings["keyword"] = (time.perf_counter() - t) * 1000
        trace_candidates('lexical_candidates', keyword_results)

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
    trace_candidates('rrf_results', fused)
    trace_event('fusion_selection', metadata={
        'algorithm': 'interleave' if fusion == 'interleave' else 'rrf',
        'input_ids': list(dict.fromkeys(r[0] for batch in lists for r in batch)),
        'selected_ids': [r['chunk'][0] for r in fused],
        'removals': ([{'chunk_id': cid, 'reason': 'interleave_pool_limit'}
                     for cid in dict.fromkeys(r[0] for batch in lists for r in batch)
                     if cid not in {r['chunk'][0] for r in fused}]
                     if fusion == 'interleave' else []),
        'decision_trace_stage': 'fusion_selection' if fusion == 'interleave' else 'rrf_selection',
        'limit': pool})

    if not rerank:
        rerank_status = "disabled"
        results = fused[:top_k]
    elif top_k == 0 or not fused:
        rerank_status = "skipped"          # nothing to rerank: do not load the model
        results = []
    else:
        t = time.perf_counter()
        try:
            results = rerank_results(
                query, fused[: rerank_top_k or cfg.RERANK_TOP_K], top_k=top_k
            )
            rerank_status = "ok"
        except Exception as error:  # noqa: BLE001 - the reranker is an optional stage
            # Keep the valid fused order; type only (messages may contain paths).
            rerank_status = f"failed:{type(error).__name__}"
            print(f"Reranker failed ({type(error).__name__}); keeping the RRF order.")
            results = fused[:top_k]
        timings["rerank"] = (time.perf_counter() - t) * 1000

    trace_candidates('rerank_results', results)
    trace_event('rerank_selection', metadata={
        'status': rerank_status, 'selected_ids': [r['chunk'][0] for r in results],
        'input_ids': [r['chunk'][0] for r in fused],
        'rerank_candidate_limit': rerank_top_k or cfg.RERANK_TOP_K,
        'removals': [{'chunk_id': item['chunk'][0],
                      'reason': ('rerank_candidate_limit'
                                 if rerank_status == 'ok' and rank >= (rerank_top_k or cfg.RERANK_TOP_K)
                                 else 'rerank_top_k' if rerank_status == 'ok' else 'fusion_top_k')}
                     for rank, item in enumerate(fused)
                     if item['chunk'][0] not in {r['chunk'][0] for r in results}],
        'output_limit': top_k, 'removal_reason': 'rerank_top_k' if rerank_status == 'ok' else 'fusion_top_k'})

    timings["total"] = (time.perf_counter() - started) * 1000

    return {
        "results": results,
        "timings_ms": timings,
        "counts": {
            "vector": len(vector_results),
            "keyword": len(keyword_results),
            "fused": len(fused),
        },
        "rerank_status": rerank_status,
    }


def hybrid_search(query: str, top_k: int = 5, document_names=None, pages=None):
    """Backward compatible entry point used by rag_service."""
    return hybrid_search_detailed(
        query, top_k, document_names=document_names, pages=pages
    )["results"]
