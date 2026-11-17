
from services.database import get_connection
from services.embedding_service import generate_embeddings
from pgvector import Vector


MEMORY_RELEVANCE_THRESHOLD = 0.35


def search_memories(
    conversation_id: str,
    query: str,
    top_k: int = 3,
    exclude_memory_ids=None,
) -> list[dict]:

    if top_k <= 0 or not isinstance(query, str) or not query.strip():
        return []

    query_embedding = generate_embeddings([query])[0]
    query_vector = Vector(query_embedding.tolist())

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    memory,
                    embedding <=> %s AS distance
                FROM conversation_memories
                WHERE conversation_id = %s
                ORDER BY embedding <=> %s, id ASC
                """,
                (
                    query_vector,
                    conversation_id,
                    query_vector
                )
            )

            rows = cursor.fetchall()

    from services.legacy_provenance_quarantine import eligible_memory_ids
    allowed = eligible_memory_ids(conversation_id, [row[0] for row in rows])
    allowed -= {int(i) for i in (exclude_memory_ids or ())}
    relevant_memories = []

    for memory_id, memory_text, distance in rows:
        if memory_id not in allowed or distance is None:
            continue
        similarity = 1 - float(distance)

        if similarity >= MEMORY_RELEVANCE_THRESHOLD:
            relevant_memories.append({
                "id": memory_id,
                "memory": memory_text,
                "distance": float(distance),
                "similarity": similarity
            })

    print(
        f"Memory search: {len(relevant_memories)} relevant memories "
        f"out of {len(rows)} retrieved for conversation {conversation_id}."
    )

    return relevant_memories[:top_k]
