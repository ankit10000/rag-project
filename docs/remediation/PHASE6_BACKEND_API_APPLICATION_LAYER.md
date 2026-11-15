# Phase 6 — Backend API and Application Layer

**Status (2026-11-15):** implemented as source code. **Not executed**: no server was started, no request was sent, no test was run and no database was accessed.
- **Dependencies not installed:** FastAPI, uvicorn and python-multipart are not installed in `.venv`. They were **not** installed, because that would need network access.

## 1. Existing architecture inventory
| Area | Existing entry point |
|---|---|
| CLI turn loop | `main.py` (classify/delete routing → retrieval → grounded answer → save → extraction → summary) |
| RAG | `services/rag_service.ask_question` (classify, rewrite, hybrid search, rerank, context assembly, grounded answer and citations) |
| Ingestion | `services/ingestion_service.ingest_pdf(path)` (A2 transactional upsert and stale cleanup, A3 limits, A4 .pdf check) |
| Conversations | `services/conversation_service` (create, exists, save_message, history/live messages, summary, checkpoints) |
| Memory | `memory_service`, `automatic_memory_service`, `memory_cleanup_service`, `memory_provenance_service`, `memory_context_service` (Phase 3), `legacy_provenance_classifier` (Phase 2) |
| Provider | `services/llm_service` (Gemini only; primary and fallback models; creates the SDK client and requires the key **at import**) |
| Config | `services/retrieval_config` (env/.env knobs) |
| Metrics | `services/perf_metrics` (Phase 5) |
| DB | `services/database.get_connection()`: a new psycopg connection per call |

**Dependencies installed:** pydantic 2.14, httpx, psycopg 3, google-genai, sentence-transformers, python-dotenv. Not installed: fastapi, starlette, uvicorn, python-multipart. `requirements.txt` is empty. No existing HTTP framework is in the repo.

## 2. Framework and rationale
**FastAPI** was chosen:
- it is the requested preference;
- pydantic v2 is already installed;
- it provides validation, dependency injection, exception handlers, lifespan and OpenAPI.

Its packages are listed in `backend/requirements-api.txt` and must be installed manually before first start (see §14). `requirements.txt` was left unchanged because it was already empty.

## 3. Backend architecture
```
run_api.py                      loopback-only uvicorn launcher (single worker)
backend/
  __init__.py                   versions (app 0.6.0, api v1)
  app.py                        create_app(): lifespan, request-id middleware, error handlers, routers under /api/v1
  config.py                     host/port defaults, upload dir, listing bounds
  errors.py                     ApiError + centralized handlers (no traces/SQL/paths/secrets)
  dependencies.py               UUID validation, existence checks, per-conversation and ingestion locks
  schemas.py                    pydantic request/response models
  repositories.py               read-only listing queries the services do not provide
  routers/ health, settings, metrics, providers, documents, chat, conversations, memories
  requirements-api.txt
```

**Single orchestration path.** The CLI loop body was moved **unchanged** into `main.run_turn(conversation_id, query)`. It now returns a small result dict describing what happened, and both the CLI loop and `POST /chat` call it. Verified by a whitespace-insensitive diff: only the wrapper, the outcome variables and the return dicts were added. There is no second RAG pipeline.

**Lazy imports.** Importing `backend.app` imports only FastAPI, pydantic and `backend.*`. Every service module is imported **inside** handlers. As a result:
- the app object can be created without a database connection, model load or provider client;
- the first chat request loads the models and the Gemini client, through `main` → `rag_service` → `llm_service` and `embedding_service`;
- the first upload loads the embedding model.

## 4. Endpoint inventory (`/api/v1`)
| Method | Path | Purpose | Service used |
|---|---|---|---|
| GET | `/health` | liveness, versions | none |
| GET | `/health/status` | component status: configured / initialized / unavailable / not_checked | env presence checks; `sys.modules` to see whether models are loaded |
| GET | `/settings/retrieval` | read-only configuration | `retrieval_config` |
| GET | `/metrics/performance` | Phase 5 aggregates (names and numbers) | `perf_metrics.snapshot()` |
| GET | `/providers` | provider and model settings, key presence only | static `ast` read of `llm_service` defaults plus env/.env precedence |
| GET | `/documents` | list documents (chunks, pages) | `repositories.list_documents` |
| GET | `/documents/{name}` | document detail and per-page chunks ("indexed") | `repositories.get_document` |
| POST | `/documents?replace=false` | upload and ingest a PDF (multipart `file`) | `ingest_pdf` |
| POST | `/chat` | ask or forget (one turn) | `main.run_turn` |
| POST | `/conversations` | create a conversation (title) | `create_conversation` |
| GET | `/conversations?limit=` | list conversations (non-excluded message count) | `repositories.list_conversations` |
| GET | `/conversations/{id}?limit=` | history (non-excluded messages, ≤ 200) | `get_live_messages` |
| GET | `/conversations/{id}/memories?limit=` | **user-supported** memories with category and valid user source ids; unverified ones are counted only | Phase 3 `load_provenance_facts` + Phase 2 `classify_memory` + `classify_memory_text` |
| GET | `/conversations/{id}/memories/{mid}/sources` | source message ids, role and link_kind (no message content) | `get_memory_sources` |

OpenAPI is at `/api/v1/openapi.json`, with docs at `/api/v1/docs`.

## 5. Schemas
`backend/schemas.py`:
- **Requests:** `ChatRequest` (message 1–8000 chars, optional `conversation_id`), `ConversationCreate`.
- **Responses:** `ChatResponse` (request_id, conversation_id, kind answer/memory_deletion, answer, status, citations [ref, document, page, chunk_id], memory_extraction, summary_update, deleted_count), `DocumentSummary/Detail`, `IngestResponse`, `ConversationSummary/Detail`, `MemoryList/Item/Source`, `ProvidersResponse`, `SystemStatusResponse`, `MetricsResponse`.
- **Errors:** `{"error": {"code", "message", "request_id"[, "details"]}}`.

## 6. Service integration mapping and behaviour preservation
- **Chat** keeps the CLI behaviour exactly, because it calls `run_turn`:
  - explicit-delete routing and the D2 gate;
  - citation validation, abstention and prompt-injection rules;
  - retrieval defaults and provider fallback;
  - persistence order, the extraction-checkpoint rules and the summary update.

  The response returns only the validated `citations`, never the prompt.
- **Same-conversation turns are serialized** by a per-conversation lock, preserving the CLI's sequential write and checkpoint ordering under concurrent HTTP requests.
- **Ingestion is serialized** by a global lock.
- **Upload flow:**
  - The file is **streamed** into a temporary file inside `data/uploads/`. The size limit is `MAX_PDF_SIZE_MB` (413 when exceeded) and empty files are rejected.
  - **Safe server filename:** basename only, restricted character set, `.pdf` only, at most 120 characters. A realpath check ensures it stays inside the upload directory.
  - **No silent overwrite:** if the document name already exists, either in the database or as a file, the request returns 409 unless `replace=true`. With `replace=true`, ingestion uses the A2 re-ingest semantics.
  - **Failure handling:** the previous file is kept as a backup until the new version has ingested. On failure the new file is removed and the previous one restored; the database is unchanged because `ingest_pdf` is one transaction.
- **Ingestion status:** ingestion is synchronous. Status is "indexed" when chunks exist (`GET /documents/{name}`). There is no background job store.

## 7. Database access boundaries
- **Writes** happen only through existing services: `create_conversation`, `save_message` (inside `run_turn`), `ingest_pdf`, memory services (inside `run_turn`).
- **Reads:** `backend/repositories.py` contains **SELECT-only** listing queries, all scoped and bounded. Conversation lists count only non-excluded messages.
- **Schema:** no schema change, no migration, and no new table or column.

## 8. Provider configuration boundaries
- **Provider:** only Gemini is implemented in the repository, and only it is reported.
- **Model names:** resolved without importing `llm_service`. Its `os.getenv` defaults are read with `ast` and overridden by the process environment and then `.env`, the application's own precedence.
- **API keys:** reported as `api_key_configured: true/false` only. Values are never read into a response or logged.
- **No write endpoint:** provider or model changes and credential storage are **deferred to Phase 7** (secure storage required). The fallback policy is unchanged.

## 9. Error handling
| Situation | Status |
|---|---|
| `ApiError` | its own status: 404 not_found, 409 conflict, 413 file_too_large, 422 invalid_* / unsupported_file_type / empty_file / ingestion_rejected / ingestion_failed |
| Request validation | 422, with field locations and messages only (submitted values are not echoed) |
| Any other exception | 500 `internal_error`; only the exception **type** and request id are logged |

Ingestion failure types are reported by class name only. Every response carries `X-Request-ID`.

## 10. Security considerations (Phase 6 scope)
- **Binding:** `run_api.py` binds to **127.0.0.1** and refuses any other host unless `--allow-non-loopback` is given. It runs a single worker with no reload.
- **No authentication, no CORS and no TLS.** The API is intended for local tools on the same machine only. **Phase 7 security is not done.**
- **Secrets and internals:** none are returned (no keys, connection strings, internal paths or tracebacks). Uploads cannot traverse paths.

## 11. Deferred features
| Feature | Reason |
|---|---|
| Document deletion | No existing deletion service. Safe removal would need defined DB, cache and file semantics; no destructive endpoint without it. |
| Conversation rename / delete | No existing service. Deletion cascades memories and links; it needs a reviewed design. |
| Direct memory delete or modify | Must go through the established deletion and cleanup flow; use chat ("forget …"). A direct endpoint would bypass the summary rewrite and context exclusion. Memory creation from the API is not offered, because provenance must come from user messages. |
| Retrieval filters and response options in chat | `ask_question` has no filter parameters; adding them would change the RAG pipeline. |
| Streaming | The turn does post-answer work (extraction, summary); safe streaming semantics are not designed. |
| Background ingestion jobs / status store | No job model; synchronous ingestion is simpler and transactional. |
| Provider/model selection, credential storage, auth, CORS, network hardening | Phase 7 |
| Quarantine-aware memory listing | The Phase 2 schema is not applied; Phase 3's `exclude_memory_ids` hook remains the integration point |

## 12. Proposed migrations
None.

## 13. Known limitations
- **Untested:** the code has never run. FastAPI and uvicorn are not installed; `py_compile` checks syntax only, not imports.
- **First-request delays:** the first `/chat` loads models and creates the Gemini client. Without `GEMINI_API_KEY` it fails with a 500 (`llm_service` raises at import). The first upload loads the embedding model.
- **Single process:** locks and caches are in-process, so the API must run with one worker.
- **Blocking chat:** `/chat` is synchronous and long-running (LLM calls, extraction, summary). Clients need a long timeout.
- **Model-load status:** reflects only whether a module has been imported in this process.

## 14. How to start (documented only; not executed)
```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements-api.txt   # requires approval + network
.venv\Scripts\python.exe run_api.py                                        # http://127.0.0.1:8765/api/v1/docs
```
The CLI is unchanged: `.venv\Scripts\python.exe main.py`.

## 15. Future frontend integration contract
- **Base URL and docs:** `http://127.0.0.1:8765/api/v1`, JSON. The OpenAPI schema is the contract.
- **Chat:** `POST /chat` `{message, conversation_id?}` returns `{conversation_id, answer, citations[], kind, status}`. Keep `conversation_id` for later turns, and render `citations` as `[ref] document, page`.
- **Errors:** always `{"error": {code, message, request_id}}`. Show `message`; log `request_id`.
- **Uploads:** `multipart/form-data` field `file`, and `?replace=true` to re-ingest.
- **Read views** for the UI: documents, conversations, history, user-supported memories with categories, providers, settings, metrics.

## Files
- **New:**
  - `backend/__init__.py`, `app.py`, `config.py`, `errors.py`, `dependencies.py`, `schemas.py`, `repositories.py`, `requirements-api.txt`
  - `backend/routers/__init__.py`, `health.py`, `settings.py`, `metrics.py`, `providers.py`, `documents.py`, `chat.py`, `conversations.py`, `memories.py`
  - `run_api.py`
  - this document
- **Modified:** `main.py`. The loop body moved into `run_turn()` with identical logic, plus outcome tracking and return dicts.

**TESTING AND API EXECUTION NOT RUN — strictly prohibited by user instruction. No unit tests, integration tests, smoke tests, regression tests, API requests, browser tests, evaluations, benchmarks, live model calls, or evaluation scripts were executed. No database access occurred. Only source inspection, static review, and optional syntax compilation were performed.**
