
import json
import re

from services.llm_service import generate_answer


def decide_memory_action(new_memory, existing_memories):
    """
    Decide whether a memory should be NEW, DUPLICATE,
    UPDATE, DELETE, or UNCERTAIN.
    """

    if not existing_memories:
        return {
            "action": "NEW",
            "memory_id": None,
            "updated_memory": None,
        }

    memories_text = "\n".join(
        f"ID: {memory_id} | Memory: {memory_text}"
        for memory_id, memory_text in existing_memories
    )

    prompt = f"""
You are a conservative memory management system.

NEW MEMORY OR USER REQUEST:
{new_memory}

EXISTING MEMORIES:
{memories_text}

Choose exactly one action:

NEW:
Information is unrelated to existing memories.

DUPLICATE:
The information repeats an existing fact without changing it.

UPDATE:
New information clearly corrects or replaces an existing fact.

DELETE:
The user explicitly requests that a stored memory be forgotten,
deleted, or removed.

UNCERTAIN:
The relationship or intent is ambiguous.

Important safety rules:
- Similar facts are not necessarily duplicates.
- "I no longer use X" is a factual update, NOT automatically a delete.
- Only use DELETE for an explicit request to forget/delete/remove stored information.
- Never delete based only on a fact becoming outdated.
- Do not update unrelated facts.
- For UPDATE or DELETE, select an existing memory ID from the list.
- Never invent a memory ID.
- Preserve project names and context to avoid changing unrelated facts.
- Return valid JSON only.

JSON format:
{{
  "action": "NEW | DUPLICATE | UPDATE | DELETE | UNCERTAIN",
  "memory_id": null,
  "updated_memory": null
}}

For UPDATE, provide the memory ID and complete replacement memory.
For DELETE, provide the memory ID and set updated_memory to null.
"""

    uncertain = {
        "action": "UNCERTAIN",
        "memory_id": None,
        "updated_memory": None,
    }

    # D3: an LLM failure (quota, network, timeout, ...) must never escape and
    # must never become a positive action. Only the exception type is logged:
    # no prompt, response text, memory text or credentials.
    try:
        response = generate_answer(prompt)
    except Exception as error:
        print(f"Memory decision LLM call failed ({type(error).__name__}).")
        return dict(uncertain)

    if not isinstance(response, str):
        print("Memory decision parsing failed.")
        return dict(uncertain)

    try:
        response = re.sub(
            r"```(?:json)?\s*|\s*```",
            "",
            response
        ).strip()

        result = json.loads(response)
        action = result.get("action", "").upper()

        allowed_actions = {
            "NEW", "DUPLICATE", "UPDATE", "DELETE", "UNCERTAIN"
        }

        if action not in allowed_actions:
            raise ValueError("Invalid memory action")

        return {
            "action": action,
            "memory_id": result.get("memory_id"),
            "updated_memory": result.get("updated_memory"),
        }

    except (json.JSONDecodeError, ValueError, AttributeError):
        print("Memory decision parsing failed.")

        return dict(uncertain)


def decide_memories_to_delete(user_request, existing_memories):
    """
    Conservatively classify memory deletion requests.

    Returns:
        {
            "status": "DELETE" | "NO_MATCH" | "UNCERTAIN",
            "memory_ids": []
        }
    """

    if not existing_memories:
        return {
            "status": "NO_MATCH",
            "memory_ids": [],
        }

    memories_text = "\n".join(
        f"ID: {memory_id} | Memory: {memory_text}"
        for memory_id, memory_text in existing_memories
    )

    prompt = f"""
You are a highly conservative long-term memory deletion classifier.

USER REQUEST:
{user_request}

AVAILABLE MEMORIES:
{memories_text}

Your task is to decide whether the user clearly wants specific memories deleted.

Return one status:

DELETE:
Only if the user's request clearly and explicitly matches one or more memories.

NO_MATCH:
The request is understandable, but none of the memories clearly match.

UNCERTAIN:
The request is vague, ambiguous, or its scope cannot be confidently determined.

STRICT RULES:
- Delete only memories directly matching the user's requested topic.
- Do not broaden the meaning of the user's request.
- Do not infer that two preferences are related just because both are preferences.
- A language, communication, or explanation-style preference is NOT a technology preference.
- A preference for Hinglish is NOT a preference for Python, JavaScript, React, PostgreSQL, or other technologies.
- "Forget my technology preferences" must NOT select a language or communication preference.
- "Forget my RAG project" may select memories directly about building or implementing the RAG project.
- "Forget my language preference" may select memories about language preference.
- "Forget everything about me" is broad. Return UNCERTAIN and select nothing.
- If you are unsure whether a memory matches, do not select it.
- Never invent or modify memory IDs.
- Never select memories from outside the provided list.

TECHNOLOGY PREFERENCE SCOPE:

- Interpret "my technology preferences", "my tech preferences",
  and "my technology-related details" broadly enough to include
  technology choices, technology stacks, programming languages,
  frameworks, databases, tools, and technologies used in the
  user's projects.

- A memory does NOT need to contain the word "prefer" or
  "preference" to match a technology preference request.

- For example, "The user's RAG project uses Python and PostgreSQL"
  is technology-related information and should match
  "Forget my technology preferences".

- "The user has experience with React and Node.js" also matches
  a technology-related deletion request.

- Do NOT delete communication or explanation-style preferences
  such as Hinglish, concise answers, or simple explanations.

- Do NOT delete unrelated personal, health, family, or lifestyle
  information merely because it is stored as a preference.

POSITIVE EXAMPLES:

Request: "Forget my technology preferences"
Matching memory: "The user's RAG project uses Python and PostgreSQL"
Decision: DELETE that memory.

Request: "Forget my tech stack"
Matching memory: "The user works with React, Node.js, and MongoDB"
Decision: DELETE that memory.

Request: "Forget my language preference"
Matching memory: "The user prefers Hinglish explanations"
Decision: DELETE that memory.

NEGATIVE EXAMPLE:

Request: "Forget my technology preferences"
Memory: "The user prefers Hinglish explanations"
Decision: NO_MATCH for that memory.

Return valid JSON only.

JSON format:
{{
  "status": "DELETE | NO_MATCH | UNCERTAIN",
  "memory_ids": []
}}

If status is NO_MATCH or UNCERTAIN, memory_ids MUST be [].
"""

    uncertain = {
        "status": "UNCERTAIN",
        "memory_ids": [],
    }

    # D4: an LLM failure must never escape and must never authorise deletion.
    # Only the exception type is logged (no prompt, memory text, message or key).
    try:
        response = generate_answer(prompt)
    except Exception as error:
        print(f"Memory deletion decision LLM call failed ({type(error).__name__}).")
        return dict(uncertain, memory_ids=[])

    if not isinstance(response, str):
        print("Memory deletion decision parsing failed.")
        return dict(uncertain, memory_ids=[])

    try:
        response = re.sub(
            r"```(?:json)?\s*|\s*```",
            "",
            response,
        ).strip()

        result = json.loads(response)

        status = str(
            result.get("status", "UNCERTAIN")
        ).upper().strip()

        allowed_statuses = {
            "DELETE",
            "NO_MATCH",
            "UNCERTAIN",
        }

        if status not in allowed_statuses:
            status = "UNCERTAIN"

        if status != "DELETE":
            return {
                "status": status,
                "memory_ids": [],
            }

        memory_ids = result.get("memory_ids", [])

        if not isinstance(memory_ids, list):
            return {
                "status": "UNCERTAIN",
                "memory_ids": [],
            }

        valid_ids = {
            int(memory_id)
            for memory_id, _ in existing_memories
        }

        selected_ids = []

        for memory_id in memory_ids:
            # D5: validate the raw JSON value before any conversion.
            # Only genuine integers and numeric strings (existing contract)
            # are accepted; bool/float/None/list/dict are never coerced
            # into another memory's id.
            if isinstance(memory_id, bool) or not isinstance(memory_id, (int, str)):
                continue

            try:
                memory_id = int(memory_id)
            except (TypeError, ValueError):
                continue

            if (
                memory_id in valid_ids
                and memory_id not in selected_ids
            ):
                selected_ids.append(memory_id)

        if not selected_ids:
            return {
                "status": "NO_MATCH",
                "memory_ids": [],
            }

        return {
            "status": "DELETE",
            "memory_ids": selected_ids,
        }

    except (
        json.JSONDecodeError,
        ValueError,
        AttributeError,
        TypeError,
    ):
        print("Memory deletion decision parsing failed.")

        return {
            "status": "UNCERTAIN",
            "memory_ids": [],
        }