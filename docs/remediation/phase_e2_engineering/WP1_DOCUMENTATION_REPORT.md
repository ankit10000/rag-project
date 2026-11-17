# Phase E2 WP1: documentation and reviewer protection, report

**Date:** 2026-11-17. **Scope:** documentation only. Addresses DOC-1, DOC-3, DOC-4, DOC-5, DOC-7, DOC-8, DOC-9 (note), DOC-10, DOC-11, DOC-13 and DOC-15 (`phase_e1_multi_agent_audit/RELEASE_READINESS_AUDIT.md`) and the documentation part of ARCH-1.

**Not done in WP1:**
- no code change;
- no frozen-manifest asset edited;
- no database, LLM or network access, and `.env` was not read;
- `run_eval.py` and `run_tests.py` were not run;
- no git add, commit, stash, reset, checkout or restore. Edited files that were staged now show as `AM`.

## 1. Files changed

| File | Change |
|---|---|
| `docs/remediation/heldout_review/HUMAN_REVIEW_GUIDE.md` | §1 "To avoid anchoring": added a bullet listing the Stage 9 analysis material not to open before recording decisions (`../STAGE9_*.md`, `../technical_dataset_audit/`, `../phase_d_decision_package/`, `../phase_e1_multi_agent_audit/`, `../phase_e2_engineering/`), plus a pointer to `REVIEWER_CHECKLISTS.md` §2. Nothing else changed (DOC-3) |
| `docs/remediation/heldout_review/REVIEWER_CHECKLISTS.md` | §2 item 1: the four analysis folders were added to the "Do not open" list, each with its phase (DOC-3) |
| `docs/remediation/dev_review/README.md` | The anti-anchoring paragraph now also lists `../STAGE9_*.md` and the four folders, naming `DEV_CORRECTION_PROPOSALS.csv`; it points to the held-out exclusions (DOC-3) |
| `docs/remediation/STAGE9_PHASE_E0_COMPLETION_REPORT.md` | **Appended** "Addendum (Phase E2)": A1 dev-runner regression (ARCH-1/SEC-1/DOC-1; repair by WP2, pointer to `WP2_RUNNER_REPAIR_REPORT.md`); A2 full `dataset_sha256` / `split_sha256` (DOC-10); A3 git state is point-in-time; A4 pointers. Sections 1–11 untouched |
| `docs/remediation/STAGE9_FROZEN_MANIFEST.md` | **Appended** "Notes added in Phase E2": interpreter and cwd for the commands (DOC-8); `HELDOUT_THRESHOLD_FREEZE.md:22` line drift `269-270` → `303-304` (DOC-11); pointer to the re-freeze procedure (DOC-4) |
| `docs/remediation/PHASE4_EVALUATION_FRAMEWORK.md` | "Superseded in part" banner inserted after the title: a table of the 9 stale statements (original lines 12, 13, 38, 55, 140, 143, 164, 168, 169) with the current state, plus pointers to Stage 9 documents. No content deleted (DOC-5) |
| `docs/remediation/STAGE9_RUNBOOK.md` (new) | Platform and interpreter (macOS/Windows), cwd, `-B`, `requirements-dev.txt`; per-command env-var table; manifest, validator, review-tool, test and probe commands; live-state test warning (DOC-2); 11-step re-freeze procedure with the hash-bearing document list (DOC-4/8/15) |
| `docs/remediation/STAGE9_STATUS_INDEX.md` (new) | Status of every Stage 9 document (current / point-in-time / superseded-by / frozen), including the frozen and pre-Stage 9 references. Supersession notes: Phase C → D (TA-06/07/08 drift table, DOC-7), Phase D CSVs → WP4, `SCORER_V2_DESIGN.md` → WP5 spec, probes C → D → WP3 (DOC-9), dev runners → WP2 (DOC-13) |
| `docs/remediation/phase_e2_engineering/WP1_DOCUMENTATION_REPORT.md` (new) | This report |

## 2. Facts verified, and how

| Fact | Command / source | Result |
|---|---|---|
| Guide and checklists are not frozen assets; `heldout_review/README.md` and `REVIEW_SIGNOFF_REPORT.md` are | `eval/framework/frozen_manifest.py:FROZEN_ASSETS` | Confirmed |
| Full dataset hashes | `eval/phase35/frozen_manifest.json` `content.dataset` | `dataset_sha256` `5c58796a…e9a7d6a1`, `split_sha256` `a185fa1c…60e44244` (full values in the E0 addendum) |
| Manifest reproduces | `.venv/bin/python -B -m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json` (test env) | `frozen manifest REPRODUCED`, exit 0 |
| Dataset valid | `.venv/bin/python -B eval/phase35/validate.py` | `VALID` |
| Manifest test | `.venv/bin/python -B test_stage9_e0_frozen_manifest.py` (test env) | `0 check(s) failed` |
| Review CLI works with the documented interpreter | `… -m eval.review.cli --help`; `… progress --kind heldout` | Subcommands as documented; status NOT_STARTED; workbook `300dc43f…`, manifest `1b73a208…` |
| Line drift | `grep -n 'args.tier == "2"' eval/phase35/run_eval.py` vs `git show HEAD:eval/phase35/run_eval.py` | HEAD 269-270 → now 303-304, same code |
| Runner side effect moved | `run_eval.py:47` (`… = None`), `:259-269` `bootstrap_execution()` | Confirmed |
| Runner comments relying on the side effect | `grep -n run_eval eval/stage6_live_dev_eval.py eval/stage8_p3_live_dev_eval.py eval/h1_relevance_gate.py` | stage6 `:28`, stage8 `:19`, h1 `:28`; read at HEAD-era content (WP2 was editing them in parallel) |
| PHASE4 stale lines | `sed -n` on each line cited by DOC-5 | All nine confirmed stale |
| Python version | `.venv/bin/python --version` | 3.14.5; `requirements.txt` states 3.14.10 on Windows 11 |
| testsafe rule | `testsafe.py` `SCRATCH_PATTERN` = `rag_[a-z0-9_]*test[a-z0-9_]*`; env only, never `.env` | Confirmed |
| CLI behaviour | `eval/framework/cli.py` (`_write_new` mode `x`; verify exit codes); `eval/review/cli.py` (arguments, `build-dev-review` default and refusal) | Runbook commands match the parsers |
| Threshold hard-coding | `eval/framework/safety.py:31-36` `FROZEN_THRESHOLDS` | 113/97, 106/69 |
| Hash-bearing documents | `grep -rl 1b73a208 docs eval`; `unzip -p <xlsx> \| grep -c 1b73a208` | The list in runbook §6 step 9; the dev workbook embeds the manifest hash, the held-out workbook does not (both embed `data_*` hashes) |
| No held-out workbook builder | `grep -rn "CURRENT_HUMAN_REVIEW\|heldout_review_sheet.csv" --include=*.py` | Only the manifest asset list, the review CLI path and a test reference it |
| Phase C vs Phase D TA-06/07/08 | `technical_dataset_audit/ISSUE_REGISTER.md:72-95` vs `phase_d_decision_package/HELDOUT_CORRECTION_PROPOSALS.csv` and the Phase D report `:57-59` | Differences tabulated in the status index |

Test env used throughout: `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1`.

## 3. Deliberately not done

- **`MASTER_GAP_REGISTER.md` (DOC-6):** not edited. P35-01/02/04 still read NOT STARTED. Whether to update the register or mark it frozen-as-historical is an owner decision. The status index records the gap.
- **Code docstrings (DOC-12):**
  - deferred to WP7 / the next re-freeze. `run_eval.py` is a frozen asset, and `safety.py` changes belong with the gate hardening;
  - `framework/__init__.py` and `framework/cli.py` are not frozen, but WP1 is documentation-only.
- **Frozen review files:** `heldout_review/README.md`, `REVIEW_SIGNOFF_REPORT.md`, `source_pages.md`, the CSVs, the xlsx files and `source_pdfs/` are untouched. The frozen `heldout_review/README.md` has no anti-anchoring list; it only describes `heldout_review_sheet_REVIEWED_by_Claude.csv` as an AI review (line 15). The extended list lives in the guide and the checklists. After the WP1 edits, `verify-frozen-manifest` still reports `REPRODUCED`.
- **`HELDOUT_THRESHOLD_FREEZE.md:22`:** not corrected (frozen); documented in `STAGE9_FROZEN_MANIFEST.md` and in runbook step 3.
- **DOC-14 (`.DS_Store`):** owner action (unstage, `.gitignore`); not in WP1's file list.
- **DOC-2 decoupling:** WP3. The runbook only warns not to re-freeze to make tests pass.
- **Point-in-time reports** that quote `1b73a208…` were not rewritten.

## 4. Uncertainties

- **Parallel work:** WP2, WP3, WP4 and WP5 were in progress. When this was written:
  - `phase_e2_engineering/wp4/` and `wp5/` were empty;
  - `WP2_RUNNER_REPAIR_REPORT.md` did not exist yet;
  - `eval/probes/` held only `__init__.py`.

  The status index and the runbook refer to these deliverables by the paths the lead gave. Re-check those paths when the work packages finish.
- **Windows commands:** derived from the existing Windows docstrings (`run_tests.py`, `validate.py`); not executed, because no Windows machine was available.
- **Re-freeze steps 4–5:** describe needs (a code change for exclusions; an approved held-out package regeneration method) that have no existing tooling. They are procedure, not verified commands.
- **`.env`:** not read, as in E1, so whether the broken runners would point at a scratch DB by accident is unknown. The addendum says so.
