import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

from services.conversation_service import create_conversation
from services.memory_storage_service import (
    save_memory,
    delete_memory
)
from services.memory_search_service import search_memories


conversation_id = create_conversation("Memory Delete Test")

# Save test memory
save_memory(
    conversation_id,
    "The user is learning RAG using PostgreSQL."
)

# Retrieve its ID
memories = search_memories(
    conversation_id=conversation_id,
    query="What is the user learning?",
    top_k=3
)

if memories:
    memory_id = memories[0]["id"]

    print("\nDeleting memory:", memory_id)

    delete_memory(
        conversation_id=conversation_id,
        memory_id=memory_id
    )

    # Verify deletion
    remaining = search_memories(
        conversation_id=conversation_id,
        query="What is the user learning?",
        top_k=3
    )

    print("\nRemaining memories:", remaining)