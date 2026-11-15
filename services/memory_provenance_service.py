"""Deterministic memory <-> message provenance.

No text matching or LLM use. Queries and mutations are scoped to one
conversation. Deletion accounts for both the modern join table and the
legacy scalar source column.
"""

import uuid

from services.database import get_connection


def get_memory_sources(conversation_id: str, memory_id: int) -> list[dict]:
    """Every message linked to a memory: [{message_id, role, link_kind, content}]."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ms.source_message_id, ms.source_role, ms.link_kind, m.content
            FROM memory_sources ms
            JOIN messages m
              ON m.conversation_id = ms.conversation_id
             AND m.id = ms.source_message_id
            WHERE ms.conversation_id = %s AND ms.memory_id = %s
            ORDER BY ms.source_message_id
            """,
            (uuid.UUID(str(conversation_id)), int(memory_id)),
        ).fetchall()

    return [
        {"message_id": r[0], "role": r[1], "link_kind": r[2], "content": r[3]}
        for r in rows
    ]


def get_memories_for_message(conversation_id: str, message_id: int) -> list[dict]:
    """Every memory that relies on a message: [{memory_id, memory, link_kind}]."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT cm.id, cm.memory, ms.link_kind
            FROM memory_sources ms
            JOIN conversation_memories cm
              ON cm.conversation_id = ms.conversation_id AND cm.id = ms.memory_id
            WHERE ms.conversation_id = %s AND ms.source_message_id = %s
            ORDER BY cm.id
            """,
            (uuid.UUID(str(conversation_id)), int(message_id)),
        ).fetchall()

    return [{"memory_id": r[0], "memory": r[1], "link_kind": r[2]} for r in rows]


def _has_valid_user_source(conn, conversation_id, memory_id: int) -> bool:
    """Whether a memory still has a same-conversation user source.

    Modern links must agree with both the stored source_role and the actual
    messages.role. Legacy scalar sources have no stored role, so the joined
    message role is authoritative. Assistant-origin links never support a
    claim of verified user provenance.
    """
    row = conn.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM memory_sources ms
            JOIN messages source_message
              ON source_message.conversation_id = ms.conversation_id
             AND source_message.id = ms.source_message_id
            WHERE ms.conversation_id = %s
              AND ms.memory_id = %s
              AND ms.source_role = 'user'
              AND source_message.role = 'user'
            UNION ALL
            SELECT 1
            FROM conversation_memories cm
            JOIN messages source_message
              ON source_message.conversation_id = cm.conversation_id
             AND source_message.id = cm.source_message_id
            WHERE cm.conversation_id = %s
              AND cm.id = %s
              AND source_message.role = 'user'
        )
        """,
        (conversation_id, memory_id, conversation_id, memory_id),
    ).fetchone()
    return bool(row and row[0])


def delete_message_with_provenance(conversation_id: str, message_id: int) -> dict:
    """
    Delete one message of a conversation safely.

    Affected memories are the deduplicated union of modern links and legacy
    scalar references. Both references to the deleted message are detached
    before the message is deleted. Memories are never deleted here: a memory
    is `orphaned` only when neither representation has a remaining valid
    same-conversation user source. All steps run in one connection
    transaction, so any exception rolls back all changes.

    Missing and foreign-conversation messages return the existing safe
    no-op shape: deleted=False, orphaned=[], still_supported=[].
    """
    cid = uuid.UUID(str(conversation_id))
    message_id = int(message_id)

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM messages WHERE conversation_id = %s AND id = %s",
            (cid, message_id),
        ).fetchone()

        if exists is None:
            return {"deleted": False, "orphaned": [], "still_supported": []}

        affected = [
            row[0]
            for row in conn.execute(
                """
                SELECT memory_id
                FROM memory_sources
                WHERE conversation_id = %s AND source_message_id = %s
                UNION
                SELECT id AS memory_id
                FROM conversation_memories
                WHERE conversation_id = %s AND source_message_id = %s
                ORDER BY memory_id
                """,
                (cid, message_id, cid, message_id),
            ).fetchall()
        ]

        conn.execute(
            """
            DELETE FROM memory_sources
            WHERE conversation_id = %s AND source_message_id = %s
            """,
            (cid, message_id),
        )

        # The legacy FK also nulls this value on message deletion. Detach it
        # explicitly in the same transaction so support classification sees
        # the post-deletion state before relying on FK side effects.
        conn.execute(
            """
            UPDATE conversation_memories
            SET source_message_id = NULL
            WHERE conversation_id = %s AND source_message_id = %s
            """,
            (cid, message_id),
        )

        conn.execute(
            "DELETE FROM messages WHERE conversation_id = %s AND id = %s",
            (cid, message_id),
        )

        orphaned, supported = [], []
        for memory_id in affected:
            (supported if _has_valid_user_source(conn, cid, memory_id) else orphaned).append(memory_id)

    return {
        "deleted": True,
        "orphaned": sorted(orphaned),
        "still_supported": sorted(supported),
    }
