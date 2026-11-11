import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.memory_storage_service import save_memory

conversation_id = "991c4838-a604-4090-8e18-cc04307ce2d4"

memory1 = (
    "I am developing a RAG application using Python, "
    "PostgreSQL, pgvector, and Gemini."
)

memory2 = (
    "My project is a retrieval augmented generation system "
    "built with Python, Gemini, and PostgreSQL vector search."
)

print("\n--- First memory ---")
save_memory(conversation_id, memory1)

print("\n--- Similar memory ---")
save_memory(conversation_id, memory2)