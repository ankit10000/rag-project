# Phase 7 — Security and Local Deployment

**Status (2026-11-15):** security controls and deployment material implemented as source and documentation. **Nothing was executed:**
- the application was not started, and no API request was sent;
- no test or security scan was run, and nothing is runtime-verified;
- no database was accessed, no package was installed, and no credential was validated.

**This is not a production or security certification.**

## 0. Starting state (inspected)
- HEAD was `84ccb95`.
- The Phase 6 files (`backend/…`, `run_api.py`, `main.py`, the Phase 6 doc) were found **already staged** in the git index. That staging was not done in this session and was left untouched.
- FastAPI, uvicorn and python-multipart are still **not installed**.

## 1. Security architecture
### Audit findings (Phase 6 code, before Phase 7)
| # | Finding | Severity (local single-user) | Fixed in Phase 7 |
|---|---|---|---|
| S1 | Every endpoint unauthenticated: any local process or web page could read conversations, memories and documents, and could chat | High | **Yes**: bearer token on all routes except `/health` |
| S2 | No Host-header check, so a malicious web page can reach a loopback API via **DNS rebinding** | High | **Yes**: TrustedHost allow-list |
| S3 | No request-size limit; multipart bodies are spooled to disk **before** the handler's size check | Medium | **Partly**: Content-Length required for POST and checked against a per-route limit (411/413) before reading |
| S4 | No CORS policy (secure by default, but undefined) | Low | **Yes**: explicit origins only, no credentials, restricted methods and headers |
| S5 | Upload target could be an existing symlink inside the upload dir | Low | **Yes**: refused |
| S6 | Interrupted uploads could leave `.upload-*.part` temp files | Low | **Yes**: removed at startup (own pattern only); `.previous-*.bak` backups are only reported, never deleted |
| S7 | `run_api.py` accepted out-of-range ports and unnormalized hosts; `127.0.0.2` etc. were refused as "non-loopback" | Low | **Yes**: host normalized, ports validated; loopback detected with `ipaddress` |
| S8 | `/health` exposed app and API versions; `/health/status` and config endpoints were public | Low | **Yes**: `/health` returns only `{"status":"ok"}`; everything else needs the token |
| S9 | Logs: `memory_cleanup_service` printed the **forgotten fact's evidence** after a "forget" request; `rag_service` printed 100-character snippets of retrieved chunks | Medium (privacy) | **Yes**: lengths and ids only |
| S10 | No `.env.example`; `.env` variants and user uploads not git-ignored; root `requirements.txt` empty | Medium | **Yes** |
| S11 | No TLS | Accepted for loopback; **blocking** for any LAN use | Documented; not implemented |
| S12 | The CLI and API print full answers to the console (stdout) | Low (local console) | Documented (§12) |

**Confirmed safe by inspection:**
- Error responses never include traces, SQL, paths or secrets (Phase 6 handlers).
- SQL is parameterized everywhere; the backend's own SQL is SELECT-only.
- Memory and sources endpoints are scoped to the conversation and check that the memory belongs to it.
- Provider endpoints return only key *presence*.

## 2. Local network binding
- **Default:** `run_api.py` binds `127.0.0.1:8765` and runs a **single worker** (in-process locks, token digest, caches).
- **Non-loopback:** refused unless `--allow-non-loopback` is given. Even then:
  - a warning is printed (no TLS; the token and data are in clear text);
  - requests are rejected unless their `Host` matches `RAG_API_ALLOWED_HOSTS`.

  The bind address alone therefore cannot expose the API. `0.0.0.0` and `::` get an extra warning.
- **Host and port handling:** the host is trimmed, lowercased and bracket-stripped, and an empty host is rejected. Ports must be 1–65535. `proxy_headers=False`, so forwarded headers are not trusted, and the server header is off.
- **LAN risk:** without TLS anyone on the network path can read the bearer token and all data. **Do not expose the API beyond this machine.**

## 3. Authentication (`backend/security.py`)
- **Token:** `secrets.token_urlsafe(32)` (256-bit), generated on first start.
- **Storage:** stored **outside the repository**:
  - Windows: `%LOCALAPPDATA%\rag-project\api_token`. Per-user profile ACLs apply; no explicit ACL is set.
  - POSIX: `~/.config/rag-project/api_token`, with dir `0700` and file `0600`.

  `RAG_API_TOKEN_FILE` overrides the path. `RAG_API_TOKEN` (≥ 32 characters) can supply the token through the environment instead (less safe: environments are inherited by child processes).
- **Server side:** only the **SHA-256 digest** is kept, in `app.state`, loaded in the lifespan. If loading fails, startup fails (**fail closed**). If the digest is missing, every protected route returns 503.
- **Client:** sends `Authorization: Bearer <token>`. The token is compared digest-to-digest with `hmac.compare_digest`. Missing, malformed and wrong tokens all get the **same 401**. Tokens longer than 512 characters are rejected.
- **Scope:** every router except the public liveness `GET /api/v1/health` is mounted with `Depends(require_token)`. That covers status, settings, metrics, providers, documents, chat, conversations and memories.
- **Rotation and lookup:**
  - `run_api.py --rotate-token` writes a new file (atomic replace); restart to apply.
  - `run_api.py --show-token-path` prints only the path.
  - **The token is never printed, logged or returned.**
- **No user accounts, OAuth or login pages.** Single user only.

## 4. CORS and request security (`backend/app.py`, `backend/config.py`)
- **CORS:** disabled unless `RAG_API_CORS_ORIGINS` lists explicit `http(s)` origins. `*` and `null` make startup fail.
  - Settings when enabled: `allow_credentials=False`, methods `GET, POST`, headers `Authorization, Content-Type, X-Request-ID`; the only exposed header is `X-Request-ID`.
  - **CORS is not authentication**: the token is still required.
- **TrustedHost:** allows `127.0.0.1`, `localhost`, `::1`, `[::1]` plus any explicit `RAG_API_ALLOWED_HOSTS`.
- **Body limits:**
  - POST, PUT and PATCH require a numeric `Content-Length` (411 otherwise).
  - `/documents` allows `MAX_PDF_SIZE_MB` + 1 MiB; every other route allows 1 MiB (413).
  - The upload handler still enforces the exact PDF limit while streaming.
- **Response headers:** `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, and `X-Request-ID`. A client-supplied request id is accepted only if it is ≤ 64 alphanumeric characters (or `-`).
- **Validation and content types:** unchanged from Phase 6. 422 responses carry locations and messages only; unexpected content types fail validation.
- **Docs:** `/api/v1/docs` and `openapi.json` (schema only, no data) stay on for local use; set `RAG_API_DOCS=0` to disable them.

## 5. Secret management
- **`.env.example`** (new) contains placeholders only.
- **`.gitignore` now also ignores:** `.env.*` (except `.env.example`), `data/uploads/`, `*.pem`, `*.key`, `api_token`. `.env` was already ignored.
- **Secrets are never returned:** API responses contain no secrets. The providers endpoint resolves model names without importing `llm_service` and reports key **presence** only.
- **Error paths:** configuration errors raise generic messages (e.g. "DATABASE_URL is missing"). API 500s hide exception text and log only the exception type.
- **Plaintext risk:** `.env` itself is plaintext on disk. That is a documented risk, since no OS credential store integration exists (`keyring` is not installed and was not added).
  - **Recommendation:** restrict the `.env` file to your user account.
  - **Option:** a future, separately approved change could move provider keys to Windows Credential Manager through `keyring`.
- **Provider selection and fallback:** unchanged, and no credential is validated.

## 6. Filesystem security
- **Upload location:** uploads are written only into `data/uploads/`.
- **Server-side names:** the basename is taken, characters are restricted to `[A-Za-z0-9._ -]`, the name must end in `.pdf`, and it is capped at 120 characters.
- **Path checks:** the realpath must stay directly inside the upload dir (no path traversal), and a target that is an existing **symlink** is refused.
- **Temp files:** `open(..., "xb")` with a random name inside the upload dir, removed on any failure, and stale ones removed at startup.
- **Overwrite protection:** 409 unless `replace=true`. On a failed re-ingest the previous file is restored from its backup, and `ingest_pdf`'s single transaction keeps the DB state.
- **No delete endpoint, no arbitrary path parameters, no shell execution.**

## 7. Upload restrictions
- **Type:** `.pdf` names only, and the content must open as a PDF in the existing ingestion path. An empty file is rejected.
- **Size:** `MAX_PDF_SIZE_MB` (50 MB), checked twice: first against `Content-Length` by the middleware (limit + 1 MiB multipart overhead, otherwise 413), then while streaming in the handler (413).
- **Pages:** `MAX_PDF_PAGES` (500), enforced by ingestion.
- **Transfer:** a request without `Content-Length` returns 411; chunked uploads are not accepted.
- **Concurrency:** one ingestion at a time (global lock); duplicates return 409 unless `replace=true`.
- **Resource exhaustion:**
  - The A3 limits apply: 50 MB and 500 pages (`MAX_PDF_SIZE_MB` / `MAX_PDF_PAGES`). Ingestion is serialized by a global lock.
  - PyMuPDF still parses a hostile file within those limits, and there is no total-chunk limit. Lower the limits if untrusted PDFs are expected.
  - Run the API under your normal (non-admin) user account.

## 8. Database security (guidance; nothing executed)
- **Least-privilege role:** create a dedicated role. The proposal `docs/remediation/proposals/006_least_privilege_app_role.sql.proposed` (not applied) gives DML on the five application tables plus sequence usage, and no DDL or role privileges. Migrations stay with the owner role.
- **Password:** set it interactively (`\password rag_app`) and put it only in `.env`.
- **Network:** PostgreSQL should listen on localhost only (`listen_addresses = 'localhost'`), and `pg_hba.conf` should use `scram-sha-256` for `127.0.0.1/32` and `::1/128`. SSL is not needed for loopback-only connections. For any non-local database use `sslmode=require` or `verify-full` in `DATABASE_URL`.
- **Code:** connection strings are never printed by the API, all SQL is parameterized, the backend's own SQL is read-only, and writes go through services with their existing transaction semantics.

## 9. Dependency installation
- **`requirements.txt`** (previously empty) now pins the core packages **as installed in `.venv` on Python 3.14.10**, read from package metadata: psycopg[binary] 3.3.6, pgvector 0.5.1, python-dotenv 1.2.4, sentence-transformers 6.2.0, torch 2.15.0, transformers 5.22.1, numpy 2.5.4, google-genai 2.34.0, httpx 0.28.1, pydantic 2.14.2, PyMuPDF 2.0, rank-bm25 0.2.2.
- **Supported Python:** **3.14.10 is the only version evidenced.** No other version is claimed.
- **`backend/requirements-api.txt`:** fastapi, uvicorn and python-multipart with bounded minimum versions, **not pinned** because they were never installed. Pin after the first reviewed install.
- **Install order:**
  1. create and activate the venv;
  2. `pip install -r requirements.txt`;
  3. `pip install -r backend/requirements-api.txt`.
- Nothing was installed in this phase.

## 10. Local deployment (documented; not executed)
```powershell
cd <project>
python -m venv .venv                                   # Python 3.14 (only verified version)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -r backend\requirements-api.txt
copy .env.example .env                                  # then edit .env with your own values
# database: create role/db per §8; apply migrations/ (see migrations/README.md) as the owner
powershell -ExecutionPolicy Bypass -File scripts\start_api.ps1      # or: .venv\Scripts\python.exe run_api.py
.venv\Scripts\python.exe run_api.py --show-token-path   # read the token from that file for your client
```

**Prerequisite checks:** `scripts/start_api.ps1` checks prerequisites only. It never installs anything, has no network-exposure option, and never prints secrets.

**Using the API:**
- **Stop** with Ctrl+C. There is no background service.
- **Logs** go to the console (stdout/stderr); redirect if you want a file, e.g. `run_api.py *> logs\api.log`.
- **Documents** are stored in `data/uploads/`.
- **Models:** `EMBEDDING_MODEL` and `RERANK_MODEL` are set in `.env`. Models are loaded from the local Hugging Face cache on first use. Set `HF_HUB_OFFLINE=1` to forbid downloads.

**Troubleshooting:**
| Symptom | Cause / action |
|---|---|
| 401 | Missing or wrong token: use the token from `--show-token-path`, and re-read it after a rotation and restart |
| 400 "Invalid host header" | Use `127.0.0.1` or `localhost` in the URL |
| 411 or 413 | The client must send `Content-Length`, and the body must be within the limits |
| 500 on first chat | Check `GEMINI_API_KEY` in `.env` |
| Startup failure "RAG_API_TOKEN … shorter" | Unset `RAG_API_TOKEN` or use a token of ≥ 32 characters |

**Docker:** not introduced. It is optional future work only.

## 11. Backup and recovery (guidance; not executed, not verified)
| What | How | Notes |
|---|---|---|
| Database | `pg_dump -Fc -f backups\rag_db_<ts>.dump rag_db` (as in `migrations/README.md`), then verify with `pg_restore -l` | `backups/` is git-ignored; keep copies off-machine and encrypted |
| Documents | copy `data/uploads/` | Restorable by re-ingesting (`replace=true`) if the DB is lost |
| Configuration | back up `.env` **separately** in an encrypted vault; never in git or plain archives | Rotate the API token after any suspected exposure |
| API token | not needed: regenerate with `--rotate-token` | |

- **Consistency:** stop the API (single-user) before dumping, so the DB and documents form one consistent point.
- **Restore order:**
  1. PostgreSQL role and database;
  2. `pg_restore`;
  3. migrations if newer;
  4. documents directory;
  5. `.env`;
  6. start the API;
  7. spot-check `GET /documents` and `GET /conversations`.
- **Integrity:** record the SHA-256 of each dump. Suggested retention: 7 daily and 4 weekly copies.
- Guidance only; no backup was run or tested.

## 12. Logging and privacy
**Never logged:**
- API keys, the token, Authorization headers, passwords, connection strings;
- memory text (Phase 5 and 7), forgotten-fact evidence;
- retrieved chunk text (Phase 7).

**What is logged instead:**
- **API exception handler:** exception type and request id only.
- **Perf metrics:** names and numbers only; exposed only behind auth.
- **Uvicorn access log:** method, path, status and client address. Paths contain conversation ids, never content.

**Still printed to the console (S12, by design for the CLI):**
- the CLI and `run_turn` print the user's answer and the cited source names;
- some warning messages include exception text from providers or the DB;
- the startup log names the token *source*, never the value.

Tradeoff: removing answer printing would change the CLI UX, so it is documented, not changed.

## 13. Known risks
- **Nothing executed:** none of the controls has run, so the middleware ordering, FastAPI and Starlette version behaviour, and the Windows file permissions are unverified.
- **Plaintext secrets on disk:** the token file and `.env` are protected only by user-profile permissions.
- **No TLS.** LAN exposure is unsafe even with the token.
- **Chunked uploads:** requests without `Content-Length` are rejected (411), which some exotic clients may not support.
- **Long chat calls:** chat is synchronous and long-running; there is no per-request timeout beyond the provider's 120 s HTTP timeout.
- **Token handling in clients:** a local process running as the same user can read the token file. That is inherent to single-user local auth.
- **Hostile PDFs:** PDF parsing of hostile files remains a resource risk within the limits.

## 14. Deferred
- TLS for any non-local use.
- OS credential-store integration for provider keys.
- Pinning the API dependency versions.
- Docker packaging.
- Rate limiting.
- Audit log of API actions.
- Applying the least-privilege role.
- Document and conversation delete endpoints (Phase 6 deferrals stand).
- Dropping console printing of answers in API mode.

## 15. Manual verification plan (for a future, explicitly authorized testing phase)
1. **Install:** `pip install -r backend\requirements-api.txt` in a scratch venv, then `python -m py_compile` and `python -c "import backend.app"` (import only).
2. **Start and token:** start with a scratch `DATABASE_URL`. Confirm the token file is created outside the repo and the token appears in no log.
3. **Auth:** `GET /health` returns 200 `{"status":"ok"}`. Every other route returns 401 without a token, 401 with a wrong token, and 200 with the right token. Rotate the token, restart, and the old token returns 401.
4. **Host header:** `Host: evil.example` returns 400.
5. **CORS:** with `RAG_API_CORS_ORIGINS` unset, there is no CORS header. Set an explicit origin and confirm the preflight allows only `GET`/`POST`. Setting `*` must make startup fail.
6. **Body limits:** a POST without `Content-Length` returns 411; an oversized JSON returns 413; an upload over `MAX_PDF_SIZE_MB` returns 413.
7. **Uploads:**
   - `../x.pdf`, `x.txt`, an empty file and a symlinked name are rejected;
   - a duplicate returns 409, and `replace=true` re-ingests;
   - a failed re-ingest restores the previous file and chunks;
   - stale `.part` files are removed at startup.
8. **Binding:** `run_api.py --host 0.0.0.0` is refused; with `--allow-non-loopback` the warnings appear and the Host check still rejects requests. `--port 0` is refused.
9. **Logs:** run a forget flow and a retrieval, and confirm no memory, chunk text or token appears in the logs.
10. **DB:** apply the least-privilege role on a scratch clone and confirm the app works and DDL is denied.

## Files
- **New:**
  - `backend/security.py`
  - `.env.example`
  - `scripts/start_api.ps1`
  - `docs/remediation/proposals/006_least_privilege_app_role.sql.proposed`
  - this document
- **Modified:**
  - `backend/app.py`: auth wiring, TrustedHost, CORS, body limits, security headers, lifespan token and temp cleanup
  - `backend/config.py`: Phase 7 settings
  - `backend/routers/health.py`: public minimal liveness, protected status
  - `backend/schemas.py`: `HealthResponse` reduced to status
  - `backend/routers/documents.py`: symlink guard
  - `backend/requirements-api.txt`: bounded versions and notes
  - `run_api.py`: host/port validation, token rotation and path commands, uvicorn hardening flags
  - `requirements.txt`: was empty; now pinned core dependencies
  - `.gitignore`: appended entries only
  - `services/memory_cleanup_service.py` and `services/rag_service.py`: **log lines only**

**TESTING AND SECURITY VERIFICATION NOT RUN — strictly prohibited by user instruction. No unit tests, integration tests, smoke tests, regression tests, API requests, browser tests, security scans, penetration tests, benchmarks, live model calls, or evaluation scripts were executed. No database access occurred, no dependencies were installed, and the application was not launched. Only source inspection, static review, and optional syntax compilation were performed.**
