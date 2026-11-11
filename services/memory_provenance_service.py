"""
Deterministic memory <-> message provenance (Phase 5).

Everything here reads/writes the memory_sources table only. No text
matching, no LLM. All queries are scoped to one conversation.
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


def delete_message_with_provenance(conversation_id: str, message_id: int) -> dict:
    """
    Delete one message of a conversation safely.

    The links to that message are detached first (the FK refuses to remove
    a message that is still referenced). Memories are NEVER deleted here:
    the ones that lose their last source are returned as `orphaned` so the
    caller can decide; the ones that keep other sources are `still_supported`.
    Atomic: all or nothing.
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
            r[0] for r in conn.execute(
                """
                SELECT memory_id FROM memory_sources
                WHERE conversation_id = %s AND source_message_id = %s
                """,
                (cid, message_id),
            ).fetchall()
        ]

        conn.execute(
            """
            DELETE FROM memory_sources
            WHERE conversation_id = %s AND source_message_id = %s
            """,
            (cid, message_id),
        )

        orphaned, supported = [], []
        for memory_id in affected:
            left = conn.execute(
                """
                SELECT count(*) FROM memory_sources
                WHERE conversation_id = %s AND memory_id = %s
                """,
                (cid, memory_id),
            ).fetchone()[0]
            (supported if left else orphaned).append(memory_id)

        # Legacy column is ON DELETE SET NULL; messages FK now unblocked.
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = %s AND id = %s",
            (cid, message_id),
        )

    return {"deleted": True, "orphaned": orphaned, "still_supported": supported}
