import math
import threading

from services import perf_metrics
from services import retrieval_config as cfg

_model = None
_lock = threading.Lock()


def get_reranker():
    """Load the cross-encoder lazily so importing the module stays cheap."""
    global _model

    with _lock:
        if _model is None:
            from sentence_transformers import CrossEncoder
            with perf_metrics.timed("reranker.model_init"):
                _model = CrossEncoder(cfg.RERANK_MODEL)

    return _model


def rerank_results(query: str, results: list, top_k: int = 5):

    if not results:
        return []

    # Extract text from retrieved chunks
    pairs = [
        (query, item["chunk"][3])
        for item in results
    ]

    # Calculate relevance scores
    model = get_reranker()
    with perf_metrics.timed("reranker.predict", candidates=len(pairs)):
        scores = model.predict(pairs)

    # Stage 5: never silently drop candidates (zip would truncate) or sort on
    # NaN (undefined order). Callers treat this like any reranker failure.
    scores = [float(score) for score in scores]
    if len(scores) != len(results):
        raise ValueError(f"reranker returned {len(scores)} scores for {len(results)} candidates")
    if not all(math.isfinite(score) for score in scores):
        raise ValueError("reranker returned a non-finite score")

    # Attach scores to results
    reranked = []

    for item, score in zip(results, scores):
        reranked.append({
            "chunk": item["chunk"],
            "rrf_score": item["rrf_score"],
            "rerank_score": float(score)
        })

    # Highest relevance score first (stable sort keeps RRF order on ties)
    reranked.sort(
        key=lambda item: item["rerank_score"],
        reverse=True
    )

    from services.evidence_trace import trace_candidates
    trace_candidates('reranker_scores', reranked,
                     selected_ids=[item['chunk'][0] for item in reranked[:top_k]],
                     removal_reason='rerank_top_k')

    return reranked[:top_k]
