# Live evaluation preparation (Stage B) — preparation only

Date: 2026-11-12.
- **No Gemini or other live-provider call was made**, and `--fresh` was not used.
- No original result was deleted or overwritten.
- No dataset, ground truth, scoring rule, threshold or application code was changed.
- Nothing was staged, committed or pushed. The backup sits under the git-ignored `backups/` folder.

## 1. Runner and what it writes
`eval/phase35/run_eval.py --tier 1|2 --split dev|heldout|all [--limit N] [--pause S] [--fresh] [--no-ingest]`:
- **Setup:** at import it calls `harness.use_scratch_database("rag_phase35_eval")`. That creates the DB if it is missing, ensures the `vector` extension and the `document_chunks` table, and sets `os.environ["DATABASE_URL"]` to the scratch DB **before** any `services` module is imported.
- **Results:** each case is appended to `eval/phase35/results/tier<T>_<split>.jsonl`. The runner is resumable: cases already in that file are skipped.
- **Tier 2:** first rebuilds the scratch corpus with `TRUNCATE document_chunks` in `rag_phase35_eval`, then ingests the 12 documents as real PDFs through the real ingestion pipeline. `--no-ingest` skips this.
- **Pause:** sleeps `--pause` seconds (default 3) between cases.
- **Summary:** `eval/phase35/summarize.py` writes `eval/phase35/results/REPORT.md`; with `--sheet` it also writes `eval/phase35/review_sheet.csv`. Neither file exists yet.

## 2. Files `--fresh` (or a re-run) could delete or overwrite
| File | Risk |
|---|---|
| `eval/phase35/results/tier1_dev.jsonl` | **deleted** by `--tier 1 --split dev --fresh` |
| `eval/phase35/results/tier2_dev.jsonl` | **deleted** by `--tier 2 --split dev --fresh` |
| `eval/phase35/results/log_tier1_dev.txt`, `log_tier2_dev.txt` | these are shell-redirect logs; the runner never writes them, so they are overwritten only if a new run is redirected to the same name. Proposed commands use new names. |
| `tier1_heldout.jsonl`, `tier2_heldout.jsonl` | do not exist; created by the held-out runs |
| `REPORT.md`, `review_sheet.csv` | do not exist; created by `summarize.py` |
| `eval/results/*` (Phase 3 and 2.5 results) | not touched by `run_eval.py` or `summarize.py` |

## 3. Backup (executed) and integrity verification
- **Location:** `backups/phase35_results_20261112_160951/`. This is git-ignored by the existing `backups/` rule and contains a `MANIFEST.json`.
- **Method:** `shutil.copy2`, then SHA-256 and size of each copy compared with the original. Size, SHA-256 and mtime of every original were recorded before and after.

| File | Bytes | SHA-256 | Copy |
|---|---|---|---|
| `log_tier1_dev.txt` | 3548 | `57c95ec9230931cc00b9d83c8c28a42840cf197b2dd12faccc70cae0e4013a10` | identical |
| `log_tier2_dev.txt` | 23729 | `853eee37def8a0645fa946304bd25109bcdb0d48353032c2c98d108ef60bcb05` | identical |
| `tier1_dev.jsonl` | 57273 | `66824d21435a6273f62b7dc8d7a978f499e2b34b0f5bef0834e5b31d2d42a6ce` | identical |
| `tier2_dev.jsonl` | 52081 | `77e49b26ea5cf714a6c8239f0cfb31f294838d8e94baeefecedd8b291f994954` | identical |

- **File count:** 4 originals → 4 copies (plus `MANIFEST.json`).
- **All copies byte-identical:** True.
- **Originals unchanged:** True (size, SHA-256 and mtime).
- **Second safety net:** all four baseline files are also tracked in git; their last change was in commit `1bcc0d1`. They can therefore be restored from `HEAD` as well.

## 4. Held-out split and review / freeze status
- **Split:** deterministic, `sha1(case_id) % 10 < 3` → dev, otherwise held-out.
  - Dev: 47 cases (42 also eligible for Tier 2).
  - **Held-out: 113 cases (106 eligible for Tier 2 = `tier == "both"`).**
- **Held-out never run:** no `tier*_heldout.jsonl` exists.
- **Dataset validation:** `validate.py` → VALID (160 cases, 12 docs, 56 pages; executed in B4).
- **Dataset fingerprints** (record these to prove the freeze):

| File | SHA-256 |
|---|---|
| `data_A.py` | `b4d8b3516a777c59a280d6cb9b5bbb23aefaf40459130bf46fc4e1d8c51cbf65` |
| `data_B.py` | `a3434f5b6ad1fbd3da30f2413f9f855595f6ec09278afb296b28e5f7d82b1778` |
| `data_C.py` | `67bc2b5e1ea01e27516c6fb61809efe6c90573630498e3384408dd8c4ad3b647` |
| `data_D.py` | `655be7b3c60cd13af50c2e15d1c9346b727ad3f57998233ffebc43d934b2306e` |
| `run_eval.py` | `3b066a5b3b4c1de908cb5a555db17762af2bd70606f0854d5f2ba0ce7106e989` |
| `validate.py` | `1727a33421202da3bd0d52aabcf0bf11dd9515c16c73a8b10e385aa356fe1a7d` |
| `eval/answer_scoring.py` | `c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af` |

- **Review status: NOT reviewed.**
  - Every case carries only the author's `review_note`, the author's own justification.
  - No `review_sheet.csv` exists, and there is no reviewer name, verdict or sign-off anywhere.
  - `run_eval.py` and `summarize.py` state "NOT yet human reviewed".
  - `docs/PROJECT_COMPLETION_AUDIT.md` lists "✘ human-reviewed answers, ✘ held-out run".
- **No evidence of human review exists. None is claimed.**

## 5. Independent human reviewer requirement
- **Reviewer:** a named person other than the dataset author, i.e. not Claude and not the helpers that wrote `data_A..D`.
- **Before any held-out result is seen:**
  - Generate the sheet with `.venv\Scripts\python.exe eval\phase35\summarize.py --sheet` (offline; it writes `REPORT.md` from the existing dev files plus `review_sheet.csv`).
  - The reviewer fills `REVIEWER_verdict` (ok / fix / drop) and `REVIEWER_comment` for the 113 held-out cases.
  - Fixes are applied, `validate.py` is re-run, and the dataset is frozen by recording new SHA-256 values.
- **After the run:** the reviewer labels all failures, plus a sample of at least 20 passes, for semantic correctness and claim support.
- **Option if no reviewer is available:** you may still choose to run held-out now. Every report must then say "author-written, not human-reviewed; held-out run before review". That would be a provisional result, not the independent validation Phase 3.5 requires.

## 6. Model, configuration and expected usage
- **Model:** `services/llm_service.py` uses `GEMINI_MODEL` (default `gemini-3.5-flash-lite`) with fallbacks from `GEMINI_FALLBACK_MODELS` (default `gemini-3.1-flash-lite,gemini-2.5-flash`). It switches models on HTTP 404, 429 or 5xx, has a 60 s quota cooldown per model, and makes one last-resort retry after all models are exhausted.
  - **`.env` could not be inspected:** access was blocked because it holds credentials. Please confirm whether `.env` sets `GEMINI_MODEL` or `GEMINI_FALLBACK_MODELS`. The recorded dev results do not store the model name either. If a fallback model is used mid-run, results mix models, and per-call model names exist only in the in-memory `usage_log`.
- **Answer config, unchanged:** `ANSWER_MAX_RETRIES=1`, `CONTEXT_MAX_CHARS=12000`, `CONTEXT_MAX_CHUNKS=8`, `FINAL_TOP_K=5`, `RERANK_ENABLED=True`, `RERANK_SCORE_MARGIN=2.0`, and embedding `all-MiniLM-L6-v2` (cached, loaded offline).
- **Measured on the dev baseline:**
  - Tier 1: 1.00 call per case, 1554 prompt and 38 output tokens per case, 126 s in total for 47 cases.
  - Tier 2: 2.05 calls per case (classify, possibly rewrite, answer), 1066 prompt and 40 output tokens per case (summed over its calls), 208 s for 42 cases.
- **Estimate.** The upper bound adds one Stage B regeneration per case (`uncited_claim` and similar).

| Run | Cases | Gemini calls | Prompt tokens | Wall time (incl. 3 s pause) |
|---|---|---|---|---|
| Tier 1 dev (re-run) | 47 | 47–94 | ~73k–146k | ~4–6 min |
| Tier 2 dev (re-run) | 42 | 86–130 | ~45k–70k | ~6–8 min, plus ingestion |
| Tier 1 held-out | 113 | 113–226 | ~176k–352k | ~10–14 min |
| Tier 2 held-out | 106 | 217–320 | ~113k–170k | ~14–20 min, plus ingestion |
| **Total (all four)** | 308 | **~463–770** | **~0.41M–0.74M** | ~35–50 min |

Output tokens total about 12k–25k.
- **Cost:** I do not have a verified current price for these models, so none is invented. Cost = tokens × your account's per-token price. On a free tier the limit is requests per minute/day: 429s trigger model fallback and waits, which slow the run and can mix models.
- **Token and latency reporting:** each result row stores `latency_s`, `llm_calls`, `prompt_tokens` and `output_tokens`, taken from `llm_service.usage_log` via Gemini `usage_metadata`. `summarize.py` aggregates them.

## 7. `rag_db` safety for the live run
- **Scratch database:** `run_eval.py` points `DATABASE_URL` at `rag_phase35_eval` before importing `services`. `services/database.py` calls `load_dotenv()` with `override=False` (verified), so `.env` cannot switch it back to `rag_db`.
- **Guards:** `harness._check_scratch_name` allow-lists only `rag_*{test,eval,scale,emb,scratch}*` and blocks `rag_db` and `postgres`. `harness.assert_scratch()` runs before work starts.
- **Writes:**
  - Tier 1 writes nothing to any database.
  - Tier 2 truncates and ingests only `rag_phase35_eval.document_chunks`.
  - `ask_question` reads chunks only. It does not save messages or memories (that happens in `main.py`, which the runner does not use).
- **Admin connection:** the only connection outside the scratch DB is to the `postgres` maintenance DB, to check or create `rag_phase35_eval` (`CREATE DATABASE` only if missing).
- **Checks around the run:** capture the established read-only `rag_db` fingerprint (`run_tests.fingerprint`) before and after it; the values must match.

## 8. Proposed exact commands (NOT executed; awaiting approval)
Run from the project root in Git Bash, as Claude would run them. `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` keep Hugging Face offline; only Gemini needs network.

```bash
# 0. pre-checks (offline)
.venv/Scripts/python.exe <fingerprint helper using run_tests.fingerprint>   # rag_db before
.venv/Scripts/python.exe eval/phase35/validate.py                           # must print VALID
sha256sum eval/phase35/data_*.py                                            # must equal section 4

# 1. Stage B DEV re-run (comparison with the backed-up baseline).
#    Needs explicit approval to use --fresh: it deletes tier{1,2}_dev.jsonl
#    (backed up in backups/phase35_results_20261112_160951/ and tracked in git).
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/Scripts/python.exe -u eval/phase35/run_eval.py --tier 1 --split dev --fresh > eval/phase35/results/log_tier1_dev_stageB.txt 2>&1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/Scripts/python.exe -u eval/phase35/run_eval.py --tier 2 --split dev --fresh > eval/phase35/results/log_tier2_dev_stageB.txt 2>&1

# 2. HELD-OUT, once, only after human review + freeze (or explicit decision to run unreviewed)
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/Scripts/python.exe -u eval/phase35/run_eval.py --tier 1 --split heldout > eval/phase35/results/log_tier1_heldout.txt 2>&1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/Scripts/python.exe -u eval/phase35/run_eval.py --tier 2 --split heldout > eval/phase35/results/log_tier2_heldout.txt 2>&1

# 3. summary (offline) + rag_db fingerprint after
.venv/Scripts/python.exe eval/phase35/summarize.py
```

A smoke test such as `--limit 3` is **not** proposed for held-out: any held-out case run once has been "seen". If a smoke test is wanted, run it on dev only.

## 9. Decisions needed from you before any live call
1. Approve the **dev re-run with `--fresh`** (step 1). The baseline is safely backed up. Without `--fresh`, the runner would skip every dev case as already done.
2. **Held-out:** wait for an independent reviewer and freeze (recommended), or run now explicitly labelled "unreviewed".
3. Confirm the **Gemini model** in `.env` (`GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`) and that you accept the ~460–770 calls and quota usage.
4. **Acceptance thresholds:** none are recorded in the project docs. `PROJECT_COMPLETION_AUDIT.md` lists only criteria, with no numbers. Please fix the numeric pass criteria **before** the run, so that they are not chosen after seeing results.

STOP — no live call has been made. Waiting for explicit approval.
