import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.conversation_service import create_conversation, save_message
from services.memory_storage_service import save_memory


conversation_id = create_conversation("Semantic Memory Test")

print("\nSaving first memory:")
source1 = save_message(
    conversation_id,
    "user",
    "I am building a RAG application using Python and PostgreSQL.",
)
save_memory(
    conversation_id,
    "I am building a RAG application using Python and PostgreSQL.",
    source_message_id=source1,
)

print("\nSaving similar memory:")
source2 = save_message(
    conversation_id,
    "user",
    "The user is developing a Retrieval-Augmented Generation system with Python and PostgreSQL.",
)
save_memory(
    conversation_id,
    "The user is developing a Retrieval-Augmented Generation system with Python and PostgreSQL.",
    source_message_id=source2,
)

print("\nSaving unrelated memory:")
source3 = save_message(
    conversation_id,
    "user",
    "The user prefers explanations in simple Hinglish.",
)
save_memory(
    conversation_id,
    "The user prefers explanations in simple Hinglish.",
    source_message_id=source3,
)
