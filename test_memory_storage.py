from services.conversation_service import create_conversation
from services.memory_storage_service import save_memory


def main():
    conversation_id = create_conversation(
        title="Vector Memory Test"
    )

    print("Conversation ID:", conversation_id)

    save_memory(
        conversation_id=conversation_id,
        memory_text=(
            "The user is building a RAG application "
            "using Python, PostgreSQL, pgvector, and Gemini."
        )
    )


if __name__ == "__main__":
    main()