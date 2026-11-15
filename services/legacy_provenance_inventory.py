"""Phase 2 — READ-ONLY legacy provenance inventory.

Collects provenance facts for every memory (optionally one conversation) from
``conversation_memories``, ``memory_sources`` and ``messages`` and hands them to
the pure classifier. It never writes: no INSERT/UPDATE/DELETE/DDL statement
exists in this module, the connection is opened with
``default_transaction_read_only=on`` and every query runs inside an explicit
``BEGIN READ ONLY`` transaction that is rolled back at the end. It does not use
``services.database.get_connection`` (whose default is the application
database); the caller must pass an explicit connection string.

Columns read (all confirmed in the repository schema/migrations):
  conversation_memories: id, conversation_id, source_message_id
  memory_sources:        memory_id, conversation_id, source_message_id, link_kind, source_role
  messages:              id, conversation_id, role
Message text and memory text are NOT read, except an optional memory-text
SHA-256 for change detection (never the text itself).

Messages are joined BY MESSAGE ID ONLY so that a reference to a message of a
different conversation is reported, not hidden by a conversation-scoped join.
"""

import hashlib
import json
import uuid

import psycopg

from services.legacy_provenance_classifier import (
    LegacyScalarFact,
    MemoryProvenanceFacts,
    ModernLinkFact,
    classify_all,
    summarize,
)

READ_ONLY_OPTIONS = "-c default_transaction_read_only=on"


def _scope(conversation_id):
    if conversation_id is None:
        return "", ()
    return " WHERE cm.conversation_id = %s", (uuid.UUID(str(conversation_id)),)


def collect_facts(conn, conversation_id=None, include_text_hash=False):
    """Read provenance facts. ``conn`` must be a read-only psycopg connection.

    Returns (facts_list, text_hashes) where text_hashes maps memory_id ->
    sha256(memory text) only when include_text_hash is True.
    """
    where, params = _scope(conversation_id)

    memories = conn.execute(
        "SELECT cm.id, cm.conversation_id::text, cm.source_message_id"
        " FROM conversation_memories cm" + where + " ORDER BY cm.id",
        params,
    ).fetchall()

    modern_rows = conn.execute(
        """
        SELECT ms.memory_id, ms.conversation_id::text, ms.source_message_id,
               ms.link_kind, ms.source_role,
               m.id IS NOT NULL, m.conversation_id::text, m.role
        FROM memory_sources ms
        JOIN conversation_memories cm ON cm.id = ms.memory_id
        LEFT JOIN messages m ON m.id = ms.source_message_id
        """ + where + " ORDER BY ms.memory_id, ms.source_message_id",
        params,
    ).fetchall()

    legacy_rows = conn.execute(
        """
        SELECT cm.id, cm.source_message_id,
               m.id IS NOT NULL, m.conversation_id::text, m.role
        FROM conversation_memories cm
        LEFT JOIN messages m ON m.id = cm.source_message_id
        """ + (where + " AND" if where else " WHERE") + " cm.source_message_id IS NOT NULL"
        " ORDER BY cm.id",
        params,
    ).fetchall()

    text_hashes = {}
    if include_text_hash:
        for memory_id, digest in conn.execute(
            "SELECT cm.id, encode(sha256(convert_to(coalesce(cm.memory, ''), 'UTF8')), 'hex')"
            " FROM conversation_memories cm" + where + " ORDER BY cm.id",
            params,
        ).fetchall():
            text_hashes[memory_id] = digest

    links_by_memory = {}
    for (memory_id, link_conv, sid, link_kind, stored_role,
         exists, msg_conv, actual_role) in modern_rows:
        links_by_memory.setdefault(memory_id, []).append(ModernLinkFact(
            source_message_id=sid, link_conversation_id=link_conv, link_kind=link_kind,
            stored_role=stored_role, message_exists=bool(exists),
            message_conversation_id=msg_conv, actual_role=actual_role,
        ))

    legacy_by_memory = {
        memory_id: LegacyScalarFact(
            source_message_id=sid, message_exists=bool(exists),
            message_conversation_id=msg_conv, actual_role=actual_role,
        )
        for memory_id, sid, exists, msg_conv, actual_role in legacy_rows
    }

    facts = [
        MemoryProvenanceFacts(
            memory_id=memory_id,
            conversation_id=conv,
            modern_links=tuple(links_by_memory.get(memory_id, ())),
            legacy_scalar=legacy_by_memory.get(memory_id),
        )
        for memory_id, conv, _scalar in memories
    ]
    return facts, text_hashes


def provenance_fingerprint(conn, conversation_id=None) -> dict:
    """Deterministic, read-only fingerprint of the provenance state (counts +
    SHA-256 over sorted rows). Used to prove before/after equality around a
    future rehearsal or rollback. Memory text is not included."""
    where, params = _scope(conversation_id)

    def digest(sql):
        rows = conn.execute(sql, params).fetchall()
        h = hashlib.sha256()
        for row in rows:
            h.update(json.dumps(row, default=str).encode("utf-8"))
            h.update(b"\n")
        return {"rows": len(rows), "sha256": h.hexdigest()}

    return {
        "conversation_memories(id,conversation_id,source_message_id)": digest(
            "SELECT cm.id, cm.conversation_id::text, cm.source_message_id"
            " FROM conversation_memories cm" + where + " ORDER BY cm.id"),
        "memory_sources(memory_id,source_message_id,conversation_id,link_kind,source_role)": digest(
            "SELECT ms.memory_id, ms.source_message_id, ms.conversation_id::text, ms.link_kind,"
            " ms.source_role FROM memory_sources ms"
            " JOIN conversation_memories cm ON cm.id = ms.memory_id" + where
            + " ORDER BY ms.memory_id, ms.source_message_id"),
    }


def run_inventory(conninfo: str, conversation_id=None, include_text_hash=False) -> dict:
    """Open a READ-ONLY connection to ``conninfo``, collect, classify, roll back.

    ``conninfo`` is mandatory: there is no default target database.
    """
    if not conninfo:
        raise ValueError("an explicit connection string is required (no default database)")

    with psycopg.connect(conninfo, options=READ_ONLY_OPTIONS, autocommit=True) as conn:
        conn.execute("BEGIN READ ONLY")
        try:
            database = conn.execute("SELECT current_database()").fetchone()[0]
            read_only = conn.execute("SHOW transaction_read_only").fetchone()[0]
            if read_only != "on":
                raise RuntimeError("refusing to run: transaction is not read-only")
            facts, text_hashes = collect_facts(conn, conversation_id, include_text_hash)
            fingerprint = provenance_fingerprint(conn, conversation_id)
        finally:
            conn.execute("ROLLBACK")

    classifications = classify_all(facts)
    records = []
    for c in classifications:
        record = c.as_dict()
        if include_text_hash:
            record["memory_text_sha256"] = text_hashes.get(c.memory_id)
        records.append(record)

    return {
        "database": database,
        "transaction_read_only": read_only,
        "scope_conversation_id": str(conversation_id) if conversation_id else None,
        "summary": summarize(classifications),
        "fingerprint": fingerprint,
        "memories": records,
    }
