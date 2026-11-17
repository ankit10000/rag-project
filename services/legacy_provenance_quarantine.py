"""Phase 2 — quarantine plans and read-only application eligibility.

The plan builder turns reviewed inventory classifications into a proposed,
auditable quarantine plan (a list of dicts). It does NOT connect to any
database. Read helpers below inspect existing markers but never apply plans.
Applying a plan requires the
proposed schema (docs/remediation/proposals/004_memory_provenance_quarantine.sql.proposed),
a separately approved migration, a rehearsal on an isolated clone, and a
separately approved apply step — none of which exist or were run.

Rules:
  * Only memories whose memory_id is in the explicitly APPROVED set are
    planned; nothing is quarantined just because of its category.
  * USER_SUPPORTED memories are never planned for quarantine, even if approved
    (their invalid extra links are recorded as issues, not quarantined).
  * The plan preserves the original evidence (classification, issues, source
    IDs) verbatim; it never proposes deleting a memory, a link, a message, or
    changing link_kind / source_role / memory text / embeddings.
"""

from services.legacy_provenance_classifier import (
    ASSISTANT_ONLY_OR_UNVERIFIED,
    INCONSISTENT_SOURCE,
    MISSING_SOURCE,
    USER_SUPPORTED,
)

QUARANTINABLE = (ASSISTANT_ONLY_OR_UNVERIFIED, MISSING_SOURCE, INCONSISTENT_SOURCE)

REASONS = {
    ASSISTANT_ONLY_OR_UNVERIFIED: "no verified user source; references are assistant-origin or otherwise unverified",
    MISSING_SOURCE: "no source reference in either the modern or the legacy representation",
    INCONSISTENT_SOURCE: "provenance references are structurally inconsistent (missing/foreign message, role or representation mismatch)",
}


class QuarantinePlanError(ValueError):
    """The requested plan is not allowed by the quarantine rules."""


def build_quarantine_plan(inventory_records, approved_memory_ids, approval_ref: str) -> dict:
    """Return a proposed plan for the approved memories only.

    inventory_records: the "memories" list produced by run_inventory()
    approved_memory_ids: memory IDs a reviewer explicitly approved
    approval_ref: a non-empty reference to the written approval
    """
    if not isinstance(approval_ref, str) or not approval_ref.strip():
        raise QuarantinePlanError("an approval reference is required")

    approved = set(approved_memory_ids or ())
    by_id = {r["memory_id"]: r for r in inventory_records}

    unknown = sorted(approved - set(by_id))
    if unknown:
        raise QuarantinePlanError(f"approved IDs not present in the inventory: {unknown}")

    refused = sorted(m for m in approved if by_id[m]["category"] == USER_SUPPORTED)
    if refused:
        raise QuarantinePlanError(
            f"USER_SUPPORTED memories cannot be quarantined: {refused}")

    entries = []
    for memory_id in sorted(approved):
        record = by_id[memory_id]
        category = record["category"]
        if category not in QUARANTINABLE:
            raise QuarantinePlanError(f"memory {memory_id}: unexpected category {category!r}")
        entries.append({
            "memory_id": memory_id,
            "conversation_id": record["conversation_id"],
            "classification": category,
            "reason": REASONS[category],
            "issues": record.get("issues", []),
            "modern_source_ids": record.get("modern_source_ids", []),
            "legacy_source_id": record.get("legacy_source_id"),
            "memory_text_sha256": record.get("memory_text_sha256"),
            "proposed_action": "INSERT quarantine marker row only (no change to the memory, links, messages or embeddings)",
        })

    return {
        "approval_ref": approval_ref.strip(),
        "planned_count": len(entries),
        "entries": entries,
        "executed": False,
        "note": "Plan only. No database change has been made. Applying requires a separately approved migration, rehearsal and apply step.",
    }


def active_quarantine_ids(conversation_id, memory_ids=None, connection=None):
    """Read optional Proposal 004 markers without applying its schema.

    Query failures propagate rather than silently releasing quarantined facts.
    """
    import uuid
    from services.database import get_connection
    cid = uuid.UUID(str(conversation_id))
    ids = None if memory_ids is None else sorted({int(i) for i in memory_ids})
    if ids == []:
        return set()
    def read(conn):
        exists = conn.execute("SELECT to_regclass('memory_provenance_quarantine') IS NOT NULL").fetchone()[0]
        if not exists:
            return set()
        sql = "SELECT memory_id FROM memory_provenance_quarantine WHERE conversation_id = %s AND status = 'quarantined'"
        params = [cid]
        if ids is not None:
            sql += " AND memory_id = ANY(%s::bigint[])"
            params.append(ids)
        return {int(r[0]) for r in conn.execute(sql, params).fetchall()}
    if connection is not None:
        return read(connection)
    with get_connection() as conn:
        return read(conn)


def eligible_memory_ids(conversation_id, memory_ids=None):
    """Existing same-conversation user-supported and unquarantined IDs."""
    import uuid
    from services.database import get_connection
    from services.memory_context_service import load_provenance_facts
    from services.legacy_provenance_classifier import classify_memory
    if memory_ids is None:
        with get_connection() as conn:
            memory_ids = [r[0] for r in conn.execute(
                "SELECT id FROM conversation_memories WHERE conversation_id = %s",
                (uuid.UUID(str(conversation_id)),)).fetchall()]
    facts = load_provenance_facts(conversation_id, memory_ids)
    return {mid for mid, fact in facts.items()
            if not fact.quarantined and classify_memory(fact).category == USER_SUPPORTED}


def filter_supported_memories(conversation_id, rows, exclude_memory_ids=None):
    rows = list(rows)
    allowed = eligible_memory_ids(conversation_id, [r[0] for r in rows])
    allowed -= {int(i) for i in (exclude_memory_ids or ())}
    return [r for r in rows if r[0] in allowed]


def get_blocked_source_message_ids(conversation_id, exclude_memory_ids=None):
    """Same-conversation sources of blocked facts, including paired assistants.

    Never guesses sources for source-less historical facts. All references are
    checked against actual message ownership before suppressing history.
    """
    import uuid
    from services.database import get_connection
    from services.memory_context_service import load_provenance_facts
    from services.legacy_provenance_classifier import classify_memory
    cid = uuid.UUID(str(conversation_id))
    with get_connection() as conn:
        mids = [r[0] for r in conn.execute(
            "SELECT id FROM conversation_memories WHERE conversation_id = %s", (cid,)).fetchall()]
    facts = load_provenance_facts(conversation_id, mids)
    excluded = {int(i) for i in (exclude_memory_ids or ())}
    source_ids = set()
    for mid, fact in facts.items():
        if mid not in excluded and not fact.quarantined and classify_memory(fact).category == USER_SUPPORTED:
            continue
        source_ids.update(l.source_message_id for l in fact.modern_links
                          if l.message_exists and str(l.message_conversation_id) == str(cid))
        scalar = fact.legacy_scalar
        if scalar and scalar.message_exists and str(scalar.message_conversation_id) == str(cid):
            source_ids.add(scalar.source_message_id)
    if not source_ids:
        return set()
    with get_connection() as conn:
        messages = conn.execute(
            "SELECT id, role FROM messages WHERE conversation_id = %s ORDER BY id", (cid,)).fetchall()
    blocked = set()
    for index, (mid, role) in enumerate(messages):
        if mid in source_ids:
            blocked.add(mid)
            if role == 'user' and index + 1 < len(messages) and messages[index + 1][1] == 'assistant':
                blocked.add(messages[index + 1][0])
    return blocked
