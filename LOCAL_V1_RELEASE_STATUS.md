# Local v1.0 release status

2026-11-18 · `main` at `690fcfbbf0abdf43b274161a5e6545f7ad11c325` · application version **1.0.0** · profile **local-v1.0**

**PASS — ready for the locked single-user, single-process, localhost scope in the tested environment. No unresolved critical release blocker.** This is local operational readiness, not formal evaluation acceptance or a production/cloud/multi-user certification.

## Release gates

| Gate | Result | Executed evidence |
|---|---|---|
| 1 — full user journey | PASS | Three real PostgreSQL/TestClient journeys: PDF upload/replacement and failed-replacement rollback → hybrid retrieval → grounded citations → memory/provenance → follow-up → natural forgetting and scoped memory/message/conversation deletion. |
| 2 — failures/security/deadlines/concurrency | PASS | Missing/wrong/oversized tokens, absent digest, token permissions/rotation, Host/CORS/body lengths, DB/provider failures, statement cancellation, atomic deletion rollback, deadline/lock waits, chat/delete ordering and no abandoned worker. |
| 3 — representative development behavior | PASS | 13 new routing/retrieval/grounding/model-identity tests; 245 focused retained checks; v1/frozen-policy regressions preserved. Multi-page fixture evidence is retained under the unchanged ranking margin. |
| 4 — setup/startup/regression/restore | PASS | Versioned 000–003 applied twice to a fresh scratch DB; real localhost process/start/readiness/stop; custom-format PostgreSQL restore including memory links and document vectors; 92/92 registered offline scripts; dependency consistency check. |

HTTP end-to-end fixtures mock Gemini, embeddings and reranking for determinism. Real PostgreSQL/pgvector, PDF parsing, retrieval algorithms, citation validation, conversation/memory storage and deletion execute. The retained ingestion/retrieval suite additionally exercises locally cached embedding/reranker models offline. No live provider request was made.

## Critical blocker register

| Blocker | State | Resolution |
|---|---|---|
| Release-critical user journeys | CLOSED | Final serial journey, rollback, failure and real-server smoke tests pass. |
| Integration regressions encountered | CLOSED | Scratch runner now emits an escaped URL compatible with legacy harnesses; CLI diagnostics retained while API output is redacted; float-shaped deletion IDs are rejected before service calls. |
| Remaining critical blockers within locked scope | NONE | Missing original Phase 4 criteria and formal evaluation decisions do not block this local release. |

## Implemented changes

- API: scoped `DELETE /api/v1/conversations/{id}`, `DELETE /api/v1/conversations/{id}/messages/{message_id}`, and `DELETE /api/v1/conversations/{id}/memories/{memory_id}`. Chat and deletion share deadline-aware conversation locks; existence is rechecked inside the lock. IDs are positive decimal integers, not float-shaped strings. Blank conversation IDs fail validation; default titles match persistence.
- Data: each new deletion operation, source/pair exclusion and summary/checkpoint fence commits or rolls back together. Orphan memories stay stored but unsupported context is excluded. Unknown legacy provenance returns `cleanup_status=incomplete_unknown_provenance`; it is never reported as complete erasure. No provenance is guessed.
- Database: defaults are 5-second connect, 15-second statement and 5-second lock timeouts, with bounded overrides and active request-budget clamping. Existing per-connection commit/rollback/close semantics remain. Shared connection reuse was not introduced: it is unnecessary for this scope and would risk transaction semantics.
- Retrieval/grounding: malformed classifier output cannot match MEMORY by substring; invalid rewrites fall back safely; MIXED answers cannot use a MEMORY tag to bypass document citations; loaded embedding identity cannot silently change. The explicit local-v1.0 profile fixes the embedding model to `all-MiniLM-L6-v2` and fails unverified when document results lack successful reranking. Existing retrieval margins, frozen scorer rules and thresholds are unchanged.
- Reliability: a default 60-second cooperative request budget propagates to body reads, lock waits, provider attempt timeouts/retry waits and DB waits. Late successful responses are fenced; a writing worker is never detached. CPU/native parsing/model work is not hard-preempted, so this is a cooperative budget rather than a promise to kill arbitrary code at a wall-clock instant.
- Security/operations: launcher enforces loopback under the release profile, actual body bytes are checked, CORS supports DELETE, startup/shutdown clear token state, API errors redact details, and private answers/document names stay out of API console output. `/api/v1/health` is public liveness; authenticated `/api/v1/health/ready` checks actual DB connectivity; `/health/status` reports provider presence without calling it.
- Tooling: `offline_local_tests.py` never contacts a database and blocks network calls. `scripts/local_v1_scratch.py` verifies the actual scratch database, initializes only 000–003, runs explicit/registered offline tests without an application-DB fingerprint, and rehearses isolated restore.

## Exact final validation commands and outcomes

Commands ran from `/Volumes/Storage/rag-project`; no staging or commits. Results paths are private test logs, not application data. Use an unused `--results-file` path for repeat runs. Counts overlap and are **not added** into a fabricated unique-test total.

| Command | Result |
|---|---|
| `.venv/bin/python -B offline_local_tests.py` | 6/6 scripts; 52 methods; one deliberate native-DB skip. That native test passes separately with real scratch integration. |
| `LOCAL_V1_RESTORE_DRILL=1 .venv/bin/python -B scripts/local_v1_scratch.py --run-registered --results-file /private/tmp/local-v1-regression-final.json` | 92/92 scripts; 340 unittest method invocations; 2,766 printed PASS checks; 0 failures, 0 skips. Ten live and eight manual scripts excluded. |
| `LOCAL_V1_RESTORE_DRILL=1 .venv/bin/python -B scripts/local_v1_scratch.py --run-tests test_local_v1_budget.py test_local_v1_api.py test_local_v1_database.py test_local_v1_retrieval.py test_local_v1_security.py test_local_v1_deadlines.py test_local_v1_journey.py test_local_v1_restore.py test_local_v1_startup.py --results-file /private/tmp/local-v1-release-gates.json` | Final native release gates: 9/9 scripts, 65 methods, 0 failures/skips. Includes real restore of document content/vector and memory provenance. |
| `.venv/bin/python -B scripts/local_v1_scratch.py --run-tests test_local_v1_api.py test_local_v1_journey.py test_p1_delete_routing.py test_local_v1_startup.py --results-file /private/tmp/local-v1-final-route-checks.json` | 4/4 after final lexical-ID/privacy changes; 13 methods and 137 CLI routing checks, 0 failures/skips. |
| `.venv/bin/python -B scripts/local_v1_scratch.py --run-tests test_local_v1_startup.py --results-file /private/tmp/local-v1-version-startup.json` | Actual loopback process reports application version 1.0.0, readiness succeeds, unauthenticated reads fail, clean shutdown; 1/1. |
| `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch GEMINI_API_KEY=offline-placeholder .venv/bin/python -B run_api.py --check-config` | Exit 0, `configuration OK`; configuration-only, no connection/provider call. |
| `.venv/bin/python -B -m pip check` | Exit 0, no broken requirements. No install or upgrade. |
| `git diff --check` | Exit 0. |

Initial broad run was 89/92: two legacy harnesses rejected the runner's keyword DSN, and one CLI test caught over-redacted diagnostic text. These were fixed and all three passed serially; the subsequent full run passed 92/92. A later offline negative case exposed float-shaped deletion-path coercion; canonical lexical validation now passes. Final route/privacy assertions and 1.0.0 metadata were verified after the full regression.

Native local test files:

| File | Methods |
|---|---:|
| `test_local_v1_budget.py` | 7 |
| `test_local_v1_api.py` | 9 |
| `test_local_v1_database.py` | 8 |
| `test_local_v1_retrieval.py` | 13 |
| `test_local_v1_security.py` | 9 |
| `test_local_v1_deadlines.py` | 6 |
| `test_local_v1_journey.py` | 3 |
| `test_local_v1_restore.py` | 9 |
| `test_local_v1_startup.py` | 1 |

Restore record: `Restore drill verified: rag_local_v1_test_backup_1795001473_e39bcb -> rag_local_v1_test_restore_1795001473_e39bcb`. The disposable backup/restore databases are retained for inspection; no application database was dumped, restored or fingerprinted. The final fixture verifies source-role links, summary flags, document text and 384-dimensional vectors.

## Clean local startup

Validated on the existing macOS/Python 3.14 environment with installed PostgreSQL/pgvector and locally cached models. A completely new machine/venv build was not performed. On a new checkout, configure a private `.env` using `.env.example`; never replace an existing `.env` or copy secrets into logs. Supply an approved localhost `DATABASE_URL` and your `GEMINI_API_KEY`. The selected database must have reviewed migrations 000–003 and a corpus ingested with the fixed release embedding model. Do not apply proposals 004–007. Unknown historical vector origins are not certified.

For scratch verification, an existing `rag_test_scratch` is required. The helper reuses connection credentials but replaces the database name before any connection and verifies `current_database()` before writes. It never connects to `rag_db`. Fresh disposable databases are created only from that verified scratch bootstrap.

```sh
# Scratch setup/verification only; uses .env credentials with DB name replaced.
.venv/bin/python -B scripts/local_v1_scratch.py --initialize
.venv/bin/python -B offline_local_tests.py

# Normal application launch uses your explicitly configured approved local DB.
LOCAL_V1_PROFILE=1 .venv/bin/python -B run_api.py --check-config
LOCAL_V1_PROFILE=1 .venv/bin/python -B run_api.py --host 127.0.0.1 --port 8765
```

The normal launch commands above are instructions, not an invocation against the existing application database during this task. The actual process smoke test used scratch and an isolated temporary token/upload directory, then stopped the process. The launcher defaults to the release profile; do not disable it or launch a separate remote/multi-worker uvicorn configuration for this release.

Locate the private token using `run_api.py --show-token-path` and supply it as `Authorization: Bearer <token>` in your client; do not print it to logs. `run_api.py --rotate-token` rotates it, requiring restart. On POSIX the token file/directory are 0600/0700. Useful entry points:

- `GET /api/v1/health` (public); `GET /api/v1/health/ready` and `/health/status` (authenticated).
- `POST /api/v1/documents` with multipart PDF; replacement requires `?replace=true`.
- `POST /api/v1/conversations`; `POST /api/v1/chat` with `message` and optional `conversation_id`.
- `GET /api/v1/conversations/{id}`, `/conversations/{id}/memories` and `/conversations/{id}/memories/{memory_id}/sources`.
- Scoped DELETE routes above, or a natural-language forgetting request through chat. Unknown legacy provenance is explicitly incomplete, never guessed.

## Integrity and release boundary

All 44 protected assets, official v1 scorer, frozen datasets/manifests/thresholds and historical results remain byte-identical. v2.1 stays development-only. All pre-existing untracked files and initial unrelated tracked changes are preserved; `run_tests.py` has nine additive registrations, and removing those exact lines reproduces its initial hash. Staged content, branch and HEAD are unchanged. Final Git state: 27 modified tracked files and 167 untracked files, including the preserved prior work.

No `rag_db` access, production migrations/backfills/quarantine, proposal application, external model/API calls, held-out/full-split evaluation, staging, commit, push, reset, clean or stash. No dependency was installed. Only verified scratch databases received fixture/schema/restore writes.

Local readiness does not assert live Gemini credential/quota availability, arbitrary-corpus semantic entailment, perfect retrieval recall or formal evaluation acceptance. Numeric/citation guards and representative development cases are verified; existing adaptive ranking margins remain unchanged. No multi-user/multiprocess, OCR, cloud, frontend or TLS-proxy release scope is implied.

## Source/test changes

Updated existing files: `backend/__init__.py`, `backend/app.py`, `backend/config.py`, `backend/dependencies.py`, `backend/errors.py`, `backend/routers/chat.py`, `backend/routers/conversations.py`, `backend/routers/health.py`, `backend/routers/memories.py`, `backend/schemas.py`, `main.py`, `run_api.py`, `run_tests.py`, `services/answer_service.py`, `services/database.py`, `services/embedding_service.py`, `services/gemini_retry_service.py`, `services/llm_service.py`, `services/rag_service.py`.

New files: `LOCAL_V1_RELEASE_STATUS.md`, `offline_local_tests.py`, `scripts/local_v1_scratch.py`, `services/local_deletion_service.py`, `services/local_release_profile.py`, `services/request_budget.py`, `test_local_v1_api.py`, `test_local_v1_budget.py`, `test_local_v1_database.py`, `test_local_v1_deadlines.py`, `test_local_v1_journey.py`, `test_local_v1_restore.py`, `test_local_v1_retrieval.py`, `test_local_v1_security.py`, `test_local_v1_startup.py`.
