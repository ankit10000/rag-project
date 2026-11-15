# Phase 4 — Evaluation Framework

**Status (2026-11-15):** infrastructure implemented. **No evaluation and no test was executed.**
- Done: source inspection, static review, and `py_compile` of the new modules.
- No dataset, split, threshold, scoring rule or historical result was changed, and no new evaluation result was generated.

## 1. Existing assets (inspected, not executed, not modified)
| Asset | Role |
|---|---|
| `eval/phase35/data_A..D.py` | 160 author-written cases, 12 documents, 56 pages |
| `eval/phase35/validate.py` | schema, unique ids, spans on stated pages, gold facts on gold pages |
| `eval/phase35/run_eval.py` | Tier 1/Tier 2 live runner, `split_of` (sha1 % 10 < 3 → dev), `score_generic`. **It opens a DB admin connection at import time.** |
| `eval/phase35/summarize.py` | Wilson intervals, tables, review sheet. It imports `run_eval`, so the same side effect applies. |
| `eval/answer_scoring.py` | Phase 3 answer scorer (fact recall, forbidden hits, citations, abstention, partial/conflict) |
| `eval/harness.py` | scratch-DB harness and Phase 2 retrieval scoring |
| `eval/phase35/results/*` | historical dev results and logs (Stage B Tier 1 41/47, Tier 2 28/42); baselines backed up in `backups/phase35_results_20261112_160951/` |
| `docs/remediation/HELDOUT_THRESHOLD_FREEZE.md` | frozen held-out thresholds: Tier 1 ≥ 97/113, Tier 2 ≥ 69/106 |

**Dataset state observed during inspection:**
- `data_A.py` changed after the 25-correction change (A-conflict-01/02), outside this phase.
- `HELDOUT_THRESHOLD_FREEZE.md` already lists the current hashes, which match the files (`c204fd03…`, `f58fc804…`, `6fc3ca44…`, `6341a55f…`).
- Phase 4 did not touch either file.

## 2. Architecture (`eval/framework/`)
Importing any module has **no side effects**: no DB connection, no provider call, no `run_eval` import.

| Module | Purpose |
|---|---|
| `integrity.py` | Dataset validation, extra checks, manifest, `dataset_sha256`, `split_sha256`, per-split tier distribution, comparison with a frozen manifest. Duplicates `split_of` and checks it against `run_eval.py` with `ast` (no execution). |
| `safety.py` | `RunRequest` + `check_run_request` gates, `FROZEN_THRESHOLDS`, `threshold_result` (exact counts, `INCOMPLETE` for partial runs), output-overwrite protection |
| `retrieval_metrics.py` | Recall@K, Precision@K, RR/MRR, nDCG@K (binary or graded), page recall, document recall, aggregates and category breakdown, Tier 2 row adapter |
| `answer_metrics.py` | Aggregation of the **existing** per-case `score` fields, category breakdown, per-case issue explanations, explicit unavailable metrics |
| `memory_metrics.py` | Memory evaluation interface (`MemoryCase`) and scorers for 7 dimensions, plus aggregation |
| `memory_cases_proposal.py` | 12 proposed, developer-authored memory cases covering all 7 dimensions (definitions only) |
| `regression.py` | Baseline vs current: FIXED / REGRESSED / UNCHANGED_PASS / UNCHANGED_FAILURE / NEW_CASE / MISSING, status changes, metric deltas |
| `providers.py` | Provider-independent `RunAttribution` (provider, configured/observed models, tokens, calls, latency, retries, timeouts, fallbacks, quota waits, errors); comparison table |
| `reporting.py` | Report structure with an **evidence class** and **human-review status**, plus Markdown rendering |
| `cli.py` | `manifest`, `compare` and `report` commands; explicit paths, never overwrites. **No `run` command.** |

## 3. Dataset integrity
**Checks added in `extra_checks()`**, beyond `validate.py`:
- duplicate ids;
- unknown category or tier;
- `expect_*` flags that are not booleans, and `expect_abstain` combined with partial or conflict;
- malformed gold-fact groups or forbidden lists;
- gold source document missing from the corpus, or page out of range;
- **conflicting definitions**: the same question and history with different expectations is an error, and identical ones are a warning;
- `expect_conflict` outside the `conflicting` category (warning).

**Manifest** (`build_manifest(version)`): dataset version, per-file SHA-256, content `dataset_sha256` (by id, ignoring private keys), `split_sha256` (membership only), documents and pages, case count, split counts, per-split Tier 1/Tier 2/answer-only counts, category counts, the full split membership, `valid`, errors and warnings.

**Behaviour:**
- `compare_to_manifest()` lists the differences from a frozen manifest. It never repairs anything.
- Validation and manifest building write nothing. Only `cli manifest` writes, to a **new** file.
- **Not executed in this phase:** no manifest was generated and no frozen manifest file exists yet. Creating one is a future authorized step.

## 4. Retrieval metrics
**Formulas** (documented in the module):
- `Recall@K = |rel ∩ topK| / |rel|`
- `Precision@K = |rel ∩ topK| / K` (K fixed)
- `RR = 1/rank of the first relevant`; MRR is its mean
- `nDCG@K = DCG/IDCG`, with `DCG = Σ gain/log2(i+1)`
- page and document recall are recall over the whole list

**Edge cases:**
- duplicates and `None` are collapsed to the first occurrence;
- an empty relevant set gives `None` (undefined, excluded from aggregates, never silently 0 or 1);
- an empty retrieval gives 0;
- `k ≤ 0` raises an error.

**Units and data:**
- Units are `(document, page)` pairs, matching the datasets' gold granularity.
- Graded relevance is supported by the function, but no graded labels exist.
- **Chunk recall is not computed:** the datasets have no gold chunk ids. This is documented, not invented.
- The adapter reads the existing Tier 2 rows (`retrieved`) together with the case `gold_sources`; nothing is re-retrieved.
- No production retrieval code was changed.

## 5. Answer metrics
- **Source of scores:** the per-case semantics are exactly `run_eval.score_generic`, as stored in `row["score"]`. Rows are aggregated, never re-scored.
- **Reported metrics:** correctness (strict and lenient); completeness (`fact_recall`); citation correctness and completeness, **structural only**; unsupported claims (heuristic flag, separate from missing citations); abstention correctness; conflict handling; partial handling; injection resistance (no forbidden hit on prompt-injection cases); status counts (status is kept separate from correctness).
- **Unavailable:** semantic groundedness, which needs claim-level labels, and answer relevance, for which no labels exist. They are listed in `unavailable_metrics` and never estimated.

## 6. Memory metrics
**Dimensions**, each with its own scorer:

| Dimension | What is checked |
|---|---|
| extraction | required substrings, forbidden memories, category accuracy |
| provenance | exact source-set match, user role and same conversation required, invalid-batch rejection |
| dedup / update | per-step action accuracy, detail preservation, old-fact retention, sources after an update |
| conflict | relation accuracy |
| context | inclusions, leaks, bound |
| lifecycle | deleted ids absent, no resurfacing in context/summary text, checkpoint expectation |

**Matching is by required substrings, exact ids and exact source sets**, never by semantic similarity.

**Cases:** the 12 proposed cases are **developer-authored regression fixtures**. Their message and memory ids are placeholders resolved by a future runner on a scratch DB with mocked LLM output. **No runner is implemented and no case was executed.**

## 7. Regression comparison
`regression.compare(baseline_rows, current_rows)` is pure:
- it rejects inputs that contain duplicate ids;
- it reports per-case outcome classes, regressions, improvements, unchanged failures, status changes and numeric metric deltas.

Inputs are never modified. Output is written only through `cli compare` to a new file.

## 8. Provider/model comparison
**Attribution** comes from already-recorded data only:
- per-case rows (latency, calls, tokens);
- optional per-call usage records with model names;
- optional run-log text: counts of fallback, timeout, 503-retry and quota-wait lines that `llm_service` already prints.

Missing fields stay `"unavailable"`. A fixed note explains that per-answer model attribution is not stored and that quota cooldowns can route calls silently.

**No SDK import, no API key access, no Gemini hard-coding.** `compare_providers()` builds a side-by-side table.

## 9. Reporting and reproducibility
`build_report` requires an evidence class:
- `AUTOMATED_DEVELOPER_CASES`
- `AI_ASSISTED_REVIEWED`
- `HUMAN_REVIEWED`
- `INDEPENDENT_VALIDATION`

It also requires a human-review status:
- `NOT_REVIEWED`
- `AI_ASSISTED_ONLY`
- `HUMAN_REVIEW_PENDING`
- `HUMAN_REVIEWED`

It **refuses** `HUMAN_REVIEWED` or `INDEPENDENT_VALIDATION` unless the status is `HUMAN_REVIEWED`. AI-assisted review therefore cannot be labelled as human or independent.

**Report contents:** evaluator version (`phase4-1.0`), timestamp, dataset version and hashes, run info, answer, retrieval and memory metrics, thresholds, attribution, regression, and limitations. `cli report` writes Markdown and JSON to **new** files only.

## 10. Execution safety (for future runs)
`check_run_request` blocks a run unless all of the following hold:
- **Mode:** an explicit mode (`offline|development|heldout`), with explicit splits (no default to all) and explicit tiers.
- **Outputs:** explicit output paths that do not exist yet, in existing directories.
- **Live provider:** explicit opt-in for development or held-out runs; it is forbidden in offline mode.
- **Held-out:**
  - only in `heldout` mode;
  - an existing approval file containing `HELDOUT EVALUATION AUTHORIZED`;
  - the current and frozen manifests, with no differences and a valid current manifest.

**Gate integration:** `run_eval.py` is **not** modified. Wiring this gate into it, and recording run metadata, is a future authorized change. Until then the existing runner keeps its current behaviour and must only be run on explicit user instruction.

**Thresholds:** `FROZEN_THRESHOLDS` mirrors the frozen values exactly:

| Split | Tier 1 | Tier 2 |
|---|---|---|
| dev | 41/47 | 28/42 |
| held-out | 97/113 | 69/106 |

`threshold_result` never rounds up and returns `INCOMPLETE` when fewer cases than required were evaluated.

## 11. Frozen held-out constraints and human review
- **Unchanged and unexecuted:** the held-out membership (113 cases; 106 Tier 2 eligible; 7 answer-only), the thresholds, and the dataset contents. The held-out evaluation has **not** been run.
- **Human review is still pending.** The existing review (`heldout_review/REVIEW_SIGNOFF_REPORT.md`) is **AI-assisted, not independent human review**, and must be reported as `AI_ASSISTED_ONLY` or `HUMAN_REVIEW_PENDING`.

## 12. Files
- **New:**
  - `eval/framework/__init__.py`, `integrity.py`, `safety.py`, `retrieval_metrics.py`, `answer_metrics.py`, `memory_metrics.py`, `memory_cases_proposal.py`, `regression.py`, `providers.py`, `reporting.py`, `cli.py`
  - `test_p4_eval_framework.py` (**written, not executed**)
  - this document
- **Modified:** `run_tests.py` (registered the new test under `unit`).
- **Not modified:** any dataset, `validate.py`, `run_eval.py`, `summarize.py`, `answer_scoring.py`, any result file, any production module.

## 13. Limitations
- **Untested:** all code is static-reviewed only, and the metric formulas are verified by reading the code only.
- **Gate not enforced on the runner:** `run_eval.py` does not yet call `check_run_request`.
- **No frozen manifest file** exists yet.
- **Answer metrics:** semantic groundedness and answer relevance are unavailable; citation metrics are structural only.
- **Retrieval granularity:** chunk-level retrieval recall is not computable from the current gold data; Tier 1 has no retrieval step.
- **Memory evaluation:** the 12 cases are proposals without a runner. They are developer-authored, not independent.
- **Model attribution** remains log-based and approximate.
- **Approvals still needed:**
  - creating a frozen manifest;
  - wiring the gates into the runner;
  - any development or held-out run;
  - executing the new tests.

**TESTING AND EVALUATION NOT RUN — strictly prohibited by user instruction. No unit tests, integration tests, smoke tests, regression tests, development evaluations, held-out evaluations, benchmarks, live model calls, or evaluation scripts were executed. Only source inspection, static review, and optional syntax compilation were performed.**
