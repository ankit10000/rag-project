import re


def _content_key(result) -> str:
    """Normalised text identity used to drop duplicate chunks."""
    return re.sub(r"\s+", " ", result[3]).strip().lower()


def reciprocal_rank_fusion(
    result_lists: list[list],
    k: int = 60,
    top_k: int = 5,
    weights: list[float] | None = None,
    dedupe_content: bool = True,
):
    """
    Fuse ranked lists with RRF: score(d) = sum_i w_i / (k + rank_i(d)).

    Every result is a tuple whose first element is the chunk id and whose
    fourth element is the text. Chunks are de-duplicated by id and, when
    dedupe_content is true, by identical normalised text (the best ranked
    copy is kept). Metadata (document, page) travels inside the tuple.
    """
    if top_k <= 0:
        return []

    weights = weights or [1.0] * len(result_lists)
    scores = {}
    chunks = {}
    first_seen = {}

    for weight, results in zip(weights, result_lists):

        for rank, result in enumerate(results, start=1):

            chunk_id = result[0]

            if chunk_id not in scores:
                scores[chunk_id] = 0.0
                chunks[chunk_id] = result
                first_seen[chunk_id] = len(first_seen)

            scores[chunk_id] += weight / (k + rank)

    # score desc; ties keep first-seen order so output is deterministic
    ranked_chunks = sorted(
        scores.items(),
        key=lambda item: (-item[1], first_seen[item[0]]),
    )

    fused = []
    seen_text = set()

    for chunk_id, score in ranked_chunks:

        if dedupe_content:
            key = _content_key(chunks[chunk_id])

            if key in seen_text:
                continue

            seen_text.add(key)

        fused.append({"chunk": chunks[chunk_id], "rrf_score": score})

        if len(fused) >= top_k:
            break

    return fused
