"""Chat / RAG question answering.

Delegates to main.run_turn — the SAME orchestration the CLI uses (explicit
memory-deletion routing, grounded answer with citation validation, message
persistence, memory extraction with checkpoint safety, summary update). No
second RAG pipeline exists here. Turns of one conversation are serialized.
Retrieval filters and streaming are not supported yet (deferred): ask_question
has no filter parameters and the turn performs post-answer work.
"""

from fastapi import APIRouter, Request

from backend.dependencies import conversation_lock, require_conversation
from backend.schemas import ChatRequest, ChatResponse, Citation

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request):
    from services.conversation_service import create_conversation

    message = body.message.strip()
    if not message:
        from backend.errors import unprocessable
        raise unprocessable("empty_message", "message must not be blank")

    if body.conversation_id:
        conversation_id = require_conversation(body.conversation_id)
    else:
        conversation_id = create_conversation()

    import main as turn_module   # imported lazily: loads models and the LLM client on first chat

    with conversation_lock(conversation_id):
        outcome = turn_module.run_turn(conversation_id, message)

    citations = [Citation(ref=c.get("ref"), document=c.get("document"), page=c.get("page"),
                          chunk_id=c.get("chunk_id")) for c in outcome.get("citations") or []]
    return ChatResponse(
        request_id=getattr(request.state, "request_id", None),
        conversation_id=conversation_id,
        kind=outcome["kind"],
        answer=outcome["answer"],
        status=outcome.get("status"),
        citations=citations,
        memory_extraction=outcome.get("memory_extraction"),
        summary_update=outcome.get("summary_update"),
        deleted_count=outcome.get("deleted_count"),
    )
