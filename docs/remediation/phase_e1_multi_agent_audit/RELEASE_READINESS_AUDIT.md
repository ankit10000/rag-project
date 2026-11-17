# Phase E1: documentation and release readiness audit (Agent 6, consolidated)

**Summary:** most hashes and counts in the Stage 9 documents check out. Three items must be resolved before the Stage 9 PR can merge:
- DOC-1: undocumented runner breakage;
- DOC-2: live-state "unit" tests;
- DOC-3: anti-anchoring coverage.

## Verified consistent (agent; spot-checked by the lead)

| Area | Checks |
|---|---|
| Manifest | `content_sha256` `1b73a208…`, REPRODUCED; 27 assets equal on-disk hashes; 160 / 47 / 113; T1/T2/answer-only 113/106/7; category counts conflicting 13 and multi_page 17 |
| Scorer files and freeze doc | `run_eval.py` `9d4670ce` / HEAD `3b066a5b` and blobs as in E0 §11; `HELDOUT_THRESHOLD_FREEZE.md` byte-unchanged |
| Workbooks | Held-out: 113 rows, 29 cols, dropdown `Y2:Y114`, 0 reviewer fields, 26 ledger rows. Dev: 7 rows, 30 cols, `Y2:Y8`, empty ledger |
| Phase C counts | 11/22/80; per domain; severities; dev 4/2/1 |
| Phase D counts | 11 + 4 proposals, all pending; 72-row matrix with `expected_v1 == observed_v1` |
| Staging history | 17 → 32 → 37 → 47 staged is consistent across reports |

## Findings

| ID | Sev. | Finding | Lead check | Action |
|---|---|---|---|---|
| DOC-1 | **High** | Dev runners broken by E0 are undocumented (E0 §9 only says they "remain dev-only by their own preflights") | Verified (ARCH-1) | E0 addendum and release note; fix or retire the runners |
| DOC-2 | **High** | Three registered "unit" tests check live repository state and fail once review or corrections start. That creates pressure to regenerate the manifest "to make tests pass", which contradicts `HUMAN_REVIEW_GUIDE.md` ("never to hide a change") | **Verified** (`test_stage9_b_review_tools.py:251-258`; `test_stage9_e0_frozen_manifest.py:118`; `test_stage9_e0_runner_gate.py:28`) | Split into a separately named readiness check, or skip when review is in progress; document |
| DOC-3 | **Medium–High** | Anti-anchoring lists (`REVIEWER_CHECKLISTS.md:33-37`, `HUMAN_REVIEW_GUIDE.md` §1, `dev_review/README.md`) do not cover `technical_dataset_audit/` or `phase_d_decision_package/`, which contain per-case verdicts and proposed answers. Once merged they sit in the reviewer's checkout | **Verified** (the list covers only `../STAGE9_*.md`) | Add both directories (and `phase_e1_multi_agent_audit/`); decide S-2 before merge |
| DOC-4 | Medium | No re-freeze runbook:<br>• the CLI refuses to overwrite, so the manual move is undocumented;<br>• freeze rule 2 needs the new `data_*` hashes in `HELDOUT_THRESHOLD_FREEZE.md`, itself a manifest asset, so edit order matters;<br>• exclusions need code changes (`safety.FROZEN_THRESHOLDS` hard-codes 113/106);<br>• the manifest hash is hard-coded in three reviewer docs | — | Write a re-freeze runbook |
| DOC-5 | Medium | `PHASE4_EVALUATION_FRAMEWORK.md` is stale in more places than E0 admits (lines 12, 13, 38, 55, 140, 143, 164, 168-169) | — | "Superseded by" banner (not a manifest asset) |
| DOC-6 | Medium | `MASTER_GAP_REGISTER.md` has no Stage 9 updates (P35-01/02/04 still NOT STARTED although addressed) | — | Update it, or state that it is unchanged |
| DOC-7 | Medium | TA-07 (and TA-06/TA-08) recommendations differ between Phase C and Phase D with no supersession note | — | Note that Phase D supersedes |
| DOC-8 | Medium | Platform and Python guidance conflicts (Windows 3.14.10 in `requirements.txt` and docstrings vs macOS 3.14.5 in practice); `STAGE9_FROZEN_MANIFEST.md` uses bare `python` with no cwd | — | One platform/runbook note |
| DOC-9 | Low–Med | Phase C probes are not reproducible (kept in the scratchpad); Phase D's suite supersedes them, but no document says so | — | Note it |
| DOC-10 | Low | E0 report line 147 shortens hashes as `…a7d6` / `…4424`; the actual endings are `…e9a7d6a1` / `…60e44244` | **Verified (lead's error)** | Correct them in an addendum |
| DOC-11 | Low | `HELDOUT_THRESHOLD_FREEZE.md:22` cites `run_eval.py:269-270`; that code is now at lines 303-304. The freeze doc is frozen, so it cannot be edited | — | Note it in `STAGE9_FROZEN_MANIFEST.md` |
| DOC-12 | Low | Stale docstrings: `run_eval.py` "resumable"; `framework/__init__.py` command list; `framework/cli.py` names `check_run_request`; `safety.py` promises date-format checks | — | Fix at the next code change (`run_eval.py` and `safety.py` changes need a re-freeze) |
| DOC-13 | Low | Point-in-time reports lack "superseded" markers (Phase A "no manifest", "openpyxl not installed", out-of-date git-state sections, phase-naming drift) | — | Status index document |
| DOC-14 | Medium (hygiene) | `.DS_Store` staged; not in `.gitignore` | **Verified** | Owner unstages; add to `.gitignore` |
| DOC-15 | Low | Required environment variables per command are not explained | — | Runbook table |

## Reproducibility

| Activity | Reproducible from the docs? | Gaps |
|---|---|---|
| Manifest generate/verify | Mostly | cwd, interpreter, re-freeze move step |
| Individual tests | Yes | openpyxl install note; `run_tests.py` never run for Stage 9 (needs a scratch DB); its docs are Windows-only |
| Review tooling | Yes | Platform note |
| Probe suite | Command only in the docstring and the Phase D completion report | — |
| Phase C probes | **No** | Superseded by the Phase D suite (DOC-9) |

## Proposed release checklist

### A. Before merging the Stage 9 PR

- [ ] **Hygiene:** owner unstages `docs/remediation/.DS_Store` and `eval/.DS_Store`; add `.DS_Store` to `.gitignore` (DOC-14).
- [ ] **Runners:** fix the dev runners or document them as broken; correct the comments (DOC-1, ARCH-1).
- [ ] **Live-state tests:** decouple them from the unit tests, or document their expected failure during review (DOC-2, TEST-10, TEST-11).
- [ ] **Reviewer exposure:** owner decides S-2 and whether `technical_dataset_audit/`, `phase_d_decision_package/` and `phase_e1_multi_agent_audit/` merge now; extend the anti-anchoring lists (DOC-3).
- [ ] **Test runs:**
  - run the four Stage 9 test files and the probe suite under the documented env and record the counts;
  - run `run_tests.py` once in an environment with a scratch DB, or record why it was not run.
- [ ] **Manifest:** `verify-frozen-manifest` reports REPRODUCED on the exact merge commit (optionally also on a Windows checkout).
- [ ] **Docs:**
  - platform, env and re-freeze runbook notes (DOC-4, DOC-8, DOC-15);
  - PHASE4 "superseded" banner (DOC-5);
  - `MASTER_GAP_REGISTER` decision (DOC-6);
  - E0 addendum covering DOC-1 and DOC-10;
  - Phase D supersession note (DOC-7);
  - docstrings (DOC-12, deferred to the next re-freeze for frozen files).
- [ ] **Assets:** no manifest asset changed apart from the accepted `run_eval.py`.
- [ ] **PR description:** no held-out run, no approval file, no re-freeze; `run_eval.py` hash change accepted (E0.1); known limitations listed.

### B. Before any held-out run

- [ ] **Human review:**
  - independent reviewer named and confirmed;
  - all 113 rows decided;
  - `validate --kind heldout --baseline-git <pre-review rev>` reports COMPLETE with 0 errors;
  - sign-off complete;
  - workbook SHA recorded.
- [ ] **Owner decisions:** every item in `OWNER_DECISION_CHECKLIST.md` decided, plus the E1 additions (see the implementation plan).
- [ ] **Corrections:** approved corrections applied as one documented set:
  - `validate.py` reports VALID;
  - new hashes recorded in `HELDOUT_THRESHOLD_FREEZE.md` (rule 2);
  - thresholds recomputed if any case is excluded;
  - ledger and review package regenerated (DATA-7).
- [ ] **Acceptance scorer chosen (V-5).** If v2:
  - implemented and tested;
  - v2 probe expectations met;
  - v2 files included as frozen assets;
  - v1/v2 side-by-side reporting.
- [ ] **Runner hardening** (as approved): O_EXCL claim and run-once ledger; `all` refused; provider preflight and circuit breaker; run-header provenance; config bound (ARCH-3/4/5, SEC-2/3/4/5).
- [ ] **Re-freeze:** manifest regenerated through the documented re-freeze, owner-approved, REPRODUCED; hash-bearing docs updated.
- [ ] **Run plan approved:**
  - tiers and fresh output paths;
  - no `--limit` or `--fresh`;
  - interruption policy;
  - quota;
  - model attribution;
  - scratch DB only.
- [ ] **Approval file:** created by the owner, bound to the new `content_sha256`.
- [ ] **Authorization:** explicit written authorization (freeze rule 4). Run once per tier; preserve raw outputs, logs and hashes.
