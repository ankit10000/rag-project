
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import uuid

from services.automatic_memory_service import process_memory
from services.conversation_service import create_conversation, save_message
from services.database import get_connection

conversation_id = create_conversation("Automatic memory manual test")

new_memory = (
    "I switched my RAG application's LLM from Gemini to OpenAI."
)

try:
    source_message_id = save_message(conversation_id, "user", new_memory)
    process_memory(
        conversation_id=conversation_id,
        new_memory=new_memory,
        source_message_id=source_message_id,
    )
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id=%s", (uuid.UUID(conversation_id),))
