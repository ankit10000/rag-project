import json
import re

from services.automatic_memory_service import process_memory
from services.llm_service import generate_answer
from services.conversation_service import (
    get_messages_to_summarize,
    update_conversation_memory
)
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
    source_message_id is kept only if it is one of the batch's
    message IDs; otherwise it becomes None.
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
            continue

        text = str(item.get("memory") or "").strip()

        if not text:
            continue

        try:
            source_id = int(item.get("source_message_id"))
        except (TypeError, ValueError):
            source_id = None

        if source_id not in valid_ids:
            source_id = None

        memories.append(
            {"memory": text, "source_message_id": source_id}
        )

    return memories


def extract_memories(messages: list[dict]) -> list[dict]:
    """
    Extract useful long-term memories from conversation messages.

    Returns a list of {"memory": str, "source_message_id": int | None}.
    source_message_id is the batch message the memory came from, or
    None when it could not be determined reliably.
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

    valid_ids = {
        message["id"]
        for message in user_messages
        if message.get("id") is not None
    }

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
- Keep each memory concise and self-contained.
- For each memory, set source_message_id to the [id=N] of the
  user message that states the fact.
- If no useful memory exists, return exactly: []

USER MESSAGES:
{conversation_text}

IMPORTANT:
Return ONLY a JSON array, for example:
[
  {{"memory": "User prefers simple Hinglish explanations.", "source_message_id": 12}}
]
"""

    response = (generate_answer(prompt) or "").strip()

    if not response or response.upper() == "NONE":
        return []

    memories = _parse_json_memories(response, valid_ids)

    if memories is None:
        # Model ignored the JSON format: fall back to bullet parsing.
        # Per-memory source IDs are unknown in this case.
        print("Memory extraction: JSON parsing failed, using bullet fallback.")

        memories = [
            {"memory": text, "source_message_id": None}
            for text in _parse_bullet_memories(response)
        ]

        if not memories:
            print("Memory extraction: no memories parsed from response.")

    return memories


def extract_and_save_memories(
    conversation_id,
    messages,
    source_message_id=None,
):
    memories = extract_memories(messages)

    if not memories:
        print("No memories extracted.")
        return []

    processed_memories = []

    # Fallback attribution: the last USER message of the batch (an
    # assistant message must never be recorded as a memory's source).
    last_user_id = next(
        (
            message["id"]
            for message in reversed(messages)
            if message.get("role") == "user"
            and message.get("id") is not None
        ),
        None,
    )

    fallback_source_id = (
        last_user_id if last_user_id is not None else source_message_id
    )

    for item in memories:
        memory = item["memory"]

        # Per-memory ID when known; otherwise the fallback above.
        memory_source_id = item.get("source_message_id")

        if memory_source_id is None:
            memory_source_id = fallback_source_id

        status = process_memory(
            conversation_id=conversation_id,
            new_memory=memory,
            source_message_id=memory_source_id,
            allow_new=True,
            delete_only=False,
        )

        print(
            f"Memory processing status: {status} "
            f"(source_message_id={memory_source_id})"
        )

        if status in {"SAVED", "UPDATED"}:
            processed_memories.append(memory)

    print(
        f"Processed {len(memories)} memories. "
        f"{len(processed_memories)} changes applied."
    )

    return processed_memories