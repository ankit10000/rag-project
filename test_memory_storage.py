import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import uuid

from services.conversation_service import create_conversation, save_message
from services.database import get_connection
from services.memory_storage_service import save_memory


def main():
    conversation_id = create_conversation(
        title="Vector Memory Test"
    )
    try:
        print("Conversation ID:", conversation_id)
        memory_text = (
            "The user is building a RAG application "
            "using Python, PostgreSQL, pgvector, and Gemini."
        )
        source_id = save_message(conversation_id, "user", memory_text)
        save_memory(
            conversation_id=conversation_id,
            memory_text=memory_text,
            source_message_id=source_id,
        )
    finally:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id=%s",
                (uuid.UUID(conversation_id),),
            )


if __name__ == "__main__":
    main()
