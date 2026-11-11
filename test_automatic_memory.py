
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.automatic_memory_service import process_memory

conversation_id = "991c4838-a604-4090-8e18-cc04307ce2d4"

new_memory = (
    "I switched my RAG application's LLM from Gemini to OpenAI."
)

process_memory(
    conversation_id=conversation_id,
    new_memory=new_memory,
)
