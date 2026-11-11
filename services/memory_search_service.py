
from services.database import get_connection
from services.embedding_service import generate_embeddings
from pgvector import Vector


MEMORY_RELEVANCE_THRESHOLD = 0.35


def search_memories(
    conversation_id: str,
    query: str,
    top_k: int = 3
) -> list[dict]:

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
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (
                    query_vector,
                    conversation_id,
                    query_vector,
                    top_k
                )
            )

            rows = cursor.fetchall()

    relevant_memories = []

    for memory_id, memory_text, distance in rows:
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

    return relevant_memories
