"""Memory inspection (read-only).

Only memories whose provenance is USER_SUPPORTED (Phase 2 pure classifier on
facts read by Phase 3's load_provenance_facts) are listed; unverified ones are
counted, never shown as supported. Source metadata excludes message content.
There is no create/update/delete endpoint: memory deletion keeps going through
the chat flow ("forget ...") which runs the established deletion + cleanup
(summary rewrite, context exclusion, checkpoint fencing). A direct delete
endpoint would bypass that cleanup and is deferred.
"""

from fastapi import APIRouter, Query

from backend import config
from backend.dependencies import require_conversation
from backend.errors import not_found
from backend.schemas import MemoryItem, MemoryList, MemorySource

router = APIRouter(prefix="/conversations/{conversation_id}/memories", tags=["memories"])


@router.get("", response_model=MemoryList)
def list_memories(conversation_id: str, limit: int = Query(50, ge=1, le=config.MAX_MEMORIES_LISTED)):
    from backend.repositories import list_memory_rows
    from services.legacy_provenance_classifier import USER_SUPPORTED, classify_memory
    from services.memory_classification_service import classify_memory_text
    from services.memory_context_service import load_provenance_facts

    cid = require_conversation(conversation_id)
    rows = list_memory_rows(cid, limit)
    facts = load_provenance_facts(cid, [r[0] for r in rows]) if rows else {}

    items, hidden = [], 0
    for memory_id, text in rows:
        fact = facts.get(memory_id)
        verdict = classify_memory(fact) if fact is not None else None
        if verdict is None or verdict.category != USER_SUPPORTED:
            hidden += 1
            continue
        items.append(MemoryItem(memory_id=memory_id, memory=text, category=classify_memory_text(text),
                                provenance="USER_SUPPORTED",
                                source_message_ids=list(verdict.valid_user_source_ids)))
    return MemoryList(conversation_id=cid, memories=items, unverified_hidden=hidden)


@router.get("/{memory_id}/sources", response_model=list[MemorySource])
def memory_sources(conversation_id: str, memory_id: int):
    from backend.repositories import memory_exists
    from services.memory_provenance_service import get_memory_sources

    cid = require_conversation(conversation_id)
    if memory_id < 1 or not memory_exists(cid, memory_id):
        raise not_found("memory")
    return [MemorySource(message_id=s["message_id"], role=s.get("role"), link_kind=s.get("link_kind"))
            for s in get_memory_sources(cid, memory_id)]
