from services.conversation_service import (
    create_conversation,
    save_message,
    get_conversation_history
)


def main():

    # Create a new conversation
    conversation_id = create_conversation(
        "Forest Botany Discussion"
    )

    print("Conversation ID:", conversation_id)

    # Save messages
    save_message(
        conversation_id,
        "user",
        "Who qualified for Forest Botany?"
    )

    save_message(
        conversation_id,
        "assistant",
        "Rahul Rana, Tanya Bangalia and Yashasvi."
    )

    save_message(
        conversation_id,
        "user",
        "What are their application IDs?"
    )

    # Retrieve history
    history = get_conversation_history(
        conversation_id,
        limit=6
    )

    print("\nConversation History:\n")

    for message in history:
        print(message["role"], ":", message["content"])


if __name__ == "__main__":
    main()