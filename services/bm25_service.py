import re
from rank_bm25 import BM25Okapi
from services.database import get_connection


def tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())


def bm25_search(query: str, top_k: int = 5):
    with get_connection() as conn:
        documents = conn.execute(
            """
            SELECT id, document_name, page_number, content
            FROM document_chunks
            """
        ).fetchall()

    if not documents:
        return []

    tokenized_corpus = [
        tokenize(document[3])
        for document in documents
    ]

    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = tokenize(query)

    scores = bm25.get_scores(tokenized_query)

    ranked_results = sorted(
        zip(documents, scores),
        key=lambda item: item[1],
        reverse=True
    )

    return [
        (*document, float(score))
        for document, score in ranked_results[:top_k]
    ]