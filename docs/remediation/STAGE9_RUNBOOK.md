# Stage 9 runbook: platform, environment, commands and re-freeze

**Written:** 2026-11-17 (Stage 9 Phase E2, work package WP1). Documentation only.

This runbook authorizes nothing. A held-out run still needs the independent human review, every owner decision, a re-freeze if anything changed, a bound approval file and explicit written authorization (`HELDOUT_THRESHOLD_FREEZE.md` rule 4).

Each command below was checked against the argument parsers in `eval/framework/cli.py` and `eval/review/cli.py`. Commands marked **(run in E2)** were executed when this runbook was written; the results are recorded in `phase_e2_engineering/WP1_DOCUMENTATION_REPORT.md`.

## 1. Platform and interpreter

| | macOS (current working environment) | Windows (original project environment) |
|---|---|---|
| Interpreter | `.venv/bin/python` | `.venv\Scripts\python.exe` |
| Python version | **3.14.5** (`.venv/bin/python --version`, checked in E2) | 3.14.10 on Windows 11 (the version stated in `requirements.txt`; not re-checked in Stage 9) |
| Set an env var for one command | `VAR=value .venv/bin/python …` | PowerShell: `$env:VAR = "value"` before the command (it persists for the session) |

- **Working directory:** always the **repository root**. Every module is run with `-m eval.…` or a root-relative path, and the default paths in the CLIs are root-relative.
- **`-B`:** use it so that runs do not write `__pycache__` files into the tree.
- **Never use a bare `python`.** The commands in older documents (for example `STAGE9_FROZEN_MANIFEST.md` §Commands) mean the project interpreter above.
- **Development extra:** the review tooling needs `openpyxl`. Install it once with:
  - macOS: `.venv/bin/python -m pip install -r requirements-dev.txt`
  - Windows: `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`

  It pins `openpyxl==3.1.5` and `et-xmlfile==2.0.0`. The RAG application does not need them.

## 2. Environment variables per command

| Command group | Required | Why |
|---|---|---|
| Stage 9 test scripts (§5) | `DATABASE_URL` naming a database that matches `rag_*test*`, for example `postgresql://nobody@127.0.0.1:1/rag_test_scratch`; `TESTSAFE_BLOCK_NETWORK=1`; `HF_HUB_OFFLINE=1` | Each test calls `testsafe.require_scratch_db()`, which reads `DATABASE_URL` **from the process environment only** (never `.env`) and refuses names that do not match `rag_[a-z0-9_]*test[a-z0-9_]*`, plus `rag_db`, `postgres` and `template*`. Port 1 is deliberately unreachable, so no connection can succeed. `TESTSAFE_BLOCK_NETWORK=1` blocks sockets; `HF_HUB_OFFLINE=1` stops model downloads |
| Manifest generate/verify (§3) | none; the test env above is harmless and recommended | Reads files only |
| Review tooling (§4) | none; the test env above is recommended | Reads workbooks and the dataset; no DB, no network |
| Probe suite (§5) | `DATABASE_URL` as for tests, `HF_HUB_OFFLINE=1` | As given in the suite's docstring |
| `run_tests.py` | **Not for Stage 9 checks.** It builds a scratch URL from `.env` and fingerprints the application DB, so it opens a DB connection | Run it only in an environment with a real scratch DB and the owner's agreement |
| `eval/phase35/run_eval.py` | **Do not run** without explicit authorization. Even `--split dev` connects to the scratch DB and calls the live provider | — |

macOS one-liner used below:
```bash
export DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1
```
Windows (PowerShell):
```powershell
$env:DATABASE_URL = "postgresql://nobody@127.0.0.1:1/rag_test_scratch"; $env:TESTSAFE_BLOCK_NETWORK = "1"; $env:HF_HUB_OFFLINE = "1"
```

## 3. Frozen manifest

```bash
# verify (read-only): rebuilds the content from the working tree and compares   (run in E2: REPRODUCED, exit 0)
.venv/bin/python -B -m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json

# generate: writes a NEW file only (mode "x"); refuses if --output exists. Part of a re-freeze (§6) only
.venv/bin/python -B -m eval.framework.cli frozen-manifest --dataset-version phase35-corrected-2026-11-12 --output eval/phase35/frozen_manifest.json

# dataset validator (read-only; prints VALID or "<n> ERRORS")                      (run in E2: VALID)
.venv/bin/python -B eval/phase35/validate.py
```

- `verify-frozen-manifest` prints `MISMATCH: …` lines and `<n> problem(s)` with exit 1 on any difference.
- `frozen-manifest` exits 1 if the dataset is invalid; the file is still written in that case.
- Current `content_sha256`: `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.

## 4. Review tooling (`eval/review/cli.py`)

`--kind` is `heldout` or `dev`. `--workbook` overrides the default workbook path.

```bash
.venv/bin/python -B -m eval.review.cli validate      --kind heldout [--baseline-git REV] [--json NEW.json] [--all]
.venv/bin/python -B -m eval.review.cli progress      --kind heldout [--baseline-git REV] [--output NEW.md]   # (run in E2: NOT_STARTED)
.venv/bin/python -B -m eval.review.cli locate        --kind heldout --case <CASE_ID>
.venv/bin/python -B -m eval.review.cli check-sources --kind heldout
.venv/bin/python -B -m eval.review.cli build-dev-review --output <NEW PATH>
```

- No command edits a workbook. `--json`, `--output` and `build-dev-review` create **new** files only.
- `build-dev-review` defaults to `docs/remediation/dev_review/dev_review_sheet.xlsx` and refuses if that file exists.
- `--baseline-git REV` reads the committed workbook with `git show REV:<path>`; it works only once the workbook is committed.
- `validate` exits 1 if there are errors. `check-sources` exits 1 if there are lookup problems.
- The reviewer-facing procedure is in `heldout_review/HUMAN_REVIEW_GUIDE.md` and `REVIEWER_CHECKLISTS.md`, and in `dev_review/README.md`.

## 5. Tests and probe suite

Run each file individually with the env from §2:
```bash
.venv/bin/python -B test_stage9_e0_runner_gate.py
.venv/bin/python -B test_stage9_e0_frozen_manifest.py      # (run in E2: 0 check(s) failed)
.venv/bin/python -B test_stage9_b_review_tools.py
.venv/bin/python -B test_p4_eval_framework.py
```

**Live-state checks (DOC-2):** some checks in these files assert the *current* repository state, not code behaviour:
- `test_stage9_b_review_tools.py` (about lines 251-258) expects both real workbooks to have 0 reviewed rows;
- `test_stage9_e0_frozen_manifest.py` and `test_stage9_e0_runner_gate.py` expect the real manifest to verify.

Once the human review starts, or a correction is applied, these checks **fail by design**. **Do not regenerate the manifest to make them pass.** A re-freeze is never a test fix. Phase E2 WP3 is separating these checks from the unit tests.

**Probe suite:**
- **Current (Phase E2 WP3):** the 110-probe harness `eval/probes/` and its registered test (lead-verified 2026-11-17: 110 probes, 0 failures; test 134/0):
  ```bash
  DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 \
    .venv/bin/python -B -m eval.probes.scorer_regression --validate-proposals
  DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 \
    .venv/bin/python -B test_stage9_scorer_probes.py
  ```
- **Historical (Phase D):** kept unchanged as a record. It still runs (72 probes, 0 failures):
  ```bash
  DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch HF_HUB_OFFLINE=1 \
    .venv/bin/python -B docs/remediation/phase_d_decision_package/scorer_regression_probes.py [--validate-proposals]
  ```
- **Live-state readiness** (not a test; fails by design once the manifest or workbooks change): `.venv/bin/python -B check_stage9_readiness.py` (same environment).
- **v2 expectations:** the harness's `expected_v2` values are design intent and are not executed until v2 exists. Where they differ from `phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md` Appendix B (P-TS1-06, P-TS1-08, P-TS4-10, P-E2-STAT-06), the specification governs; aligning them is the first WP6 step.

## 6. Re-freeze procedure

A re-freeze is needed whenever **any** manifest asset changes. The assets are listed in `eval/framework/frozen_manifest.py:FROZEN_ASSETS`, plus every PDF in `heldout_review/source_pdfs/`. Examples: an approved dataset correction, a scorer or runner change, or the completed human-review workbook.

**Preconditions:**
- **Written owner approval** of the exact change set;
- for dataset changes, the independent human review is complete (freeze rule 2: corrections come from the reviewer);
- no held-out result has been seen (freeze rule 1).

Steps, **in this order**. Each step depends on the one before.

1. **Apply the approved change** to the assets, for example `eval/phase35/data_*.py`, as one documented change set listing every affected case and its reason (freeze rule 2).
2. **Validate:** `.venv/bin/python -B eval/phase35/validate.py` must print `VALID`.
3. **Record the new dataset hashes in `HELDOUT_THRESHOLD_FREEZE.md`** (rule 2: "frozen again by recording new SHA-256 hashes of `data_A..D.py`").
   - This edits a frozen document. Only the owner authorizes it, as part of the approved change set.
   - Record the **portable** hashes (CRLF → LF). Get them from `.venv/bin/python -B -m eval.framework.cli manifest --dataset-version <v> --output <NEW tmp path>` (field `file_sha256`), or with `shasum -a 256` on an LF checkout.
   - Fix the stale line reference at the same time: `run_eval.py:269-270` is now `303-304` (see `STAGE9_FROZEN_MANIFEST.md`).
   - **Edit this document before generating the manifest:** it is itself a manifest asset (group `thresholds`), so any later edit would invalidate the new manifest.
4. **Exclusions or count changes:** if a case is excluded, the eligible-case counts change.
   - Recompute the minimums with the same frozen percentages (85% / 65%, rounded up) and record them in the freeze document (rule 2).
   - **Change the code too:** `eval/framework/safety.py:FROZEN_THRESHOLDS` hard-codes `113`/`97` and `106`/`69`. The manifest copies these into `content.thresholds`, and `cli report` checks row counts against them.
   - Changing `safety.py` is a code change that needs its own approval and tests.
5. **Regenerate the review package if held-out cases changed** (DATA-7):
   - the workbook and CSV columns copy the case definitions, so they go stale;
   - the repository has **no builder for the held-out workbook or CSV**. Any regeneration must preserve the reviewer's recorded decisions and needs an owner-approved method.
   - Dev cases changed: regenerate the dev workbook with `build-dev-review` (move the old one aside first; the builder refuses to overwrite).
   - If the dataset version label changes, note that `eval/review/cli.py:DATASET_VERSION` hard-codes `phase35-corrected-2026-11-12`.
6. **Move the old manifest aside.** `frozen-manifest` refuses to overwrite (mode `x`), and there is no `supersede` command (ARCH-12).
   - Move `eval/phase35/frozen_manifest.json` to a non-asset path the owner chooses, for example `eval/phase35/frozen_manifest.superseded-1b73a208.json`. Files in `eval/phase35/` are not manifest assets unless listed in `FROZEN_ASSETS`.
   - Record the old `content_sha256` in the re-freeze report; the manifest has no lineage field.
7. **Generate:**
   ```bash
   .venv/bin/python -B -m eval.framework.cli frozen-manifest --dataset-version <label> --output eval/phase35/frozen_manifest.json
   ```
   It must print `valid=True` and the new `content_sha256`.
8. **Verify:** `verify-frozen-manifest` must print `frozen manifest REPRODUCED`. Re-run the §5 tests.
9. **Update the documents that quote the manifest hash.** Find them with `grep -rl 1b73a208 docs eval`. At this writing, they are:
   - **current guidance (update):**
     - `heldout_review/HUMAN_REVIEW_GUIDE.md`;
     - `heldout_review/REVIEW_PROGRESS_REPORT_TEMPLATE.md`;
     - `dev_review/README.md`;
     - `STAGE9_FROZEN_MANIFEST.md`;
     - this runbook;
     - `PHASE4_EVALUATION_FRAMEWORK.md` (banner);
   - **binary:** `dev_review/dev_review_sheet.xlsx` embeds the manifest hash and the `data_*` hashes; regenerate it (step 5). The held-out workbook embeds the `data_*` hashes (`Read Me & Sign-off` rows 14-17);
   - **point-in-time records (do not rewrite; their hash is historical):**
     - `STAGE9_PHASE_B_PROGRESS_REPORT.md`;
     - `STAGE9_PHASE_B_STRUCTURAL_INVENTORY.md`;
     - `STAGE9_PHASE_E0_COMPLETION_REPORT.md`;
     - `technical_dataset_audit/STAGE9_PHASE_C_TECHNICAL_AUDIT_REPORT.md`;
     - `phase_d_decision_package/STAGE9_PHASE_D_DECISION_REPORT.md`;
     - `phase_d_decision_package/PHASE_D_COMPLETION_REPORT.md`;
     - `phase_e1_multi_agent_audit/ARCHITECTURE_AUDIT.md`;
     - `phase_e1_multi_agent_audit/RELEASE_READINESS_AUDIT.md`.
   - **Workbook hash:** the workbook SHA-256 `300dc43f…` appears in `heldout_review/REVIEWER_CHECKLISTS.md` §1 and several point-in-time reports. Update the checklist if the workbook is regenerated.
10. **Bind a new approval.** Any approval file must carry the **new** `content_sha256` in `frozen_manifest_sha256` (`safety.py` docstring). An approval bound to the old hash is refused.
11. **Write a re-freeze report** listing:
    - the approval;
    - the change set;
    - old and new `content_sha256`;
    - the validator output;
    - the verify output;
    - the test counts.

## 7. Related documents

- `STAGE9_STATUS_INDEX.md`: every Stage 9 document and whether it is current, point-in-time or superseded.
- `STAGE9_FROZEN_MANIFEST.md`: manifest format and normalization.
- `STAGE9_PHASE_E0_COMPLETION_REPORT.md`: the gate, and its Phase E2 addendum (dev-runner regression, corrected hashes).
- `HELDOUT_THRESHOLD_FREEZE.md`: thresholds and freeze rules (frozen asset).
