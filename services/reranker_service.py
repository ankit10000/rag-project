import threading

from services import retrieval_config as cfg

_model = None
_lock = threading.Lock()


def get_reranker():
    """Load the cross-encoder lazily so importing the module stays cheap."""
    global _model

    with _lock:
        if _model is None:
            from sentence_transformers import CrossEncoder
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
    scores = get_reranker().predict(pairs)

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

    return reranked[:top_k]
