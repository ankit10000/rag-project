from services.conversation_service import create_conversation
from services.memory_storage_service import save_memory


conversation_id = create_conversation("Semantic Memory Test")

print("\nSaving first memory:")
save_memory(
    conversation_id,
    "I am building a RAG application using Python and PostgreSQL."
)

print("\nSaving similar memory:")
save_memory(
    conversation_id,
    "The user is developing a Retrieval-Augmented Generation system with Python and PostgreSQL."
)

print("\nSaving unrelated memory:")
save_memory(
    conversation_id,
    "The user prefers explanations in simple Hinglish."
)