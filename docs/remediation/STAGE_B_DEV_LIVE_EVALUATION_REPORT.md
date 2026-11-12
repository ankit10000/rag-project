# Stage B — development live evaluation report (Tier 1)

Date: 2026-11-12. This report supersedes the earlier "BLOCKED at pre-flight" and "INCOMPLETE" versions of this file, whose history is summarised below.

**Overall outcome:**
- **Tier 1 development: COMPLETE, 41/47 (87.2%), threshold ≥ 41/47 → PASS (exactly at the threshold).**
- **Tier 2 development: COMPLETE, 28/42 (66.7%), threshold ≥ 28/42 → PASS (exactly at the threshold).** See the Tier 2 section at the end.
- Held-out: not run.

## Configuration used
- **Models:** primary `gemini-3.5-flash-lite`; fallbacks `gemini-3.1-flash-lite`, `gemini-2.5-flash`. Both settings were resolved from `.env` and re-verified at 17:05 before the resume, with no process-environment override.
- **Pipeline:** the Stage B answer pipeline (HEAD `aa6a876`), plus the uncommitted Gemini timeout fix in `services/llm_service.py` (`HttpOptions.timeout = 120000 ms`; a timeout falls through to the next model). See `STAGE_B_GEMINI_TIMEOUT_FIX_REPORT.md`.
- **Defaults:** `ANSWER_MAX_RETRIES=1`, `CONTEXT_MAX_CHARS=12000`, `CONTEXT_MAX_CHUNKS=8`.
- **Offline and database:** Hugging Face and Transformers ran offline. Tier 1 uses no database; the runner's scratch guard targets `rag_phase35_eval`.

## Execution history
| Run | Command | Result |
|---|---|---|
| 1 (16:28:36) | `run_eval.py --tier 1 --split dev --fresh > log_tier1_dev_stageB.txt` | cases 1–29 done by 16:32:06. Case 30 `C-prompt_injection-01` hung for about 25 min on an HTTP request with no timeout. Stopped at about 16:58, no exit code. |
| fix | 120 s Gemini request timeout added (separately approved; 19 focused tests and 3 mutations caught) | no API call |
| 2, resume (17:06:08) | `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/Scripts/python.exe -u eval/phase35/run_eval.py --tier 1 --split dev >> eval/phase35/results/log_tier1_dev_stageB.txt 2>&1` (**no `--fresh`**) | runner printed `47 cases selected, 29 already done, 18 to run`. All 18 done by 17:07:30, `done ->` at 17:07:33, **exit code 0**. |

**Resume timeline** (time each case finished, from the timestamped log monitor; each case took about 4–8 s including the 3 s pause):

| Finished | Case | Result |
|---|---|---|
| 17:06:12 | C-prompt_injection-01 (the case that hung in run 1) | ✔ |
| 17:06:16 | C-prompt_injection-04 | ✔ |
| 17:06:20 | C-irrelevant_retrieval-01 | ✔ (abstained) |
| 17:06:24 | C-missing_metadata-01 | ✘ |
| 17:06:28 | D-direct-01 | ✔ |
| 17:06:32 | D-direct-04 | ✔ |
| 17:06:37 | D-direct-05 | ✔ |
| 17:06:41 | D-multi_chunk-03 | ✔ |
| 17:06:46 | D-compound-04 | ✔ (partial) |
| 17:06:50 | D-multi_page-03 | ✔ |
| 17:06:54 | D-multi_page-04 | ✔ |
| 17:06:59 | D-no_answer-01 | ✔ |
| 17:07:04 | D-no_answer-03 | ✔ |
| 17:07:12 | D-conflicting-01 | ✔ |
| 17:07:17 | D-conflicting-03 | ✘ |
| 17:07:22 | D-conflicting-04 | ✘ |
| 17:07:26 | D-follow_up-04 | ✔ |
| 17:07:30 | D-irrelevant_retrieval-01 | ✔ (abstained) |

**Timeout and fallback evidence:**
- The whole log `log_tier1_dev_stageB.txt` (run 1 plus the resume) contains **no** `timed out`, `trying next model`, `out of quota`, `temporary error` or traceback lines.
- The new timeout never fired, and no fallback occurred.

## Tier 1 results (all 47 cases)
| Metric | Stage B (this evaluation) | Original baseline (pre-Stage-B, backed up) |
|---|---|---|
| **Correct** | **41/47 = 87.2%** (lenient 41) | 41/47 = 87.2% |
| **Frozen threshold ≥ 41/47** | **PASS** (exactly at the threshold, no margin) | — |
| Status mix | answered 36, abstained 9, conflict 1, partial 1 | identical |
| Unsupported answers (scorer) | **0** | 1 (`C-multi_page-03`, ungrounded number `4.0`) |
| Fabricated citations | 0 | 0 |
| Gemini calls (successful) | 47, one per case | 47 |
| Regenerations (attempts > 1) | **0** | 0 |
| Prompt / output tokens | 73,040 / 1,933 | 73,040 / 1,783 |
| Latency, median / p90 / max / total (generation only) | 1.81 s / 6.22 s / 15.50 s / 151.7 s | 2.12 s / 4.25 s / – / 126 s |
| Timeouts / fallbacks / quota waits / API errors | 0 / 0 / 0 / 0 | — |

**Notes on the comparison:**
- **Per-case agreement.** Every one of the 47 cases has the same correctness and the same status as the baseline. The one measurable difference is that the baseline's single scorer-flagged unsupported answer is no longer flagged.
- **Prompt tokens are identical in total.** This is expected: the prompts are deterministic for the same contexts, and the Stage B marker neutralisation did not trigger on this data.
- **The Stage B checks were never exercised by these answers.** There were zero regenerations and every `issues` list is empty, so `uncited_claim`, the tag rule and repair never fired on this data. The result shows **no regression and no measurable improvement** on dev Tier 1. That matches the offline replay in B4.
- **Latency is not comparable.** Run 1's first 29 cases had a higher median (3.28 s) than the resumed 18 (1.32 s), which reflects provider latency at the time of day, not the code.

**Incorrect cases**, all 6 identical to the baseline failures:
| Case | Category | Status | Reason (scorer) | Baseline |
|---|---|---|---|---|
| A-conflict-02 | conflicting | answered | `conflict_ok=False` (disagreement not surfaced) | ✘ |
| B-conf-04 | conflicting | answered | `conflict_ok=False` | ✘ |
| D-conflicting-03 | conflicting | answered | `conflict_ok=False`; citation completeness 0.5 | ✘ |
| D-conflicting-04 | conflicting | answered | `conflict_ok=False` | ✘ |
| B-comp-04 | compound | answered | `partial_ok=False`; citation correctness 0.5 | ✘ |
| C-missing_metadata-01 | missing_metadata | abstained | unnecessary abstention (`abstain_ok=False`) | ✘ |

Conflict handling remains the dominant Tier-1 weakness (4/6) and is not addressed by Stage B.

## Model attribution
- No fallback, timeout or quota line exists in the log. Every model switch prints such a line, so **all 47 counted calls were served by the primary model `gemini-3.5-flash-lite`**.
- In run 1, the request for case 30 that hung was also on the primary model. Its result was never recorded; the case was re-run fresh in the resume.
- **Limitation:** the runner does not persist the model per row. Attribution rests on the absence of fallback log lines.

## Integrity checks
| Check | Result |
|---|---|
| Result file | `eval/phase35/results/tier1_dev.jsonl`: **47 rows, 47 unique ids**, the same case set as the baseline. SHA-256 now `6e89c07ca77201d65a1c1e469e32fd22fe687ca5248a9736d54c58c0d62ac60b`. |
| The 29 pre-resume rows | **byte-identical** to the copy taken before the resume (pre-resume file SHA-256 `638494fc…`), so none of the 29 was re-run |
| Log | `log_tier1_dev_stageB.txt` appended, not overwritten (SHA-256 now `51f1d4cb…`) |
| `rag_db` fingerprint before vs after the resume | **identical**; the same values as at every previous checkpoint |
| Backup `backups/phase35_results_20261112_160951/` | 4/4 match the manifest |
| Original `tier2_dev.jsonl`, `log_tier1_dev.txt`, `log_tier2_dev.txt` | unchanged (SHA-256 equal to the manifest) |
| Tier 2 or held-out files | **none created or modified**; no `tier*_heldout.jsonl` exists |
| Code and datasets during the run | unchanged; the combined SHA-256 of `services/*.py` and `data_*.py` is identical before and after (`55392f5e…`) |
| Full test suite | not run |
| Git | HEAD `aa6a876`, nothing staged, committed or pushed. Modified: `eval/phase35/results/tier1_dev.jsonl` (the new full result), `services/llm_service.py` and `run_tests.py` (timeout fix, uncommitted). Untracked: `test_llm_timeout.py`, `log_tier1_dev_stageB.txt` and the reports. |

## Limitations
- **Development data only.** These are author-written cases, not human-reviewed, and the dev split was inspected during development, so this is **not independent validation**.
- **No margin on the pass.** 41/47 is exactly the threshold; a single additional failure would fail it. The Wilson 95% interval for 41/47 is roughly 75–94%.
- **Interrupted execution.** The run spans two executions (the 18 resumed cases ran about 35 min after the first 29), so provider conditions differed between them.
- **No signal on the Stage B rules.** They did not fire on any Tier-1 answer, so this run neither confirms nor refutes their effect on live output.
- **Not production-ready.** Nothing here supports a production-readiness claim.

---

# Tier 2 (development) — end-to-end

**Outcome: PASS. 28/42 = 66.7%, frozen threshold ≥ 28/42, met exactly with no margin.**

## Pre-flight (17:11, all PASS)
| Check | Result |
|---|---|
| Effective models | `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-2.5-flash`; both settings from `.env`, no process-environment override |
| Timeout implementation | present and unchanged: `REQUEST_TIMEOUT_MS = 120_000`, `HttpOptions(timeout=REQUEST_TIMEOUT_MS)`, `except httpx.TimeoutException` → next model, and `raise last_error` once every model is exhausted |
| `validate.py` | `VALID` |
| Backup | 4/4 files match `MANIFEST.json`; the original `tier2_dev.jsonl` matched its recorded hash before the run |
| Tier 1 result | 47 rows, 47 unique, SHA-256 `6e89c07c…ac60b` (the accepted result) |
| Code, datasets, runner, scorer, harness | unchanged (combined `services/*.py` + `data_*.py` hash `55392f5e…`; `run_eval.py` `3b066a5b…`, `answer_scoring.py` `c3b54228…`, `harness.py` `6e3ba55e…`) |
| Git | HEAD `aa6a876`, nothing staged |
| `rag_db` fingerprint before | the same values as every earlier checkpoint |

**Scratch database safety:**
- `run_eval.py:35` calls `harness.use_scratch_database("rag_phase35_eval")` before any `services` import (line 41 onward). That sets `DATABASE_URL` to the scratch DB, and `load_dotenv` (`override=False`) cannot revert it.
- `harness.assert_scratch()` runs at `run_eval.py:266`. The allow-list `rag_*{test,eval,scale,emb,scratch}*` blocks `rag_db` and `postgres`.
- Tier 2 writes only `TRUNCATE` + ingestion into `rag_phase35_eval.document_chunks`. `ask_question` only reads chunks.
- All 12 dataset documents are `.pdf` files of at most 5 pages, so they are within the A3/A4 limits.
- Database configuration was not changed by hand.

## Execution
Command, run exactly once:
`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/Scripts/python.exe -u eval/phase35/run_eval.py --tier 2 --split dev --fresh > eval/phase35/results/log_tier2_dev_stageB.txt 2>&1`

**Timeline:**
- Started 17:11:41.
- Ingestion, scratch only: `Ingested 12 PDFs -> 135 chunks` at 17:12:14.
- Cases ran from 17:12:19 to 17:19:25. `done ->` was printed at 17:19:29, and the process exited with **code 0** at 17:19:34.
- All 42 cases completed. There was no runner error, no stall and no restart. Each case took about 6–10 s including the 3 s pause.

**Long cases:**
| Case | Time | Note |
|---|---|---|
| C-prompt_injection-01 | 63.8 s | within the fallback/cooldown window (below); no timeout line |
| A-injection-04 | 25.6 s | includes one 503 retry |
| B-chunk-03 | 18.5 s | |
| C-multi_page-03 | 17.7 s | includes a 429 fallback |

**Provider events in the log.** These are the complete list; there were **no timeouts** and the 120 s limit never fired.
| Log line | During case | Event |
|---|---|---|
| 130 | #8 A-conflict-02 (classification call) | `gemini-3.5-flash-lite failed (429); trying next model...` |
| 153 | #9 A-injection-04 | `Gemini temporary error 503. Retrying in 1s (1/1)...`, then success |
| 358 | #27 C-multi_page-03 (answer call) | `gemini-3.5-flash-lite failed (429); trying next model...` |

No quota-wait ("all models out of quota") line, no `timed out` line, no traceback and no `RUNNER ERROR` appears.

## Results (42/42 cases, 42 unique ids, the same case set as the baseline)
| Metric | Stage B Tier 2 | Original Tier 2 baseline |
|---|---|---|
| **Correct** | **28/42 = 66.7%** (lenient 28) | 28/42 = 66.7% |
| **Threshold ≥ 28/42** | **PASS** (exactly at the threshold) | — |
| Status mix | answered 29, partial 6, abstained 6, conflict 1 | identical counts |
| Mean retrieval page recall | 0.816 | 0.816 |
| Unsupported (scorer) / fabricated citations | 1 / 0 | 1 / 0 |
| Gemini calls (successful) | 86 (2 per case ×40, 3 per case ×2) | 86 (identical distribution) |
| Answer regenerations (attempts > 1) | **0** (every `issues` list is empty) | — |
| Prompt / output tokens | 44,751 / 1,642 | 44,751 / 1,659 |
| Latency, median / p90 / max / total | 4.14 s / 9.85 s / 63.83 s / 304.8 s | 3.92 s / 8.58 s / 12.64 s / 208.1 s |
| Timeouts / 429 fallbacks / 503 retries / quota waits / errors | 0 / 2 / 1 / 0 / 0 | — |

**Changed outcomes vs the baseline:**
| Case | Stage B | Baseline | Effect on score |
|---|---|---|---|
| D-compound-04 | partial, ✔ | answered, ✘ | +1 |
| B-conf-04 | answered, ✘ (`conflict_ok=False`) | answered, ✔ | −1 |
| B-chunk-03 | partial, ✘ | abstained, ✘ | 0 |
| B-none-01 | abstained, ✔ | partial, ✔ | 0 |
| C-multi_page-03 | answered, ✘ | partial, ✘ | 0 |

- The net correctness change is 0.
- The retrieval inputs are identical (same page recall per case), so the changes come from **LLM output variability**, not from the Stage B rules. The Stage B rules caused no regeneration and no repair.
- D-compound-04 and B-conf-04 ran outside both fallback windows (below), so model mixing does not explain them.

**All 14 incorrect cases, by failure type:**
| Failure type | Cases (scorer evidence) |
|---|---|
| Retrieval failure (no gold page retrieved) | A-multipage-04, B-chunk-03, C-direct-05, D-follow_up-04: page recall 0.0, recall 0.0 (the last two abstained, `abstain_ok=False`) |
| Retrieval partial → incomplete answer | A-multipage-03 (page recall 0.5, recall 0.67), D-multi_page-04 (page recall 0.5, recall 0.5), C-multi_page-03 (page recall 0.5, recall 0.5, ungrounded number `4.0`, the one *unsupported* answer) |
| Conflict not surfaced | B-conf-02, B-conf-03, D-conflicting-04 (page recall 0.5: one side not retrieved); B-conf-04, D-conflicting-03 (page recall 1.0: both sides available, model did not state the disagreement) |
| Incomplete answer with full retrieval | A-multichunk-04 (page recall 1.0, recall 0.5) |
| Incomplete answer + citation | B-inject-04 (page recall 1.0, recall 0.5, citation correctness 0.5; no forbidden hit, so the injection was **not** obeyed) |

Retrieval is involved in 10/14 failures and conflict handling in 5/14 (with overlap). Neither is targeted by Stage B.

## Model attribution
- **Primary model** `gemini-3.5-flash-lite` served all calls except those described below.
- **Two 429 quota errors** on the primary (#8 classification, #27 answer) switched those calls to `gemini-3.1-flash-lite`. No further fallback line appears, so that model succeeded and `gemini-2.5-flash` was never logged as used.
- **Cooldown window (important).** After a 429, `llm_service` puts the primary into a **60 s cooldown** (`QUOTA_COOLDOWN_SECONDS = 60`), and `_model_order()` tries `gemini-3.1-flash-lite` first during that time. **These calls print no log line.**
  - Calls from about 17:13:03 to 17:14:03 therefore most likely went to `gemini-3.1-flash-lite`: the rest of #8 A-conflict-02, #9 A-injection-04, #10 B-direct-03 and possibly the first call of #11 B-chunk-03.
  - The same applies from about 17:16:09 to 17:17:09: the rest of #27 C-multi_page-03 and probably #28 C-prompt_injection-01.
- **Conclusion:** about 5–7 of the 42 cases contain at least one `gemini-3.1-flash-lite` response. Exact per-call attribution is **not** established, because the runner does not persist the model per row and cooldown routing is silent. **The Tier 2 results therefore mix two models.**

## Post-run integrity
| Check | Result |
|---|---|
| `rag_db` fingerprint after vs before | **identical** (5 tables, counts and hashes) |
| Backup | 4/4 files match `MANIFEST.json`; the original Tier 2 baseline is preserved byte-identically in the backup (and in git `HEAD`) |
| `tier2_dev.jsonl` | replaced by the approved `--fresh` run: 42 rows, SHA-256 `51ebe836…aa79` |
| New log | `log_tier2_dev_stageB.txt` (SHA-256 `91fce59d…a2e`) |
| Original `log_tier1_dev.txt`, `log_tier2_dev.txt` | unchanged |
| Tier 1 result | unchanged (`6e89c07c…ac60b`) |
| Held-out files | none created |
| Code, datasets, scorer, runner, harness, thresholds | unchanged (hashes identical before and after) |
| Scratch DB | `rag_phase35_eval.document_chunks` truncated and re-ingested (expected; scratch only) |
| Full test suite | not run |
| Git | HEAD `aa6a876`, nothing staged, committed or pushed. Modified: `tier1_dev.jsonl`, `tier2_dev.jsonl` (new results), `services/llm_service.py`, `run_tests.py` (timeout fix). Untracked: both Stage B logs, `test_llm_timeout.py` and the reports. |

## Tier 2 limitations
- **No margin.** 28/42 is exactly the threshold; one more failure would fail it. The Wilson 95% interval is about 50–81%.
- **Different cases flipped.** The aggregate equals the baseline, but different individual cases flipped. Run-to-run LLM variability is visible at the ±1 case level.
- **Two models.** The results mix `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` (about 5–7 cases).
- **Development data only.** These are author-written cases with no human review and are not independent. The held-out split has not been run.
- **Stage B rules untested here.** They did not trigger on any live Tier 2 answer, so their live effect is still unmeasured.
- **Not production-ready.** Nothing here supports a production-readiness claim.

STOP. Held-out evaluation, Stage C, threshold changes and further remediation are not authorised. Waiting for your review.
