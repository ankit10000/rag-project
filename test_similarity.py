import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.embedding_service import generate_embeddings

texts = [
    "I am building a RAG application using Python and PostgreSQL.",
    "The user is developing a Retrieval-Augmented Generation system with Python and PostgreSQL.",
    "The user prefers explanations in simple Hinglish."
]

embeddings = generate_embeddings(texts)

similarity_1 = float(embeddings[0] @ embeddings[1])
similarity_2 = float(embeddings[0] @ embeddings[2])

print(f"Similar sentences: {similarity_1:.4f}")
print(f"Unrelated sentences: {similarity_2:.4f}")