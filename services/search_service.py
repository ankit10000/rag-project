from services.database import get_connection
from services.embedding_service import generate_embeddings
from pgvector import Vector


def semantic_search(query: str, top_k: int = 5):
    query_embedding = generate_embeddings([query])[0]

    # Convert embedding into pgvector format
    vector = Vector(query_embedding.tolist())

    with get_connection() as conn:
        results = conn.execute(
            """
            SELECT
                id,
                document_name,
                page_number,
                content,
                embedding <=> %s AS distance
            FROM document_chunks
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (vector, vector, top_k)
        ).fetchall()

    return results