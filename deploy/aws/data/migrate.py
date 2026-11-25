"""Apply the existing reviewed SQL files only to a fresh dedicated AWS database.

Run explicitly with the Compose tools profile. Application startup never migrates.
Existing non-ledger databases are refused rather than adopted or backfilled.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

from runtime import connection_info, secret, verify

MIGRATIONS = (
    "000_base_schema.sql", "001_add_messages_context_excluded.sql",
    "002_add_memory_sources.sql", "003_memory_sources_provenance.sql",
    "007_v2_identity_jobs.sql", "008_v2_turn_results.sql",
)


def main() -> None:
    root = Path(os.getenv("RAG_MIGRATION_DIR", "/app/migrations"))
    with psycopg.connect(connection_info(admin=True), autocommit=True) as connection:
        verify(connection, admin=True)
        connection.execute("SELECT pg_advisory_lock(917240821)")
        ledger = connection.execute("SELECT to_regclass('public.aws_deployment_migrations')").fetchone()[0]
        if not ledger:
            tables = connection.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).fetchone()[0]
            if tables:
                raise ValueError("fresh database required; existing unrecorded tables are not adopted")
            verify(connection, admin=True)
            connection.execute("CREATE TABLE public.aws_deployment_migrations "
                               "(name text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())")
        applied = []
        for name in MIGRATIONS:
            content = (root / name).read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            existing = connection.execute(
                "SELECT sha256 FROM public.aws_deployment_migrations WHERE name=%s", (name,)
            ).fetchone()
            if existing and existing[0] != digest:
                raise ValueError("recorded migration content changed; automatic application refused")
            verify(connection, admin=True)  # Mandatory immediately before EACH SQL migration.
            if not existing:
                connection.execute(content.decode())
                connection.execute("INSERT INTO public.aws_deployment_migrations(name,sha256) VALUES(%s,%s)",
                                   (name, digest))
                applied.append(name)
        verify(connection, admin=True)
        password = secret(os.getenv("RAG_APP_PASSWORD_FILE", "/run/secrets/db_app_password"))
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='rag_v2_app'").fetchone():
            connection.execute(sql.SQL("CREATE ROLE rag_v2_app LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS "
                                       "NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 12")
                               .format(sql.Literal(password)))
        else:
            flags = connection.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication "
                                       "FROM pg_roles WHERE rolname='rag_v2_app'").fetchone()
            if any(flags):
                raise ValueError("existing application role has excess privileges")
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT USAGE ON SCHEMA public TO rag_v2_app")
        connection.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO rag_v2_app")
        connection.execute("REVOKE ALL ON public.aws_deployment_migrations FROM rag_v2_app")
        connection.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_v2_app")
        connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(os.environ["RAG_DATABASE_NAME"])))
        connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO rag_v2_app").format(sql.Identifier(os.environ["RAG_DATABASE_NAME"])))
        rls = connection.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace "
                                 "AND relrowsecurity AND relforcerowsecurity").fetchone()[0]
        if rls != 9:
            raise ValueError("nine FORCE RLS tables required")
        connection.execute("SELECT pg_advisory_unlock(917240821)")
    with psycopg.connect(connection_info()) as connection:
        verify(connection)
    print(json.dumps({"status": "PASS", "database": os.environ["RAG_DATABASE_NAME"],
                      "applied": applied, "force_rls_tables": rls, "role": "rag_v2_app"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"migration refused ({type(error).__name__})") from None
