"""Conversation views and scoped, transactional local deletion entry points."""

from services.request_budget import budgeted_lock

from fastapi import APIRouter, Query, Path

from backend import config
from backend.dependencies import require_conversation, parse_conversation_id, conversation_lock
from backend.schemas import ConversationCreate, ConversationDetail, ConversationSummary, Message, DeletionResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationSummary, status_code=201)
def create(body: ConversationCreate):
    from services.conversation_service import create_conversation
    title = body.title.strip() or "New Conversation"
    cid = create_conversation(title)
    return ConversationSummary(conversation_id=cid, title=title, message_count=0)


@router.get("", response_model=list[ConversationSummary])
def list_all(limit: int = Query(50, ge=1, le=config.MAX_CONVERSATIONS_LISTED)):
    from backend.repositories import list_conversations
    return [ConversationSummary(**c) for c in list_conversations(limit)]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def history(conversation_id: str, limit: int = Query(40, ge=1, le=config.MAX_HISTORY_MESSAGES)):
    from services.conversation_service import get_live_messages
    cid = require_conversation(conversation_id)
    messages = [Message(**m) for m in get_live_messages(cid, limit=limit)]
    return ConversationDetail(conversation_id=cid, messages=messages)


@router.delete("/{conversation_id}", response_model=DeletionResponse)
def delete_conversation(conversation_id: str):
    from services.local_deletion_service import delete_conversation as delete
    from backend.errors import not_found
    cid = parse_conversation_id(conversation_id)
    with budgeted_lock(conversation_lock(cid)):
        require_conversation(cid)
        if not delete(cid):
            raise not_found("conversation")
    return DeletionResponse(resource="conversation", conversation_id=cid, deleted=True)


@router.delete("/{conversation_id}/messages/{message_id}", response_model=DeletionResponse)
def delete_message(conversation_id: str, message_id: str = Path(pattern=r"^[1-9][0-9]*$")):
    message_id = int(message_id)
    from services.local_deletion_service import delete_message as delete
    from backend.errors import not_found
    cid = parse_conversation_id(conversation_id)
    with budgeted_lock(conversation_lock(cid)):
        require_conversation(cid)
        result = delete(cid, message_id)
        if not result.get("deleted"):
            raise not_found("message")
    return DeletionResponse(resource="message", conversation_id=cid, message_id=message_id,
        deleted=True, orphaned_memory_ids=result.get("orphaned", []),
        still_supported_memory_ids=result.get("still_supported", []))
