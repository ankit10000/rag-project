"""Read-only queries the existing services do not provide (listing views).

All SQL here is SELECT-only and uses the existing services.database
connection helper (imported lazily, so importing this module opens nothing).
Writes always go through the existing services.
"""

import uuid


def _conn():
    from services.database import get_connection
    return get_connection()


def list_documents() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT document_name, count(*) AS chunks, count(DISTINCT page_number) AS pages
            FROM document_chunks
            GROUP BY document_name
            ORDER BY document_name
            """
        ).fetchall()
    return [{"document_name": r[0], "chunks": r[1], "pages": r[2]} for r in rows]


def get_document(document_name: str) -> dict | None:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT page_number, count(*)
            FROM document_chunks
            WHERE document_name = %s
            GROUP BY page_number
            ORDER BY page_number
            """,
            (document_name,),
        ).fetchall()
    if not rows:
        return None
    return {
        "document_name": document_name,
        "chunks": sum(r[1] for r in rows),
        "pages": len(rows),
        "page_breakdown": [{"page_number": r[0], "chunks": r[1]} for r in rows],
    }


def list_conversations(limit: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id::text, c.title, count(m.id), max(m.id)
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id AND NOT m.context_excluded
            GROUP BY c.id, c.title
            ORDER BY max(m.id) DESC NULLS LAST, c.id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [{"conversation_id": r[0], "title": r[1], "message_count": r[2]} for r in rows]


def list_memory_rows(conversation_id: str, limit: int) -> list[tuple]:
    with _conn() as conn:
        return conn.execute(
            """
            SELECT id, memory
            FROM conversation_memories
            WHERE conversation_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (uuid.UUID(conversation_id), limit),
        ).fetchall()


def memory_exists(conversation_id: str, memory_id: int) -> bool:
    with _conn() as conn:
        return conn.execute(
            "SELECT 1 FROM conversation_memories WHERE conversation_id = %s AND id = %s",
            (uuid.UUID(conversation_id), memory_id),
        ).fetchone() is not None
