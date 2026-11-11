from services.database import get_connection
from services.embedding_service import generate_embeddings
from pgvector import Vector

conversation_id = "c19ff16f-df58-423e-aa76-9c6b86171d78"

memory = (
    "The RAG application uses sentence-transformers/all-MiniLM-L6-v2 "
    "for embeddings, generating 384-dimensional vectors."
)

embedding = generate_embeddings([memory])[0]
embedding_vector = Vector(embedding.tolist())

with get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversation_memories (
                conversation_id,
                memory,
                embedding,
                source_message_id
            )
            VALUES (%s, %s, %s, NULL)
            """,
            (
                conversation_id,
                memory,
                embedding_vector
            )
        )

print("Memory inserted successfully.")