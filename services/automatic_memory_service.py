
from services.database import get_connection
from services.memory_storage_service import (
    save_memory,
    update_memory,
    delete_memory,
    get_memory_details,
    confirm_memory,
    normalize_memory_text,
    normalize_source_ids,
    normalize_positive_id,
)


# Phase 1 Task 4 candidate-coverage contract. Automatic NEW/DUPLICATE/UPDATE
# detection compares a new memory only with the latest N memories of the
# conversation (highest ids first). A conflicting or duplicate memory OLDER
# than this window is NOT considered by automatic update detection; there is
# deliberately no full-history fallback scan and no additional ranking.
# (Explicit deletion requests use get_all_conversation_memories instead.)
AUTOMATIC_CANDIDATE_WINDOW = 20

from services.memory_consolidation_service import (
    TEMPORARY_STATE,
    TIME_DEPENDENT,
    analyze_relation,
    find_exact_duplicate,
    new_details_preserved,
)
from services.memory_decision_service import (
    decide_memory_action,
    decide_memories_to_delete,
)


def normalize_memory_id(memory_id):
    """Strictly normalize positive memory IDs without lossy coercion.

    Positive ASCII numeric strings remain supported for compatibility with
    existing single-memory decision tests/callers. Booleans, fractional or
    unsafe floats, malformed strings, and non-positive IDs are rejected.
    """
    return normalize_positive_id(memory_id, allow_numeric_string=True)


def get_recent_memories(conversation_id: str, limit: int = AUTOMATIC_CANDIDATE_WINDOW):
    """Latest ``limit`` memories of this conversation, newest first (by id).

    This is the complete automatic-update candidate set; see
    AUTOMATIC_CANDIDATE_WINDOW for the documented coverage limitation.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, memory
                FROM conversation_memories
                WHERE conversation_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            )

            return cursor.fetchall()


def _save_new_retaining_existing(conversation_id, new_memory, source_ids, allow_new) -> str:
    """Store a statement as its own memory instead of merging/replacing.

    Used when merging would lose information. Provenance is the statement's
    own validated source IDs; the existing memory is not touched.
    """
    if not allow_new:
        print("NEW action blocked; nothing stored.")
        return "SKIPPED"
    saved = save_memory(
        conversation_id=conversation_id,
        memory_text=new_memory,
        source_message_ids=source_ids,
    )
    return "SAVED" if saved else "SKIPPED"


def get_all_conversation_memories(conversation_id: str):
    """
    Fetch every memory belonging to this conversation only.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, memory
                FROM conversation_memories
                WHERE conversation_id = %s
                ORDER BY id ASC
                """,
                (conversation_id,),
            )

            rows = cursor.fetchall()

    return [
        (int(memory_id), memory_text)
        for memory_id, memory_text in rows
    ]


def process_memory(
    conversation_id: str,
    new_memory: str,
    source_message_id: int | None = None,
    candidate_memories=None,
    allow_new: bool = True,
    delete_only: bool = False,
    allow_delete: bool = False,
    source_message_ids: list[int] | None = None,
) -> str:

    # Validate supplied provenance before candidate lookup or a model decision.
    # Explicit delete-only operations do not create facts and need no source;
    # every NEW/DUPLICATE/UPDATE path must carry valid user-message evidence.
    source_ids = normalize_source_ids(
        source_message_id, source_message_ids
    )
    if not source_ids and not (delete_only or allow_delete):
        print("Memory processing refused: source message ID is required.")
        return "UNCERTAIN"

    # Task 4: trim-only normalization before the decision model sees the text
    # and before any write. Non-string or blank text is rejected, not saved.
    new_memory = normalize_memory_text(new_memory)
    if new_memory is None:
        print("Memory processing refused: memory text is empty or not text.")
        return "UNCERTAIN"

    if candidate_memories is None:
        existing_memories = get_recent_memories(conversation_id)
    else:
        existing_memories = candidate_memories

    normalized_memories = []

    for memory_id, memory_text in existing_memories:
        normalized_id = normalize_memory_id(memory_id)

        if normalized_id is not None:
            normalized_memories.append(
                (normalized_id, memory_text)
            )

    existing_memories = normalized_memories

    # Phase 5 observability: ids and counts only (no memory content in logs).
    print(
        f"\nExisting memory candidates: {len(existing_memories)} "
        f"(ids {[memory_id for memory_id, _ in existing_memories]})"
    )

    if not existing_memories:
        print("No existing memories available.")

        if delete_only:
            return "UNCERTAIN"

        if not source_ids:
            print("Memory creation refused: source message ID is required.")
            return "UNCERTAIN"

        if not allow_new:
            return "SKIPPED"

        saved = save_memory(
            conversation_id=conversation_id,
            memory_text=new_memory,
            source_message_ids=source_ids,
        )

        return "SAVED" if saved else "SKIPPED"

    # Phase 3 dedup: an exact restatement (same text ignoring case, spacing and
    # trailing punctuation) of a candidate is a DUPLICATE without a model call.
    # The new source is linked as confirmation; nothing is overwritten.
    if not delete_only and source_ids:
        exact_id = find_exact_duplicate(new_memory, existing_memories)
        if exact_id is not None:
            confirm_memory(
                conversation_id=conversation_id,
                memory_id=exact_id,
                source_message_ids=source_ids,
            )
            print(f"Exact duplicate of memory {exact_id}: confirmation linked, nothing saved.")
            return "SKIPPED"

    decision =decide_memory_action(
        new_memory=new_memory,
        existing_memories=existing_memories,
    )

    action = str(
        decision.get("action", "UNCERTAIN")
    ).upper().strip()

    memory_id = normalize_memory_id(
        decision.get("memory_id")
    )

    updated_memory = decision.get("updated_memory")

    print(
        "\nMemory decision: action="
        f"{action} memory_id={memory_id} "
        f"updated_text_chars={len(updated_memory) if isinstance(updated_memory, str) else 0}"
    )

    valid_ids = {
        existing_id
        for existing_id, _ in existing_memories
    }
    existing_text_by_id = dict(existing_memories)

    # Automatic memory extraction must never delete stored memories.
    # Explicit deletion is permitted only through delete_only mode
    # or an explicitly authorized allow_delete=True call.
    if action == "DELETE" and not (allow_delete or delete_only):
        print("DELETE action blocked in automatic memory extraction.")
        return "SKIPPED"

    if delete_only and action != "DELETE":
        print("Delete-only mode rejected action:", action)
        return "UNCERTAIN"

    if action in {"NEW", "DUPLICATE", "UPDATE"} and not source_ids:
        print("Memory write/update decision rejected: source message ID is required.")
        return "UNCERTAIN"

    if action == "NEW":

        if not allow_new:
            print("NEW action blocked.")
            return "SKIPPED"

        saved = save_memory(
            conversation_id=conversation_id,
            memory_text=new_memory,
            source_message_ids=source_ids,
        )

        return "SAVED" if saved else "SKIPPED"

    elif action == "DUPLICATE":

        # Phase 3: a "duplicate" that carries a number, amount, date, time or
        # version the existing memory does not have is a genuinely new detail.
        # Keep it as a separate memory instead of discarding it.
        if memory_id in valid_ids and not new_details_preserved(
            new_memory, existing_text_by_id[memory_id]
        ):
            print("DUPLICATE decision rejected: the new statement has details "
                  "the existing memory lacks; keeping both.")
            return _save_new_retaining_existing(
                conversation_id, new_memory, source_ids, allow_new
            )

        # The restating message becomes supporting evidence of the existing
        # memory. Without a valid memory id nothing is linked (no guessing).
        if memory_id in valid_ids:
            confirm_memory(
                conversation_id=conversation_id,
                memory_id=memory_id,
                source_message_ids=source_ids,
            )
        else:
            print("Duplicate without a valid memory id: not linked.")

        print("Duplicate memory skipped.")
        return "SKIPPED"

    elif action == "UPDATE":

        if memory_id not in valid_ids:
            print("Invalid memory ID returned by Gemini.")
            return "UNCERTAIN"

        # Task 4: the model's replacement text must be a non-blank string;
        # it is trimmed only (no str() coercion of numbers/objects).
        updated_text = normalize_memory_text(updated_memory)
        if updated_text is None:
            print("Updated memory text is empty or not text.")
            return "UNCERTAIN"

        # Phase 3 conflict handling (auditable, conservative). Replacement is
        # allowed only when it cannot destroy information:
        #   * a temporary state ("today", "right now") never overwrites a fact;
        #   * different dates/years may both be true (time-dependent facts);
        #   * the replacement must keep every material detail of the new
        #     statement (numbers, amounts, dates, versions).
        # Otherwise the existing memory is kept unchanged and the new statement
        # is stored as its own memory with its own sources.
        relation = analyze_relation(existing_text_by_id[memory_id], new_memory)
        print(f"Update relation evidence: {relation} (memory {memory_id})")
        if relation in (TEMPORARY_STATE, TIME_DEPENDENT) or not new_details_preserved(
            new_memory, updated_text
        ):
            print("UPDATE not applied as a replacement; keeping the existing "
                  "memory and storing the new statement separately.")
            return _save_new_retaining_existing(
                conversation_id, new_memory, source_ids, allow_new
            )

        updated = update_memory(
            conversation_id=conversation_id,
            memory_id=memory_id,
            new_memory_text=updated_text,
            source_message_ids=source_ids,
        )

        return "UPDATED" if updated else "SKIPPED"

    elif action == "DELETE":

        if memory_id not in valid_ids:
            print("DELETE blocked: invalid memory ID.")
            return "UNCERTAIN"

        deleted = delete_memory(
            conversation_id=conversation_id,
            memory_id=memory_id,
        )

        return "DELETED" if deleted else "SKIPPED"

    return "UNCERTAIN"


def delete_matching_memories(
    conversation_id: str,
    user_request: str,
) -> dict:
    """
    Identify and delete multiple memories matching the user's request.

    The candidate list is ALWAYS every memory of this conversation
    (loaded here from the database); callers cannot supply a partial
    list. All candidates and all deletions are scoped to the supplied
    conversation_id.
    """

    deleted_ids = []
    deleted_memories = []
    skipped_ids = []
    failed_ids = []

    # Always use all conversation memories, never a partial or
    # semantic-search subset.
    existing_memories = get_all_conversation_memories(
        conversation_id
    )

    normalized_memories = []

    for memory_id, memory_text in existing_memories:
        memory_id = normalize_memory_id(memory_id)

        if memory_id is not None and memory_text:
            normalized_memories.append(
                (memory_id, memory_text)
            )

    existing_memories = normalized_memories

    print("\nStarting multi-memory deletion...")
    print(f"Conversation memories found: {len(existing_memories)}")

    if not existing_memories:
        return {
            "status": "SKIPPED",
            "deleted_ids": [],
            "deleted_count": 0,
            "skipped_ids": [],
            "failed_ids": [],
        }

        # Ask Gemini to classify the deletion request.
    decision = decide_memories_to_delete(
        user_request=user_request,
        existing_memories=existing_memories,
    )

    # Fail-safe: anything that is not a well-formed classifier answer is
    # treated as UNCERTAIN and can never lead to a deletion.
    if not isinstance(decision, dict):
        decision = {}

    decision_status = decision.get(
        "status",
        "UNCERTAIN",
    )

    selected_ids = decision.get(
        "memory_ids",
        [],
    )

    if not isinstance(selected_ids, list):
        selected_ids = []

    valid_ids = {
        memory_id
        for memory_id, _ in existing_memories
    }

    # Only genuine integer ids that belong to this conversation survive
    # (bool is an int subclass and unhashable values are rejected).
    selected_ids = [
        memory_id
        for memory_id in selected_ids
        if isinstance(memory_id, int)
        and not isinstance(memory_id, bool)
        and memory_id in valid_ids
    ]

    print("\nGemini deletion decision:", decision)

    # Ambiguous request: do not delete anything.
    if decision_status == "UNCERTAIN":
        return {
            "status": "UNCERTAIN",
            "deleted_ids": [],
            "deleted_count": 0,
            "skipped_ids": list(valid_ids),
            "failed_ids": [],
        }

    # Only an explicit DELETE may proceed. Unknown, missing or malformed
    # statuses (e.g. "MAYBE", None, a list) are treated as UNCERTAIN.
    if decision_status not in ("DELETE", "NO_MATCH"):
        print(f"Unrecognised classifier status {decision_status!r}: nothing deleted.")
        return {
            "status": "UNCERTAIN",
            "deleted_ids": [],
            "deleted_count": 0,
            "skipped_ids": list(valid_ids),
            "failed_ids": [],
        }

    # No memory matches the user's request.
    if decision_status == "NO_MATCH" or not selected_ids:
        return {
            "status": "NO_MATCH",
            "deleted_ids": [],
            "deleted_count": 0,
            "skipped_ids": list(valid_ids),
            "failed_ids": [],
        }

    selected_id_set = set(selected_ids)

    skipped_ids = [
        memory_id
        for memory_id, _ in existing_memories
        if memory_id not in selected_id_set
    ]

    print("\nGemini selected memory IDs:", selected_ids)

    # Capture text + source message IDs BEFORE deleting so callers can
    # clean the summary / exclude source messages. Conversation-scoped.
    memory_details = get_memory_details(
        conversation_id,
        selected_ids,
    )

    for memory_id in selected_ids:

        print(f"\nDeleting memory ID: {memory_id}")

        try:
            # Storage layer verifies conversation ownership again.
            deleted = delete_memory(
                conversation_id=conversation_id,
                memory_id=memory_id,
            )

            if deleted:
                deleted_ids.append(memory_id)

                if memory_id in memory_details:
                    deleted_memories.append(memory_details[memory_id])
            else:
                failed_ids.append(memory_id)

        except Exception as exc:
            failed_ids.append(memory_id)
            print(f"Deletion error for ID {memory_id}: {exc}")

    print("\n===== MULTI-MEMORY DELETION SUMMARY =====")
    print(f"Deleted: {len(deleted_ids)}")
    print(f"Skipped: {len(skipped_ids)}")
    print(f"Failed: {len(failed_ids)}")
    print(f"Deleted IDs: {deleted_ids}")

    return {
        "status": "DELETED" if deleted_ids else "FAILED",
        "deleted_ids": deleted_ids,
        "deleted_memories": deleted_memories,
        "deleted_count": len(deleted_ids),
        "skipped_ids": skipped_ids,
        "failed_ids": failed_ids,
    }
