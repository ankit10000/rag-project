# Batch 1: Repository Security, Dependencies, Startup and Database Foundation

**Date:** 2026-11-15.
**Scope:** Stages 0–3 of the Batch 1 developer handoff.
**Not covered:** the out-of-scope list in that handoff.

This file is a durable record. No secret values appear in it.

## Stage 0: Security incident and Git history cleanup

### Exposure

`backups/rag_db_pre_phase1_20261111_133022.dump` (178,238 bytes, custom-format `pg_dump`) was committed in the **root commit** `e59d203`. That means it was in every commit on `main`. It was pushed to the **public** repository `github.com/ankit10000/rag-project` (visibility `public`, 0 forks, checked via the GitHub API).

### What the dump contained

The table of contents was listed and per-table row counts were taken. No content was printed. Tables and row counts:

| Table | Rows |
|---|---|
| `conversations` | 219 |
| `messages` | 994 |
| `conversation_memories` | 90 |
| `memory_sources` | 56 |
| `document_chunks` | 9 |
| `vector_test` | 2 |

This is personal conversation and memory data.

### Credential audit

Values were compared against `.env`, and only booleans were printed.

| Credential | Found in the dump or Git history? | Notes |
|---|---|---|
| `GEMINI_API_KEY` | No | No `AIza…` pattern anywhere |
| PostgreSQL password | No credential leak | The local password is the default `postgres`. It "matches" only because the word *postgres* appears everywhere (role names, docs). Every connection URL in history is a placeholder or test dummy. |
| GitHub, private keys, other tokens | No | |
| API bearer token | No | Never committed; `api_token` is git-ignored |

**Result:** no credential was exposed, so none was rotated (rotation applies only to confirmed exposures).

**Recommendation:** the default `postgres`/`postgres` superuser password is weak whether or not it leaked. Change it and apply proposal 006 (least-privilege role). This needs your decision because it affects other local apps.

### Recovery backup (outside the repository, verified)

Location: `C:\Users\vijay puri\Downloads\rag-project-history-backup-20261115\`

- `rag-project-mirror.git`: a full mirror. `fsck` OK, `main` = `2ffab47`, 11 commits.
- `rag-project-all.bundle`: `git bundle verify` OK.
- `rag_db_pre_phase1_20261111_133022.dump`: byte-identical copy.
- `ORIGINAL_REFS.txt`: the original refs.

This backup contains the old history, including the dump. Keep it private, and delete it once it is no longer needed.

### History rewrite

- **Tool:** `git filter-branch --index-filter 'git rm --cached --ignore-unmatch …'` (`git-filter-repo` is not installed).
- **What was removed:** only the dump file.
- **What was preserved:** for each of the 11 commits, the tree differs from the original only by that file. Authors, dates and messages are identical.
- **Local cleanup:** `refs/original/*` was deleted afterwards. The working copy of the dump was restored from the backup; it is ignored by `.gitignore`.

### Remote update

- **Command:** `git push --force-with-lease=main:2ffab47… origin main`.
- **Pre-push check:** the remote was confirmed unchanged (`2ffab47`).
- **Remote now:** `main` = `bdd8d51`.
- **Verification:** a fresh clone has 0 commits touching `backups/` and 0 `.dump` objects.

### Old-to-new commit IDs

Docs that quote the old IDs refer to the same content:

| Old | New | Subject |
|---|---|---|
| e59d203 | d1b4964 | Add comprehensive tests for memory management services |
| 573ae72 | 0efc537 | Add comprehensive test suites for answer scoring, context assembly, and retrieval |
| 1bcc0d1 | dfa10d7 | Add testsafe module … phase 5 provenance tests |
| 2a0e06f | 3366ea8 | Add tests for sentence chunking and metadata filtering … |
| 67aa30a | c8183fb | Add comprehensive tests for PDF ingestion and retrieval functionality |
| aa6a876 | 9bc97b9 | Improve RAG answer grounding and citation reliability |
| c701f6c | c1bbcae | Add timeout handling for Gemini model requests … |
| a81626e | db100fa | Freeze held-out evaluation thresholds |
| 84ccb95 | 4a5e090 | Add comprehensive tests for provenance reconciliation … |
| 2d499ec | 2c165e9 | Implement Phase 6 Backend API and Application Layer |
| 2ffab47 | bdd8d51 | Implement Phase 7 security enhancements … |

### Residual exposure (needs the repository owner)

1. **GitHub still serves the old commits by SHA.** On 2026-11-15, `api.github.com/repos/…/commits/e59d203…` returned 200. GitHub keeps unreferenced commits cached until its own garbage collection runs. The owner must open a GitHub Support request to remove cached views and dereferenced commits, or make the repository private or recreate it.
2. **Other clones** made before the rewrite (other machines, the VS Code/Codex tooling) still contain the old history. Delete them and re-clone.
3. **Local Codex extension refs** (`refs/codex/turn-diffs/*`, two trees) still reference the dump blob in this local repository. They are not pushed and were left untouched (they belong to another tool).
4. **Anyone who already downloaded the dump keeps it.** This cannot be undone. Treat the 994 messages and 90 memories as disclosed.

### Prevention

`.gitignore` now also ignores `*.dump`, `*.backup`, `*.bak`, `*.sql.gz`, `venv/` and `.pytest_cache/`. These were already ignored: `backups/`, `.env`, `.env.*` (except `.env.example`), `api_token`, `*.pem`, `*.key`, `data/uploads/`, `.venv/`, `__pycache__/`.

Checked: `.env.example`, `migrations/*.sql`, the proposals and `requirements.txt` stay trackable.

## Stage 1: Dependencies

- **Environment:** `.venv` on Python 3.14.10 (Windows 11 10.0.26300), pip 26.2.2.
- **Installed (only these 5):** fastapi 0.163.1, starlette 1.10.0, uvicorn 0.54.0, python-multipart 0.0.33, opentelemetry-api 1.45.2 (a FastAPI dependency).
- **Not changed:** no existing package was upgraded (`pip freeze` before/after diff).
- **Checks:** `pip check` reports no broken requirements. A dry-run of `-r requirements.txt -r backend/requirements-api.txt` reports nothing to install.
- **Python compatibility:** the package metadata requires Python ≥ 3.11 for fastapi, starlette and python-multipart, and ≥ 3.10 for uvicorn.
- **Imports verified:** fastapi, starlette, uvicorn, multipart, pydantic 2.14.2, psycopg 3.3.6, pgvector, dotenv, pymupdf 2.0, rank_bm25, numpy 2.5.4, httpx, google.genai 2.34.0, torch 2.15.0+cpu (CPU build), transformers 5.22.1, sentence_transformers 6.2.0 (including the `CrossEncoder` reranker class).
- **Pins:** `backend/requirements-api.txt` now pins exact versions. The `requirements.txt` header documents the Python requirement and the full install command.

## Stage 2: Configuration and startup

### Startup import sequence (after the fix)

1. `run_api.py` imports `backend.config`.
2. `backend.config` runs `load_dotenv(ROOT/.env, override=False)` before reading any `RAG_API_*` setting.
3. uvicorn imports `backend.app`.
4. At startup, the lifespan runs `config_problems()`: errors make startup fail, warnings are logged by name only.
5. The lifespan then loads the token digest.
6. Services are imported lazily per request.

### Changes

- **Lazy embedding model** (`services/embedding_service.py`):
  - `get_model()` loads on first use, under a lock, exactly once.
  - Failures raise `EmbeddingModelLoadError` naming the model, and are not cached.
  - `embedding_service.model` still works.
  - Model identity and the cache key `(EMBEDDING_MODEL, text)` are unchanged.
- **Lazy Gemini client** (`services/llm_service.py`):
  - `get_client()` creates the client on the first request.
  - A missing key raises the same `ValueError("GEMINI_API_KEY is missing from .env")`.
  - `llm_service.client`, `MODEL_NAME` and `FALLBACK_MODELS` keep working and stay patchable.
  - Fallback policy is unchanged.
- **Single provider configuration** (`services/llm_config.py`, new): defaults, env precedence and key presence live here. `backend/routers/providers.py` now uses it; the `ast` parsing of `llm_service.py` was removed.
- **Configuration validation:**
  - `backend/config.py` adds `config_problems()`. Invalid `RAG_API_DOCS` and invalid numeric retrieval knobs are errors. A missing `DATABASE_URL` or `GEMINI_API_KEY` is a warning.
  - New `run_api.py --check-config`.
  - `.env.example` now labels each variable as required, provider-specific or optional. The development-only variables are listed in the `backend/config.py` docstring.
- **Start script** (`scripts/start_api.ps1`):
  - No longer turns native stderr into terminating errors.
  - Checks the venv, `.env`, the packages and the configuration, each with a clear message and exit code 1.
  - Propagates the server's exit code and reports a failed start.

### Verification

- 19/19 unit tests passed, including the new `test_batch1_provider_config.py` and the updated `test_a1_embedding_model_config.py`.
- Network was blocked during the tests, and the `rag_db` fingerprint was unchanged.
- Imports of `backend.app`, `main`, `rag_service`, `ingestion_service`, `memory_service` and `hybrid_search_service` succeed with an empty `GEMINI_API_KEY`. The model was not loaded and no client was created.
- **`.env` loading** was checked with a temporary copy and a dummy `.env`:
  - CORS, hosts and docs values were read from the file;
  - a process environment variable overrides the file;
  - invalid values give clear errors.
- **Live start** via `run_api.py` on 127.0.0.1:8799, offline:

  | Request | Result |
  |---|---|
  | `/health` | 200 |
  | `/health/status` without a token | 401 |
  | `/health/status` with the token | 200, all components "configured" |
  | `/providers` | primary and fallback models, sourced from `.env`, key presence only |
  | `Host: evil.example` | 400 |
  | `/docs` | 200 |

  The token was never printed.
- **Start script:**
  - an invalid configuration exits 1 with a message;
  - `-Port 0` is rejected;
  - a busy port propagates exit code 3 with a red error line.

## Stage 3: Database foundation

### Base schema migration

- **Base schema was missing.** Grep confirmed no `CREATE TABLE` for `conversations`, `messages` or `conversation_memories` in any migration; `document_chunks` existed only in `eval/harness.py`.
- **Source:** a read-only `pg_dump --schema-only` of `rag_db`. No data was copied, and no dump containing user records was used.
- **New file `migrations/000_base_schema.sql`:**
  - creates the `vector` extension and 4 tables (PKs, FKs, the UNIQUE chunk key, 2 btree indexes);
  - is idempotent and does not duplicate any object from 001–003;
  - leaves out `vector_test`, which the code does not use.

### Server and index checks

- **Extensions:** PostgreSQL 18.6; pgvector 0.8.7 is available and installed in `rag_db`. `pg_trgm` is available but not used.
- **Indexes:** no ANN or GIN indexes exist and none were added. Vector and FTS search are sequential scans. This is documented as an option to measure later.

### Fresh build test

- **Database:** `rag_migration_test`, new and empty (from `template0`); it did not exist before.
- **Runs:** 000 → 001 → 002 → 003 applied cleanly **twice** (idempotent).
- **Schema comparison:** the resulting `pg_dump --schema-only` is identical to `rag_db` (excluding `vector_test`).
- **Constraint checks:** a transactional test, rolled back afterwards, confirmed:
  - inserts into conversation, message, memory and user-source link work;
  - `link_kind` and `source_role` defaults apply;
  - the chunk `ON CONFLICT` upsert works;
  - the `<=>` vector operator works;
  - an assistant-source link and a bad `link_kind` are both rejected by their CHECK constraints;
  - deleting a conversation cascades to messages, memories and links.
- **Cleanup:** the disposable database was dropped afterwards.

### Documentation and safety

- **`migrations/README.md`:**
  - now lists 000 and 003 and how to build a fresh database;
  - covers prerequisites (the server-side pgvector extension) and the expected schema;
  - warns that rolling back 003 breaks the current code.
- **`rag_db` safety:** only read-only operations were run against it (`pg_dump --schema-only`, `SELECT`). Its schema was unchanged before and after.

## Files changed in Batch 1 (uncommitted, apart from the history rewrite)

- **Modified:**
  - `.gitignore`, `.env.example`
  - `requirements.txt`, `backend/requirements-api.txt`
  - `backend/config.py`, `backend/app.py`, `backend/routers/providers.py`, `backend/routers/health.py`
  - `services/embedding_service.py`, `services/llm_service.py`
  - `run_api.py`, `run_tests.py`, `scripts/start_api.ps1`
  - `test_a1_embedding_model_config.py`
  - `migrations/README.md`
- **New:**
  - `services/llm_config.py`
  - `test_batch1_provider_config.py`
  - `migrations/000_base_schema.sql`
  - this report
