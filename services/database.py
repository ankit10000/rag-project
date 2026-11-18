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


def get_connection():
    if not DATABASE_URL:
        raise ValueError('DATABASE_URL is missing')
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
        remaining_seconds()
    except BaseException:
        conn.close()
        raise
    return conn
