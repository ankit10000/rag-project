# Stage 9 Phase D: completion report

**Date:** 2026-11-17. **Scope:** preparation and design only. Nothing was applied.

## Completed

| Criterion | Result |
|---|---|
| Held-out proposals | **11 / 11** (TA-01 – TA-11) in `HELDOUT_CORRECTION_PROPOSALS.csv`, all `PENDING_OWNER_DECISION` |
| Development proposals | **4 / 4** (TA-D1 – TA-D4) in `DEV_CORRECTION_PROPOSALS.csv`, all `PENDING_OWNER_DECISION`, kept separate |
| Potential findings | **12 / 12** (TP-01 – TP-10, TP-D1, TP-D2) in `POTENTIAL_ISSUE_DECISIONS.md`; none promoted to confirmed |
| Scorer v2 design | TS-1 – TS-5, versioning, offline re-scoring, sidecar metadata, backward compatibility, acceptance criteria (`SCORER_V2_DESIGN.md`) |
| Regression matrix | **72** deterministic probes (`SCORER_REGRESSION_MATRIX.csv`, generated from `scorer_regression_probes.py`) |
| Impact | Held-out and development separated (`PHASE_D_IMPACT_MATRIX.md`) |
| Owner checklist | Complete; every decision `PENDING_OWNER_DECISION` (`OWNER_DECISION_CHECKLIST.md`) |
| Deliverables | 9 / 9, plus the probe-suite script |

## Tests and checks run

All were run with `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1` (an unreachable database and a blocked network).

| Command | Result |
|---|---|
| `.venv/bin/python -B docs/remediation/phase_d_decision_package/scorer_regression_probes.py --validate-proposals` | **72/72** v1 expectations hold; `validate.py` on all 15 proposals applied **in memory** → **VALID** |
| Mutation check: proposals removed | 17 proposal probes change outcome (they really test the proposed definitions); TA-06 is the documented exception |
| In-memory impact computation | Held-out conflicting 7 → 5 and multi_page 12 → 14; dev conflicting 6 → 3; `split_sha256` unchanged; denominators unchanged |
| `test_stage9_e0_runner_gate.py` | 108/108 PASS |
| `test_stage9_e0_frozen_manifest.py` | 25/25 PASS |
| `test_stage9_b_review_tools.py` | 40/40 PASS |
| `test_p4_eval_framework.py` | 22/22 PASS |
| `verify-frozen-manifest` | **REPRODUCED** (`1b73a208…`) |
| `py_compile` of the probe script | OK |

**How the probe suite runs:**
- It imports the frozen `score_generic`; that import has had no side effects since E0.
- It installs a `psycopg.connect` tripwire.
- It writes nothing except `--write-matrix` (new file only).
- It is not registered in `run_tests.py`.

## Protected files (SHA-256 before = after)

| Group | Files |
|---|---|
| Dataset, scorer, runner, validator | `data_A..D.py` (`c204fd03`, `f58fc804`, `6fc3ca44`, `6341a55f`); `answer_scoring.py` `c3b54228`; `run_eval.py` `9d4670ce`; `validate.py` `2f29ba0f` |
| Review artefacts | held-out workbook `300dc43f` (correction ledger inside); dev workbook `6b94f343` |
| Freeze and audit | `HELDOUT_THRESHOLD_FREEZE.md` `3e4bd5d7`; all 5 Phase C files |
| Manifest | `frozen_manifest.json`, which still reproduces |

**Not done:**
- no threshold or policy change;
- no correction applied;
- no reviewer field filled;
- no approval status changed;
- no held-out approval file created.

## Safety

- **No database:** no connection opened; `rag_db`, `rag_phase35_eval` and `rag_test_scratch` were not touched.
- **No external calls:** no LLM/provider call and no network access.
- **No evaluation:** no held-out or `--split all` run, and no `run_eval.py` execution.
- **No packages:** nothing installed.
- **No git changes:** no commit, push, reset, clean, stash, checkout, staging or unstaging.

## Git

| | State |
|---|---|
| Before | HEAD `69e8b8e`; 37 staged, 0 unstaged, 0 untracked |
| After | identical, plus 10 **untracked** files in `docs/remediation/phase_d_decision_package/` (the 9 deliverables + `scorer_regression_probes.py`) |

A `__pycache__` folder created by the compile check was removed.

## Remaining work (each requires owner approval)

1. Owner decisions in `OWNER_DECISION_CHECKLIST.md`.
2. The independent human review (held-out 113; dev 7). It is still outstanding and authoritative.
3. An implementation phase for the approved items: a documented correction set, `validate.py`, a new frozen manifest and a re-freeze report; scorer v2 build and tests if approved.
4. A separate decision on the acceptance scorer before any held-out run. Held-out execution needs its own explicit approval.
