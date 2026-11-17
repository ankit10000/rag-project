
import re
import math

from services.database import get_connection
from services.embedding_service import generate_embeddings
from services.memory_consolidation_service import new_details_preserved
from pgvector import Vector


SIMILARITY_THRESHOLD = 0.90

LINK_KINDS = ("origin", "update", "confirmation", "legacy")
_BIGINT_MIN = -(2 ** 63)
_BIGINT_MAX = 2 ** 63 - 1
_MAX_SAFE_FLOAT_ID = 2 ** 53 - 1
_NUMERIC_ID_STRING = re.compile(r"[ \t\r\n]*\+?[0-9]+[ \t\r\n]*", re.ASCII)


def normalize_positive_id(
    value,
    *,
    allow_numeric_string=False,
    allow_integral_float=True,
):
    """Return a strictly validated positive bigint ID, or None.

    Booleans are never IDs. Integral floats are accepted only while they are
    exactly representable as integers; fractional, non-finite, and unsafe
    large floats are rejected. Numeric strings are opt-in and restricted to
    positive ASCII decimal strings (optionally surrounded by ASCII whitespace
    and a leading plus).
    """
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        if (
            not allow_integral_float
            or not math.isfinite(value)
            or not value.is_integer()
            or value > _MAX_SAFE_FLOAT_ID
        ):
            return None
        normalized = int(value)
    elif allow_numeric_string and isinstance(value, str):
        if not _NUMERIC_ID_STRING.fullmatch(value):
            return None
        normalized = int(value)
    else:
        return None

    if not (1 <= normalized <= _BIGINT_MAX):
        return None
    return normalized


def normalize_source_ids(
    source_message_id=None,
    source_message_ids=None,
    *,
    required=False,
) -> list[int]:
    """
    Strictly validate and de-duplicate contributing message IDs. The singular
    argument (kept for backward compatibility) comes first. Source IDs must
    be integer or exactly integral, safely representable floats; numeric
    strings are rejected because no source-ID string compatibility contract
    exists.
    """
    ordered = []

    candidates = []
    if source_message_id is not None:
        candidates.append(source_message_id)

    if source_message_ids is not None:
        if not isinstance(source_message_ids, (list, tuple)):
            raise ValueError("source_message_ids must be a list or tuple")
        candidates.extend(source_message_ids)

    for value in candidates:
        if value is None:
            raise ValueError("source message IDs cannot contain null values")
        normalized = normalize_positive_id(value)
        if normalized is None:
            raise ValueError("source message ID must be a positive integer")
        if normalized not in ordered:
            ordered.append(normalized)

    if required and not ordered:
        raise ValueError("at least one source message ID is required")

    return ordered


def normalize_memory_text(text) -> str | None:
    """Phase 1 Task 4 normalization contract: trim-only.

    Returns ``text.strip()`` for a string, preserving casing, punctuation and
    internal whitespace (repeated spaces and newlines are kept). Returns None
    for non-string input and for text that is empty after trimming; callers
    must treat None as "reject, write nothing". This is the single
    normalization used by every memory writer, and the returned string is both
    the persisted memory text and the exact embedding input.
    """
    if not isinstance(text, str):
        return None
    normalized = text.strip()
    return normalized or None


def validate_source_messages(conversation_id: str, source_message_ids) -> list[int]:
    """Read-only pre-write check of a whole set of source IDs.

    Normalizes the IDs (at least one required) and verifies, in one query, that
    every ID is a user message of this conversation. Raises ValueError on the
    first invalid ID; nothing is written. Used to reject an extraction batch
    before its first memory write.
    """
    source_ids = normalize_source_ids(None, source_message_ids, required=True)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            _validate_source_messages(cursor, conversation_id, source_ids)
    return source_ids


def save_memory(
    conversation_id: str,
    memory_text: str,
    source_message_id: int | None = None,
    source_message_ids: list[int] | None = None,
    link_kind: str = "origin",
) -> bool:

    # Task 4: trim-only normalization; the same string is embedded and stored.
    memory_text = normalize_memory_text(memory_text)

    if memory_text is None:
        return False

    source_ids = normalize_source_ids(
        source_message_id, source_message_ids, required=True
    )

    from services.legacy_provenance_quarantine import eligible_memory_ids

    # An unsafe legacy row must never become a duplicate-confirmation target.
    # It remains quarantined; a current, user-supported statement is stored
    # independently instead of reviving the historical row.
    supported_ids = sorted(eligible_memory_ids(conversation_id))

    embedding = generate_embeddings([memory_text])[0]
    embedding_vector = Vector(embedding.tolist())

    with get_connection() as conn:
        with conn.cursor() as cursor:

            # Validate EVERY source before any write; a bad id raises and the
            # whole transaction (including later inserts) is rolled back.
            _validate_source_messages(cursor, conversation_id, source_ids)

            cursor.execute(
                """
                SELECT id, memory,
                       embedding <=> %s AS distance
                FROM conversation_memories
                WHERE conversation_id = %s
                  AND id = ANY(%s::bigint[])
                ORDER BY embedding <=> %s
                LIMIT 1
                """,
                (
                    embedding_vector,
                    conversation_id,
                    supported_ids,
                    embedding_vector,
                ),
            )

            existing_memory = cursor.fetchone()

            if existing_memory:
                memory_id, existing_text, distance = existing_memory

                similarity = 1 - distance

                print(f"Similarity score: {similarity:.3f}")

                # Phase 3: similar wording is not enough. A statement with a
                # number, amount, date, time or version that the nearest memory
                # lacks is a new detail and is stored (threshold unchanged).
                if similarity >= SIMILARITY_THRESHOLD and not new_details_preserved(
                    memory_text, existing_text
                ):
                    print(
                        "Similar memory found but the new text has different "
                        f"details (similarity {similarity:.3f}); storing it separately."
                    )
                elif similarity >= SIMILARITY_THRESHOLD:
                    print(
                        "Semantic duplicate skipped. "
                        f"Similarity: {similarity:.3f}"
                    )
                    print(f"Existing memory id: {memory_id}")

                    # The user restated a fact we already hold: record the
                    # message as supporting evidence of that memory so that
                    # forgetting the memory also forgets this message.
                    _link_memory_sources(
                        cursor, conversation_id, memory_id,
                        source_ids, "confirmation",
                    )
                    return False

            cursor.execute(
                """
                INSERT INTO conversation_memories
                    (conversation_id, memory, embedding, source_message_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    conversation_id,
                    memory_text,
                    embedding_vector,
                    source_ids[0] if source_ids else None,
                ),
            )
            memory_id = cursor.fetchone()[0]
            _link_memory_sources(
                cursor, conversation_id, memory_id, source_ids, link_kind
            )

        conn.commit()

    print("Memory saved successfully.")
    return True


def get_memory_details(
    conversation_id: str,
    memory_ids: list[int],
) -> dict:
    """
    Return {memory_id: {"id", "memory", "source_message_id"}} for the
    given IDs, restricted to this conversation.
    """

    ids = list(dict.fromkeys(
        valid for value in memory_ids
        if (valid := _valid_memory_id(value)) is not None
    ))

    if not ids:
        return {}

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, memory, source_message_id
            FROM conversation_memories
            WHERE conversation_id = %s
              AND id = ANY(%s::bigint[])
            """,
            (conversation_id, ids),
        ).fetchall()

        source_rows = conn.execute(
            """
            SELECT memory_id, source_message_id
            FROM memory_sources
            WHERE conversation_id = %s AND memory_id = ANY(%s::bigint[])
            ORDER BY memory_id, source_message_id
            """,
            (conversation_id, ids),
        ).fetchall()

    sources = {}
    for memory_id, source_id in source_rows:
        sources.setdefault(memory_id, []).append(source_id)

    return {
        row[0]: {
            "id": row[0],
            "memory": row[1],
            "source_message_id": row[2],
            "source_message_ids": sorted(set(
                sources.get(row[0], []) + ([row[2]] if row[2] is not None else [])
            )),
        }
        for row in rows
    }


def _validate_source_messages(cursor, conversation_id, source_ids):
    """
    Every source must be a USER message of this conversation. Raises
    ValueError otherwise (assistant ids, unknown ids and ids of other
    conversations are all rejected; nothing is written).
    """
    if not source_ids:
        return

    cursor.execute(
        """
        SELECT id, role FROM messages
        WHERE conversation_id = %s AND id = ANY(%s::bigint[])
          AND NOT context_excluded
        FOR SHARE
        """,
        (conversation_id, list(source_ids)),
    )
    found = dict(cursor.fetchall())

    for source_id in source_ids:
        if found.get(source_id) != "user":
            raise ValueError(
                "Source message must be a user message in this conversation "
                f"(rejected id {source_id})"
            )


def _validate_source_message(cursor, conversation_id, source_message_id):
    """Single-id form kept for backward compatibility."""
    if source_message_id is None:
        return
    normalized = normalize_positive_id(source_message_id)
    if normalized is None:
        raise ValueError("source message ID must be a positive integer")
    _validate_source_messages(cursor, conversation_id, [normalized])


def _link_memory_sources(cursor, conversation_id, memory_id, source_ids, link_kind):
    if link_kind not in LINK_KINDS:
        raise ValueError(f"unknown link_kind {link_kind!r}")

    for source_id in source_ids:
        _link_memory_source(cursor, conversation_id, memory_id, source_id, link_kind)


def _link_memory_source(cursor, conversation_id, memory_id, source_message_id, link_kind="origin"):
    if source_message_id is None:
        return
    cursor.execute(
        """
        INSERT INTO memory_sources
            (conversation_id, memory_id, source_message_id, link_kind, source_role)
        VALUES (%s, %s, %s, %s, 'user')
        ON CONFLICT (memory_id, source_message_id) DO NOTHING
        """,
        (conversation_id, memory_id, source_message_id, link_kind),
    )


def confirm_memory(
    conversation_id: str,
    memory_id: int,
    source_message_ids: list[int],
) -> bool:
    """
    Record that user message(s) restated an existing memory (link_kind
    'confirmation'). The memory must belong to this conversation; the text
    is not changed. Returns False when the memory is not found here.
    """
    valid_memory_id = normalize_positive_id(
        memory_id, allow_numeric_string=True
    )
    if valid_memory_id is None:
        return False
    memory_id = valid_memory_id

    source_ids = normalize_source_ids(
        None, source_message_ids, required=True
    )

    with get_connection() as conn:
        with conn.cursor() as cursor:
            _validate_source_messages(cursor, conversation_id, source_ids)

            cursor.execute(
                """
                SELECT id FROM conversation_memories
                WHERE id = %s AND conversation_id = %s
                """,
                (memory_id, conversation_id),
            )

            if cursor.fetchone() is None:
                return False

            _link_memory_sources(
                cursor, conversation_id, memory_id, source_ids, "confirmation"
            )

        conn.commit()

    return True


def _valid_memory_id(memory_id):
    """Return memory_id as an int if it is a usable memory id, otherwise None.

    Accepted: positive genuine ints (not bool) and compatible ASCII numeric
    strings such as "2", " 2 ", "+2". The existing delete-ID contract rejects
    all floats (including 2.0), fractional/non-finite values, zero/negative
    values, malformed strings, containers, bytes, and values outside bigint
    range before SQL.
    """
    return normalize_positive_id(
        memory_id,
        allow_numeric_string=True,
        allow_integral_float=False,
    )


def delete_memory(
    conversation_id: str,
    memory_id: int,
) -> bool:

    # D7: validate the raw id before any SQL; invalid ids never reach the database.
    valid_id = _valid_memory_id(memory_id)

    if valid_id is None:
        print(
            "Memory deletion refused: invalid memory ID "
            f"(type {type(memory_id).__name__})."
        )
        return False

    memory_id = valid_id

    print("\n--- Memory deletion diagnostics ---")
    print(f"Requested memory ID: {memory_id}")
    print(f"Requested conversation ID: {conversation_id}")

    with get_connection() as conn:
        with conn.cursor() as cursor:

            # First check which conversation owns this memory ID
            cursor.execute(
                """
                SELECT id, conversation_id::text, memory
                FROM conversation_memories
                WHERE id = %s
                """,
                (memory_id,),
            )

            record = cursor.fetchone()

            if not record:
                print(
                    f"Memory ID {memory_id} does not exist "
                    "in the connected database."
                )
                return False

            actual_id, actual_conversation_id, memory_text = record

            print(f"Database memory ID: {actual_id}")
            print(
                "Actual memory conversation ID:",
                actual_conversation_id,
            )
            # Phase 5 observability: size only, never the memory content.
            print("Memory text length:", len(memory_text or ""))

            # Safety check: refuse cross-conversation deletion
            if str(actual_conversation_id) != str(conversation_id):

                print(
                    "Conversation ID mismatch. "
                    "Deletion blocked for safety."
                )

                return False

            # Delete only when ownership matches
            cursor.execute(
                """
                DELETE FROM conversation_memories
                WHERE id = %s
                  AND conversation_id = %s
                RETURNING id
                """,
                (
                    memory_id,
                    conversation_id,
                ),
            )

            deleted = cursor.fetchone()

        conn.commit()

    if deleted:
        print(f"Memory {memory_id} deleted successfully.")
        return True

    print(
        f"Memory {memory_id} was not deleted. "
        "The database returned no deleted row."
    )

    return False


def update_memory(
    conversation_id: str,
    memory_id: int,
    new_memory_text: str,
    source_message_id: int | None = None,
    source_message_ids: list[int] | None = None,
) -> bool:

    # Task 4: trim-only normalization; the same string is embedded and stored.
    new_memory_text = normalize_memory_text(new_memory_text)

    if new_memory_text is None:
        print("Memory text cannot be empty.")
        return False

    valid_memory_id = normalize_positive_id(
        memory_id, allow_numeric_string=True
    )
    if valid_memory_id is None:
        print("Memory update refused: invalid memory ID.")
        return False
    memory_id = valid_memory_id

    # Stage 7: a content update needs at least one valid user source (same
    # rule as save_memory); a missing source raises ValueError before any
    # embedding or SQL, so content can never change without provenance.
    source_ids = normalize_source_ids(
        source_message_id, source_message_ids, required=True
    )

    embedding = generate_embeddings([new_memory_text])[0]
    embedding_vector = Vector(embedding.tolist())

    with get_connection() as conn:
        with conn.cursor() as cursor:

            _validate_source_messages(cursor, conversation_id, source_ids)

            cursor.execute(
                """
                UPDATE conversation_memories
                SET memory = %s,
                    embedding = %s,
                    source_message_id = COALESCE(%s, source_message_id)
                WHERE id = %s
                  AND conversation_id = %s
                RETURNING id
                """,
                (
                    new_memory_text,
                    embedding_vector,
                    source_ids[0] if source_ids else None,
                    memory_id,
                    conversation_id,
                ),
            )

            updated = cursor.fetchone()
            if updated:
                # Previous links stay; every new contributor is appended.
                _link_memory_sources(
                    cursor, conversation_id, memory_id, source_ids, "update"
                )

        conn.commit()

    if updated:
        print(f"Memory {memory_id} updated successfully.")
        return True

    print(
        f"Memory {memory_id} not found in this conversation."
    )

    return False
