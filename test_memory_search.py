from services.memory_search_service import search_memories

CONVERSATION_ID = "437cf5c1-5e52-4740-9255-497d7d207567"


def main():
    query = "Which technologies am I using for my AI project?"

    memories = search_memories(
        conversation_id=CONVERSATION_ID,
        query=query,
        top_k=3
    )

    print("\nRetrieved memories:")

    for memory in memories:
        print(f"\nMemory: {memory['memory']}")
        print(f"Distance: {memory['distance']:.4f}")


if __name__ == "__main__":
    main()