
from services.memory_decision_service import decide_memory_action


existing_memories = [
    (501, "The user prefers simple Hinglish explanations."),
    (502, "The user's RAG project uses MongoDB."),
]

# Test explicit deletion request
result = decide_memory_action(
    new_memory="Please forget my preference for simple Hinglish explanations.",
    existing_memories=existing_memories,
)

print("\nExplicit forget request:")
print(result)

# Test factual change — should NOT be treated as deletion
result = decide_memory_action(
    new_memory="I no longer use MongoDB for my RAG project; I switched to PostgreSQL.",
    existing_memories=existing_memories,
)

print("\nFactual change:")
print(result)
