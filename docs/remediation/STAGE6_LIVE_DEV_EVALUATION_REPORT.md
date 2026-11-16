# Stage 6: Live Development Evaluation

**Date:** 2026-11-16, run 15:41:43–15:49:34 local time. **Scope:** measure how the real Gemini model behaves with the Stage 6 numeric-grounding safeguard and its regeneration feedback.
**Not done:**
- No held-out evaluation.
- No change to application code, prompts, grounding rules, retrieval, provider configuration, datasets, splits, thresholds or the frozen scorer.
- Nothing committed or pushed.
- Stage 7 not started.

## 1. Preflight and safety verification

| Check | Result |
|---|---|
| Branch / HEAD | `main` at `09e6007`; `main` = `origin/main` (fetched) |
| Worktree | The uncommitted Stage 6 changes and H.1 artifacts (see `BATCH2_STAGE6_ANSWER_REPORT.md`) plus `.vscode/`; nothing unexpected |
| Code under test | Working tree = HEAD + uncommitted Stage 6 (`grounding_service.py`, `answer_service.py`, `rag_service.py`, `main.py`) |
| Models | Primary `gemini-3.5-flash-lite`; fallbacks `gemini-3.1-flash-lite`, `gemini-2.5-flash`. Defaults, the same configuration as the Stage B baseline |
| Output directory | `eval/results/stage6_live_dev_20261116/`. Did not exist before the run; the entry point refuses an existing directory unless `--resume` (not used) |
| Recorded results | SHA-256 of all 6 files in `eval/phase35/results/`, the 2 H.1 artifacts and `.vscode/settings.json` taken before; **identical after** |
| Evaluation database | `rag_phase35_eval`, checked by `current_database()` before any work: 12 documents, 135 chunks. Used as is (no re-ingestion, no TRUNCATE); still 135 / 12 after. The Stage 6 replay had already verified that its chunk ids match the recorded Tier 2 document/page values |
| `rag_db` | Read-only fingerprint (`run_tests.fingerprint`) identical before and after. On this Mac it is an empty schema, not the Windows application database |
| Secrets | No key, URL or password printed; the outputs contain none (grep on all 4 output files: 0 matches) |

**Why a separate entry point.** `eval/phase35/run_eval.py` writes to a fixed path (`eval/phase35/results/tier*_dev.jsonl`), and `--fresh` deletes those recorded files. So a new entry point was written, `eval/stage6_live_dev_eval.py`. It reuses `run_eval.run_tier1`, `run_eval.run_tier2`, `run_eval.load_all`, `split_of` and the frozen scorer `score_generic` **unchanged**, and adds observation only:
- every Gemini request is counted at the client (kind, model, outcome, seconds, correction reasons); prompt text is not stored;
- the grounded-answer outcome (attempts, issues) and Tier 2 `retrieval_status` are captured by pass-through wrappers.

A pre-run check confirmed the wrapper sends nothing: 0 requests during preflight.

## 2. Cases and split

- **Selection rule:** the existing split, `run_eval.split_of` (`sha1(id) % 10 < 3` → dev). Tier 2 additionally requires `tier == "both"`.
- **Check:** before running, the entry point asserts that the selected ids equal the recorded baseline's ids; after the run, every output id was re-checked as dev, unique, and complete.
- **Held-out definitions** are read only by the dataset validator in `load_all`. They are never retrieved, answered or scored.

**Tier 1 (47):**
A-direct-05, A-direct-07, A-multichunk-03, A-multichunk-04, A-multipage-03, A-multipage-04, A-noanswer-03, A-conflict-02, A-injection-04, A-irrelevant-02,
B-direct-03, B-chunk-03, B-comp-02, B-comp-04, B-comp-05, B-none-01, B-conf-02, B-conf-03, B-conf-04, B-follow-03, B-inject-02, B-inject-03, B-inject-04, B-irrel-01,
C-direct-02, C-direct-05, C-direct-07, C-compound-01, C-multi_page-03, C-prompt_injection-01, C-prompt_injection-04, C-irrelevant_retrieval-01, C-missing_metadata-01,
D-direct-01, D-direct-04, D-direct-05, D-multi_chunk-03, D-compound-04, D-multi_page-03, D-multi_page-04, D-no_answer-01, D-no_answer-03, D-conflicting-01, D-conflicting-03, D-conflicting-04, D-follow_up-04, D-irrelevant_retrieval-01.

**Tier 2 (42):** the Tier 1 list minus the 5 `answer_only` cases (A-irrelevant-02, B-irrel-01, C-irrelevant_retrieval-01, C-missing_metadata-01, D-irrelevant_retrieval-01).

## 3. Execution

```
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -u -m eval.stage6_live_dev_eval \
    --out eval/results/stage6_live_dev_20261116          # one run, no resume
.venv/bin/python -m eval.stage6_live_dev_analyze --run eval/results/stage6_live_dev_20261116
```

- **One uninterrupted run:** 89/89 cases completed, **0 runner errors**, 0 resumes, no case re-run. Exit code 0.
- **Pause:** 3 s between cases (`run_eval`'s default).
- **Outputs** (all new):
  - `tier1_dev.jsonl`, `tier2_dev.jsonl`: `run_eval` records + a `stage6` block per case.
  - `run_log.txt`: console log.
  - `summary.json`: written by the analysis script, mode `x`.
- **Baseline for comparison:** the recorded **Stage B** live dev run (`eval/phase35/results/tier1_dev.jsonl`, `tier2_dev.jsonl`; `STAGE_B_DEV_LIVE_EVALUATION_REPORT.md`): 41/47 and 28/42, same model configuration, run on Windows on 2026-11-12, read only.
- **Scores** are the frozen `score_generic` values stored in each record. Nothing was re-scored.

## 4. Results and comparison with the baseline

| | Tier 1 new | Tier 1 baseline | Tier 2 new | Tier 2 baseline |
|---|---|---|---|---|
| Completed / failed | 47 / 0 | 47 / 0 | 42 / 0 | 42 / 0 |
| **Correct** (frozen scorer) | **41/47 (87.2%)** | 41/47 (87.2%) | **29/42 (69.0%)** | 28/42 (66.7%) |
| Frozen dev threshold | ≥ 41 → **PASS** | PASS | ≥ 28 → **PASS** | PASS |
| Status: answered / abstained / partial / conflict | 35 / 9 / 1 / 2 | 36 / 9 / 1 / 1 | 30 / 5 / 6 / 1 | 29 / 6 / 6 / 1 |
| Status `unverified` / `error` | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Answer text identical to baseline | 19 / 47 | – | 12 / 42 | – |
| Scorer `unsupported` flag | 1 (`C-multi_page-03`, artefact, see 6) | 0 | 1 (`C-multi_page-03`, artefact) | 1 (same case and artefact) |

**Like-for-like note (Tier 1).** After Stage B, `A-conflict-02` was corrected in the dataset: `conflicting` → `direct_factual` (`HELDOUT_DATASET_CORRECTIONS.md`, an approved correction). The recorded baseline was scored under the old definition. Scored under the current definition, the baseline is **42/47**, which is what the Stage 6 offline replay showed. Measured on today's dataset, Tier 1 is therefore **41 vs 42 (−1, `D-compound-04`, see 6)**, and Tier 2 is **29 vs 28 (+1, `C-direct-05`)**. Neither change involves the safeguard.

### Safeguard and regeneration behaviour

| | Tier 1 | Tier 2 | Total |
|---|---|---|---|
| Cases regenerated (attempts > 1) | 2 (B-inject-02, C-direct-02) | 2 (B-inject-04, C-multi_page-03) | **4 / 89 (4.5%)** |
| Attempts distribution | 1: 45, 2: 2 | 1: 40, 2: 2 | max 2 |
| Baseline regenerations | 0 (47 × 1 attempt) | not recorded | – |
| **Numeric-grounding rejections (`unsupported_number`)** | **0** | **0** | **0** |
| Rejections by the existing `uncited_claim` rule (B2) | 2 | 2 | 4 |
| Repairs / dropped number sentences / dropped uncited sentences | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| Final `unverified` / abstained after a failed retry | 0 | 0 | 0 |
| Regeneration outcome | both accepted on attempt 2, both correct (as in baseline) | both accepted on attempt 2; both incorrect, **as in baseline** (retrieval / page recall < 1) | – |

- **The numeric safeguard never fired on real model output:** none of 89 cases introduced a number its cited passage does not contain. That matches the offline replay (0/89).
- On this set, the safeguard therefore had **no measurable cost and no measurable effect**.
- All 4 regenerations came from the pre-existing uncited-claim rule, and **all 4 happened while the request was served by the fallback model `gemini-3.1-flash-lite`**. No regeneration happened on the primary model.

### Tier 2 retrieval status

| Status | Cases |
|---|---|
| `ok` | 41 |
| `not_run` (classified MEMORY: `D-follow_up-04`, incorrect as in the baseline) | 1 |
| `disabled` / `skipped` / `failed:*` | 0 |

## 5. Token, latency and API-call costs

| | Tier 1 new | Tier 1 baseline | Tier 2 new | Tier 2 baseline | Total new | Total baseline |
|---|---|---|---|---|---|---|
| Gemini requests sent (incl. failed) | 51 | n/a | 91 | n/a | **142** | n/a |
| Successful LLM calls (`llm_calls`) | 49 | 47 | 88 | 86 | **137** | 133 |
| By kind | answer 49, answer_retry 2 | | classify 45, answer 42, rewrite 2, answer_retry 2 | | | |
| By model | 3.5-flash-lite 35, 3.1-flash-lite 15, 2.5-flash 1 | | 3.5-flash-lite 56, 3.1-flash-lite 35 | | | |
| Provider errors | 429 × 2 | 0 | 429 × 3 | 429 × 2 (log) | 5 × 429 | 2 × 429 |
| Timeouts / other errors | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 |
| Prompt tokens | 76,289 | 73,040 | 47,130 | 44,751 | **123,419** | 117,791 (+4.8%) |
| Output tokens | 2,481 | 1,933 | 1,816 | 1,642 | **4,297** | 3,575 (+20.2%) |
| Latency median / p90 / max (s) | 1.18 / 1.81 / 4.02 | 1.81 / 6.22 / 15.5 | 2.30 / 3.66 / 30.02 | 4.14 / 9.85 / 63.83 | | |
| Latency total (s) | 62.7 | 151.7 | 139.9 | 304.8 | **202.6** | 456.5 |

- **Rate limits:** every 429 was absorbed by fallback, with no failed case. The Tier 2 maximum of 30.0 s is a case that hit 429s on the primary model. The "requests sent" count includes the 5 rejected requests.
- **Cost of the safeguard itself:** 0 extra requests, since it never fired.
- **Cost of regeneration overall:** 4 extra answer requests (`uncited_claim`), +2.9% of successful calls. The token increase also reflects model variability: answers from the fallback model are longer.
- **Monetary cost:** not reported, because no price data is available in this environment. The token counts above are exact from `usage_metadata`.
- **Latency is not comparable as a performance result.** The baseline ran on Windows, on another network and day, and its Tier 1 run included recovery from a hung request (Stage B report). The lower latency here is not attributed to Stage 6.

## 6. Changed-answer analysis

Answer texts differ in 58 of 89 cases. Generation is nondeterministic, so text differences alone mean nothing. Every case whose **score or status** changed, plus every regenerated case and every scorer flag, was inspected:

| Case | Change | Safeguard involved? | Cause |
|---|---|---|---|
| T1 `A-conflict-02` | correct False → True | No (1 attempt) | **Dataset correction** after Stage B (`conflicting` → `direct_factual`); the old baseline score used the old definition |
| T1 `D-compound-04` | correct True → False (`partial_ok` False) | No (1 attempt) | **Model wording + scorer heuristic.** Both answers give the cited cap "USD 185 [S1]" and say gym fees are not covered by the documents. Baseline: "I couldn't find sufficient information…"; new: "The provided documents do not mention whether…". The frozen scorer's partial check does not recognise the new phrasing. The answer is substantively equivalent |
| T1 `D-conflicting-01` | status answered → conflict, correct both | No | Model variability (disagreement wording); still correct |
| T2 `C-direct-05` | correct False → True (abstained → answered, page recall 0 → 1) | No | **Classifier variability.** The baseline log shows 2 questions classified MEMORY (retrieval skipped); in this run only `D-follow_up-04` was. Here retrieval ran and found the gold page; the answer "£34 [S1]" is correct and grounded |
| T2 `A-multipage-03` | status partial → answered, incorrect both | No | Model variability; retrieval still misses one gold page (page recall 0.5) |
| T2 `C-multi_page-03` | status answered → partial, incorrect both | No (regenerated for `uncited_claim`) | Retrieval misses one gold page (page recall 0.5), as in the baseline |
| T1 `B-inject-02`, `C-direct-02`; T2 `B-inject-04` | regenerated once, score unchanged | No (`uncited_claim`) | The fallback model omitted a citation; corrected on attempt 2 |
| T1/T2 `C-multi_page-03` scorer `ungrounded_numbers ['4.0']` | scorer flag | **No:** the safeguard correctly accepted it | **Scorer artefact:** the answer says "version 4.0", and the passage writes `v4.0`, which `run_eval.norm_numbers` does not extract. This is the same artefact found in the Stage 6 replay (corrects B4's interpretation). The safeguard's evidence-side extraction handles it, so there is no false rejection live |

**Attribution:**
- **0** score or status changes are attributable to the numeric-grounding safeguard.
- **4** regenerations are attributable to the pre-existing uncited-claim rule; they all ended in accepted answers with unchanged correctness.
- The other changes come from the dataset correction, model and classifier variability, or scorer heuristics.

## 7. Limitations and recommendations

**Limitations:**
- **Single run.** Model variability (19/47 and 12/42 identical texts) means ±1–2 correct cases are within noise. One run cannot separate small effects.
- **Mixed models.** Rate limits sent 51 of 142 requests to fallback models, the baseline's mix is unknown, and its logs record only 2 rate-limit events.
- **No live trigger.** The safeguard's live trigger path (feedback → corrected answer) was **not exercised**, because no case triggered it. Its behaviour after triggering is covered only by unit, integration and replay tests.
- **Dev only.** The dev set is small (47 / 42) and author-written; held-out was not run.
- **Platform.** The baseline ran on Windows and this run on macOS, so latency comparisons are not meaningful.

**Recommendations:**
1. **Keep the numeric-grounding safeguard as implemented.** There were 0 false rejections across 89 live and 89 replayed dev answers, no live cost, and it blocks the fabricated-number failures shown in the tests. Its benefit on this dev set is unproven, because the model did not produce such errors here.
2. **Fallback-model quality:** all citation regenerations occurred on `gemini-3.1-flash-lite`. If quota pressure is normal, consider (separate decision) whether that fallback should stay first in line, or whether quota should be raised.
3. **Classifier risk:** a document question was classified MEMORY in both runs (`D-follow_up-04`; `C-direct-05` in the baseline), which skips retrieval. This is the largest upstream source of variability seen here and is outside Stage 6 scope; recommend reviewing it in a later stage.
4. **Frozen-scorer artefacts** (require approval to change; not changed):
   - `norm_numbers` misses `v4.0`-style numbers.
   - The partial-answer phrase check misses "do not mention".
   Both distort the reported correctness and support labels by about 1 case.
5. For a decision that depends on ±1–2 cases, repeat the run (or run each case several times) instead of reading a single-run difference.

## 8. Final evaluation status

**COMPLETE.**
- 89/89 dev cases ran live with 0 failures.
- Both frozen dev thresholds are met: Tier 1 41/47 ≥ 41, Tier 2 29/42 ≥ 28.
- The Stage 6 numeric-grounding safeguard caused **no regressions, no false rejections and no extra cost** on real model output. It did not trigger, so its live benefit on this set is **not demonstrated** (no fabricated numbers occurred).
- **Safety:** recorded results and artifacts are byte-identical, `rag_db` is unchanged, and no held-out case was run.
- Stage 7 was not started.

### Files (new, uncommitted)
- `eval/stage6_live_dev_eval.py`: entry point (reuses `run_eval` unchanged, observation only).
- `eval/stage6_live_dev_analyze.py`: summary against the baseline (read-only).
- `eval/results/stage6_live_dev_20261116/`: `tier1_dev.jsonl`, `tier2_dev.jsonl`, `run_log.txt`, `summary.json`.
- This report.
