"""Phase 2 READ-ONLY legacy memory provenance inventory (CLI).

    .venv\\Scripts\\python.exe legacy_provenance_inventory.py --database <name> --output <report.json>
        [--conversation-id <uuid>] [--include-text-hash]
        [--allow-protected-database --approval-ref "<written approval reference>"]

* There is NO default database. --database is required and is shown in the output.
* Credentials are taken from DATABASE_URL in .env (host/user/password only);
  the database name in that URL is ignored and replaced by --database. The
  connection string is never printed.
* Protected names (rag_db, postgres, template0, template1) are refused unless
  --allow-protected-database AND a non-empty --approval-ref are given. Running
  against production data (including a clone/snapshot of it) requires the
  separate approval described in docs/remediation/PHASE2_LEGACY_MEMORY_RECONCILIATION.md.
* The connection is read-only (default_transaction_read_only=on, BEGIN READ
  ONLY, ROLLBACK). Nothing is inserted, updated, deleted, quarantined or
  repaired; memory text is never written to the report (optional SHA-256 only).
"""

import argparse
import datetime
import json
import os
import sys
from urllib.parse import urlsplit, urlunsplit

ROOT = os.path.dirname(os.path.abspath(__file__))
PROTECTED_DATABASES = {"rag_db", "postgres", "template0", "template1"}


def _conninfo_for(database: str) -> str:
    from dotenv import dotenv_values

    base = dotenv_values(os.path.join(ROOT, ".env")).get("DATABASE_URL")
    if not base:
        raise SystemExit("No DATABASE_URL in .env to take credentials from.")
    parts = urlsplit(base)
    return urlunsplit(parts._replace(path="/" + database))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", required=True, help="target database name (no default)")
    parser.add_argument("--output", required=True, help="path of the JSON report to write")
    parser.add_argument("--conversation-id", help="limit the inventory to one conversation")
    parser.add_argument("--include-text-hash", action="store_true",
                        help="add a SHA-256 of each memory text (the text itself is never written)")
    parser.add_argument("--allow-protected-database", action="store_true",
                        help="required to target rag_db/postgres/template*; needs --approval-ref")
    parser.add_argument("--approval-ref", help="reference to the written approval for a protected target")
    args = parser.parse_args(argv)

    database = args.database.strip()
    if not database:
        parser.error("--database must not be empty")
    if database in PROTECTED_DATABASES:
        if not args.allow_protected_database or not (args.approval_ref or "").strip():
            parser.error(
                f"refusing protected database {database!r}: pass --allow-protected-database "
                "and --approval-ref only after the separate written approval")

    output = os.path.abspath(args.output)
    if os.path.exists(output):
        parser.error(f"output file already exists, refusing to overwrite: {output}")

    print(f"TARGET DATABASE : {database}  (read-only inventory)")
    if args.conversation_id:
        print(f"SCOPE           : conversation {args.conversation_id}")

    from services.legacy_provenance_inventory import run_inventory

    report = run_inventory(_conninfo_for(database), args.conversation_id, args.include_text_hash)

    if report["database"] != database:
        raise SystemExit(f"connected database {report['database']!r} does not match --database {database!r}")

    report["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    report["approval_ref"] = (args.approval_ref or "").strip() or None
    report["tool"] = "legacy_provenance_inventory.py (read-only)"

    with open(output, "x", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=False)

    summary = report["summary"]
    print(f"CONNECTED       : {report['database']}  transaction_read_only={report['transaction_read_only']}")
    print(f"MEMORIES        : {summary['total_memories']}")
    for category, count in summary["by_category"].items():
        print(f"  {category:<30} {count}")
    print(f"  USER_SUPPORTED with recorded issues: {summary['user_supported_with_recorded_issues']}")
    print(f"REPORT          : {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
