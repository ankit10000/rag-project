from services.conversation_service import create_conversation
from services.memory_storage_service import save_memory
from services.memory_search_service import search_memories


conversation_id = create_conversation("Memory Relevance Test")

save_memory(
    conversation_id,
    "The RAG application uses Python, PostgreSQL, pgvector, and Gemini."
)

save_memory(
    conversation_id,
    "The user prefers simple Hinglish explanations."
)

save_memory(
    conversation_id,
    "The user enjoys playing cricket on weekends."
)

print("\nQuery: Which database does my RAG application use?")

results = search_memories(
    conversation_id=conversation_id,
    query="Which database does my RAG application use?",
    top_k=3
)

for item in results:
    print(
        f"Similarity: {item['similarity']:.3f} | "
        f"Memory: {item['memory']}"
    )