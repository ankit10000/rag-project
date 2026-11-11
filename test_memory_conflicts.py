
from services.memory_decision_service import decide_memory_action


def test_case(title, new_memory, existing_memories):
    print(f"\n--- {title} ---")

    result = decide_memory_action(
        new_memory=new_memory,
        existing_memories=existing_memories,
    )

    print(result)


# Test 1: Additional database — should preserve both facts
test_case(
    "Additional database",
    "I also use PostgreSQL for analytics.",
    [
        (101, "The user's application uses MongoDB."),
    ],
)

# Test 2: Clear replacement — should update
test_case(
    "Database replacement",
    "I no longer use MongoDB; I switched to PostgreSQL.",
    [
        (102, "The user's application uses MongoDB."),
    ],
)

# Test 3: Different projects — should preserve both
test_case(
    "Different projects",
    "Project B uses PostgreSQL.",
    [
        (103, "Project A uses MongoDB."),
    ],
)
