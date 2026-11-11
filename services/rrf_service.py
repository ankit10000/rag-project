def reciprocal_rank_fusion(
    result_lists: list[list],
    k: int = 60,
    top_k: int = 5
):
    scores = {}
    chunks = {}

    for results in result_lists:

        for rank, result in enumerate(results, start=1):

            # Both search results have chunk ID at index 0
            chunk_id = result[0]

            if chunk_id not in scores:
                scores[chunk_id] = 0.0
                chunks[chunk_id] = result

            scores[chunk_id] += 1 / (k + rank)

    ranked_chunks = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    return [
        {
            "chunk": chunks[chunk_id],
            "rrf_score": score
        }
        for chunk_id, score in ranked_chunks[:top_k]
    ]