# Stage B — Gemini configuration re-verification (read-only), run 2

1. **Verification time:** 2026-11-12 16:25 +0530. This supersedes run 1 (16:20, BLOCKED: `.env` had not been saved; the file on disk was from 2026-10-31).

## Method (same as run 1)
- **How the app loads the config.** `services/llm_service.py` calls `load_dotenv()`, which uses `override=False`: a value already in the process environment wins over `.env`. It then reads `os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")` and `os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-2.5-flash")`. `find_dotenv()` resolves to `rag-project/.env`.
- **How the effective values were read.** Effective values come from **importing `services.llm_service` as the evaluation runner does**, from the project root, in a separate process with **all outbound sockets blocked**. They are reported as the module's `MODEL_NAME`, `FALLBACK_MODELS` and `_model_order()`.
- **Where each setting came from.** The source of each setting was taken from whether the key was in the process environment before loading, otherwise from `.env`, otherwise the code default.
- **`.env` inspection.** I looked at the structure only: key names, separators and the file timestamp. Every value was masked except the two model settings.

## `.env` state on disk
- 236 bytes, **modified 2026-11-12 16:25:16** (now saved), no BOM, CRLF.
- Lines: `DATABASE_URL=<masked>`, `GEMINI_API_KEY=<masked>`, a blank line, `GEMINI_MODEL=gemini-3.5-flash-lite`, `GEMINI_FALLBACK_MODELS=gemini-3.1-flash-lite,gemini-2.5-flash`.
- `.env` is git-ignored (`.gitignore:2`).

## Effective configuration
| Setting | Effective value | Source |
|---|---|---|
| `GEMINI_MODEL` (2) | `gemini-3.5-flash-lite` | **`.env`** (not set in the process environment) |
| `GEMINI_FALLBACK_MODELS` (3) | `['gemini-3.1-flash-lite', 'gemini-2.5-flash']` | **`.env`** (not set in the process environment) |
| Effective call order | `gemini-3.5-flash-lite → gemini-3.1-flash-lite → gemini-2.5-flash` | — |

4. **Custom configuration is active.** Both settings now resolve from `.env`, not from code defaults.
- **Note for your review.** The configured values are **identical to the code defaults**, so runtime behaviour is the same as before the edit. I cannot know which models you intended. If these are the models you meant, the configuration is correct. If you meant other models, the `.env` values need changing.
- **Fallback.** On HTTP 404, 429 or 5xx (or an empty reply), a call moves to the next model. A run may therefore contain answers from up to 3 models. The runner does not store the model per result row. `llm_service` prints `Gemini model '<name>' failed (<code>); trying next model...` on every switch, so per-call attribution must come from these log lines.

## Readiness checks (read-only)
| Check | Result |
|---|---|
| 7. `eval/phase35/validate.py` | `VALID` |
| Datasets `data_A..D.py` | SHA-256 unchanged (`b4d8b351…`, `a3434f5b…`, `67bc2b5e…`, `655be7b3…`) |
| Preparation report | present |
| 8. Backup `backups/phase35_results_20261112_160951/` + `MANIFEST.json` | present; 4/4 backup files match the manifest SHA-256 |
| 8. Original baseline files | 4/4 unchanged. `eval/phase35/results/` contains only the 4 baseline files (no new, dev re-run or held-out files). |
| 9. Git | HEAD `aa6a876`; nothing staged. The working tree has only untracked reports: `GIT_COMMIT_67AA30A_INVESTIGATION.md`, `LIVE_EVALUATION_PREPARATION_REPORT.md`, `STAGE_B_DEV_LIVE_EVALUATION_REPORT.md` and this report. |

## Confirmations
5. **No secret was exposed.** Only the two model settings and the key names were printed. The `DATABASE_URL` and `GEMINI_API_KEY` values were masked and not written anywhere.
6. **No Gemini API call was made.** Sockets were blocked in the verification process, no evaluation was run and `--fresh` was not used.

Nothing else was touched:
- No project file was modified other than this report.
- No database was accessed.
- No Git operation that changes state was run.
- The full suite was not run.

## 10. Final status: **PASS**
- `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS` resolve from `.env`, so no code default is in effect.
- Dataset validation passes.
- Backup and baseline integrity pass.
- Nothing protected was modified.

The PASS assumes that `gemini-3.5-flash-lite` with fallbacks `gemini-3.1-flash-lite, gemini-2.5-flash` are the intended models. Those values equal the defaults; please confirm this in your review.

STOP. The development live evaluation has not been started and is waiting for your explicit authorization.
