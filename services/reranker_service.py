from sentence_transformers import CrossEncoder

model = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)


def rerank_results(query: str, results: list, top_k: int = 5):

    if not results:
        return []

    # Extract text from retrieved chunks
    pairs = [
        (query, item["chunk"][3])
        for item in results
    ]

    # Calculate relevance scores
    scores = model.predict(pairs)

    # Attach scores to results
    reranked = []

    for item, score in zip(results, scores):
        reranked.append({
            "chunk": item["chunk"],
            "rrf_score": item["rrf_score"],
            "rerank_score": float(score)
        })

    # Highest relevance score first
    reranked.sort(
        key=lambda item: item["rerank_score"],
        reverse=True
    )

    return reranked[:top_k]