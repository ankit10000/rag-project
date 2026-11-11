from services.bm25_service import bm25_search
from services.search_service import semantic_search
from services.rrf_service import reciprocal_rank_fusion
from services.reranker_service import rerank_results


def hybrid_search(query: str, top_k: int = 5):

    bm25_results = bm25_search(query, top_k=10)

    vector_results = semantic_search(query, top_k=10)

    hybrid_results = reciprocal_rank_fusion(
        [bm25_results, vector_results],
        k=60,
        top_k=10
    )

    final_results = rerank_results(
        query,
        hybrid_results,
        top_k=top_k
    )

    return final_results