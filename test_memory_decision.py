
from services.memory_decision_service import decide_memory_action


existing_memories = [
    (
        25,
        "I use Gemini as the LLM in my RAG application."
    )
]

new_memory = (
    "I switched my RAG application's LLM from Gemini to OpenAI."
)

result = decide_memory_action(
    new_memory=new_memory,
    existing_memories=existing_memories
)

print("\nMemory decision:")
print(result)
