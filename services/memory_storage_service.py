
from services.database import get_connection
from services.embedding_service import generate_embeddings
from pgvector import Vector


SIMILARITY_THRESHOLD = 0.90

LINK_KINDS = ("origin", "update", "confirmation", "legacy")


def normalize_source_ids(source_message_id=None, source_message_ids=None) -> list[int]:
    """
    Ordered, de-duplicated list of contributing message ids. The singular
    argument (kept for backward compatibility) comes first.
    """
    ordered = []

    candidates = []
    if source_message_id is not None:
        candidates.append(source_message_id)
    candidates.extend(source_message_ids or [])

    for value in candidates:
        if value is None:
            continue
        value = int(value)
        if value not in ordered:
            ordered.append(value)

    return ordered


def save_memory(
    conversation_id: str,
    memory_text: str,
    source_message_id: int | None = None,
    source_message_ids: list[int] | None = None,
    link_kind: str = "origin",
) -> bool:

    memory_text = memory_text.strip()

    if not memory_text:
        return False

    source_ids = normalize_source_ids(source_message_id, source_message_ids)

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
                ORDER BY embedding <=> %s
                LIMIT 1
                """,
                (
                    embedding_vector,
                    conversation_id,
                    embedding_vector,
                ),
            )

            existing_memory = cursor.fetchone()

            if existing_memory:
                memory_id, existing_text, distance = existing_memory

                similarity = 1 - distance

                print(f"Similarity score: {similarity:.3f}")

                if similarity >= SIMILARITY_THRESHOLD:
                    print(
                        "Semantic duplicate skipped. "
                        f"Similarity: {similarity:.3f}"
                    )
                    print(f"Existing memory: {existing_text}")

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

    ids = [int(i) for i in memory_ids]

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
    _validate_source_messages(cursor, conversation_id, [int(source_message_id)])


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
            (conversation_id, memory_id, source_message_id, link_kind)
        VALUES (%s, %s, %s, %s)
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
    source_ids = normalize_source_ids(None, source_message_ids)

    if not source_ids:
        return False

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


def delete_memory(
    conversation_id: str,
    memory_id: int,
) -> bool:

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
            print("Memory text:", memory_text)

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

    new_memory_text = new_memory_text.strip()

    if not new_memory_text:
        print("Memory text cannot be empty.")
        return False

    source_ids = normalize_source_ids(source_message_id, source_message_ids)

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
