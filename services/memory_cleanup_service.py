import json
import re
import uuid

from services.database import get_connection

from services.llm_service import generate_answer
from services.memory_storage_service import normalize_positive_id
from services.conversation_service import (
    get_conversation_summary,
    update_conversation_summary,
    clear_summary_and_advance_checkpoints,
    mark_messages_excluded,
    get_paired_assistant_ids,
    get_live_messages,
)


# Validation limits for a rewritten summary.
MIN_LENGTH_RATIO = 0.4
MAX_LENGTH_RATIO = 1.05

EMPTY_SENTINEL = "EMPTY"


def _request_block(user_request: str | None) -> str:
    if not user_request or not user_request.strip():
        return "(not available)"

    return user_request.strip()


def _build_rewrite_prompt(
    summary: str,
    deleted_texts: list[str],
    user_request: str | None = None,
) -> str:
    deleted_block = "\n".join(f"- {text}" for text in deleted_texts)

    return f"""
You are editing a conversation summary because the user asked the
assistant to FORGET some information.

CURRENT SUMMARY:
{summary}

THE USER'S ORIGINAL REQUEST:
{_request_block(user_request)}

MEMORIES THAT WERE DELETED FOR THIS REQUEST:
{deleted_block}

TASK:
Remove every statement that states, repeats, or implies the
deleted memories, AND everything else in the summary that falls
under the scope of the user's original request. For example, if the
request was to forget technology preferences, remove ALL technology
details (programming languages, databases, frameworks, libraries,
tools and technology stacks), not only the ones listed above.
Keep every fact that is outside that scope exactly as it is.

RULES:
- Do NOT add any new information.
- Do NOT rephrase or shorten unrelated content.
- Do NOT mention that anything was removed.
- If the summary contains nothing about the forgotten information,
  return the summary unchanged.
- If nothing is left after removal, return exactly: {EMPTY_SENTINEL}
- Return ONLY the edited summary.

EDITED SUMMARY:
"""


def _validate_rewrite(
    original: str,
    rewritten: str,
    deleted_texts: list[str],
) -> bool:
    """Reject rewrites that look destructive or still leak the fact."""

    if not rewritten or not rewritten.strip():
        return False

    ratio = len(rewritten) / max(len(original), 1)

    if ratio < MIN_LENGTH_RATIO or ratio > MAX_LENGTH_RATIO:
        return False

    lowered = rewritten.lower()

    for text in deleted_texts:
        text = text.strip().lower().rstrip(".")

        if text and text in lowered:
            return False

    return True


def _summary_still_contains_forgotten(
    summary: str,
    deleted_texts: list[str],
    user_request: str | None,
) -> bool:
    """
    Semantic check: does the summary still state or imply anything the
    user asked to forget? Returns True when it does OR when the answer
    cannot be determined (uncertain is never accepted).
    """

    deleted_block = "\n".join(f"- {text}" for text in deleted_texts)

    prompt = f"""
The user asked an assistant to FORGET information.

THE USER'S ORIGINAL REQUEST:
{_request_block(user_request)}

MEMORIES THAT WERE DELETED FOR THIS REQUEST:
{deleted_block}

SUMMARY TO CHECK:
{summary}

Does the summary still state, repeat or imply ANY information that
the user asked to forget, either the deleted memories or anything
else within the scope of the original request (for a request about
technology: any programming language, database, framework, library,
tool or technology stack)?

Return ONLY valid JSON:
{{"still_contains": true | false, "evidence": "short quote or empty"}}
"""

    try:
        response = generate_answer(prompt)
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()
        data = json.loads(cleaned)
        value = data["still_contains"]

    except Exception as error:
        print(f"Summary verification failed ({error}). Treating as unsafe.")
        return True

    if value is True:
        # Phase 7 privacy: never echo the forgotten information itself to logs.
        evidence = data.get("evidence")
        print("Summary still contains forgotten info "
              f"(evidence length {len(evidence) if isinstance(evidence, str) else 0}).")
        return True

    if value is False:
        return False

    # Anything that is not a clean boolean is treated as unsafe.
    return True


def rewrite_summary_without(
    conversation_id: str,
    deleted_texts: list[str],
    user_request: str | None = None,
) -> str:
    """
    Remove deleted information from the conversation summary.

    Uses the deleted memory texts AND the user's original request, then
    verifies the result semantically. A forgotten fact is never allowed
    to stay in the summary: any failure or uncertainty clears it and fences
    both memory pipelines at current conversation history.

    Returns one of:
      NO_SUMMARY  - nothing to clean
      UNCHANGED   - verified: nothing to remove
      REWRITTEN   - summary rewritten and verified
      EMPTIED     - nothing remained after removal
      RESET       - rewrite failed/invalid/unverified; summary cleared and
                    checkpoints advanced past current history
    """

    deleted_texts = [t for t in deleted_texts if t and t.strip()]

    summary = get_conversation_summary(conversation_id)

    if not summary.strip() or not deleted_texts:
        return "NO_SUMMARY"

    try:
        rewritten = generate_answer(
            _build_rewrite_prompt(summary, deleted_texts, user_request)
        ).strip()

    except Exception as error:
        print(f"Summary rewrite failed ({error}). Clearing and fencing summary.")
        clear_summary_and_advance_checkpoints(conversation_id)
        return "RESET"

    if rewritten.upper() == EMPTY_SENTINEL:
        update_conversation_summary(conversation_id, "")
        return "EMPTIED"

    if not _validate_rewrite(summary, rewritten, deleted_texts):
        print("Summary rewrite failed validation. Clearing and fencing summary.")
        clear_summary_and_advance_checkpoints(conversation_id)
        return "RESET"

    # Semantic verification (also runs when the model changed nothing).
    if _summary_still_contains_forgotten(
        rewritten, deleted_texts, user_request
    ):
        print("Summary failed semantic verification. Clearing and fencing summary.")
        clear_summary_and_advance_checkpoints(conversation_id)
        return "RESET"

    if rewritten == summary.strip():
        return "UNCHANGED"

    update_conversation_summary(conversation_id, rewritten)
    return "REWRITTEN"


def find_echo_message_ids(
    conversation_id: str,
    deleted_texts: list[str],
    scan_limit: int = 40,
) -> list[int]:
    """
    Ask the model which recent live messages still state or repeat the
    forgotten information (for example an assistant reply such as
    "I will explain in simple Hinglish"). Only IDs from this
    conversation's own message list are accepted. Failures return [].
    """

    deleted_texts = [t for t in deleted_texts if t and t.strip()]
    messages = get_live_messages(conversation_id, limit=scan_limit)

    if not deleted_texts or not messages:
        return []

    valid_ids = {message["id"] for message in messages}

    messages_block = "\n".join(
        f"[id={m['id']}] {m['role']}: {m['content'][:600]}"
        for m in messages
    )
    deleted_block = "\n".join(f"- {t}" for t in deleted_texts)

    prompt = f"""
The user asked the assistant to FORGET this information:
{deleted_block}

RECENT MESSAGES:
{messages_block}

Which messages state, repeat, confirm or depend on the forgotten
information (including assistant messages that mention it or are
written because of it)? Do NOT select messages about unrelated
topics. When unsure, do not select.

Return ONLY a JSON array of message ids, for example [12, 15].
Return [] if none.
"""

    try:
        response = generate_answer(prompt)
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()
        data = json.loads(cleaned)

    except Exception as error:
        print(f"Echo-message scan failed ({error}). Skipping.")
        return []

    if not isinstance(data, list):
        return []

    selected = []

    for value in data:
        value = normalize_positive_id(value, allow_integral_float=False)
        if value is None:
            continue

        if value in valid_ids and value not in selected:
            selected.append(value)

    return selected


def _owned_source_ids(conversation_id, source_ids):
    """Resolve actual user-source ownership without guessing historical origins.

    An assistant-only historical reference cannot establish which user
    messages contained the forgotten fact, so it requires the unknown fence.
    """
    if not source_ids:
        return set()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM messages WHERE conversation_id = %s AND id = ANY(%s::bigint[]) AND role = 'user'",
            (uuid.UUID(str(conversation_id)), list(source_ids)),
        ).fetchall()
    return {row[0] for row in rows}


def apply_deletion_cleanup(
    conversation_id: str,
    deleted_memories: list[dict],
    extra_message_ids: list[int] | None = None,
    user_request: str | None = None,
) -> dict:
    """
    After memories were deleted, exclude recorded sources and their
    immediately adjacent assistant replies. Echo scanning is supplemental.
    If any deleted memory has unknown provenance, clear the summary, fence
    summary and extraction checkpoints at current history, and report an
    incomplete cleanup. All operations are scoped to conversation_id.
    """

    deleted_memories = deleted_memories or []
    source_ids = set()
    unknown_provenance = not deleted_memories

    for item in deleted_memories:
        raw_ids = []
        listed_ids = item.get("source_message_ids")
        if listed_ids is not None:
            if isinstance(listed_ids, (list, tuple)):
                raw_ids.extend(listed_ids)
            else:
                raw_ids.append(listed_ids)

        scalar_id = item.get("source_message_id")
        if scalar_id is not None:
            raw_ids.append(scalar_id)

        item_ids = set()
        for source_id in raw_ids:
            valid_id = normalize_positive_id(source_id, allow_integral_float=False)
            if valid_id is not None:
                item_ids.add(valid_id)
            else:
                unknown_provenance = True

        if not item_ids:
            unknown_provenance = True
        source_ids.update(item_ids)

    owned_ids = _owned_source_ids(conversation_id, source_ids)
    if source_ids - owned_ids:
        unknown_provenance = True
    source_ids = sorted(owned_ids)

    # Also exclude the assistant reply that followed each source user
    # message: it often repeats the forgotten fact.
    paired_ids = get_paired_assistant_ids(conversation_id, source_ids)

    message_ids = (
        list(source_ids)
        + list(paired_ids)
        + list(extra_message_ids or [])
    )

    # 1. Deterministic exclusion: every recorded source message, its
    #    paired assistant reply and the deletion-turn messages. This is
    #    committed first and never depends on an LLM.
    excluded = mark_messages_excluded(conversation_id, message_ids)

    # 2. Supplemental only: scan recent messages for additional echoes.
    #    Source links and the checkpoint fence remain the safety mechanism;
    #    a failed or short-window scan cannot make old messages eligible.
    echo_ids = []

    try:
        echo_ids = find_echo_message_ids(
            conversation_id,
            [item["memory"] for item in deleted_memories],
        )
        excluded += mark_messages_excluded(conversation_id, echo_ids)

    except Exception as error:
        echo_ids = []
        print(f"Echo scan skipped ({error}); deterministic cleanup kept.")

    rewrite_status = rewrite_summary_without(
        conversation_id,
        [item["memory"] for item in deleted_memories],
        user_request=user_request,
    )

    if unknown_provenance:
        # Unknown origins cannot be reconstructed from recent echoes. Keep
        # original message rows intact, but prevent pre-cleanup history from
        # entering either generated summary or automatic extraction again.
        if rewrite_status != "RESET":
            clear_summary_and_advance_checkpoints(conversation_id)
        status = "INCOMPLETE"
        summary_status = "CLEARED_UNKNOWN_PROVENANCE"
        print(
            "Memory deleted, historical cleanup incomplete: source "
            "provenance is unavailable; the summary was cleared and both "
            "checkpoints were advanced past current history."
        )
    else:
        status = "COMPLETE"
        summary_status = rewrite_status
        print("Historical memory cleanup completed with recorded provenance.")

    return {
        "status": status,
        "provenance_status": "UNKNOWN" if unknown_provenance else "KNOWN",
        "messages_excluded": excluded,
        "echo_messages_excluded": len(echo_ids),
        "summary_status": summary_status,
        "rewrite_status": rewrite_status,
        "checkpoints_fenced": unknown_provenance or rewrite_status == "RESET",
    }
