"""FastAPI session dependency and explicit authorization helpers.

Every tenant request binds owner context before entering existing RAG services.
RLS is defense in depth: public resource checks also include owner_id explicitly.
"""
import hmac
import os
import uuid

from fastapi import Depends, Request
from starlette.concurrency import run_in_threadpool

from backend.errors import ApiError
from backend.v2.auth import User, SESSION_COOKIE, authenticate, secret_hash
from services.database import get_connection
from services.tenant_context import tenant_scope


def verify_origin(request: Request):
    origin = request.headers.get('origin')
    if origin is None:
        return
    allowed = {value.strip().rstrip('/') for value in os.getenv(
        'RAG_V2_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if value.strip()}
    if origin.rstrip('/') not in allowed:
        raise ApiError(403, 'invalid_origin', 'request origin is not allowed')


async def require_user(request: Request):
    user = await run_in_threadpool(authenticate, request.cookies.get(SESSION_COOKIE))
    if request.method.upper() not in ('GET', 'HEAD', 'OPTIONS'):
        verify_origin(request)
        csrf = request.headers.get('x-csrf-token', '')
        if not 32 <= len(csrf) <= 128 or not hmac.compare_digest(secret_hash(csrf), user.csrf_hash):
            raise ApiError(403, 'invalid_csrf', 'request verification failed')
    request.state.user = user
    with tenant_scope(user.id):
        yield user


async def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != 'admin':
        raise ApiError(403, 'forbidden', 'administrator access required')
    return user


def parse_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ApiError(404, 'not_found', 'resource not found') from None


def require_owned_conversation(user: User, conversation_id: str) -> str:
    cid = parse_uuid(conversation_id)
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM conversations WHERE id=%s AND owner_id=%s', (cid, user.id)).fetchone()
    if not row:
        raise ApiError(404, 'not_found', 'conversation not found')
    return cid


def require_owned_memory(user: User, memory_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute('SELECT m.id FROM conversation_memories m JOIN conversations c ON c.id=m.conversation_id '
                           'WHERE m.id=%s AND m.owner_id=%s AND c.owner_id=%s',
                           (memory_id, user.id, user.id)).fetchone()
    if not row:
        raise ApiError(404, 'not_found', 'memory not found')
    return memory_id


def require_owned_document(user: User, document_id: str) -> str:
    did = parse_uuid(document_id)
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM documents WHERE id=%s AND owner_id=%s AND status<>'deleted'",
                           (did, user.id)).fetchone()
    if not row:
        raise ApiError(404, 'not_found', 'document not found')
    return did


def require_owned_job(user: User, job_id: str) -> str:
    jid = parse_uuid(job_id)
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM jobs WHERE id=%s AND owner_id=%s', (jid, user.id)).fetchone()
    if not row:
        raise ApiError(404, 'not_found', 'job not found')
    return jid
