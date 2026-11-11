from services.memory_storage_service import update_memory

conversation_id = "991c4838-a604-4090-8e18-cc04307ce2d4"
memory_id = 25

new_memory = (
    "I switched my RAG application's LLM "
    "from Gemini to OpenAI."
)

update_memory(
    conversation_id=conversation_id,
    memory_id=memory_id,
    new_memory_text=new_memory,
)