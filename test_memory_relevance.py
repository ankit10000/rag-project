import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.conversation_service import create_conversation, save_message
from services.memory_storage_service import save_memory
from services.memory_search_service import search_memories


conversation_id = create_conversation("Memory Relevance Test")

fact1 = "The RAG application uses Python, PostgreSQL, pgvector, and Gemini."
source1 = save_message(conversation_id, "user", fact1)
save_memory(conversation_id, fact1, source_message_id=source1)

fact2 = "The user prefers simple Hinglish explanations."
source2 = save_message(conversation_id, "user", fact2)
save_memory(conversation_id, fact2, source_message_id=source2)

fact3 = "The user enjoys playing cricket on weekends."
source3 = save_message(conversation_id, "user", fact3)
save_memory(conversation_id, fact3, source_message_id=source3)

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
