import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import uuid

from services.conversation_service import create_conversation, save_message
from services.database import get_connection
from services.memory_storage_service import save_memory

conversation_id = create_conversation("Duplicate memory test")

memory1 = (
    "I am developing a RAG application using Python, "
    "PostgreSQL, pgvector, and Gemini."
)

memory2 = (
    "My project is a retrieval augmented generation system "
    "built with Python, Gemini, and PostgreSQL vector search."
)

try:
    source1 = save_message(conversation_id, "user", memory1)
    source2 = save_message(conversation_id, "user", memory2)

    print("\n--- First memory ---")
    save_memory(conversation_id, memory1, source_message_id=source1)

    print("\n--- Similar memory ---")
    save_memory(conversation_id, memory2, source_message_id=source2)
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id=%s", (uuid.UUID(conversation_id),))
