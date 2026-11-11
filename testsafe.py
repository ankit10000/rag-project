"""
Shared safety guard for every test script (Phase 4 / P4-07).

Rules enforced:
  * DATABASE_URL must be present in the *process environment* (the test
    runner sets it). The .env file is deliberately NOT consulted, so a test
    started by hand can never fall back to the application database.
  * The database name must look like a scratch database
    (rag_<anything>test<anything>, e.g. rag_test_scratch, rag_phase5_test)
    and must never be rag_db / postgres / template*.
  * psycopg.connect is wrapped, so even code that builds its own connection
    string or passes dbname=... is refused when it targets a non-scratch
    database.

Usage, as the first lines of a test script (before importing services):

    import testsafe
    testsafe.require_scratch_db()

Credentials are never printed.
"""
import os
import re
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict

FORBIDDEN_NAMES = {"rag_db", "postgres", "template0", "template1"}
SCRATCH_PATTERN = re.compile(r"rag_[a-z0-9_]*test[a-z0-9_]*")


class UnsafeDatabaseError(RuntimeError):
    """Raised when a test would touch a database that is not a scratch DB."""


def is_scratch_name(name) -> bool:
    return (
        bool(name)
        and name not in FORBIDDEN_NAMES
        and SCRATCH_PATTERN.fullmatch(name) is not None
    )


def database_name(conninfo: str = "", **kwargs):
    """Database name addressed by a conninfo string plus keyword overrides."""
    info = conninfo_to_dict(conninfo) if conninfo else {}
    info.update({k: v for k, v in kwargs.items() if v is not None})
    return info.get("dbname") or os.environ.get("PGDATABASE")


def check_conninfo(conninfo: str = "", **kwargs) -> str:
    name = database_name(conninfo, **kwargs)
    if not is_scratch_name(name):
        raise UnsafeDatabaseError(
            f"refusing to use database {name!r}: tests may only use a scratch "
            "database whose name matches rag_*test* (never rag_db)"
        )
    return name


_original_connect = psycopg.connect                       # bound Connection.connect
_original_sync_func = psycopg.Connection.connect.__func__
_original_async_func = psycopg.AsyncConnection.connect.__func__
_guard_installed = False


def _guarded_sync_connect(cls, conninfo: str = "", *args, **kwargs):
    check_conninfo(conninfo, **kwargs)
    return _original_sync_func(cls, conninfo, *args, **kwargs)


async def _guarded_async_connect(cls, conninfo: str = "", *args, **kwargs):
    check_conninfo(conninfo, **kwargs)
    return await _original_async_func(cls, conninfo, *args, **kwargs)


def install_connect_guard() -> None:
    """
    Guard every psycopg entry point: psycopg.connect, Connection.connect
    (used by pgvector helpers, psycopg_pool, subclasses) and
    AsyncConnection.connect.
    """
    global _guard_installed
    if not _guard_installed:
        psycopg.Connection.connect = classmethod(_guarded_sync_connect)
        psycopg.AsyncConnection.connect = classmethod(_guarded_async_connect)
        psycopg.connect = psycopg.Connection.connect
        _guard_installed = True


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "", None}


def install_network_block(extra_allowed_hosts=()) -> None:
    """
    Refuse every outbound connection except localhost (and the database host).
    Used for unit/integration runs so a forgotten mock can never reach Gemini.
    Enabled by the runner through TESTSAFE_BLOCK_NETWORK=1.
    """
    import socket

    allowed = set(_LOCAL_HOSTS) | set(extra_allowed_hosts)
    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect

    def blocked(host):
        raise OSError(f"network blocked by testsafe (TESTSAFE_BLOCK_NETWORK): {host}")

    def getaddrinfo(host, *args, **kwargs):
        if host not in allowed:
            blocked(host)
        return original_getaddrinfo(host, *args, **kwargs)

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in allowed and not str(host).startswith("127."):
            blocked(host)
        return original_connect(self, address)

    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect


def _abort(message: str):
    print(message, file=sys.stderr)
    sys.exit(2)


def require_scratch_db() -> str:
    """Abort the process (exit code 2) unless DATABASE_URL is a scratch DB."""
    url = os.environ.get("DATABASE_URL")

    if not url:
        _abort(
            "SAFETY: DATABASE_URL is not set in the environment. Run tests "
            "through run_tests.py (or export DATABASE_URL for a scratch DB)."
        )

    try:
        name = check_conninfo(url)
    except UnsafeDatabaseError as error:
        _abort(f"SAFETY: {error}")

    install_connect_guard()

    if os.environ.get("TESTSAFE_BLOCK_NETWORK") == "1":
        db_host = conninfo_to_dict(url).get("host")
        install_network_block([db_host] if db_host else [])

    return name
