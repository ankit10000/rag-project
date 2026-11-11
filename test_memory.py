import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.conversation_service import (
    create_conversation,
    save_message,
    get_conversation_summary
)

from services.memory_service import update_long_term_memory


def main():

    conversation_id = create_conversation(
        "Memory Summarization Test"
    )

    print("Conversation ID:", conversation_id)

    # Create 10 messages for testing
    for i in range(1, 6):
        save_message(
            conversation_id,
            "user",
            f"This is user message number {i}."
        )

        save_message(
            conversation_id,
            "assistant",
            f"This is assistant response number {i}."
        )

    print("\nUpdating long-term memory...")

    update_long_term_memory(
        conversation_id,
        keep_recent=6
    )

    summary = get_conversation_summary(conversation_id)

    print("\nGenerated Summary:")
    print(summary)


if __name__ == "__main__":
    main()