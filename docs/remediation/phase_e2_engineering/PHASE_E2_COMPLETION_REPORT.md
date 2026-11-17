# Stage 9 Phase E2: completion report

**Date:** 2026-11-17. **Scope:** WP1 – WP5 of the Phase E2 implementation plan.
- Executed by five parallel agents with exclusive file ownership.
- The lead coordinated, integrated, and re-ran every test.
- WP6 and WP7 were **not** started.

**Not done:**
- no dataset, threshold or scorer-v1 change;
- no manifest regeneration;
- no workbook decision;
- no database, LLM or network;
- no held-out run;
- no commit, push or staging.

## 1. Baseline and final state

| Item | Before E2 | After E2 |
|---|---|---|
| Branch / HEAD | `audit/stage9-evaluation-readiness` / `69e8b8e` | unchanged |
| Staged entries | **56** (the handoff said 47; the owner had also staged the 9 E1 files) | **56**, no index entry added or removed. Edited staged files now show `AM`/`MM` |
| Protected assets (27 manifest assets + `frozen_manifest.json` + `safety.py`) | baseline SHA-256 | **all identical** |
| `verify-frozen-manifest` | REPRODUCED | **REPRODUCED** (`1b73a208…`) |
| Whole-tree comparison (371 files, excluding `.venv`, `.git` and `__pycache__`) | snapshot | 16 modified, 28 added, **0 removed**. Every change maps to an owning agent or the lead (`PHASE_E2_FILE_CHANGE_INVENTORY.csv`), except `docs/remediation/.DS_Store`, rewritten by macOS Finder (not an agent) |

## 2. Work packages

| WP | Agent | Outcome | Lead verification |
|---|---|---|---|
| WP1 Documentation & reviewer protection | 1 | Anti-anchoring lists now cover `technical_dataset_audit/`, `phase_d_decision_package/`, `phase_e1_multi_agent_audit/` and `phase_e2_engineering/` (guide, checklists, dev README). E0 addendum (runner regression, corrected full hashes). `STAGE9_FROZEN_MANIFEST.md` notes. PHASE4 "superseded in part" banner. New `STAGE9_RUNBOOK.md` (platform, environment, re-freeze procedure) and `STAGE9_STATUS_INDEX.md` (supersession map, incl. the Phase D supersession note). Frozen review files untouched | Grep confirmed all four folders in all three reviewer docs. Lead updated the runbook's probe section once WP3 had landed |
| WP2 Dev runner repair | 2 | `stage6_live_dev_eval.py`, `stage8_p3_live_dev_eval.py` and `h1_relevance_gate.py` now bootstrap the scratch DB (stage6: `run_eval.bootstrap_execution()`; h1: `harness.use_scratch_database`) before **lazily** importing `services.*`. Importing them has no side effect. Dev-only checks are preserved. New `test_stage9_e2_dev_runners.py` uses tripwires | Re-ran: 38/0; E0 gate test still passes. No module-level `services` imports remain |
| WP3 Test engineering | 3 | Live-state assumptions removed from the 3 Stage 9 tests (fixture manifests; workbook integrity instead of progress). New `check_stage9_readiness.py` (live-state report, not a test). New 110-probe harness `eval/probes/`: per-probe status, citations, context and annotations; all v1 sub-signals asserted. **Corrected** P-TS1-06, P-TS1-09, P-TAD4-1 and TA-11; 38 new adversarial probes. New tests: scorer probes, v1 immutability, review-check branches, gate branches. `checks.py`: 2 functional gaps fixed | Re-ran everything (§3). Lead fixed `eval/review/progress.py` to print the new `historical_check` field (WP3 flagged the defect) and registered 5 new tests |
| WP4 Revised proposals | 4 | `wp4/REVISED_PROPOSALS.json` + CSVs (11 held-out, 4 dev) + revised TP decisions, all `PENDING_OWNER_DECISION`. TA-11 accepts "batteries"; TA-02 now "errata supersedes"; TA-06 recommends deferring to the v2 negation guard; TA-07 anchored set or defer to v2; TP-06 and TP-10 now DEFER; `£40` kept; TA-D4 context impact recorded; all hedges probed | Re-ran the validator: `RESULT: OK; 0 unexpected`; denominators 113/106, 47/42 |
| WP5 Scorer v2.1 spec | 5 | `wp5/SCORER_V2_1_SPEC.md` (supersedes `SCORER_V2_DESIGN.md`) covers all 12 requirements, with ~120 test rows, traceability for every SCORER and TEST finding, and new decisions V-6 – V-11 | Section structure checked. High findings resolved: SCORER-1 (§8), SCORER-2 (§12.3), SCORER-6/TEST-4 (§7, §9), SCORER-12/TEST-3 (§13), ARCH-8 (§12.1-2). Evidence: pinning the dataset to `c1bbcae` reproduces 47/47 stored v1 results. Its regexes are specified but **not executed** (no implementation) |

## 3. Tests executed by the lead after integration

Command form: `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B <file>`

| Run | Result |
|---|---|
| `test_stage9_e0_runner_gate.py` | 110/0 |
| `test_stage9_e0_frozen_manifest.py` | 24/0 |
| `test_stage9_b_review_tools.py` | 44/0 |
| `test_stage9_e2_dev_runners.py` | 38/0 |
| `test_stage9_scorer_probes.py` | 134/0 |
| `test_stage9_v1_immutability.py` | 21/0 |
| `test_stage9_review_checks_branches.py` | 38/0 |
| `test_stage9_gate_branches.py` | 40/0 |
| `test_p4_eval_framework.py` | 22/0 |
| `-m eval.probes.scorer_regression --validate-proposals` | 110 probes, 0 failures |
| `check_stage9_readiness.py` | 0 problems, 0 warnings |
| `wp4/validate_revised_proposals.py` | OK |
| Phase D probe suite (historical) | 72/0 |

- **Total:** 471 test checks, 0 failures, all exit 0. Details in `PHASE_E2_TEST_MATRIX.csv`.
- **Registry:** every root `test_*.py` is classified in `run_tests.py`.
- **`run_tests.py` itself was not run,** because it opens a DB connection to fingerprint `rag_db`.

## 4. Disagreements and resolutions

| Topic | Resolution |
|---|---|
| WP3 harness vs WP5 spec on 4 v2 expectations (P-TS1-06, P-TS1-08, P-TS4-10, P-E2-STAT-06) | The **spec governs**. The values are not executable until v2 exists, so they are aligned in WP6 step 1 (recorded in the runbook and in `PHASE_E2_REMAINING_DECISIONS.md`) |
| `checks.py` gap (a): incomplete vs error | WP3 chose **incomplete**: an error would fail every baseline-less validation of the real workbook's 26 history rows. Owner to confirm |
| TA-03 vs v2 assertion annotation | Owner. New evidence: after TA-03, v1 accepts the value swap "GBP 2,000, not 1,800" (P-E2-SWAP-02) |
| Tier 2 ref count (lead 74 vs WP5 58) | Not a contradiction: 74 total references, 58 distinct |

## 5. Completion criteria

- [x] All five WP reports exist.
- [x] Tests executed and recorded.
- [x] Probe suite strengthened (72 → 110); v1 expectations corrected and asserted per sub-signal.
- [x] Scorer v2.1 design resolves every High scorer finding (spec §18 traceability).
- [x] Proposals revised, not applied.
- [x] Three dev runners repaired and tested.
- [x] Protected assets unchanged; manifest REPRODUCED.
- [x] Git status and file hashes documented.

## 6. Remaining limitations

- No runner `main()` was executed against a real scratch DB or provider, so end-to-end runner behaviour is untested.
- The v2.1 spec is unimplemented; its regexes and test expectations are hand-derived.
- No lint tool (`ruff`) is installed; only `py_compile` and AST checks were run.
- The Windows commands in the runbook were not executed.
- `run_tests.py` was not run (it needs a DB).

**Next:** WP0 owner decisions → WP6 and WP7 (plans in `PHASE_E2_REMAINING_DECISIONS.md` §2–3) → WP8 after the independent human review.
