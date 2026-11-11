"""Self-test of the shared database guard. No database connection is made."""
import testsafe
testsafe.require_scratch_db()

import os
import subprocess
import sys

import psycopg


def check(label, value):
    assert value, label
    print("PASS |", label)


def expect_unsafe(label, fn, *a, **k):
    try:
        fn(*a, **k)
    except testsafe.UnsafeDatabaseError:
        print("PASS |", label)
        return
    raise AssertionError(label)


def run_guard(env_updates, drop=()):
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_updates)
    return subprocess.run(
        [sys.executable, "-c", "import testsafe; print(testsafe.require_scratch_db())"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )


def main():
    # 1. name rules
    for name in ("rag_test_scratch", "rag_phase5_test", "rag_phase2_test"):
        check(f"scratch name accepted: {name}", testsafe.is_scratch_name(name))
    for name in ("rag_db", "postgres", "template1", "rag_phase35_eval", "mydb", "", None, "rag_db_test_x; drop"):
        check(f"name refused: {name!r}", not testsafe.is_scratch_name(name))

    # 2. conninfo parsing
    check("URL form accepted", testsafe.check_conninfo("postgresql://u:p@localhost:5432/rag_test_scratch") == "rag_test_scratch")
    expect_unsafe("URL form rag_db refused", testsafe.check_conninfo, "postgresql://u:p@localhost:5432/rag_db")
    expect_unsafe("keyword dbname=rag_db refused", testsafe.check_conninfo, "host=localhost dbname=rag_db user=u")
    expect_unsafe("dbname kwarg override refused", testsafe.check_conninfo, "postgresql://u:p@h/rag_test_scratch", dbname="rag_db")

    # 3. psycopg.connect is wrapped: refused BEFORE any network I/O
    check("connect guard installed", psycopg.connect is not testsafe._original_connect)
    expect_unsafe("psycopg.connect(rag_db URL) refused", psycopg.connect, "postgresql://u:p@localhost:1/rag_db")
    expect_unsafe("psycopg.connect(dbname=rag_db) refused", psycopg.connect, host="localhost", port=1, dbname="rag_db")
    expect_unsafe("psycopg.connect with no database refused", psycopg.connect, "host=localhost port=1 user=u")
    expect_unsafe("Connection.connect(rag_db) refused", psycopg.Connection.connect, "postgresql://u:p@localhost:1/rag_db")
    expect_unsafe("Connection subclass connect(dbname=rag_db) refused",
                  type("Sub", (psycopg.Connection,), {}).connect, host="localhost", port=1, dbname="rag_db")
    expect_unsafe("URL query override dbname=rag_db refused", psycopg.connect,
                  "postgresql://u:p@localhost:1/rag_test_scratch?dbname=rag_db")

    import asyncio
    try:
        asyncio.run(psycopg.AsyncConnection.connect("postgresql://u:p@localhost:1/rag_db"))
        raise AssertionError("AsyncConnection.connect(rag_db) not refused")
    except testsafe.UnsafeDatabaseError:
        print("PASS | AsyncConnection.connect(rag_db) refused")

    # 4. process-level behaviour (separate interpreters)
    secret = "s3cretpw"
    bad = run_guard({"DATABASE_URL": f"postgresql://u:{secret}@localhost:5432/rag_db"})
    check("rag_db URL aborts with exit code 2", bad.returncode == 2)
    check("abort message does not leak the password", secret not in bad.stdout + bad.stderr)

    missing = run_guard({}, drop=("DATABASE_URL",))
    check("missing DATABASE_URL aborts (does not fall back to .env)", missing.returncode == 2)

    # network block (enabled by TESTSAFE_BLOCK_NETWORK=1)
    probe = ("import testsafe, socket; testsafe.require_scratch_db()\n"
             "try:\n    socket.getaddrinfo('generativelanguage.googleapis.com', 443)\n    print('REACHED')\n"
             "except OSError as e:\n    print('BLOCKED')\n"
             "socket.getaddrinfo('localhost', 5432); print('LOCAL_OK')")
    def run_probe(extra):
        env = dict(os.environ, DATABASE_URL="postgresql://u:p@localhost:5432/rag_test_scratch", **extra)
        return subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env,
                              cwd=os.path.dirname(os.path.abspath(__file__)))
    blocked = run_probe({"TESTSAFE_BLOCK_NETWORK": "1"})
    check("network block refuses external hosts but allows localhost",
          "BLOCKED" in blocked.stdout and "LOCAL_OK" in blocked.stdout)
    unblocked = run_probe({"TESTSAFE_BLOCK_NETWORK": "0"})
    check("network not blocked unless requested", "BLOCKED" not in unblocked.stdout)

    good = run_guard({"DATABASE_URL": "postgresql://u:p@localhost:5432/rag_test_scratch"})
    check("scratch URL accepted", good.returncode == 0 and "rag_test_scratch" in good.stdout)

    print("\nALL TESTSAFE TESTS PASSED")


if __name__ == "__main__":
    main()
