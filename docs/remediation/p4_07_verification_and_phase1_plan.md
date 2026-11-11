# P4-07 verification findings and Phase 1 test plan

## A. P4-07 verification

### Findings that were fixed (all inside test infrastructure/tests; no application code)
| # | Finding | Fix |
|---|---|---|
| F1 | **Guard bypass:** only `psycopg.connect` was wrapped; `psycopg.Connection.connect(...)` (used by pgvector helpers, `psycopg_pool`, subclasses) and `AsyncConnection.connect` reached the network unguarded (demonstrated against an unreachable port, rag_db never contacted). | `testsafe.install_connect_guard()` now wraps `Connection.connect`, `AsyncConnection.connect` and `psycopg.connect`; 5 new self-test cases (URL, kwargs, subclass, async, URL-query `dbname=` override). |
| F2 | `run_tests.py --db <weird string>` crashed with a traceback (no bypass, but untidy). | Name is validated with `testsafe.is_scratch_name` before use; tested with `rag_db`, `postgres`, `template1`, `rag_x_test?dbname=rag_db`, `../rag_db`, quote/semicolon injection, upper case. |
| F3 | **Mis-classification:** `test_deleted_facts_regression.py` and `test_deletion_scenarios.py` call the real Gemini API (their own docstrings say so) but were in the default `integration` run. My P4-07 report wrongly said Gemini was mocked/unused for the default run, and those two runs consumed quota (~2.5 min each). | Moved to `live`. Default run is now 6 unit + 6 integration. |
| F4 | Two more hidden live calls found by running every test with outbound network blocked (socket wrapper, HF offline): `test_phase5_provenance.py` step 8 (real `decide_memory_action`) and `test_retrieval_phase2.py` step 15 (real `rewrite_query`). | Added the missing mocks; both re-verified with network blocked (0 blocked calls, exit 0). |
| F5 | **False-pass risk:** exit code is the runner's only criterion, and `test_similarity.py`, `test_memory_storage.py` (and the old detector script, several live/manual scripts) print results but never assert or exit non-zero. | Runner now reports them as *smoke-only* and does not count them as verified. Real assertions are added in the Phase 1 stage. |

Final default run after the fixes: 12 / 12 passed (2 smoke-only), `rag_db` fingerprint unchanged.

### Verification of the other requested points
2. **Connection paths.** All app code reaches the DB through `services/database.get_connection` → `psycopg.connect` (guarded). `eval/harness.py` and `test_phase5_provenance.py` use `psycopg.connect` (guarded once testsafe is installed). `test_retrieval_phase2.py` spawns one child process (config check) that inherits the scratch `DATABASE_URL` and makes no connection. No test uses `psql`/`pg_dump`/pools. `.env` is never read by the guard; services read it only through `load_dotenv()`, which does not override an existing `DATABASE_URL`.
3. **`--clean`.** Executes exactly `DELETE FROM conversations` and `DELETE FROM document_chunks` on the URL built from `--db`, after `is_scratch_name` and `check_conninfo` pass. No DROP/TRUNCATE exists in `run_tests.py`/`testsafe.py` (grep). Cannot target `rag_db`, `postgres` or templates (tested). The fingerprint connection uses `default_transaction_read_only=on` (mechanism confirmed on the scratch DB: DELETE refused).
4. **Registration.** 31 `test_*.py` files = 31 classified (`--list` reports 0 problems): unit 6, integration 6, live 11, manual 8 (after reclassification).
5. **Rejection.** Created two temporary scripts (unregistered; unregistered and unguarded) → `--list` and a normal run reported all four problems and the run exited 1; temp files removed afterwards.
6. **`eval/`** — see section B.
7. **No app/config/data change in P4-07.** No file under `services/`, `.env`, `requirements.txt`, `services/retrieval_config.py` or `services/database.py` is newer than the Stage-0 register (find -newer). `rag_db` row counts now 261 conversations / 1,340 messages / 127 memories / 93 links / 9 chunks = the audit baseline; runner fingerprints (counts + md5 of all rows of the 5 tables) matched before/after every run.
8. **Git.** See section C.

### B. `eval/` database safety
Guarantees today: each benchmark targets a fixed named scratch DB (`rag_phase2_eval`, `_emb`, `_scale`, `rag_phase35_eval`) created through `harness.use_scratch_database`; `PROTECTED_DBS = {rag_db, postgres}` is checked on create/drop/`assert_scratch`; no eval script calls `drop_scratch_database`; destructive statements (`TRUNCATE document_chunks`, `DROP INDEX`, `DELETE`) run only after `use_scratch_database` has rewritten `DATABASE_URL`.
Gaps (not fixed, proposal):
- Block-list, not allow-list: `use_scratch_database`/`drop_scratch_database` accept any name except two (could create or `DROP ... WITH (FORCE)` e.g. `template1` or another user DB). Proposal: require `testsafe.is_scratch_name` (or an explicit `rag_*eval*|rag_*scale*|rag_*emb*` pattern).
- The eval scripts do not install the psycopg connection guard.
- `use_scratch_database` connects to the `postgres` maintenance DB by design (needed for CREATE DATABASE).
- `scale_benchmark.py` has an extra name `assert`; the others rely on `assert_scratch`.
- `psycopg_pool` is not installed (pip list: psycopg 3.3.6, psycopg-binary, pgvector 0.5.1 only), so the pool benchmark was skipped.

### C. Exact Git status (nothing committed by me; `git log` = 2 commits)
I did not run `git add` or `git commit`. The index nevertheless contains staged entries that were not staged by this session's commands (cause not verified):
- **Staged, new (`A`):** `backups/rag_db_pre_phase5_20261111_163054.dump` (**a database dump — should not be committed**), `docs/phase5_{audit,final_report,migration_report,schema_design}.md`, `eval/phase35/{__init__,data_A..D,run_eval,summarize,validate}.py`, `eval/phase35/results/{log_tier1_dev.txt,log_tier2_dev.txt,tier1_dev.jsonl,tier2_dev.jsonl}`, `migrations/003_*.sql` (2), `services/memory_provenance_service.py`, `test_phase5_provenance.py` (`AM`: staged then modified again).
- **Staged, modified (`M `):** `services/automatic_memory_service.py`, `services/llm_service.py`, `services/memory_service.py`, `services/memory_storage_service.py`.
- **Modified, not staged (` M`):** `eval/harness.py`, 30 `test_*.py` files (guard lines; `test_phase5_provenance.py` and `test_retrieval_phase2.py` further edited).
- **Untracked (`??`):** `docs/PROJECT_COMPLETION_AUDIT.md`, `docs/remediation/` (3 files), `run_tests.py`, `test_testsafe.py`, `testsafe.py`.
- `.gitignore` = `.venv/`, `.env`, `__pycache__/`, `*.pyc` (no `backups/`); `core.autocrlf=true` (LF→CRLF warnings only). A pattern scan for API keys/credential URLs outside `.env` did not finish within the time limit and is **NOT VERIFIED**; the eval result files contain synthetic documents and model answers only (not inspected line by line).
- Suggested (not done): `git restore --staged backups/...dump` and add `backups/` to `.gitignore`; then commit in logical groups after your review of the plan.

---

## B2. Phase 1 test plan (P1-04, P1-08) — awaiting approval

Principles: no change to application behaviour; tests only (plus the runner registration). All new tests are guarded, use the scratch DB, create their own conversations (no hard-coded ids), mock every LLM touch point, finish with a non-zero exit on failure, and are proven offline by running them with the network-blocking wrapper.

### Key discovery that shapes the plan
`is_explicit_memory_delete_request` (`services/memory_delete_service.py`) is **pure regex, not LLM-based**, so it needs no mock; the existing `test_memory_delete_detector.py` has 15 expectations but always exits 0. Classification (`decide_memory_action`, `decide_memories_to_delete` in `memory_decision_service.py`) is LLM-based and mockable at `memory_decision_service.generate_answer`. "Conflict detection" has no separate module: a conflict is an `UPDATE`/`DELETE` decision from `decide_memory_action`, applied by `automatic_memory_service.process_memory`.

### New / changed test files
| File | Scope | Cases |
|---|---|---|
| `test_memory_delete_detector.py` (rewrite, same name) | P1-04 pure detector | **positive** (~14): forget/erase my…, please/kindly/can you prefixes, stop remembering, don't/do not remember/keep/store/save…, delete/remove/erase/clear/wipe + memory/memories, mixed case, extra whitespace/newlines, curly apostrophe. **negative** (~12): "Don't forget to…", "I forgot…", "I forget the formula", programming questions ("remove a column"), "Explain embeddings", empty. **ambiguous (current behaviour pinned)**: "Forget it, move on" False, "Hey, forget my…" False (intentionally conservative), "forget everything" True. **failure**: `None`, non-str input, very long input with a time bound (no catastrophic backtracking). **Probe, report only:** `"How do I clear memory in Python?"`, `"remove the memory leak"` currently match the last pattern → potential false positives; I will document them as a finding and propose a fix separately (no behaviour change without approval). |
| `test_p1_delete_routing.py` (new, scratch DB) | P1-04 routing in `main.main()` | scripted input with `is_explicit…` real, `delete_matching_memories`, `ask_question`, extraction and summary calls mocked: delete request → deletion path, no RAG, no extraction; non-delete message → RAG path, deletion never called; automatic extraction never receives a DELETE; ambiguous message → normal flow. |
| `test_p1_decision_parsing.py` (new, no DB) | P1-08 classification | `decide_memory_action`: each valid action; fenced JSON; lower-case action; unknown action → UNCERTAIN; malformed/empty/prose → UNCERTAIN; JSON list/None → UNCERTAIN; string memory_id; **probes:** `generate_answer` raising and returning `None` (currently not caught for this function — document actual behaviour, propose handling). `decide_memories_to_delete`: DELETE with valid ids; ids outside the conversation filtered; all-invalid → NO_MATCH; duplicate ids de-duplicated; string/float/bool/None ids; non-list `memory_ids` → UNCERTAIN; NO_MATCH/UNCERTAIN force empty ids; fenced/garbage/exception/`None`; prompt content asserts (all candidate ids present; broad "forget everything" instruction present). |
| `test_p1_process_memory.py` (new, scratch DB, decision mocked) | P1-08 conflict/update/delete application | NEW (allowed / `allow_new=False`); DUPLICATE (confirmation link, invalid id → none); UPDATE valid → text+embedding changed, sources appended; UPDATE with id not in candidates → UNCERTAIN, nothing written; UPDATE with empty text → UNCERTAIN; DELETE blocked in automatic mode and nothing deleted; `delete_only` rejects non-DELETE; `allow_delete=True` deletes only own-conversation memory; unknown action → UNCERTAIN; no-candidates paths; contradictory-fact scenario ("lives in Pune" vs "moved to Delhi") modelled via mocked UPDATE decision. |
| `test_p1_memory_update_delete_integration.py` (new, scratch DB) | P1-05/P1-08 correctness | `update_memory`: other conversation's id → False and row unchanged; empty text rejected; assistant source rejected. `delete_matching_memories` with mocked classifier: only selected deleted; foreign-conversation ids ignored; UNCERTAIN/NO_MATCH delete nothing; partial failure reported in `failed_ids`; second conversation untouched (row fingerprint). |
| `run_tests.py` | register all new files; keep old print-only live scripts in `live` | — |

Legacy print-only scripts (`test_memory_conflicts`, `_decision`, `_delete_classifier`, `_delete_decision`, `_fallback_models`) remain as optional live checks; their deterministic equivalents are the new files.

### Acceptance for this stage
All new tests pass in the runner; each also passes with outbound network blocked; existing default suite still 12/12; `rag_db` fingerprint unchanged; findings (possible detector false positives, unhandled `None`/exception in `decide_memory_action`) reported as candidate defects and **not** fixed without your approval. Estimated size: ~110 assertions in 4 new test files plus the detector rewrite.

### Decisions needed
1. Approve this Phase 1 plan?
2. Add a runner option that blocks outbound network (and sets HF offline) for unit/integration runs, so a hidden live call can never recur? (Recommended; it found 4 problems in this verification.)
3. Tighten `eval/harness.py` to an allow-list for scratch names (section B)?
4. Unstage the backup dump and ignore `backups/` now?
