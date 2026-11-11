# P4-07 — Test infrastructure

## What exists now
| File | Role |
|---|---|
| `testsafe.py` | Shared guard. `require_scratch_db()` aborts (exit 2) unless `DATABASE_URL` is in the process environment and names a scratch DB (`rag_*test*`, never `rag_db`, `postgres`, `template*`). Also wraps `psycopg.connect` so any connection to a non-scratch database (URL, keyword string, `dbname=` kwarg, or none) is refused before network I/O. `.env` is never consulted. Credentials are never printed. |
| `run_tests.py` | Runner. Builds the scratch URL from the `.env` credentials (not printed), checks that every `test_*.py` is classified and carries the guard, runs each test in its own process, fingerprints `rag_db` read-only before/after, optional `--clean` of the scratch DB. |
| `test_testsafe.py` | Self-test of the guard (no DB connection made). |
| `eval/harness.py` | Added `use_current_scratch_database()` (no CREATE/DROP DATABASE, no admin connection). |

Guard line added as the first statements of all 30 pre-existing `test_*.py` files (31 with the self-test); `test_phase5_provenance.py` lost its own hard-coded name check in favour of the shared one; `test_retrieval_phase2.py` now uses the runner's scratch DB instead of creating `rag_phase2_test` through the `postgres` admin database.

## Categories
`unit` (no DB writes, no Gemini), `integration` (scratch DB, Gemini mocked/unused), `live` (`--live`, real Gemini), `manual` (`--manual`; legacy print-only scripts, four with hard-coded conversation ids). Default run = unit + integration.

## One-time setup of the scratch database (read-only on rag_db)
```
psql <server>/postgres -c "CREATE DATABASE rag_test_scratch"
pg_dump -s <rag_db url> | psql <server>/rag_test_scratch -v ON_ERROR_STOP=1
```
(already done; `rag_test_scratch` exists). Re-run after any schema migration so the scratch schema matches.

## Usage
```
.venv\Scripts\python.exe run_tests.py                # unit + integration
.venv\Scripts\python.exe run_tests.py --list
.venv\Scripts\python.exe run_tests.py --live         # needs Gemini quota
.venv\Scripts\python.exe run_tests.py test_phase5_provenance.py --clean
```
Running a test by hand without `DATABASE_URL` for a scratch DB now exits with a SAFETY message instead of touching `rag_db`.

## Known limits
- Scripts under `eval/` (benchmarks, Phase 3.5 harness) are not tests and are not covered by the guard; they use their own scratch DBs.
- The `live` and `manual` scripts are guarded but not yet verified or converted to assertions (Phase 1 remediation).
- `--clean` empties conversations/messages/memories/links/chunks of the scratch DB only.
