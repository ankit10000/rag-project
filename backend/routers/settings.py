"""Read-only configuration. There is deliberately no write endpoint: changing
thresholds/defaults at runtime needs a separately approved design."""

from fastapi import APIRouter

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/retrieval")
def retrieval_settings():
    from services import retrieval_config as cfg

    return {
        "read_only": True,
        "chunking": {"chunk_size_words": cfg.CHUNK_SIZE, "chunk_overlap_words": cfg.CHUNK_OVERLAP,
                     "strategy": cfg.CHUNK_STRATEGY},
        "embedding": {"model": cfg.EMBEDDING_MODEL, "dimension": cfg.EMBEDDING_DIM,
                      "query_cache_size": cfg.EMBEDDING_QUERY_CACHE_SIZE},
        "retrieval": {"vector_top_k": cfg.VECTOR_TOP_K, "bm25_top_k": cfg.BM25_TOP_K, "rrf_k": cfg.RRF_K,
                      "rrf_top_k": cfg.RRF_TOP_K, "rerank_enabled": cfg.RERANK_ENABLED,
                      "rerank_model": cfg.RERANK_MODEL, "rerank_top_k": cfg.RERANK_TOP_K,
                      "final_top_k": cfg.FINAL_TOP_K, "rerank_score_margin": cfg.RERANK_SCORE_MARGIN,
                      "rerank_min_score": cfg.RERANK_MIN_SCORE, "similarity_threshold": cfg.SIMILARITY_THRESHOLD,
                      "bm25_backend": cfg.BM25_BACKEND, "bm25_cache_max_entries": cfg.BM25_CACHE_MAX_ENTRIES},
        "answer": {"context_max_chars": cfg.CONTEXT_MAX_CHARS, "context_max_chunks": cfg.CONTEXT_MAX_CHUNKS,
                   "history_max_turns": cfg.HISTORY_MAX_TURNS, "answer_max_retries": cfg.ANSWER_MAX_RETRIES},
        "ingestion": {"max_pdf_size_mb": cfg.MAX_PDF_SIZE_MB, "max_pdf_pages": cfg.MAX_PDF_PAGES},
        "performance": {"metrics_enabled": cfg.PERF_METRICS_ENABLED},
    }
