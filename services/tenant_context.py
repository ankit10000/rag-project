"""Request ownership propagated into each short-lived database transaction.

No implicit owner is assigned to legacy rows. V2 requires an authenticated owner;
only the explicit, local compatibility switch may select unowned legacy rows.
Auth-system scope permits account/session queries, never tenant-row bypass.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import uuid

_owner: ContextVar[str | None] = ContextVar('rag_tenant_owner', default=None)
_auth_system: ContextVar[bool] = ContextVar('rag_auth_system', default=False)


def current_owner() -> str | None:
    return _owner.get()


@contextmanager
def tenant_scope(owner_id: str):
    owner = str(uuid.UUID(str(owner_id)))
    token = _owner.set(owner)
    try:
        yield owner
    finally:
        _owner.reset(token)


@contextmanager
def auth_system_context():
    """Permit auth-table access with an empty tenant ID (RLS still denies rows)."""
    token = _auth_system.set(True)
    try:
        yield
    finally:
        _auth_system.reset(token)


def database_scope() -> tuple[str, str] | None:
    owner = current_owner()
    if owner is not None:
        return 'v2', owner
    if os.getenv('RAG_V2_COMPAT') == '1':
        if os.getenv('RAG_V2') == '1':
            raise RuntimeError('RAG_V2_COMPAT cannot be enabled for the multi-user API')
        return 'legacy', ''
    if os.getenv('RAG_V2') == '1':
        if not _auth_system.get():
            raise PermissionError('an authenticated tenant context is required')
        return 'v2', ''
    return None
