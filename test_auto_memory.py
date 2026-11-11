import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.memory_service import extract_and_save_memories
from services.conversation_service import create_conversation


def main():
    conversation_id = create_conversation(
        title="Automatic Memory Test"
    )

    messages = [
        {
            "role": "user",
            "content": (
                "I am building a RAG application using Python, "
                "PostgreSQL, pgvector, and Gemini."
            )
        },
        {
            "role": "user",
            "content": (
                "I prefer learning technical topics through "
                "simple Hinglish explanations."
            )
        }
    ]

    print("Conversation ID:", conversation_id)

    memories = extract_and_save_memories(
        conversation_id=conversation_id,
        messages=messages
    )

    print("\nSaved memories:")
    for memory in memories:
        print("-", memory)


if __name__ == "__main__":
    main()