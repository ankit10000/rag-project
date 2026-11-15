"""Conversations: create, list, history. Rename/delete are not exposed:
no existing service implements them (deferred; see Phase 6 doc)."""

from fastapi import APIRouter, Query

from backend import config
from backend.dependencies import require_conversation
from backend.schemas import ConversationCreate, ConversationDetail, ConversationSummary, Message

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationSummary, status_code=201)
def create(body: ConversationCreate):
    from services.conversation_service import create_conversation
    cid = create_conversation(body.title.strip() or "New Conversation")
    return ConversationSummary(conversation_id=cid, title=body.title.strip(), message_count=0)


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
