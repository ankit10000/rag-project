"""
Safe test runner (Phase 4 / P4-07).

    .venv\\Scripts\\python.exe run_tests.py                 # unit + integration
    .venv\\Scripts\\python.exe run_tests.py --list          # show categories only
    .venv\\Scripts\\python.exe run_tests.py --live          # also tests that call Gemini
    .venv\\Scripts\\python.exe run_tests.py --manual        # also legacy manual scripts
    .venv\\Scripts\\python.exe run_tests.py test_phase5_provenance.py
    .venv\\Scripts\\python.exe run_tests.py --clean         # empty the scratch DB afterwards

What it does
  1. Builds the scratch DATABASE_URL (same server/credentials as .env, but the
     database name is --db, default rag_test_scratch) and refuses any name that
     is not a rag_*test* scratch name. The URL is never printed.
  2. Verifies every test_*.py is classified below and starts with the shared
     guard (testsafe), so a new unguarded test fails the run.
  3. Runs each test in its own process with DATABASE_URL pointing at the
     scratch database only.
  4. Takes a read-only fingerprint of the application database (rag_db) before
     and after, and fails if it changed.

Categories
  unit         no database writes, no Gemini
  integration  scratch database, Gemini mocked or not used
  live         calls the real Gemini API (needs quota)       -> only with --live
  manual       legacy print-only scripts, some with hard-coded ids -> only with --manual
"""
import argparse
import os
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import dotenv_values

import testsafe

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRATCH = "rag_test_scratch"

CATEGORIES = {
    "unit": [
        "test_testsafe.py",
        "test_answer_scoring.py",
        "test_context_and_citations.py",
        "test_answer_phase3.py",
        "test_model_fallback.py",
        "test_similarity.py",
        "test_memory_delete_detector.py",
        "test_p1_decision_parsing.py",
        "test_p1_d3_decision_errors.py",
        "test_p1_d4_delete_decision_errors.py",
        "test_p1_d5_delete_ids.py",
    ],
    "integration": [
        "test_memory_sources_regression.py",
        "test_deletion_cleanup.py",
        "test_extraction_and_summary_guards.py",
        "test_retrieval_phase2.py",
        "test_p2_01_pdf_ingestion.py",
        "test_p2_02_sentence_chunking.py",
        "test_p2_03_metadata_filters.py",
        "test_phase5_provenance.py",
        "test_memory_storage.py",
        "test_p1_process_memory.py",
        "test_p1_memory_update_delete_integration.py",
        "test_p1_delete_routing.py",
        "test_p1_cleanup_failure.py",
        "test_p1_d2_classifier_status.py",
        "test_p1_d7_storage_id_validation.py",
    ],
    # "live" = calls the real Gemini API. Verified by running the scripts with
    # outbound network blocked: these made blocked Gemini calls.
    "live": [
        "test_deleted_facts_regression.py",   # reclassified from integration (real Gemini via main.main)
        "test_deletion_scenarios.py",         # reclassified from integration (real Gemini)
        "test_memory_conflicts.py",
        "test_memory_decision.py",
        "test_memory_delete_classifier.py",
        "test_memory_delete_decision.py",
        "test_memory_delete_fallback_models.py",
        "test_memory_extraction.py",
        "test_auto_memory.py",
        "test_memory.py",
    ],
    "manual": [
        "test_automatic_memory.py",    # hard-coded conversation id
        "test_duplicate_memory.py",    # hard-coded conversation id
        "test_memory_search.py",       # hard-coded conversation id
        "test_memory_update.py",       # hard-coded conversation id
        "test_conversation.py",
        "test_memory_delete.py",
        "test_memory_relevance.py",
        "test_semantic_memory.py",
    ],
}

# Scripts whose only pass criterion is "exits 0": they print results but assert
# nothing. They run, but are reported separately and are NOT counted as verified.
SMOKE_ONLY = {"test_similarity.py", "test_memory_storage.py"}

# Tables fingerprinted in the application database (read-only).
FINGERPRINT_TABLES = [
    "conversations", "messages", "conversation_memories",
    "memory_sources", "document_chunks",
]


def category_of(filename):
    for category, names in CATEGORIES.items():
        if filename in names:
            return category
    return None


def env_url():
    url = os.environ.get("TEST_BASE_URL") or dotenv_values(
        os.path.join(ROOT, ".env")).get("DATABASE_URL")
    if not url:
        sys.exit("No DATABASE_URL in .env (or TEST_BASE_URL) to take credentials from.")
    return url


def with_database(url, name):
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path="/" + name))


def app_database_name(url):
    return urlsplit(url).path.lstrip("/")


def fingerprint(url):
    """Read-only fingerprint of the application DB: row count + md5 per table."""
    result = {}
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
        for table in FINGERPRINT_TABLES:
            row = conn.execute(
                f"SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') "
                f"FROM {table} t"
            ).fetchone()
            result[table] = (row[0], row[1])
    return result


def check_registry():
    problems = []
    present = sorted(f for f in os.listdir(ROOT) if f.startswith("test_") and f.endswith(".py"))
    for name in present:
        if category_of(name) is None:
            problems.append(f"{name}: not classified in run_tests.CATEGORIES")
        text = open(os.path.join(ROOT, name), encoding="utf-8").read()
        if "testsafe.require_scratch_db()" not in text:
            problems.append(f"{name}: missing testsafe.require_scratch_db()")
    for names in CATEGORIES.values():
        for name in names:
            if name not in present:
                problems.append(f"{name}: listed but file not found")
    return present, problems


def clean_scratch(scratch_url):
    testsafe.check_conninfo(scratch_url)
    with psycopg.connect(scratch_url) as conn:
        conn.execute("DELETE FROM conversations")      # cascades to messages/memories/links
        conn.execute("DELETE FROM document_chunks")
    print("Scratch database emptied (conversations, messages, memories, links, chunks).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tests", nargs="*", help="specific test files (default: unit + integration)")
    parser.add_argument("--db", default=DEFAULT_SCRATCH, help="scratch database name")
    parser.add_argument("--live", action="store_true", help="include live-Gemini tests")
    parser.add_argument("--manual", action="store_true", help="include legacy manual scripts")
    parser.add_argument("--list", action="store_true", help="list classification and exit")
    parser.add_argument("--clean", action="store_true", help="empty the scratch DB afterwards")
    parser.add_argument("--allow-network", action="store_true",
                        help="do not block outbound network for unit/integration tests")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per test")
    args = parser.parse_args()

    present, problems = check_registry()

    if args.list:
        for category, names in CATEGORIES.items():
            print(f"[{category}]")
            for name in names:
                print("  ", name)
        for problem in problems:
            print("PROBLEM:", problem)
        return 1 if problems else 0

    if problems:
        print("Test registry problems:")
        for problem in problems:
            print("  -", problem)
        return 1

    if not testsafe.is_scratch_name(args.db):
        print(f"SAFETY: --db {args.db!r} is not an allowed scratch database name "
              "(letters/digits/underscore, rag_*test*, never rag_db).")
        return 2

    base = env_url()
    app_db = app_database_name(base)

    try:
        testsafe.check_conninfo(with_database(base, args.db))
    except testsafe.UnsafeDatabaseError as error:
        print(f"SAFETY: {error}")
        return 2

    scratch_url = with_database(base, args.db)

    try:
        with psycopg.connect(scratch_url) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        print(f"Scratch database {args.db!r} is not reachable. Create it first "
              "(schema only, from the application DB) - see docs/remediation/p4_07_test_infrastructure.md.")
        return 2

    if args.tests:
        selected = []
        for name in args.tests:
            name = os.path.basename(name)
            if name not in present:
                print(f"Unknown test file: {name}")
                return 2
            selected.append(name)
    else:
        categories = ["unit", "integration"]
        if args.live:
            categories.append("live")
        if args.manual:
            categories.append("manual")
        selected = [n for c in categories for n in CATEGORIES[c]]

    skipped = [n for n in present if n not in selected]

    before = fingerprint(base)
    env = dict(os.environ, DATABASE_URL=scratch_url, PYTHONIOENCODING="utf-8")
    env.pop("TEST_BASE_URL", None)

    results = []
    for name in selected:
        started = time.time()
        test_env = dict(env)
        # unit/integration tests must never reach the network (Gemini, HF hub);
        # only the "live" category (and --allow-network) may.
        if category_of(name) in ("unit", "integration") and not args.allow_network:
            test_env.update(TESTSAFE_BLOCK_NETWORK="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        try:
            proc = subprocess.run(
                [sys.executable, name], cwd=ROOT, env=test_env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=args.timeout,
            )
            code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = -1, f"TIMEOUT after {args.timeout}s"
        elapsed = time.time() - started
        results.append((name, category_of(name), code, elapsed, out))
        print(f"{'PASS' if code == 0 else 'FAIL'}  {name:<46} {category_of(name):<12} {elapsed:6.1f}s")
        if code != 0:
            print("      " + "\n      ".join(out.strip().splitlines()[-8:]))

    after = fingerprint(base)
    unchanged = before == after

    if args.clean:
        clean_scratch(scratch_url)

    failed = [r for r in results if r[2] != 0]
    print("\n=== Summary ===")
    print(f"scratch database : {args.db}")
    print(f"run / passed / failed : {len(results)} / {len(results) - len(failed)} / {len(failed)}")
    smoke = [r[0] for r in results if r[0] in SMOKE_ONLY and r[2] == 0]
    print(f"of the passes, smoke-only (exit code only, no assertions) : {len(smoke)} {smoke}")
    print(f"not run (by category) : {len(skipped)}")
    for name in skipped:
        print(f"   skipped {name} [{category_of(name)}]")
    print(f"application database '{app_db}' fingerprint unchanged : {unchanged}")
    if not unchanged:
        for table in FINGERPRINT_TABLES:
            if before[table] != after[table]:
                print(f"   CHANGED: {table} {before[table][0]} -> {after[table][0]} rows")

    return 0 if (not failed and unchanged) else 1


if __name__ == "__main__":
    sys.exit(main())
