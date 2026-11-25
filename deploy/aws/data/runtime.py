"""Container-only secrets adapter and exact database identity guard.

Secrets remain outside images and command arguments. No schema changes occur here.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys

import psycopg
from psycopg.conninfo import make_conninfo


def database_name(value: str) -> str:
    if value not in {"rag_v2_demo", "rag_aws_scratch"} and not re.fullmatch(
        r"rag_aws_restore_[a-f0-9]{32}", value
    ):
        raise ValueError("only the explicitly dedicated AWS demonstration/scratch database is allowed")
    return value


def secret(path: str) -> str:
    value = Path(path).read_text().strip()
    if len(value) < 24 or any(char in value for char in "\r\n\x00"):
        raise ValueError("secret must be a single value of at least 24 characters")
    return value


def connection_info(*, admin: bool = False, name: str | None = None) -> str:
    expected = database_name(name or os.environ["RAG_DATABASE_NAME"])
    return make_conninfo(
        host=os.getenv("RAG_DATABASE_HOST", "db"),
        port=os.getenv("RAG_DATABASE_PORT", "5432"),
        dbname=expected,
        user=os.getenv("RAG_ADMIN_ROLE", "rag_admin") if admin else "rag_v2_app",
        password=secret(os.getenv(
            "RAG_ADMIN_PASSWORD_FILE" if admin else "RAG_APP_PASSWORD_FILE",
            "/run/secrets/db_admin_password" if admin else "/run/secrets/db_app_password",
        )),
        connect_timeout=5,
        options="-c statement_timeout=15000 -c lock_timeout=5000",
    )


def verify(connection, *, admin: bool = False, name: str | None = None) -> None:
    expected = database_name(name or os.environ["RAG_DATABASE_NAME"])
    actual, role = connection.execute("SELECT current_database(), current_user").fetchone()
    expected_role = os.getenv("RAG_ADMIN_ROLE", "rag_admin") if admin else "rag_v2_app"
    if actual != expected or role != expected_role:
        raise ValueError("database or role identity mismatch; operation refused")
    if not admin:
        flags = connection.execute(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        if not flags or any(flags):
            raise ValueError("application requires NOSUPERUSER NOBYPASSRLS")


def main() -> None:
    if not sys.argv[1:]:
        raise ValueError("container command is required")
    from prepare_assets import verify_assets
    verify_assets(Path("/models"), full=True)
    url = connection_info()
    with psycopg.connect(url) as connection:
        verify(connection)
        tables = connection.execute(
            "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace "
            "AND relname=ANY(%s) AND relrowsecurity AND relforcerowsecurity",
            (["documents", "jobs", "job_events", "conversations", "messages", "conversation_memories",
              "memory_sources", "document_chunks", "v2_turn_receipts"],),
        ).fetchone()[0]
        if tables != 9:
            raise ValueError("all nine tenant tables require FORCE RLS before startup")
    os.environ["DATABASE_URL"] = url
    key_file = os.getenv("RAG_GEMINI_KEY_FILE")
    if key_file:
        os.environ["GEMINI_API_KEY"] = secret(key_file)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not render DSNs, password files or provider keys in startup logs.
        raise SystemExit(f"container startup refused ({type(error).__name__})") from None
