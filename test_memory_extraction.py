import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.memory_service import extract_memories


def main():
    messages = [
        {
            "role": "user",
            "content": (
                "I'm building a RAG application using PostgreSQL "
                "and Gemini."
            )
        },
        {
            "role": "assistant",
            "content": "That's great! Let's build it step by step."
        },
        {
            "role": "user",
            "content": "I want to use pgvector for memory retrieval."
        },
        {
            "role": "user",
            "content": "I prefer learning through simple Hinglish explanations."
        }
    ]

    memories = extract_memories(messages)

    print("\nExtracted memories:")

    for memory in memories:
        print("-", memory["memory"], "| source:", memory["source_message_id"])


if __name__ == "__main__":
    main()