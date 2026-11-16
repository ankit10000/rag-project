
from services.rag_service import ask_question
from services.memory_search_service import search_memories
from services.memory_context_service import assemble_memory_context

from services.conversation_service import (
    create_conversation,
    conversation_exists,
    save_message,
    get_conversation_history,
    get_conversation_summary,
    get_messages_for_memory_extraction,
    update_memory_extraction_checkpoint,
)

from services.memory_delete_service import (
    is_explicit_memory_delete_request,
)

from services.memory_cleanup_service import apply_deletion_cleanup

from services.automatic_memory_service import (
    process_memory,
    delete_matching_memories,
)

from services.memory_service import (
    update_long_term_memory,
    extract_and_save_memories,
    MemoryExtractionError,
)

# Testing value: extraction runs once this many new messages exist.
MEMORY_EXTRACTION_THRESHOLD = 4


def run_turn(conversation_id: str, query: str) -> dict:
    """Process ONE user turn exactly as the CLI loop always did.

    Phase 6: extracted unchanged from the main() loop so that the CLI and the
    HTTP API (backend/) share a single orchestration path: explicit memory
    deletion routing, retrieval + grounded answer, message persistence,
    memory extraction with checkpoint safety and summary update. Exceptions
    propagate to the caller (the CLI prints them; the API maps them to an
    error response). The returned dict only describes what happened.
    """

    extraction_outcome = "skipped"
    summary_outcome = "not_run"

    # ==============================================
    # 3. EXPLICIT MEMORY DELETE REQUEST
    # ==============================================

    if is_explicit_memory_delete_request(query):
        print("\nExplicit memory deletion request detected.")

        # Keep this part
        result = delete_matching_memories(
            conversation_id=conversation_id,
            user_request=query,
        )

        # Replace your old answer logic with this
        status = result.get("status", "UNCERTAIN")
        deleted_count = result.get("deleted_count", 0)
        failed_ids = result.get("failed_ids", [])

        if status == "UNCERTAIN":
            answer = (
                "I'm not sure which memories you want me to forget. "
                "Could you specify the topic or information?"
            )

        elif status == "SKIPPED":
            answer = (
                "There are no stored memories in this "
                "conversation, so nothing was deleted."
            )

        elif status == "NO_MATCH":
            answer = (
                "I couldn't find any memories that clearly match "
                "your deletion request. No memories were deleted."
            )

        elif deleted_count > 0:
            answer = f"Deleted {deleted_count} matching memory/memories."

            if failed_ids:
                answer += (
                    f" {len(failed_ids)} deletion(s) could not be completed."
                )

        else:
            answer = (
                "No memories were deleted. "
                "The deletion operation could not be completed."
            )

        request_message_id = save_message(
            conversation_id, "user", query
        )
        answer_message_id = save_message(
            conversation_id, "assistant", answer
        )

        print("\nAssistant:")
        print(answer)

        cleanup_status = "not_needed"

        # After a real deletion, stop the forgotten information
        # from resurfacing via history, summary or extraction.
        if deleted_count > 0:
            try:
                cleanup = apply_deletion_cleanup(
                    conversation_id=conversation_id,
                    deleted_memories=result.get(
                        "deleted_memories", []
                    ),
                    extra_message_ids=[
                        request_message_id,
                        answer_message_id,
                    ],
                    user_request=query,
                )

                print(
                    f"Deletion cleanup: "
                    f"{cleanup['messages_excluded']} message(s) "
                    f"excluded; summary: "
                    f"{cleanup['summary_status']}."
                )
                cleanup_status = str(cleanup.get("summary_status"))

            except Exception as cleanup_error:
                print(
                    f"\nWarning: deletion cleanup failed; "
                    f"forgotten information may still appear in "
                    f"the summary or history: {cleanup_error}"
                )
                cleanup_status = "failed"

        return {
            "kind": "memory_deletion",
            "answer": answer,
            "status": status,
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "cleanup": cleanup_status,
            "sources": [],
            "citations": [],
        }

    # ==============================================
    # 4. LOAD CONVERSATION HISTORY
    # ==============================================

    history = get_conversation_history(
        conversation_id,
        limit=16,
    )

    # ==============================================
    # 5. LOAD CONVERSATION SUMMARY
    # ==============================================

    summary = get_conversation_summary(
        conversation_id
    )

    # ==============================================
    # 6. RETRIEVE LONG-TERM MEMORIES
    # ==============================================

    # Phase 3: relevance + provenance-filtered, categorized context.
    # Same search (threshold 0.35, top_k=5); only user-supported
    # memories are included; internal IDs stay out of the text.
    memory_context = assemble_memory_context(
        conversation_id=conversation_id,
        query=query,
        top_k=5,
        search_fn=search_memories,
    )

    memory_text = memory_context["text"]

    combined_memory = "\n".join(
        part
        for part in [summary, memory_text]
        if part and part.strip()
    )

    # ==============================================
    # 7. GENERATE RAG ANSWER
    # ==============================================

    result = ask_question(
        query=query,
        history=history,
        memory_summary=combined_memory,
    )

    answer = result["answer"]

    # ==============================================
    # 8. SAVE CONVERSATION MESSAGES
    # ==============================================

    save_message(
        conversation_id,
        "user",
        query,
    )

    save_message(
        conversation_id,
        "assistant",
        answer,
    )

    # ==============================================
    # 9. DISPLAY ANSWER IMMEDIATELY
    # (before background memory work, so a later failure
    #  can never hide an already-saved answer)
    # ==============================================

    print("\nAssistant:")
    print(answer)

    sources = result.get("sources", [])

    if sources:

        print("\nSources:")

        for source in sources:

            page = source.get("page")
            ref = source.get("ref")

            print(
                (f"[{ref}] " if ref else "- ")
                + f"{source.get('document') or 'Unknown document'} | "
                + (f"Page {page}" if page else "Page unknown")
            )

    # ==============================================
    # 10. AUTOMATIC MEMORY EXTRACTION (isolated failure)
    #
    # The checkpoint advances only after an explicit successful
    # extraction outcome. Invalid provenance or unresolved model
    # decisions raise MemoryExtractionError and leave this batch
    # eligible for retry.
    # ==============================================

    try:

        new_messages = get_messages_for_memory_extraction(
            conversation_id,
            limit=MEMORY_EXTRACTION_THRESHOLD,
        )

        if len(new_messages) >= MEMORY_EXTRACTION_THRESHOLD:

            print(
                f"Running memory extraction for "
                f"{len(new_messages)} messages..."
            )

            extract_and_save_memories(
                conversation_id=conversation_id,
                messages=new_messages,
            )

            last_message_id = new_messages[-1]["id"]

            update_memory_extraction_checkpoint(
                conversation_id=conversation_id,
                last_message_id=last_message_id,
            )

            print(
                "Memory extraction checkpoint updated."
            )
            extraction_outcome = "checkpoint_advanced"

        else:

            print(
                f"Memory extraction skipped. "
                f"{len(new_messages)} new messages; "
                f"{MEMORY_EXTRACTION_THRESHOLD} required."
            )

    except MemoryExtractionError as extraction_error:

        extraction_outcome = "rejected_will_retry"
        print(
            "\nWarning: memory extraction rejected or incomplete "
            "(checkpoint not advanced; batch will retry): "
            f"{extraction_error}"
        )

    except Exception as extraction_error:

        extraction_outcome = "failed_will_retry"
        print(
            f"\nWarning: memory extraction failed "
            f"(checkpoint not advanced, will retry): "
            f"{extraction_error}"
        )

    # ==============================================
    # 11. UPDATE CONVERSATION SUMMARY (isolated failure)
    # ==============================================

    try:

        update_long_term_memory(
            conversation_id,
            keep_recent=6,
        )
        summary_outcome = "ok"

    except Exception as summary_error:

        summary_outcome = "failed_will_retry"
        print(
            f"\nWarning: conversation summary update "
            f"failed (will retry): {summary_error}"
        )

    return {
        "kind": "answer",
        "answer": answer,
        "status": result.get("status"),
        "sources": result.get("sources", []),
        "citations": result.get("citations", []),
        "issues": result.get("issues", []),
        "retrieval_status": result.get("retrieval_status"),
        "memory_extraction": extraction_outcome,
        "summary_update": summary_outcome,
    }


def main():

    print("\n===== RAG CONVERSATIONAL ASSISTANT =====")

    # ==============================================
    # 1. CREATE OR RESUME CONVERSATION
    # ==============================================

    existing_id = input(
        "\nEnter existing Conversation ID to resume "
        "or press Enter for a new conversation: "
    ).strip()

    if existing_id:

        try:
            if not conversation_exists(existing_id):
                print("Conversation not found!")
                return

            conversation_id = existing_id

        except ValueError:
            print("Invalid Conversation ID!")
            return

    else:
        conversation_id = create_conversation()

    print("\nConversation ID:", conversation_id)
    print("\nType 'exit' to quit.")

    # ==============================================
    # 2. MAIN CONVERSATION LOOP
    # ==============================================

    while True:

        query = input("\nYou: ").strip()

        if query.lower() == "exit":
            print("Goodbye!")
            break

        if not query:
            continue

        try:

            run_turn(conversation_id, query)

        except Exception as error:

            print(f"\nError: {error}")


if __name__ == "__main__":
    main()
