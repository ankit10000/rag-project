"""Short-lived PostgreSQL connections with bounded local operation timeouts.

Each returned connection retains psycopg's existing context-manager semantics:
commit on success, rollback on failure, and close on exit. Connections are not
shared across requests; introducing reuse requires an actual checked-out pool.
"""
import os
import psycopg
from psycopg.conninfo import conninfo_to_dict
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')


def _timeout(name, default, maximum):
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name} must be a positive integer') from None
    if not 1 <= parsed <= maximum:
        raise ValueError(f'{name} must be between 1 and {maximum}')
    return parsed


class TenantConnection:
    """Retain psycopg semantics and close even if a deferred commit fails."""
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    @property
    def autocommit(self):
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._conn.autocommit = value

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._conn.__exit__(exc_type, exc, traceback)
        finally:
            self._conn.close()


def get_connection():
    from services.tenant_context import database_scope
    tenant = database_scope()
    if not DATABASE_URL:
        raise ValueError('DATABASE_URL is missing')
    if os.getenv('RAG_V2') == '1' and conninfo_to_dict(DATABASE_URL).get('dbname') == 'rag_db':
        raise ValueError('v2 must not access rag_db')
    connect = _timeout('DB_CONNECT_TIMEOUT_SECONDS', 5, 60)
    statement = _timeout('DB_STATEMENT_TIMEOUT_MS', 15000, 300000)
    lock = _timeout('DB_LOCK_TIMEOUT_MS', 5000, 60000)
    from services.request_budget import remaining_seconds, RequestDeadlineExceeded
    remaining = remaining_seconds()
    if remaining is not None:
        # libpq rounds short connect timeouts up to two seconds. Refuse rather
        # than opening a connection that cannot honor a shorter caller budget.
        if remaining < 2:
            raise RequestDeadlineExceeded()
        connect = min(connect, max(2, int(remaining)))
        statement = min(statement, max(1, int(remaining * 1000)))
        lock = min(lock, statement)
    existing_options = conninfo_to_dict(DATABASE_URL).get('options', '')
    options = f'{existing_options} -c statement_timeout={statement} -c lock_timeout={lock}'.strip()
    conn = psycopg.connect(DATABASE_URL, connect_timeout=connect, options=options)
    try:
        register_vector(conn)
        if tenant is not None:
            mode, owner = tenant
            conn.execute("SELECT set_config('app.tenant_mode', %s, true), "
                         "set_config('app.user_id', %s, true)", (mode, owner))
        remaining_seconds()
    except BaseException:
        conn.close()
        raise
    return TenantConnection(conn) if tenant is not None else conn
