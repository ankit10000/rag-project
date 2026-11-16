# Batch 2, Stage 8: Completion Report

**Date:** 2026-11-16. **Scope:** Stage 8 as approved: the Phase A audit, Phase B memory test contract recovery, and P3 rewrite-first question classification. This report consolidates the existing stage reports; it adds no new measurements.

## A. Scope and stages

| Part | What | Report |
|---|---|---|
| Phase A | Read-only audit of the 2 failing memory test files and of the MEMORY question-classification misroutes | `BATCH2_STAGE8_PHASE_A_AUDIT.md` |
| Phase B (P1 + P2) | Tests-only recovery: `test_p1_process_memory.py` and `test_p1_delete_routing.py` updated to the documented Phase 1 Task 1 / Task 4 and Phase 3 contracts | `BATCH2_STAGE8_PHASE_B_REPORT.md` |
| P3 | `rag_service.ask_question` rewrites the query first and classifies the rewritten standalone query | `BATCH2_STAGE8_P3_CLASSIFICATION_REPORT.md` |

Baseline before Stage 8: `POST_MERGE_BASELINE_REPORT.md`, with `main` at `7176751` → 48 run / 46 passed / 2 failed (the two memory files).

## B. Implementation and evidence

### Commits and merges (all on `main`)

| Commit | What | Merged into `main` by |
|---|---|---|
| `5ab6d79` | test: update memory tests to the current Task 1/4 and Phase 3 contracts (2 test files) | `9beecc7` |
| `16f1e88` | docs: Phase A audit, Phase B report, post-merge baseline report, gap-register re-verification of P1-03 / P1-05 / P1-08 | `0344fbc` |
| `21979fa` | feat: classify rewritten queries before retrieval (7 files) | `49e6eb1`, PR #2 (https://github.com/ankit10000/rag-project/pull/2) |

The gap-register row `S8-P3` and this report follow in a separate documentation commit (`docs/stage8-completion`).

### Root causes (Phase A)
- **Both memory test files:** test drift. Commit `4a5e090` (2026-11-15) intentionally changed `main.py` and `automatic_memory_service.py` but did not update these two tests. The check-`[7]` crash aborted `test_p1_process_memory.py`, which hid 91 checks, including the P1-03 DELETE ban.
- **`D-follow_up-04`:** the classifier saw the raw follow-up without its referent, because classification ran before the rewrite.
- **`C-direct-05`:** classifier variability. It has no history, so the reordering does not affect it.

### Results

| Evidence | Result |
|---|---|
| `test_p1_process_memory.py` | **106/106**. All 91 previously hidden checks executed; DELETE ban `[22]`–`[27]` 18/18; isolation checks pass; one newly surfaced stale check (`[13]`) classified as an outdated expectation, no defect |
| `test_p1_delete_routing.py` | **137/137** (`[N2]` summary + memory-context composition, `[N3]` no fallback source) |
| `test_stage8_p3_classification.py` | **20/20** focused checks (mocked). Restoring the old order fails 2 checks |
| Full regression (`run_tests.py`, unit + integration) | **49/49** on merged `main` `49e6eb1` (48/48 after Phase B; 49 with the P3 test). 18 live/manual tests not run |

### Six-case dev-only live check (P3; 14 Gemini requests, primary model only, no errors; prompt / output tokens 6,577 / 287)

| Case | Classification (Stage B → Stage 6 → P3) | Retrieval (P3) | Correct (B / S6 / P3) |
|---|---|---|---|
| `D-follow_up-04` | MEMORY → MEMORY → **DOCUMENT** | `ok`, gold 1/1 | ✗ / ✗ / **✓** |
| `B-follow-03` | MIXED → MIXED → DOCUMENT | `ok`, gold 1/1 | ✓ / ✓ / ✓ |
| `C-direct-05` | MEMORY → DOCUMENT → MEMORY | `not_run` | ✗ / ✓ / ✗ |
| `A-multipage-03` | MIXED ×3 | `ok`, gold 1/2 | ✗ / ✗ / ✗ |
| `D-multi_page-03` | MIXED ×3 | `ok`, gold 2/2 | ✓ / ✓ / ✓ |
| `D-multi_page-04` | MIXED ×3 | `ok`, gold 1/2 | ✗ / ✗ / ✗ |

Only the two follow-ups (with history) receive a different classifier input after P3. The four no-history cases have byte-identical classifier inputs.

## C. Database and evaluation safety

- **Database fingerprints** (read-only `run_tests.fingerprint` method, `current_database()` verified) of `rag_db`, `rag_test_scratch` and `rag_phase35_eval` (135 chunks) were identical before and after Phase A, Phase B, the P3 tests, the P3 live check and the merged-`main` regression.
- Test fixtures cleaned up after themselves. No `--clean`, no manual cleanup.
- **No held-out evaluation.** The live check used 6 dev cases only, through the dev-only Stage 6 preflight.
- **Frozen evaluation assets unchanged:** `eval/phase35/`, `eval/framework/`, the recorded Stage B results, the H.1, Stage 6 replay and Stage 6 live results.
- **No migrations applied**, no schema change, no database created or dropped. Proposal 004 is still unapplied.
- No application change in Phase A or B. P3 changed only the order inside `rag_service.ask_question`.

## D. Remaining limitations

1. **`C-direct-05` classification variability:** "…my B3 espresso machine…" was classified MEMORY in Stage B and in P3, and DOCUMENT in the Stage 6 live run (fallback model). It is unresolved; options are in the Phase A audit §8 (prompt definition, deterministic pre-check, or no MEMORY bypass), each needing approval and its own dev evaluation.
2. **Retrieval misses:** `A-multipage-03` and `D-multi_page-04` retrieve one of two gold pages (page recall 0.5) in all three runs. That is a retrieval limitation, not classification.
3. **Memory decision accuracy is unverified live:** the Phase B decision checks (P1-08) mock the decision model; the real model's NEW / DUPLICATE / UPDATE accuracy is not measured.
4. **Phase 3 temporary-state / time-dependent conflict rules** were not re-assessed in Phase B (they are covered by `test_p3_memory_intelligence.py`, which passes, but was not re-reviewed).
5. **Small samples:** the P3 live check is one run of six cases; a single follow-up success is not a rate.
6. **Earlier open items unchanged by Stage 8:** H.1 no-rerank policy; extraction batch atomicity; proposal 004; the frozen-scorer artefacts (`v4.0`-style numbers, "do not mention" phrasing); the 18 live/manual tests not run.
7. **Pre-existing code-limit notes:**
   - `rag_service.ask_question` is 129 lines (over the 50-line guideline; +5 comment lines from P3).
   - `REFUSAL_MESSAGE` is an unused import.
   - `ruff` is not installed, so linting used compile and static checks instead.

## E. Final status

- **Stage 8 Phase A:** completed.
- **Stage 8 Phase B:** completed (both memory test files pass; no implementation defect found).
- **Stage 8 P3:** implemented and development-validated (gap register `S8-P3`: PARTIALLY COMPLETE, with `C-direct-05` open).
- **Stage 8 overall:** completed for the approved scope, with the limitations above.

This is not a claim that the RAG application is production-ready. The next stage needs its own plan and approval.
