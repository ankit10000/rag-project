# Batch 2, Stage 8 P3: Rewrite-First Question Classification

**Date:** 2026-11-16. **Scope (approved):** classify the rewritten standalone query instead of the raw query; focused tests; a six-case dev-only live check.
**Not done:**
- No prompt, category, fallback or parser change.
- No retrieval, grounding, memory or schema change.
- No held-out evaluation.
- Nothing committed, pushed or merged; the gap register was not updated.

## 1. Git baseline and branch

| Item | Value |
|---|---|
| Start | `main` at `0344fbc86dbba4808c7c62cf4def5582de0f6786` = `origin/main`, clean tree |
| Branch | `feature/stage8-p3-classification` (new; it did not exist locally or on origin) |
| Instructions | No project `CLAUDE.md`; the global `CLAUDE.md` applies (feature branch, tests for new behaviour, lint before reporting) |

## 2. Root cause (Phase A)

From `BATCH2_STAGE8_PHASE_A_AUDIT.md` §5–§6:
- `rag_service.ask_question` called `classify_question(query)` on the **raw** query, before `rewrite_query`. The classifier never saw what a follow-up refers to.
- `D-follow_up-04` ("How long must I wait before restarting after that trip?") was classified MEMORY in both earlier runs, so retrieval was skipped (`not_run`) and the system refused.
- `C-direct-05`'s MEMORY/DOCUMENT flip is a **separate** classifier-variability issue. It has no history, so the reordering can't affect it.

## 3. Implementation

**`services/rag_service.py`, `ask_question` only** (+14 / −9):
- The existing rewrite block (unchanged: same inputs, same failure fallback to the original question, same empty/blank fallback) now runs **first**.
- The existing classification block (unchanged: same `classify_question`, same `DOCUMENT` fallback on an exception, same print) now runs second, on **`search_query`** (the rewritten query) instead of `query`.

Everything else is untouched:
- retrieval still uses `search_query`;
- the MEMORY bypass still yields `retrieval_status = "not_run"`;
- answer generation still receives the original `query`;
- `main.run_turn`, its return contract and the API are unchanged.

**No extra LLM call:**
- With no history and no memory, `rewrite_query` returns the query unchanged **without** a model call, as before. So standalone questions get the same classifier input as before.
- With history, the same one rewrite + one classify requests run, now in the opposite order.

**Other files:**
- `run_tests.py`: +1 line registering the new unit test.
- New: `test_stage8_p3_classification.py` and `eval/stage8_p3_live_dev_eval.py`.

## 4. Execution flow

```
Before:  classify_question(raw) → rewrite_query(raw, history, memory) → MEMORY? skip : hybrid_search(rewritten)
After:   rewrite_query(raw, history, memory) → classify_question(rewritten) → MEMORY? skip : hybrid_search(rewritten)
         (answer generation receives the raw question in both)
```

## 5. Unit tests

**`test_stage8_p3_classification.py`** (unit, registered). Mocks only; no database (it also passes against a non-existent database) and no LLM. **20 checks.**

| Group | Checks |
|---|---|
| A. Ordering | Rewrite before classify; classifier gets the rewritten query, not the raw one; retrieval gets the same rewritten query; answer generation gets the original question and history; rewrite inputs unchanged; the real `classify_question` prompt contains the rewritten text; a standalone question makes no rewrite LLM call and its classifier input is the raw query (1 LLM call in total); a follow-up makes exactly one rewrite and one classify request, rewrite first |
| B. MEMORY | Retrieval skipped; `retrieval_status == "not_run"`; MEMORY type reaches the answer layer |
| C. DOCUMENT | Retrieval with the rewritten query; evidence reaches context assembly; end to end with the real answer layer → `answered`, citing page 3 |
| D. MIXED | Retrieval runs; memory context is passed to the answer |
| E. Failures | Rewrite exception → the original query is used for classification and retrieval; empty/blank rewrite → original; classifier exception → `DOCUMENT` fallback, retrieval runs (no bypass) |

**Mutation:** restoring `classify_question(query)` makes 2 checks FAIL (both classifier-input checks). The file was restored byte-identically.

## 6. Focused test results

| Command | Result |
|---|---|
| `.venv/bin/python run_tests.py test_stage8_p3_classification.py` | PASS (20/20 checks), `rag_db` unchanged |

## 7. Regression

| Command | Result |
|---|---|
| `.venv/bin/python run_tests.py` (unit + integration, `rag_test_scratch`) | **49 run / 49 passed / 0 failed** (48 + the new test); 18 live/manual not run; `rag_db` unchanged |

All of these pass:
- Stage 4: `test_stage4_ingestion*`.
- Stage 5: `test_stage5_retrieval*`, `test_retrieval_phase2`.
- Stage 6: `test_stage6_answer*`, `test_b2`, `test_b3`, `test_answer_phase3`.
- Stage 7: `test_stage7_memory_provenance`.
- Stage 8 Phase B: `test_p1_process_memory`, `test_p1_delete_routing`.

No existing test needed changing: none asserted the old order.

## 8–14. Six-case dev-only live check

**Command:** `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -u -m eval.stage8_p3_live_dev_eval --out eval/results/stage8_p3_live_dev_20261116` (one run, 17:42:35–17:43:12).
- **Cases:** the Phase A cases: the two classified MEMORY plus the four classified MIXED in the earlier runs, all **Tier 2 dev** (asserted via the Stage 6 preflight).
- **Method:** each case runs once through the unchanged `run_eval.run_tier2`: real retrieval on `rag_phase35_eval`, real Gemini, frozen `score_generic`.
- **Inputs:** the case questions and histories are taken from the dataset unchanged (the same inputs as the recorded runs).
- **Outputs:** `eval/results/stage8_p3_live_dev_20261116/cases.json` and `run_log.txt`.

### Raw vs rewritten query and classifier input

| Case | History | Raw query | Rewritten (= classifier input) |
|---|---|---|---|
| `D-follow_up-04` | 2 turns | How long must I wait before restarting after that trip? | **Aquaflow pump E-41 fault restart cooldown time** |
| `B-follow-03` | 2 turns | And for part-timers? | **When does a part-time MPhil student have to submit the upgrade report at Velmoor?** |
| `C-direct-05` | none | What would a spare burr set for my B3 espresso machine set me back? | identical (no rewrite call) |
| `A-multipage-03` | none | I'm expecting. Which jab does the clinic give during pregnancy and in which weeks, and what time does the Saturday session finish? | identical |
| `D-multi_page-03` | none | For a 7-hour flight to Lisbon, what cabin class may I book and what's the hotel cap per night? | identical |
| `D-multi_page-04` | none | Which contractor firm was involved in the bearing heater burn, and how hot can the induction heater surface get? | identical |

In all 6 cases the recorded classifier input equals the rewritten query.

### Classification, retrieval, evidence, correctness

| Case | Class: Stage B → Stage 6 live → **now** | `retrieval_status` now | Gold pages retrieved now (Stage B / Stage 6) | Correct: Stage B / Stage 6 / **now** |
|---|---|---|---|---|
| **`D-follow_up-04`** | MEMORY → MEMORY → **DOCUMENT** | **ok** | **1/1** (0 / 0) | ✗ / ✗ / **✓** "A trip on E-41 requires a 30-minute cool-down before restart [S1]." |
| `B-follow-03` | MIXED → MIXED → DOCUMENT | ok | 1/1 (1 / 1) | ✓ / ✓ / ✓ |
| `C-direct-05` | MEMORY → DOCUMENT → **MEMORY** | not_run | 0/1 (0 / 1) | ✗ / ✓ / ✗ (refusal) |
| `A-multipage-03` | MIXED → MIXED → MIXED | ok | 1/2 (0.5 / 0.5) | ✗ / ✗ / ✗ (`partial`) |
| `D-multi_page-03` | MIXED → MIXED → MIXED | ok | 2/2 (1 / 1) | ✓ / ✓ / ✓ |
| `D-multi_page-04` | MIXED → MIXED → MIXED | ok | 1/2 (0.5 / 0.5) | ✗ / ✗ / ✗ (`partial`) |

**Totals:** correct 3/6 now vs Stage B 2/6 vs Stage 6 live 3/6, on these six cases only.

### Provider, model, requests, tokens

| Item | Value |
|---|---|
| Gemini requests | **14** (rewrite 2, classify 6, answer 6), within the 12–20 estimate; no extra exploratory calls |
| Models | All 14 served by the primary `gemini-3.5-flash-lite`; **no fallback, no 429, no timeout, no errors** |
| Tokens | Prompt 6,577 / output 287 |
| Latency per case | 1.7–4.7 s |

## 15. Database fingerprints

Read-only `run_tests.fingerprint` method, `current_database()` verified.

| Database | Before | After |
|---|---|---|
| `rag_db` | 0 rows in all 5 tables | identical |
| `rag_test_scratch` | 0 rows in all 5 tables | identical (test fixtures self-cleaned) |
| `rag_phase35_eval` | 135 chunks | identical (live check read only) |

- No migration applied, no database created or dropped, no `--clean`.
- `eval/phase35/`, `eval/framework/`, the H.1 and Stage 6 results, and the migrations are unchanged vs `0344fbc`.
- `git diff --check` clean. The run log was checked for secrets and URLs (0 matches).

## 16. Findings

**Verified improvement:**
- **`D-follow_up-04`:** the classifier received the rewritten standalone query ("Aquaflow pump E-41 fault restart cooldown time") and classified it DOCUMENT. Retrieval ran, found the gold Aquaflow p.3 page, and the answer is correct. It was wrong in both earlier runs. **The primary acceptance condition is met.**
- **`B-follow-03`**, the other follow-up, was also classified from its rewritten query (DOCUMENT instead of MIXED). Retrieval and correctness are unchanged (✓).

**Unchanged behaviour:**
- The 4 cases without history get a byte-identical classifier input. Their labels (MIXED ×3) and outcomes match both earlier runs.
- `A-multipage-03` and `D-multi_page-04` remain incorrect because of **retrieval** (one of two gold pages found), not classification. That is the pre-existing Stage 6 finding.

**Remaining problem: `C-direct-05` (not fixed, and not expected to be).**
- It has no history, so its classifier input is identical before and after.
- It was classified MEMORY again ("my B3 espresso machine"), so retrieval was skipped and the system refused.
- Observed so far: MEMORY in Stage B, DOCUMENT in the Stage 6 live run (served by the fallback `gemini-3.1-flash-lite`), MEMORY now (primary `gemini-3.5-flash-lite`).
- That is consistent with model-dependent or sampling variability, but three single observations **don't establish** the cause.

**Limitations:**
- One run per case.
- Six cases only, of which two exercise the change (the follow-ups).
- LLM non-determinism means a single follow-up success isn't a rate. The deterministic part (the classifier receives the rewritten query) is proven by the unit tests.
- Pre-existing code-limit notes, unchanged by P3: `ask_question` is 129 lines (was 124; +5 comment lines); `REFUSAL_MESSAGE` is an unused import.

**Recommendations (need separate approval):**
1. Commit `feature/stage8-p3-classification` and review it like the earlier branches.
2. For `C-direct-05`-style personal-pronoun document questions, choose among the Phase A options: a narrower MEMORY definition in the prompt (option 3), a deterministic pre-check, or never skipping retrieval for MEMORY (option 4, the largest contract change). Each needs its own dev evaluation.
3. Optionally, repeat the six-case check several times (≈ 14 calls per run) to measure follow-up classification rates rather than single outcomes.
4. Update the gap register only after review.

## 17. Held-out evaluation

**Not run.** No held-out case was loaded into the live check; the Stage 6 preflight asserts dev-only ids. No Phase 3.5 threshold, scorer, split or acceptance criterion was touched.

## Status

**P3 implemented and development-validated.** All the stated conditions hold:
- the ordering change is in;
- focused tests pass (20/20) and the regression passes (49/49);
- the six-case check is complete, with the key follow-up resolved;
- the database and frozen-asset checks pass.

`C-direct-05` variability remains open as a separate issue.
