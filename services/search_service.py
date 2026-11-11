from services.database import get_connection
from services.embedding_service import generate_embeddings
from services import retrieval_config as cfg
from pgvector import Vector


def build_scope_filter(document_names=None, pages=None):
    """
    Metadata filter shared by every retriever. Returns (sql_fragment, params)
    that is safe to append after a WHERE / AND.
    """
    clauses = []
    params = []

    if document_names:
        clauses.append("document_name = ANY(%s)")
        params.append(list(document_names))

    if pages:
        clauses.append("page_number = ANY(%s)")
        params.append([int(p) for p in pages])

    return " AND ".join(clauses), params


def semantic_search(
    query: str,
    top_k: int = 5,
    document_names=None,
    pages=None,
    similarity_threshold=None,
):
    """
    Returns (id, document_name, page_number, content, distance) tuples,
    nearest first. distance is cosine distance (similarity = 1 - distance).
    """
    query_embedding = generate_embeddings([query])[0]

    # Convert embedding into pgvector format
    vector = Vector(query_embedding.tolist())

    scope_sql, scope_params = build_scope_filter(document_names, pages)
    where = f"WHERE {scope_sql}" if scope_sql else ""

    threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else cfg.SIMILARITY_THRESHOLD
    )

    with get_connection() as conn:
        results = conn.execute(
            f"""
            SELECT
                id,
                document_name,
                page_number,
                content,
                embedding <=> %s AS distance
            FROM document_chunks
            {where}
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (vector, *scope_params, vector, top_k)
        ).fetchall()

    if threshold is not None:
        results = [row for row in results if (1 - row[4]) >= threshold]

    return results
