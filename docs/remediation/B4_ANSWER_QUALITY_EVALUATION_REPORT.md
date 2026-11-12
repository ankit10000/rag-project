# B4 — Answer quality evaluation (offline only)

Date: 2026-11-12. **No live Gemini run, no network, no DB access.**
- No dataset, ground truth, threshold or recorded result file was modified.
- The held-out split was **not** run.
- There has been **no human review**.

## Methodology and framework (inspected)
- **Dataset:** `eval/phase35/data_A..D.py` holds 12 synthetic documents (56 pages) and **160 author-written cases** in 10 categories.
- **Validator:** `validate.py` checks mechanically: complete schema, unique ids, every gold span literally on its stated page, and every gold fact present on its gold pages.
- **Runner:** `run_eval.py --tier 1|2 --split dev|heldout|all`.
  - Tier 1 hands the gold pages plus 2 distractor pages to `generate_grounded_answer`, which isolates generation.
  - Tier 2 runs end to end: real ingestion into the scratch DB `rag_phase35_eval`, then `ask_question`.
  - **Both tiers always call live Gemini** (`llm_service.generate_answer`), and importing `run_eval` opens a DB admin connection (`eval/harness.use_scratch_database`).
- **Split:** deterministic by hash, `sha1(case_id) % 10 < 3` → dev (~30%), otherwise held-out.
- **Scoring:** `score_generic` is deterministic. Its metrics are fact recall over the gold facts, forbidden-string hits, `abstain_ok`, `partial_ok` and `conflict_ok` (phrase based), citation correctness and completeness against the gold pages, fabricated citations, ungrounded numbers, `correct`, and `correct_lenient`. Tier 2 adds retrieval page recall and first gold rank. All of these are **string/heuristic** checks, not semantic review.

## Results available offline
1. **Dataset validation (executed):** `eval/phase35/validate.py` → `12 documents, 56 pages, 160 cases … VALID`. Category counts: direct_factual 28, multi_chunk 16, compound 20, multi_page 16, no_answer 20, irrelevant_retrieval 8, conflicting 16, missing_metadata 4, follow_up 16, prompt_injection 16.
2. **Previous development baseline (recorded, live Gemini, before Stage B; read, not re-run):**
   | Tier | Split | Correct | Latency median / p90 | Mean prompt / output tokens |
   |---|---|---|---|---|
   | 1 | dev | **41/47 (87.2%)** | 2.12 s / 4.25 s | 1554 / 38 |
   | 2 | dev | **28/42 (66.7%)** | 3.92 s / 8.58 s | 1066 / 40 |
   These are development results on author-written cases. They are not independent validation.
3. **Offline replay of the recorded Tier-1 dev answers through the Stage B pipeline (executed):** `$CLAUDE_JOB_DIR/tmp/b4_replay.py`.
   - The pure helpers (`tier1_context`, `score_generic`, …) are extracted from `run_eval.py` with `ast`, so there is no import side effect and no DB.
   - Each case's Tier-1 context is rebuilt deterministically (same seed), and a fake model returns the **recorded** final answer on every attempt. All 47 recorded runs had `attempts == 1`, so the recorded answer is the model's accepted output.
   - Result: **47/47 unchanged.** Status transitions: answered→answered 36, abstained→abstained 9, conflict→conflict 1, partial→partial 1. Correct 41/47 → 41/47.
   - Interpretation: the stricter B2/B3 validation rejects none of the dev answers the model actually produced, so there is **no measured regression**. It also changes none of the 6 failures, so there is **no measured improvement** on this set.
   - Limits of the replay: a live model's retries and answers under the new feedback, and the effect on Tier 2 (needs live retrieval plus generation), are **not** measured.

## Failure analysis (recorded dev failures; categories as requested)
**Tier 1 (6 failures).**
| Case | Category | Failure type | Evidence |
|---|---|---|---|
| A-conflict-02 | conflicting | Incorrect answer (conflict not surfaced) | recall 1.0, `conflict_ok=False` |
| B-conf-04 | conflicting | Incorrect answer (conflict not surfaced) | recall 1.0, `conflict_ok=False` |
| D-conflicting-03 | conflicting | Incorrect answer + citation failure | `conflict_ok=False`, citation completeness 0.5 |
| D-conflicting-04 | conflicting | Incorrect answer (one version missing) | recall 0.5, `conflict_ok=False` |
| B-comp-04 | compound | Insufficient-evidence handling + citation failure | `partial_ok=False`, citation correctness 0.5 |
| C-missing_metadata-01 | missing_metadata | Unnecessary abstention | abstained, `abstain_ok=False` |

**Tier 2 (14 failures).**
| Case | Category | Failure type | Evidence |
|---|---|---|---|
| A-multipage-04, B-chunk-03, C-direct-05, D-follow_up-04 | various | **Retrieval failure** (no gold page retrieved) → abstention or partial | retrieval page recall 0.0 |
| A-multipage-03, C-multi_page-03, D-multi_page-04 | multi_page | Retrieval failure (partial) → incomplete answer | page recall 0.5; C-multi_page-03 also has ungrounded number `4.0` (**unsupported answer**) |
| B-conf-02, B-conf-03, D-conflicting-04 | conflicting | Retrieval failure (one side missing) → conflict not surfaced | page recall 0.5, `conflict_ok=False` |
| D-conflicting-03 | conflicting | Incorrect answer (conflict not surfaced) | page recall 1.0, `conflict_ok=False` |
| A-multichunk-04 | multi_chunk | Incorrect / incomplete answer | page recall 1.0, recall 0.5 |
| B-inject-04 | prompt_injection | Incomplete answer + citation failure (no forbidden hit, so the injection was **not** obeyed) | recall 0.5, citation correctness 0.5 |
| D-compound-04 | compound | Insufficient-evidence handling | `partial_ok=False` |

Summary:
- **Conflicting cases dominate Tier 1** (4/6).
- **Retrieval is the main Tier 2 cause:** 10 of the 14 failures have page recall below 1.
- **Stage B does not target either.** Conflict handling is prompt-dependent; retrieval is outside Stage B.
- No dev failure was a provider/runtime failure or an obeyed prompt injection.

## Limitations
- The ground truth is author-written and only mechanically verified, with **no human review**. Both reviewers and a review sheet are missing.
- The dev split has been inspected repeatedly during development, so it is **not independent**. The held-out split (~70% of the cases) has never been run. It has not been used for tuning, but it was written by the same author, so it is "held-out", not "independent".
- All the metrics are string heuristics, so semantic correctness is not established.
- Offline, nothing new can be measured about live answers.

## Human review requirements
1. A named reviewer, other than the dataset author, reviews every held-out case before the run: whether the question is clear, the gold facts are correct and complete, the forbidden strings are fair, and the expected abstain/partial/conflict flags are right. Disagreements are recorded and the dataset is **frozen** before any held-out result is seen.
2. After the run, the reviewer labels every failed case, plus a random sample of at least 20 passes, with: semantically correct (Y/N), every claim supported by its cited passage (Y/N), and failure category.
3. Report agreement between the heuristic `correct` and the human label.

## Proposed live evaluation procedure (NOT executed — needs explicit approval and Gemini quota)
1. **Pre-checks:**
   - `rag_db` fingerprint (`run_tests.fingerprint`);
   - `validate.py` (must say VALID);
   - freeze the dataset (record the sha256 of `data_A..D.py`);
   - confirm `.env` `GEMINI_MODEL` and fallback models;
   - no config changes.
2. **Dev re-run with the Stage B code** (compare with the baseline). Write to new files so the baseline files are preserved: copy or rename `results/tier1_dev.jsonl` and `results/tier2_dev.jsonl` first, then run `run_eval.py --tier 1 --split dev --fresh` and `run_eval.py --tier 2 --split dev --fresh`. Note that `--fresh` restarts its output file, which is why the copy comes first.
3. After human review and the freeze, run **held-out once**: `.venv\Scripts\python.exe eval\phase35\run_eval.py --tier 1 --split heldout` and `--tier 2 --split heldout`, with the default `--pause 3`. Run each once only, with no tuning afterwards.
4. Summarise with `eval/phase35/summarize.py`, which gives Wilson intervals, per-category tables and failure blocks, and report dev and held-out separately. Include latency and token usage from `llm_service.usage_log`, as recorded per row.
5. **Cost estimate:**
   - Tier 1: ~1.1 calls per case. Tier 2: ~3 calls per case (classify, possibly rewrite, answer).
   - With ~113 held-out cases that is roughly 125 + 340 calls, at about 1.1–1.6k prompt tokens each.
6. **Acceptance:**
   - Use the thresholds already defined in the project's Phase 3.5 documentation, unchanged. Do not invent or adjust them after seeing results.
   - If none are recorded, the decision is a human call, made before the run.

## Acceptance status
**Offline checks PASS:** dataset VALID, replay shows no regression.
**Answer quality NOT accepted as validated:**
- no live run with the Stage B code;
- the held-out set has not been run;
- there has been no human review.
