"""Deterministic local deletion; each operation and privacy fence is atomic.

API callers serialize these operations with the same conversation lock as chat.
Every SQL statement is scoped to the supplied conversation. No provider calls.
"""
import uuid
from services.database import get_connection
from services.memory_storage_service import normalize_positive_id
from services.memory_provenance_service import _has_valid_user_source


def _id(value):
    return normalize_positive_id(value, allow_numeric_string=True, allow_integral_float=False)


def _fence(conn, cid):
    conn.execute('''
        UPDATE conversations SET summary = '',
            summary_up_to_message_id = GREATEST(COALESCE(summary_up_to_message_id, 0),
                COALESCE((SELECT MAX(id) FROM messages WHERE conversation_id = %s), 0)),
            memory_extraction_up_to_message_id = GREATEST(COALESCE(memory_extraction_up_to_message_id, 0),
                COALESCE((SELECT MAX(id) FROM messages WHERE conversation_id = %s), 0))
        WHERE id = %s
    ''', (cid, cid, cid))


def _exclude_sources_and_pairs(conn, cid, source_ids):
    if not source_ids:
        return []
    rows = conn.execute('''
        WITH ordered AS (
            SELECT id, role, LEAD(id) OVER (ORDER BY id) AS next_id,
                   LEAD(role) OVER (ORDER BY id) AS next_role
            FROM messages WHERE conversation_id = %s
        ), excluded AS (
            SELECT id FROM ordered WHERE id = ANY(%s::bigint[])
            UNION
            SELECT next_id FROM ordered WHERE id = ANY(%s::bigint[])
                AND role = 'user' AND next_role = 'assistant'
        )
        UPDATE messages SET context_excluded = TRUE
        WHERE conversation_id = %s AND id IN (SELECT id FROM excluded)
        RETURNING id
    ''', (cid, source_ids, source_ids, cid)).fetchall()
    return sorted(row[0] for row in rows)


def delete_conversation(conversation_id):
    cid = uuid.UUID(str(conversation_id))
    with get_connection() as conn:
        row = conn.execute('DELETE FROM conversations WHERE id = %s RETURNING id', (cid,)).fetchone()
    return row is not None


def delete_message(conversation_id, message_id):
    cid, mid = uuid.UUID(str(conversation_id)), _id(message_id)
    empty = {'deleted': False, 'orphaned': [], 'still_supported': []}
    if mid is None:
        return empty
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM messages WHERE conversation_id = %s AND id = %s FOR UPDATE', (cid, mid)).fetchone()
        if row is None:
            return empty
        affected = [row[0] for row in conn.execute('''
            SELECT memory_id FROM memory_sources WHERE conversation_id = %s AND source_message_id = %s
            UNION SELECT id FROM conversation_memories WHERE conversation_id = %s AND source_message_id = %s
        ''', (cid, mid, cid, mid)).fetchall()]
        # The immediate assistant may echo the removed message even when no memory exists.
        _exclude_sources_and_pairs(conn, cid, [mid])
        conn.execute('DELETE FROM memory_sources WHERE conversation_id = %s AND source_message_id = %s', (cid, mid))
        conn.execute('UPDATE conversation_memories SET source_message_id = NULL WHERE conversation_id = %s AND source_message_id = %s', (cid, mid))
        conn.execute('DELETE FROM messages WHERE conversation_id = %s AND id = %s', (cid, mid))
        orphaned, supported = [], []
        for memory_id in affected:
            (supported if _has_valid_user_source(conn, cid, memory_id) else orphaned).append(memory_id)
        _fence(conn, cid)
    return {'deleted': True, 'orphaned': sorted(orphaned), 'still_supported': sorted(supported)}


def delete_memory(conversation_id, memory_id):
    cid, mid = uuid.UUID(str(conversation_id)), _id(memory_id)
    empty = {'deleted': False, 'memory_id': mid, 'sources_excluded': []}
    if mid is None:
        return empty
    with get_connection() as conn:
        memory = conn.execute('SELECT source_message_id FROM conversation_memories WHERE conversation_id = %s AND id = %s FOR UPDATE', (cid, mid)).fetchone()
        if memory is None:
            return empty
        # Record deletion is possible even for a legacy source-less memory, but
        # missing provenance cannot prove every old mention was excluded.
        supported = _has_valid_user_source(conn, cid, mid)
        sources = {row[0] for row in conn.execute('SELECT source_message_id FROM memory_sources WHERE conversation_id = %s AND memory_id = %s', (cid, mid)).fetchall()}
        if memory[0] is not None:
            sources.add(memory[0])
        excluded = _exclude_sources_and_pairs(conn, cid, sorted(sources))
        conn.execute('DELETE FROM conversation_memories WHERE conversation_id = %s AND id = %s', (cid, mid))
        _fence(conn, cid)
    return {'deleted': True, 'memory_id': mid, 'sources_excluded': excluded,
            'cleanup_status': 'source_fenced' if supported else 'incomplete_unknown_provenance'}
