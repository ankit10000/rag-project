"""Shared request helpers: id validation, existence checks, per-resource locks."""

import threading
import uuid

from backend.errors import ApiError, not_found

_locks_guard = threading.Lock()
_conversation_locks: dict[str, threading.Lock] = {}

# One ingestion at a time (ingest_pdf is a single DB transaction per document;
# serializing avoids two uploads racing on the same document_name).
ingestion_lock = threading.Lock()


def conversation_lock(conversation_id: str) -> threading.Lock:
    """Turns of the SAME conversation run one at a time so message order,
    memory writes and checkpoint advancement keep the CLI's sequential order."""
    with _locks_guard:
        lock = _conversation_locks.get(conversation_id)
        if lock is None:
            lock = _conversation_locks[conversation_id] = threading.Lock()
        return lock


def parse_conversation_id(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise ApiError(422, "invalid_conversation_id", "conversation_id must be a UUID") from None


def require_conversation(conversation_id: str) -> str:
    from services.conversation_service import conversation_exists

    cid = parse_conversation_id(conversation_id)
    if not conversation_exists(cid):
        raise not_found("conversation")
    return cid
