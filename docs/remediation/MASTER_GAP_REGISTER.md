# Master gap register (baseline — stage 0)

Created from the read-only audit (`docs/PROJECT_COMPLETION_AUDIT.md`) and re-checked against the current tree. No code, config or database was changed for this baseline.

Baseline facts re-checked now:
- Git: 2 commits; **26 uncommitted/untracked entries** (Phase 3.5 harness, Phase 5 code/migrations/docs/tests, a backup dump).
- Active database: `rag_db` from `DATABASE_URL` (value not shown). Scratch DBs present: `rag_phase2_eval/_test/_emb/_scale`, `rag_phase35_eval`, `rag_phase5_mig`, `rag_phase5_test`.
- Fallback source (P5-02) still present: `services/memory_service.py` l.290–312.
- 30 modules in `services/`, 35 root test scripts, no runner. DB-touching scripts and LLM/mocking per script were counted by grep: only `test_phase5_provenance.py` has a database-name guard.
- Test inventory facts used below: `test_memory_delete_detector.py`, `test_memory_extraction.py`, `test_memory_update.py`, `test_automatic_memory.py`, `test_duplicate_memory.py`, `test_memory_search.py` contain no mock/patch (so they are live-LLM or hard-coded-id scripts, not deterministic unit tests).

Status vocabulary: VERIFIED COMPLETE · IMPLEMENTED, NOT VERIFIED · PARTIALLY COMPLETE · NOT STARTED · BLOCKED · NOT APPLICABLE.
"Verified (baseline)" means a test/result was observed in this working session; stage work must re-verify and record the final result.

## Register

| ID | Phase | Requirement | Baseline status | Evidence / root cause | Planned correction | Files | Test required | Final |
|---|---|---|---|---|---|---|---|---|
| P1-01 | 1 | User-only extraction | VERIFIED (baseline) | `memory_service.extract_memories` filters role=user | keep | — | existing guards test | VERIFIED COMPLETE: guards test passes in default run (Cycle 1, 18/18) |
| P1-02 | 1 | Assistant text never evidence | VERIFIED (baseline) | parser keeps batch user ids; DB check | keep | — | existing + P5 tests | VERIFIED COMPLETE: guards + P5 provenance tests pass in default run (Cycle 1, 18/18) |
| P1-03 | 1 | Automatic extraction cannot DELETE | VERIFIED (baseline) | `process_memory` blocks DELETE | keep | — | deletion scenarios | VERIFIED COMPLETE: `test_p1_process_memory.py` DELETE-ban cases 22/23/27 pass (Cycle 1) |
| P1-04 | 1 | Explicit deletion detection | IMPLEMENTED, NOT VERIFIED | `memory_delete_service.py`; detector test has no mocks, not run | deterministic mocked tests; live run optional | tests | new mocked test | VERIFIED COMPLETE (tests): `test_memory_delete_detector.py` (75 checks) + `test_p1_delete_routing.py` (121 checks) pass; detector false positives reported as FINDINGs, not fixed |
| P1-05 | 1 | Ownership / conversation isolation | VERIFIED (baseline) | `delete_memory` ownership check, composite keys | add cross-conversation edge tests | tests | edge tests | VERIFIED COMPLETE: ownership/hijack/isolation cases in `test_p1_process_memory.py` and `test_p1_memory_update_delete_integration.py` pass (Cycle 1) |
| P1-06 | 1 | Paired-assistant handling | VERIFIED (baseline) | positional pairing | see P5-05 | — | — | DEFERRED to P5-05 (not in Cycle 1) |
| P1-07 | 1 | Cleanup + summary rewrite + semantic verification | VERIFIED (baseline, LLM mocked) | cleanup tests | add "failed cleanup cannot leave misleading summary" test | `memory_cleanup_service.py` (only if defect) | new test | VERIFIED COMPLETE (LLM mocked): `test_p1_cleanup_failure.py` proves failure branches leave summary empty/clean (Cycle 1) |
| P1-08 | 1 | Memory classification / conflict / update | IMPLEMENTED, NOT VERIFIED | decision/conflict tests have no mocks, not run | mocked deterministic tests | tests | new mocked tests | VERIFIED COMPLETE (tests): `test_p1_decision_parsing.py` (110), `test_p1_process_memory.py` (103), `test_p1_memory_update_delete_integration.py` (37) pass; decision-service exception handling reported as FINDINGs, not fixed |
| P1-09 | 1 | Legacy memory behaviour | PARTIALLY COMPLETE | 34 sourceless memories | see P5-03 | — | — | DEFERRED to P5-03 (not in Cycle 1) |
| P1-10 | 1 | Documentation | NOT STARTED | no Phase 1 report exists | write `phase1_remediation.md` | docs | — | DONE: `docs/remediation/phase1_remediation.md` written (Cycle 1) |
| P2-01 | 2 | End-to-end PDF ingestion test | NOT STARTED | no repo test | add test on scratch DB with a generated PDF | tests | new | pending |
| P2-02 | 2 | Sentence-aware chunking tests | NOT STARTED | `chunker.chunk_text_sentences` untested in repo | unit tests | tests | new | pending |
| P2-03 | 2 | Malformed/empty document handling | NOT STARTED | `pdf_parser.py` has no guards | tests; fixes if defects | `pdf_parser.py`, `ingestion_service.py` | new | pending |
| P2-04 | 2 | Metadata filters across vector/BM25/FTS | IMPLEMENTED, NOT VERIFIED beyond `test_retrieval_phase2.py` | needs per-stage assertions | extend tests | tests | new | pending |
| P2-05 | 2 | BM25 cache invalidation, dedup, duplicate ingestion, dimension mismatch, empty retrieval, RRF determinism, reranker failure isolation | PARTIALLY COMPLETE | some covered in phase-2 test; reranker-failure and empty-retrieval handling not confirmed | inspect, test, fix defects only | `reranker_service.py`, `hybrid_search_service.py` | new | pending |
| P2-06 | 2 | Retrieval defaults unchanged | VERIFIED (read in audit) | `retrieval_config.py` | guard test pinning defaults | tests | new | pending |
| P25-01 | 2.5 | Re-run benchmarks with fixed seeds | NOT STARTED (this round) | results exist, not re-run | re-run on scratch DBs | `eval/*` | reproducibility check | pending |
| P25-02 | 2.5 | Recompute metrics from raw files; compare to reports | NOT STARTED | audit did not re-derive | script + comparison table | `eval/` new script | — | pending |
| P25-03 | 2.5 | Filtered ANN | NOT APPLICABLE (proposed) | no ANN index exists; exact scan is the design | document as verified design; test filtered exact scan | docs | filter test | pending |
| P25-04 | 2.5 | Memory consumption | NOT STARTED | no measurement | measure RSS per stage | `eval/` new | — | pending |
| P25-05 | 2.5 | Synthetic vs real corpus separation | PARTIALLY COMPLETE | real DB has 9 chunks | label in docs; real-document run limited by corpus | docs | — | pending |
| P3-01 | 3 | Adversarial answer tests (missing evidence, partial, contradictory, fake page/file/ref, injection in docs and history, empty retrieval, malformed LLM, retry exhaustion, provider/quota failure) | PARTIALLY COMPLETE | 69 + 62 tests cover much; coverage per item to be mapped | map vs list, add missing | tests | new | pending |
| P3-02 | 3 | Semantic groundedness | IMPLEMENTED, NOT VERIFIED | only structural + self-authored | covered by P35 | — | P35 | pending |
| P35-01 | 3.5 | Failure analysis of dev failures (6 + 14) | NOT STARTED | JSONL exists | analyse each failure, classify | `docs/remediation/` | — | pending |
| P35-02 | 3.5 | Review sheet for ground truth | NOT STARTED | no CSV | generate `review_sheet.csv`, all rows "unreviewed" | `eval/phase35/` | — | pending |
| P35-03 | 3.5 | Human-reviewed ground truth | **BLOCKED** (needs a human) | — | request review | — | — | BLOCKED until reviewer |
| P35-04 | 3.5 | Pre-registered acceptance thresholds | NOT STARTED | none defined | propose, get approval before held-out | docs | — | pending |
| P35-05 | 3.5 | Held-out run, hashes, raw outputs, final report | NOT STARTED | never run | run once after P35-01..04 | `eval/phase35/` | — | **BLOCKED** by P35-03/04 |
| P4-01 | 4 | Config centralisation + env validation | NOT STARTED | env read in several modules | small `config` check on startup | `services/` | new | pending |
| P4-02 | 4 | PDF validation (type, size, pages, malformed) | NOT STARTED | `pdf_parser.py` | limits, tests | `pdf_parser.py`, `ingestion_service.py` | new | pending |
| P4-03 | 4 | Connection pool, timeouts, rollback, shutdown | NOT STARTED | one connection per call, 32 call sites | psycopg_pool needs approval (dependency) — check if installed first | `database.py` | concurrency + before/after benchmark | **approval gate** |
| P4-04 | 4 | Structured logging, correlation IDs, stage timings, redaction | NOT STARTED | `print` only | stdlib logging, request id via contextvars | `services/`, `main.py` | new | pending |
| P4-05 | 4 | Retry/timeout policy, idempotent ingestion, error classification | PARTIALLY COMPLETE | Gemini retry exists; ingestion `ON CONFLICT` exists | add timeouts, classify errors | `llm_service.py`, `gemini_retry_service.py` | new | pending |
| P4-06 | 4 | Health check / startup / shutdown for CLI | NOT STARTED | — | `--check` command; clean exit handling | `main.py` | new | pending |
| P4-07 | 4 | Test infrastructure: DB-name guard, one runner, cleanup, unit/integration/live split | VERIFIED COMPLETE | only P5 test guarded | shared test helper + runner | tests, new `run_tests.py` | self-test | VERIFIED COMPLETE: runner + guard in place; default run 18/18 passed (2 smoke-only), rag_db fingerprint unchanged (see p4_07_verification_and_phase1_plan.md; Cycle 1 re-run) |
| P4-08 | 4 | Backup: ignore dir, restore drill into scratch DB | NOT STARTED | `backups/` untracked and not ignored | `.gitignore` entry; restore both dumps into new scratch DBs | `.gitignore`, docs | restore verify | pending |
| P4-09 | 4 | Performance + concurrency benchmarks | NOT STARTED | — | measure before/after | `eval/` new | — | pending |
| P4-10 | 4 | Auth / multi-user | NOT APPLICABLE (until interface decided) | CLI single user | decision needed | — | — | pending decision |
| P5-01 | 5 | Live Gemini multi-source extraction | BLOCKED until run | mock only | run on scratch DB if quota allows | tests | live test | pending |
| P5-02 | 5 | Remove silent last-message fallback | NOT STARTED | `memory_service.py` l.290–312 | mark fallback explicitly (uncertain), no silent attribution; tests | `memory_service.py`, `memory_storage_service.py` | new | pending (behaviour change; propose first) |
| P5-03 | 5 | 34 sourceless legacy memories | NOT STARTED | no source, no evidence recoverable by design | explicit `unknown_legacy` marker if approved (touches rag_db) + safe forget path | migration | scratch DB test | **approval gate** |
| P5-04 | 5 | 4 assistant-sourced legacy links | NOT STARTED | NOT VALID check tolerates them | reversible quarantine (needs rag_db change) | migration | scratch DB test | **approval gate** |
| P5-05 | 5 | Assistant pairing | PARTIALLY COMPLETE | positional | document assumptions + tests; explicit relation only if justified | docs/tests | new | pending |
| P5-06 | 5 | Shared-source deletion policy | PARTIALLY COMPLETE | all sources excluded (safe) | design source-aware policy, tests | `memory_cleanup_service.py` | new | pending (design first) |
| P5-07 | 5 | Orphan lifecycle for message delete | PARTIALLY COMPLETE | reports orphans only | quarantine flag/report, never delete silently | `memory_provenance_service.py` | new | pending |
| P5-08 | 5 | `memory_revisions` | NOT APPLICABLE (proposed) | not needed for deletion semantics | document rationale | docs | — | pending decision |
| P5-09 | 5 | Migration docs (003) | PARTIALLY COMPLETE | `migrations/README.md` lacks 003 | update | `migrations/README.md` | — | pending |
| G-01 | all | Commit current work | NOT STARTED | 26 uncommitted | needs your go-ahead | git | — | **approval gate** |
| G-02 | all | Full safe regression + "no write to rag_db" check | NOT STARTED | — | table counts/checksums before and after | runner | — | pending |

Requirement count at baseline: **47 rows**, of which 3 proposed NOT APPLICABLE (P25-03, P4-10, P5-08), 2 BLOCKED on a human or live quota (P35-03, P35-05; P5-01 is blocked only if quota fails). This register is finer-grained than the audit's 114-item count; both denominators will be reported at the end.

## Safest execution order
1. Test infrastructure first (P4-07): DB-name guard + runner, so every later stage is safe. No `rag_db` risk, no dependency.
2. Phase 1 → 2 → 2.5 test gaps (all scratch-DB, mostly new tests; code changes only if a test exposes a defect).
3. Phase 3 adversarial tests.
4. Phase 3.5 failure analysis and review sheet (held-out stays untouched).
5. Phase 4 code (logging, PDF limits, timeouts, health check, backup drill), pool last.
6. Phase 5 items; anything touching `rag_db` waits for approval.
7. Full regression and final acceptance report.

## Decisions / approvals needed before code or DB changes
1. Start with P4-07 (test infrastructure) — OK to add `run_tests.py` and a shared guard module and edit the existing test files to use it?
2. Dependency: is `psycopg_pool` already installed in `.venv`? (I will check; installing needs your yes.)
3. Is the product staying a **single-user CLI**? (decides auth, health-check shape, deployment scope).
4. P5-02: OK to change the last-message fallback so such memories are flagged as uncertain instead of silently attributed?
5. P5-03/P5-04: OK to add (via scratch-tested migration 004, applied to `rag_db` only after your approval) an `unknown_legacy` marker and a quarantine of the 4 assistant links?
6. G-01: OK to commit the current uncommitted work first (and add `backups/` to `.gitignore`)?
7. Phase 3.5: who will review the ground truth, and what acceptance thresholds (e.g. correctness, unsupported-claim rate, citation correctness, abstention accuracy) do you want pre-registered?
8. Live Gemini runs: is quota available now for P1-04/P1-08/P5-01 live checks, or should they stay mocked-only?

Stopping here: no code, config, database or dependency change has been made in this stage.
