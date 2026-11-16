# Post-Merge Baseline — Batch 2 Stages 5, 6 and 7

**Date:** 2026-11-16. **Scope:** verification only.
**Not done:**
- No code, test, migration, dataset, threshold or behaviour change.
- No dependency install or upgrade.
- No database created, dropped, reset or cleaned by hand.
- No held-out evaluation, no H.1 rerun, no Gemini or other LLM call.
- This report is not committed or pushed.

## 1. Git and merge verification

| Check | Result |
|---|---|
| Branch | `main` |
| HEAD | `71767514a1e334af6c785f71c0dbc816c1674318` |
| origin/main | `71767514a1e334af6c785f71c0dbc816c1674318` (fetched), equal to HEAD |
| Working tree at start | Clean (`git status --short` empty) |
| History (`git log -8`) | `7176751` .vscode settings → `593b577` Merge PR #1 → `888cd89` Stage 7 → `0d52538` Stage 6 live eval → `5dc23a4` Stage 6 → `6c08061` Stage 5 H.1 → `09e6007` (pre-Batch-2 base) → `358b8b2` |
| Merge commit | `593b577`, parents `09e6007` + `888cd89` |
| Merge content | `git diff 888cd89 593b577` is **empty**: the merged tree equals the reviewed branch tip exactly, and the merge added nothing |
| After the merge | `7176751` changes only `.vscode/settings.json` (+3 lines: `"python.terminal.useEnvFile": true`) |

All four Batch 2 commits and the merge commit are present. There were no unexpected modifications.

## 2. Python and dependency environment

| Item | Result |
|---|---|
| OS | macOS (Apple silicon) |
| Python | 3.14.5, `.venv` at `/Volumes/Storage/rag-project/.venv` (a virtual environment: `sys.prefix != sys.base_prefix`) |
| Pinned dependencies | All **16/16** pins in `requirements.txt` + `backend/requirements-api.txt` are installed at exactly the pinned versions (psycopg 3.3.6, pgvector 0.5.1, python-dotenv 1.2.4, sentence-transformers 6.2.0, torch 2.15.0, transformers 5.22.1, numpy 2.5.4, google-genai 2.34.0, httpx 0.28.1, pydantic 2.14.2, PyMuPDF 2.0, rank-bm25 0.2.2, fastapi 0.163.1, starlette 1.10.0, uvicorn 0.54.0, python-multipart 0.0.33) |
| `pip check` | No broken requirements |
| App configuration | `run_api.py --check-config` → `configuration OK` (`DATABASE_URL` and `GEMINI_API_KEY` set; values not read or printed) |
| PostgreSQL | 18.7 (Homebrew `postgresql@18`, service started), pgvector 0.8.7, `127.0.0.1:5432`. `postgresql@17` is installed but not running |
| Models | `all-MiniLM-L6-v2` and `cross-encoder/ms-marco-MiniLM-L-6-v2` from the local Hugging Face cache; the runner forces offline mode |

## 3. Database safety and fingerprints

### Test runner safety (inspected before running)
- **Scratch target:** `run_tests.py` takes `.env`'s credentials and replaces only the database name with `--db` (default `rag_test_scratch`). It refuses any name that is not `rag_*test*`, and refuses `rag_db`, `postgres` and `template0`/`template1` (`testsafe.is_scratch_name`).
- **Per-test isolation:** each test runs in its own process with `DATABASE_URL` set to the scratch URL. `TESTSAFE_BLOCK_NETWORK=1` plus offline Hugging Face / Transformers block network access. Every test file must call `testsafe.require_scratch_db()` (the registry check), which wraps `psycopg.connect` so that a non-scratch connection is refused before any network I/O.
- **Application database:** fingerprinted in a read-only transaction before and after the run.
- **Scratch emptying:** `clean_scratch` empties scratch **only** with `--clean`, which was **not** used.
- **Databases the runner can reach:** `rag_test_scratch` (tests) and `rag_db` (read-only fingerprint). No registered test calls the database-creating `harness.use_scratch_database`. `test_retrieval_phase2.py` uses `harness.use_current_scratch_database`, which never creates or drops a database.
- **By-design scratch writes:** `test_retrieval_phase2.py` and `test_stage4_ingestion.py` `TRUNCATE` the **scratch** `document_chunks` table. Scratch was empty before the run, so no existing scratch data could be lost.

### Databases on the server
`postgres`, `rag_db`, `rag_phase35_eval`, `rag_test_scratch`. No database was created during this task.

### Migration state
- `migrations/` contains 000–003 (+ the 002/003 rollback scripts).
- `pg_dump -s` of `rag_db` and `rag_test_scratch` (read-only) produce **identical schemas**.
- Present: `messages.context_excluded` (001), `memory_sources` (002), `link_kind` / `source_role` and `memory_sources_user_source_ck … NOT VALID` (003).
- Absent: the proposal 004 quarantine table, the proposal 005 `category` column, and the proposal 007 `embedding_model` column.
- No migration was applied.

### Fingerprints
Method: `run_tests.fingerprint`, i.e. row count + md5 of all rows per table, in a `default_transaction_read_only=on` session after checking `current_database()`. Only tables that exist are fingerprinted.

| Database | conversations | messages | conversation_memories | memory_sources | document_chunks | Before = after |
|---|---|---|---|---|---|---|
| `rag_db` | 0 | 0 | 0 | 0 | 0 | **identical** |
| `rag_test_scratch` | 0 | 0 | 0 | 0 | 0 | **identical** |
| `rag_phase35_eval` | absent | absent | absent | absent | 135 | **identical** |

- `rag_db` is also identical to the fingerprint recorded before the H.1 evaluation earlier the same day.
- The runner independently reported `application database 'rag_db' fingerprint unchanged : True`.

## 4. Full regression test results

**Command:** `.venv/bin/python run_tests.py` (unit + integration; scratch `rag_test_scratch`), exit code 1 because of the 2 known failures.

| Result | Count |
|---|---|
| Test files run | **48** |
| Passed | **46** (2 of them smoke-only: `test_similarity.py`, `test_memory_storage.py`, exit code only, no assertions) |
| Failed | **2** |
| Not run (by category) | **18**: 10 live (real Gemini: `test_auto_memory`, `test_deleted_facts_regression`, `test_deletion_scenarios`, `test_memory`, `test_memory_conflicts`, `test_memory_decision`, `test_memory_delete_classifier`, `test_memory_delete_decision`, `test_memory_delete_fallback_models`, `test_memory_extraction`) + 8 manual (`test_automatic_memory`, `test_conversation`, `test_duplicate_memory`, `test_memory_delete`, `test_memory_relevance`, `test_memory_search`, `test_memory_update`, `test_semantic_memory`) |

The runner counts **files**. Per-file check counts for the Stage 5–7 suites (from their stage reports, unchanged code):

| Suite | Checks |
|---|---|
| Stage 5 | 47 / 33 |
| Stage 6 | 66 / 13 |
| Stage 7 | 42 |

## 5. Known versus new failures

| Test | Failure | Status |
|---|---|---|
| `test_p1_process_memory.py` | `AttributeError: 'NoneType' object has no attribute 'kwargs'` (check `[5] whitespace-only memory -> SKIPPED, no row`) | **Known.** Same error as the Stage 6 and Stage 7 runs, which were shown identical at the pre-Batch-2 HEAD |
| `test_p1_delete_routing.py` | `FAILED CHECKS: [N2] memory_summary composition: summary + memories ## [N2] memory_summary composition: memories only ## [N3] 4 messages -> extraction with last id as source` | **Known.** Same three checks as before |

**New failures: none.** Result 48 / 46 / 2 equals the recorded Stage 7 baseline.

## 6. Stage 4–7 test coverage (all ran in this suite)

| Stage | Test files | Result |
|---|---|---|
| Stage 4 ingestion | `test_stage4_ingestion.py`, `test_stage4_ingestion_api.py` (+ `test_p2_01`…`test_p2_04`, `test_a2`…`test_a4`) | PASS |
| Stage 5 retrieval | `test_stage5_retrieval.py` (unit), `test_stage5_retrieval_integration.py`, `test_retrieval_phase2.py`, `test_p2_05_zero_top_k.py` | PASS |
| Stage 6 answers | `test_stage6_answer.py` (unit), `test_stage6_answer_integration.py`, `test_b2_citation_evidence.py`, `test_b3_answer_reliability.py`, `test_answer_phase3.py`, `test_context_and_citations.py`, `test_llm_timeout.py`, `test_model_fallback.py` | PASS |
| Stage 7 memory provenance | `test_stage7_memory_provenance.py`, `test_phase5_provenance.py`, `test_memory_sources_regression.py`, `test_p1_memory_update_delete_integration.py`, `test_p1_task1`…`task3`, `test_p1_d7_storage_id_validation.py`, `test_deletion_cleanup.py`, `test_extraction_and_summary_guards.py` | PASS |

## 7. Frozen evaluation asset integrity

| Asset | Check | Result |
|---|---|---|
| `eval/phase35/` (datasets, runner, recorded Stage B results), `eval/framework/` (scorer, thresholds) | `git diff 09e6007 HEAD` | Unchanged since the pre-Batch-2 base |
| Recorded Stage B results (`eval/phase35/results/*`, 6 files) | SHA-256 vs the record taken before the Stage 6 live run | Identical |
| H.1 (`eval/h1_relevance_gate.py`, `eval/results/h1_relevance_gate_dev.json`) | SHA-256 + `git diff 888cd89 HEAD` | Identical |
| Stage 6 offline replay (`eval/stage6_answer_replay.py`, `eval/results/stage6_answer_replay_dev.json`) | `git diff 888cd89 HEAD` | Identical |
| Stage 6 live dev evaluation (`eval/stage6_live_dev_*.py`, `eval/results/stage6_live_dev_20261116/`) | `git diff 888cd89 HEAD` | Identical |
| Stage reports (`docs/remediation/`) | `git diff 888cd89 HEAD` + working-tree status | Identical; no working-tree change under `eval/` or `docs/` |

No held-out evaluation, H.1 rerun or LLM call was made.

## 8. Environment-specific limitations

- **`rag_db` on this Mac is an empty schema**, created from migrations 000–003 on 2026-11-16. It is not the Windows application database (earlier reports: 261 conversations, 1340 messages, …). "`rag_db` unchanged" is verified here, but the suite's effect on real data cannot be observed on this machine.
- **Live and manual tests were not run** (18 files), by design: no Gemini calls were allowed. Their behaviour after the merge is unverified.
- **Platform:** Python 3.14.5 on macOS. The project's original verification used 3.14.10 on Windows 11.
- **Fingerprint scope:** row data only. Identity sequences in `rag_test_scratch` advance during tests (ids are not reused). That is expected, and is not data.
- **Smoke-only passes:** 2 of the 46 passes assert nothing beyond exit code 0.
- **Model cache:** offline mode depends on the two Hugging Face models staying in the local cache.

## 9. Final status

**PASS WITH KNOWN ISSUES.**
- The merge is exactly the reviewed branch: `593b577` tree = `888cd89`, plus the separate `.vscode` commit.
- The environment matches every pin.
- The full regression is 48 run / 46 passed / 2 failed, with **no new failures**. The 2 failures are the long-standing pre-existing memory tests, with identical errors.
- All Stage 4–7 suites pass.
- All three databases are byte/logically unchanged by the run, the test residue is zero, and the frozen and evaluation assets are intact.

**Known issues (not fixed in this task):** `test_p1_process_memory.py`, `test_p1_delete_routing.py`. The open decisions are tracked in the Stage 5–7 reports: H.1 policy, extraction atomicity, proposal 004, scorer artefacts, classifier MEMORY misroutes.
