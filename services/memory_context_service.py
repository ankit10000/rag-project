"""Phase 3 — conversational memory relevance and context assembly.

Builds the bounded "long-term memory" block that main.py passes to the
answer pipeline (as context, never as document evidence).

Pipeline (one conversation only):
  1. candidates  : services.memory_search_service.search_memories() — the
                   existing conversation-scoped vector search with its existing
                   threshold (MEMORY_RELEVANCE_THRESHOLD = 0.35) and top_k.
                   No new threshold or ranking is introduced.
  2. exclusions  : memory IDs in ``exclude_memory_ids`` are dropped. This is the
                   integration point for explicit per-turn exclusions. Active
                   Proposal 004 quarantine markers are loaded when its optional
                   table exists; this code never creates or changes markers.
  3. provenance  : only memories classified USER_SUPPORTED by the Phase 2 pure
                   classifier (a same-conversation source whose actual role and
                   stored role are 'user') are used as user facts. Unsupported,
                   assistant-only, missing or inconsistent provenance is left out.
  4. organization: deterministic category (memory_classification_service),
                   grouped in a fixed category order, newest memory first.
  5. output      : {"text", "memories", "excluded"}. ``text`` contains only the
                   memory sentences (no IDs). ``memories`` keeps the internal
                   provenance metadata (ids, source ids, category, similarity)
                   for debugging/future citations; it is never shown as a claim.

Deleted memories are absent by construction (they no longer exist in
conversation_memories). Provider-independent: no LLM call here.
"""

import uuid

from services.legacy_provenance_classifier import (
    USER_SUPPORTED,
    LegacyScalarFact,
    MemoryProvenanceFacts,
    ModernLinkFact,
    classify_memory,
)
from services import perf_metrics
from services.memory_classification_service import CATEGORIES, CATEGORY_LABELS, classify_memory_text

DEFAULT_TOP_K = 5   # the value main.py already used for search_memories()

CONTEXT_HEADER = (
    "Relevant stored facts about the user (from the user's own earlier messages; "
    "newest first within each group; if two facts disagree, prefer asking the user):"
)


def load_provenance_facts(conversation_id, memory_ids):
    """Read-only provenance facts for the given memories of ONE conversation.

    Messages are joined by id only so a foreign-conversation reference is
    visible to the classifier (and therefore not counted as support).
    """
    from services.database import get_connection

    ids = sorted({int(i) for i in memory_ids})
    if not ids:
        return {}
    cid = uuid.UUID(str(conversation_id))

    from services.legacy_provenance_quarantine import active_quarantine_ids

    with get_connection() as conn:
        quarantined = active_quarantine_ids(cid, ids, connection=conn)
        existing_ids = {r[0] for r in conn.execute(
            "SELECT id FROM conversation_memories WHERE conversation_id = %s AND id = ANY(%s::bigint[])",
            (cid, ids),
        ).fetchall()}
        modern = conn.execute(
            """
            SELECT ms.memory_id, ms.conversation_id::text, ms.source_message_id,
                   ms.link_kind, ms.source_role,
                   (m.id IS NOT NULL AND NOT COALESCE(m.context_excluded, FALSE)), m.conversation_id::text, m.role
            FROM memory_sources ms
            LEFT JOIN messages m ON m.id = ms.source_message_id
            WHERE ms.conversation_id = %s AND ms.memory_id = ANY(%s::bigint[])
            ORDER BY ms.memory_id, ms.source_message_id
            """,
            (cid, ids),
        ).fetchall()
        legacy = conn.execute(
            """
            SELECT cm.id, cm.source_message_id,
                   (m.id IS NOT NULL AND NOT COALESCE(m.context_excluded, FALSE)), m.conversation_id::text, m.role
            FROM conversation_memories cm
            LEFT JOIN messages m ON m.id = cm.source_message_id
            WHERE cm.conversation_id = %s AND cm.id = ANY(%s::bigint[])
              AND cm.source_message_id IS NOT NULL
            """,
            (cid, ids),
        ).fetchall()

    links = {}
    for (mid, link_conv, sid, kind, stored, exists, msg_conv, role) in modern:
        links.setdefault(mid, []).append(ModernLinkFact(
            source_message_id=sid, link_conversation_id=link_conv, link_kind=kind,
            stored_role=stored, message_exists=bool(exists),
            message_conversation_id=msg_conv, actual_role=role))
    scalars = {
        mid: LegacyScalarFact(source_message_id=sid, message_exists=bool(exists),
                              message_conversation_id=msg_conv, actual_role=role)
        for mid, sid, exists, msg_conv, role in legacy
    }
    return {
        mid: MemoryProvenanceFacts(
            memory_id=mid, conversation_id=str(cid),
            modern_links=tuple(links.get(mid, ())), legacy_scalar=scalars.get(mid),
            quarantined=mid in quarantined)
        for mid in ids if mid in existing_ids
    }


def assemble_memory_context(
    conversation_id,
    query,
    top_k=DEFAULT_TOP_K,
    exclude_memory_ids=None,
    search_fn=None,
    provenance_fn=None,
) -> dict:
    """Return {"text": str, "memories": [...], "excluded": {...}} for one turn."""
    if search_fn is None:
        from services.memory_search_service import search_memories as search_fn
    if provenance_fn is None:
        provenance_fn = load_provenance_facts

    excluded = {"quarantined_or_excluded": [], "unverified_provenance": []}
    if top_k <= 0 or not isinstance(query, str) or not query.strip():
        return {"text": "", "memories": [], "excluded": excluded}

    blocked = {int(i) for i in (exclude_memory_ids or ())}
    candidates = search_fn(conversation_id=conversation_id, query=query, top_k=top_k + len(blocked)) or []

    usable = []
    for item in candidates:
        mid = int(item["id"])
        if mid in blocked:
            excluded["quarantined_or_excluded"].append(mid)
            continue
        if isinstance(item.get("memory"), str) and item["memory"].strip():
            usable.append(item)

    with perf_metrics.timed("memory_context.provenance", candidates=len(usable)):
        facts = provenance_fn(conversation_id, [int(i["id"]) for i in usable]) if usable else {}

    selected = []
    for item in usable:
        mid = int(item["id"])
        fact = facts.get(mid)
        if fact is not None and fact.quarantined:
            excluded["quarantined_or_excluded"].append(mid)
            continue
        verdict = classify_memory(fact) if (fact is not None
            and fact.memory_id == mid and str(fact.conversation_id) == str(conversation_id)) else None
        if verdict is None or verdict.category != USER_SUPPORTED:
            excluded["unverified_provenance"].append(mid)
            continue
        selected.append({
            "id": mid,
            "memory": item["memory"],
            "category": classify_memory_text(item["memory"]),
            "similarity": item.get("similarity"),
            "source_message_ids": list(verdict.valid_user_source_ids),
        })

    selected = selected[:top_k]
    order = {c: i for i, c in enumerate(CATEGORIES)}
    selected.sort(key=lambda m: (order[m["category"]], -m["id"]))

    lines = []
    current = None
    for m in selected:
        if m["category"] != current:
            current = m["category"]
            lines.append(f"{CATEGORY_LABELS[current]}:")
        lines.append(f"- {m['memory']}")

    text = (CONTEXT_HEADER + "\n" + "\n".join(lines)) if lines else ""
    for key in excluded:
        excluded[key] = sorted(excluded[key])
    return {"text": text, "memories": selected, "excluded": excluded}
