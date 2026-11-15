import json
import re

from services.automatic_memory_service import process_memory
from services.llm_service import generate_answer
from services.conversation_service import (
    get_messages_to_summarize,
    update_conversation_memory
)
from services.memory_storage_service import (
    normalize_memory_text,
    normalize_positive_id,
    normalize_source_ids,
    validate_source_messages,
)


# ---------------------------------------------------------------------------
# Phase 1 Task 4 extraction-result contract
#
# extract_memories() / extract_and_save_memories() have exactly three outcomes:
#   1. success with records : a non-empty list (every record has a trimmed,
#                             non-empty "memory" string and validated sources)
#   2. success, no memories : [] -- ONLY for an explicit "NONE" response
#                             (case-insensitive, nothing else), a JSON empty
#                             array "[]" (optionally in a ```json fence), or a
#                             batch that contains no user messages (no model
#                             call is made)
#   3. failure              : MemoryExtractionError (or its subclass
#                             InvalidMemoryProvenanceError) -- empty, non-text,
#                             malformed, ambiguous or non-list responses,
#                             malformed items, missing/invalid/out-of-batch
#                             source IDs, bullet-style output (it carries no
#                             per-memory source IDs), unresolved decisions.
# A failure is never converted into []. Callers advance the extraction
# checkpoint only after outcome 1 or 2 returns normally (see main.py).
# ---------------------------------------------------------------------------
EXPLICIT_NO_MEMORY_TOKEN = "NONE"


class MemoryExtractionError(RuntimeError):
    """An extraction batch was not safely completed and must not checkpoint."""


class InvalidMemoryProvenanceError(MemoryExtractionError):
    """At least one extracted memory did not have explicit valid sources."""
def update_long_term_memory(
    conversation_id: str,
    keep_recent: int = 6,
    min_messages: int = 10
):

    existing_summary, messages = get_messages_to_summarize(
        conversation_id,
        keep_recent
    )

    if len(messages) < min_messages:
        print(
            f"Memory update skipped. "
            f"{len(messages)} older messages available; "
            f"{min_messages} required."
        )
        return

    print(f"Summarizing {len(messages)} older messages...")

    new_summary = summarize_conversation(
        existing_summary,
        messages
    )

    if not new_summary:
        raise ValueError("Gemini returned an empty summary")

    last_message_id = messages[-1]["id"]

    update_conversation_memory(
        conversation_id,
        new_summary,
        last_message_id
    )

    print("Long-term memory updated successfully!")

def summarize_conversation(
    existing_summary: str,
    messages: list[dict]
) -> str:

    if not messages:
        return existing_summary

    conversation_text = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in messages
    )

    prompt = f"""
You are a conversation memory summarization assistant.

Your task is to maintain a useful long-term memory
of the conversation.

EXISTING SUMMARY:
{existing_summary or "No previous summary."}

NEW CONVERSATION MESSAGES:
{conversation_text}

INSTRUCTIONS:

1. Preserve important facts, names, IDs, dates and numbers.
2. Preserve questions and their answers when they contain useful information.
3. Remember the user's goals, preferences and ongoing tasks.
4. Combine related information into meaningful topics.
5. Remove greetings, repetition and irrelevant conversation.
6. Never invent or assume facts.
7. Keep the summary concise but information-rich.
8. If an existing summary is provided, update it rather than replacing useful information.
9. Return ONLY the updated summary.

UPDATED SUMMARY:
"""

    return generate_answer(prompt).strip()




def _parse_bullet_memories(response: str) -> list[str]:
    """Fallback parser for bullet-style output (-, *, bullet char)."""

    memories = []

    for line in response.splitlines():
        line = line.strip()
        match = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)

        if match and match.group(1).strip():
            memories.append(match.group(1).strip())

    return memories


def _parse_json_memories(response: str, valid_ids: set):
    """
    Parse a JSON array of {"memory", "source_message_id"} objects.

    Returns None if the response is not valid JSON of that shape.
    Every memory must have explicit source IDs that are positive integer IDs
    from this batch's user messages. Any invalid or missing source rejects the
    extraction batch before the caller can write a partial set of memories.
    """

    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, list):
        return None

    memories = []

    for item in data:
        if not isinstance(item, dict):
            raise MemoryExtractionError("extraction returned a malformed memory item")

        # Task 4: the memory must be a string; it is trimmed only (casing,
        # punctuation and internal whitespace are preserved). Numbers, objects
        # or blank text make the whole batch malformed.
        text = normalize_memory_text(item.get("memory"))

        if text is None:
            raise MemoryExtractionError(
                "extraction returned a missing, empty or non-text memory"
            )

        listed = item.get("source_message_ids")
        if listed is not None and not isinstance(listed, list):
            raise InvalidMemoryProvenanceError(
                "extraction source_message_ids must be a list"
            )

        try:
            source_ids = normalize_source_ids(
                item.get("source_message_id"), listed, required=True
            )
        except ValueError:
            raise InvalidMemoryProvenanceError(
                "extraction contained missing or invalid source IDs"
            ) from None

        if any(source_id not in valid_ids for source_id in source_ids):
            raise InvalidMemoryProvenanceError(
                "extraction source IDs must identify user messages in this batch"
            )

        memories.append(
            {
                "memory": text,
                "source_message_id": source_ids[0],
                "source_message_ids": source_ids,
            }
        )

    return memories


def extract_memories(messages: list[dict]) -> list[dict]:
    """
    Extract useful long-term memories from conversation messages.

    Returns a list of memories with explicit, validated user-message source
    IDs. Missing, malformed, assistant, or out-of-batch provenance raises
    InvalidMemoryProvenanceError instead of returning a source-less memory.
    """

    if not messages:
        return []

    # Code-level source filter: only the USER's own messages may be a
    # source of memories. Assistant text (guesses, explanations, or a
    # leaked forgotten fact) is never shown to the extractor, so it
    # cannot be saved or used to update a memory.
    user_messages = [
        message for message in messages
        if message.get("role") == "user"
    ]

    if not user_messages:
        return []

    valid_ids = set()
    for message in user_messages:
        message_id = normalize_positive_id(message.get("id"))
        if message_id is None:
            raise MemoryExtractionError(
                "extraction batch contains an invalid user message ID"
            )
        valid_ids.add(message_id)

    conversation_text = "\n".join(
        (
            f"[id={message['id']}] "
            if message.get("id") is not None
            else ""
        )
        + f"user: {message['content']}"
        for message in user_messages
    )

    prompt = f"""
You are a long-term memory extraction assistant.

Extract only useful facts that may matter in future conversations.

Examples of useful memories:
- User's ongoing projects
- Technologies used in a project
- Long-term goals
- Important preferences
- Decisions and constraints
- Important names, IDs, and facts

Do NOT extract:
- Greetings
- Temporary questions
- Generic information
- Repeated facts
- Questions the user asks (a question is not a fact about the user)

Rules:
- The text below contains ONLY the user's own messages.
- Only extract facts the user states about themselves, their
  projects, preferences or goals.
- Only extract facts supported by the conversation.
- Do not invent or infer facts.
- Keep each memory concise and self-contained, one fact per memory.
- Only keep information that is useful in FUTURE conversations
  (profile, preferences, goals, projects, skills, relationships,
  routines). Skip temporary states and one-off details such as
  "I'm tired today" or "right now I'm on the train".
- Never infer sensitive attributes (health, religion, politics,
  sexuality, finances, ethnicity) that the user did not state
  explicitly about themselves.
- Keep exact numbers, amounts, dates, versions and status words
  (e.g. "completed", "no longer") exactly as the user said them.
- Suggestions or answers from the assistant are never user facts.
- For each memory, set source_message_ids to the [id=N] of EVERY
  user message that states or contributes to the fact (a list,
  even when there is only one).
- If no useful memory exists, return exactly: []

USER MESSAGES:
{conversation_text}

IMPORTANT:
Return ONLY a JSON array, for example:
[
  {{"memory": "User prefers simple Hinglish explanations.", "source_message_ids": [12, 14]}}
]
"""

    response = generate_answer(prompt)

    if not isinstance(response, str):
        raise MemoryExtractionError("extractor returned a non-text response")

    response = response.strip()

    if not response:
        raise MemoryExtractionError("extractor returned an empty response")

    # Explicit successful "no memories" outcome (exact token, any case).
    if response.upper() == EXPLICIT_NO_MEMORY_TOKEN:
        return []

    memories = _parse_json_memories(response, valid_ids)

    if memories is None:
        # Model ignored the JSON format: fall back to bullet parsing.
        print("Memory extraction: JSON parsing failed, using bullet fallback.")
        bullet_memories = _parse_bullet_memories(response)
        if bullet_memories:
            raise InvalidMemoryProvenanceError(
                "bullet extraction has no explicit per-memory source IDs"
            )
        raise MemoryExtractionError("extractor response was not parseable")

    return memories


def extract_and_save_memories(
    conversation_id,
    messages,
    source_message_id=None,
):
    """Extract and persist only memories with explicit, validated sources.

    ``source_message_id`` remains as a deprecated call-compatibility argument;
    it is deliberately never used as a fallback attribution.
    """
    memories = extract_memories(messages)

    if not memories:
        print("No memories extracted.")
        return []

    # Validate every memory before the first write so an invalid item cannot
    # leave a partial batch that the caller mistakes for a completed extract.
    validated = []
    batch_user_ids = {
        normalize_positive_id(message.get("id"))
        for message in messages
        if message.get("role") == "user"
    }
    for item in memories:
        try:
            source_ids = normalize_source_ids(
                item.get("source_message_id"),
                item.get("source_message_ids"),
                required=True,
            )
        except (AttributeError, ValueError):
            raise InvalidMemoryProvenanceError(
                "extraction contained missing or invalid source IDs"
            ) from None

        if any(source_id not in batch_user_ids for source_id in source_ids):
            raise InvalidMemoryProvenanceError(
                "extraction source IDs must identify user messages in this batch"
            )
        validated.append((item, source_ids))

    # Task 4: one read-only database check of the whole batch's sources
    # (user messages of THIS conversation) before the first write, so a
    # mixed-validity batch is rejected without saving any of its memories.
    all_source_ids = sorted({sid for _, ids in validated for sid in ids})
    try:
        validate_source_messages(conversation_id, all_source_ids)
    except ValueError:
        raise InvalidMemoryProvenanceError(
            "extraction source IDs are not user messages of this conversation"
        ) from None

    processed_memories = []

    for item, memory_source_ids in validated:
        memory = item["memory"]

        try:
            status = process_memory(
                conversation_id=conversation_id,
                new_memory=memory,
                source_message_ids=memory_source_ids,
                allow_new=True,
                delete_only=False,
            )
        except ValueError:
            raise InvalidMemoryProvenanceError(
                "storage rejected extracted source IDs"
            ) from None

        if status == "UNCERTAIN":
            raise MemoryExtractionError(
                "an extracted memory was unresolved; checkpoint must not advance"
            )

        print(
            f"Memory processing status: {status} "
            f"(source_message_ids={memory_source_ids})"
        )

        if status in {"SAVED", "UPDATED"}:
            processed_memories.append(memory)

    print(
        f"Processed {len(memories)} memories. "
        f"{len(processed_memories)} changes applied."
    )

    return processed_memories
