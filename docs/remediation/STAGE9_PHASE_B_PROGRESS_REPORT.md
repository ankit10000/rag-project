# Stage 9 Phase B: progress report

**Date:** 2026-11-17. **Scope:** review-workflow preparation, a separate development review artifact, workbook tooling and source lookup. The project owner approved this work, including installing `openpyxl` as a development-only tool.

**Status: preparation is complete. The remaining work needs human judgment.** No held-out or development case has been reviewed. No reviewer decision, name, date or sign-off was entered. No review is claimed to have occurred.

## 1. Completed preparation work

| Workstream | Deliverable | Status |
|---|---|---|
| A: held-out readiness | `heldout_review/REVIEWER_CHECKLISTS.md`: onboarding (§1), anti-anchoring rules (§2), per-case completion (§3), sign-off (§4), progress-report procedure (§5), source lookup (§6) | Done |
| A | `heldout_review/HUMAN_REVIEW_GUIDE.md`: pointer to the checklists; the source-JSON key is named correctly (`span`; only the header says `gold_span`) | Updated |
| A | `HUMAN_REVIEW_GUIDE.md`, `REVIEW_PROGRESS_REPORT_TEMPLATE.md`, `STAGE9_PHASE_B_STRUCTURAL_INVENTORY.md` | From the earlier Phase B step |
| B: development artifact | `dev_review/dev_review_sheet.xlsx` and `dev_review/README.md` | Done (§2) |
| C: tooling | `eval/review/` (read-only validator, progress report, dev-artifact builder), `requirements-dev.txt`, `test_stage9_b_review_tools.py` | Done (§3) |
| D: evidence support | `eval/review/sources.py` + `cli locate` / `check-sources` | Done (§3) |

**The held-out workbook was not changed.** Its SHA-256 is `300dc43f…1467` before and after, and it is checked again by the tests.

## 2. Development review artifact

**Case IDs:**
- All 7 owner-named ids were verified against the current dataset: `B-comp-04`, `B-conf-02`, `B-conf-03`, `B-conf-04`, `D-conflicting-01`, `D-conflicting-03`, `D-conflicting-04`.
- Each exists and is `dev` under the split rule. None was missing; none was substituted.
- `B-comp-04` is `compound` with `expect_partial`; the other six are `conflicting` with `expect_conflict`.

**Workbook** (`dev_review_sheet.xlsx`, SHA-256 `6b94f343…2b09`):
- Same three-tab layout and the same 29 columns as the held-out workbook, plus column AD `review_focus` (the owner's question, verbatim, not an answer).
- Case definitions are copied from the dataset. The validator confirms 0 differences.
- The decision dropdown covers `Y2:Y8`. All reviewer fields are blank.
- The correction ledger is empty, and the sign-off rows are blank.

**Separation:**
- The workbook is not part of the held-out workbook, denominators, thresholds or sign-off; `dev_review/README.md` states this.
- The builder refuses non-dev or missing ids and never overwrites an existing workbook.

**Validator result:** `NOT_STARTED`; 7 pending; 0 errors; 13 source references, 0 lookup problems.

## 3. Workbook tooling and tests

**`openpyxl` install:**
- Before installing, I inspected `requirements.txt` (production pins) and `backend/requirements-api.txt`; neither was changed.
- A dry run showed only `openpyxl 3.1.5` and `et-xmlfile 2.0.0`. Those were installed into `.venv`, and `pip freeze` before/after differs by exactly those two lines; nothing was upgraded.
- They are recorded in the new `requirements-dev.txt`.

**`eval/review/` modules:**

| Module | Role |
|---|---|
| `workbook.py` | Reads a held-out or dev workbook: cases, ledger, sign-off, decision dropdown |
| `checks.py` | Validation (§ below) and counts. Status: `NOT_STARTED` / `IN_PROGRESS` / `NEEDS_RESOLUTION` / `COMPLETE` |
| `progress.py` | Markdown progress report, using the template's fields, computed from the file |
| `sources.py` | Mechanical lookup: PDF path, page validity, `source_pages.md` line, span on the PDF page (via PyMuPDF) and on the dataset page, other pages with the same text |
| `dev_artifact.py` | Builds the development workbook (new file only) |
| `cli.py` | `validate`, `progress`, `locate`, `check-sources`, `build-dev-review` |

**What the validator checks:**
- sheets and columns present;
- the decision dropdown exists and covers every case row;
- duplicate, missing and unexpected ids;
- the split column against the split rule;
- **columns A–R unchanged against the dataset** (data file, category, tier, question, history, facts, forbidden, sources, flags);
- decision values;
- a rationale for NEEDS REVISION / EXCLUDE;
- name and date (`YYYY-MM-DD` or a real date cell);
- name/date entered without a decision;
- attention flags addressed in a rationale;
- the ledger:
  - `change_no` sequence and unknown ids;
  - the split column;
  - historical entries unchanged against `--baseline-git`;
  - new entries marked `PROPOSED (not applied):`;
  - each proposal tied to a NEEDS REVISION / EXCLUDE case in the same workbook;
  - every NEEDS REVISION / EXCLUDE having a proposal;
- sign-off fields, where the placeholder prompt counts as blank.

**Write behaviour:**
- **No command edits a workbook.**
- Only `build-dev-review`, `progress --output` and `validate --json` write, and only **new** files: they refuse to overwrite.
- Since no command edits an existing workbook, no backup mechanism was needed. Any future editing feature would need an explicit command and a backup, as instructed.

**What the source lookup does not do:** it makes no judgement of support, recommends no decision, writes no rationale and marks nothing reviewed. Every output ends with that disclaimer. It prints no case text.

**Tests** were run individually, not through `run_tests.py`, which would fingerprint `rag_db`. Environment: `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1`.

| Command | Result |
|---|---|
| `.venv/bin/python test_stage9_b_review_tools.py` (new; registered as `unit` in `run_tests.py`) | **40/40 PASS** |
| `.venv/bin/python test_stage9_e0_runner_gate.py` | 108/108 PASS |
| `.venv/bin/python test_stage9_e0_frozen_manifest.py` | 25/25 PASS |
| `.venv/bin/python test_p4_eval_framework.py` | 22/22 PASS |

**What the new test covers:**
- Temporary workbook fixtures built from a fake three-case dataset: every validator rule above, including both acceptance and rejection paths.
- Generated PDFs for the source lookup: found, other pages listed, page out of range, missing PDF, span not on page, empty span, no decision fields in the output.
- The dev-artifact builder: correct ids, dev split only, blank fields, refuses overwrite, refuses missing ids.
- Read-only checks of both real workbooks: 0 errors, all pending, hashes unchanged.
- Fixture-only workbooks never appear in the repository.

**Other checks:**
- Mutation check: with the row checks disabled (in memory only), 5 checks fail as expected.
- `py_compile` OK on all new files.
- An AST scan found no unused imports, no function over 50 lines and no file over 300 lines.
- `ruff` is still not installed; the approval covered `openpyxl` only.

## 4. Reviewer status

| | Held-out (113) | Development (7) |
|---|---|---|
| Reviewer identified | **No** | **No** |
| Independence confirmed | No | No |
| Reviewed / pending | 0 / 113 | 0 / 7 |
| VALID / NEEDS REVISION / EXCLUDE | 0 / 0 / 0 | 0 / 0 / 0 |
| Attention items resolved | 0 of 2 (`A-conflict-03`, `D-conflicting-02`) | 0 of 7 (all rows carry a review focus) |
| Validator status / errors | `NOT_STARTED` / 0 (with `--baseline-git HEAD`) | `NOT_STARTED` / 0 |
| Source references / lookup problems | 139 / 0 | 13 / 0 |

All counts were computed by `python -m eval.review.cli validate`.

## 5. Outstanding human decisions

1. **Name the held-out reviewer** and confirm independence (`REVIEWER_CHECKLISTS.md` §1).
2. **Name the development reviewer** (the same or a different person) and confirm independence.
3. Whether reviewers may use AI assistance for evidence lookup. If yes, it is recorded per row.
4. Entering all review decisions and sign-offs: **reviewers only**.
5. After review: approve or reject the proposed correction sets. Any approved change to `data_A..D.py` or to the review workbook requires a documented re-freeze of the manifest.

## 6. Frozen manifest and protected files

- `verify-frozen-manifest` → **REPRODUCED**; `content_sha256` `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97` (unchanged).
- All new files are outside the manifest's asset list; no manifest input changed.
- The 34-file pre-E0 hash snapshot shows only the already-accepted `run_eval.py` change.
- **Unchanged:**
  - `HELDOUT_THRESHOLD_FREEZE.md`, the scorer, the dataset, the thresholds;
  - the E0 gate and approval mechanism;
  - the held-out workbook, both review CSVs, `source_pages.md`, the PDFs;
  - historical results.
- **Safety:**
  - no evaluation, no `run_eval.py` invocation, no LLM call;
  - no database connection;
  - no approval file.

## 7. Git state

- HEAD is `69e8b8ec6822959a72d40a18688442808540f3c8` on `audit/stage9-evaluation-readiness`.
- **Staging:** at the start of this step, the 17 earlier Stage 9 files were already **staged**; the index matched the working tree. That staging was done outside this session. I left it as found and staged nothing.
- **Files changed this session:**
  - `HUMAN_REVIEW_GUIDE.md` and `run_tests.py` now carry unstaged edits on top of their staged versions (`AM` / `MM`);
  - the new files are untracked.
- No commits or pushes.

```
A  docs/remediation/STAGE9_FROZEN_MANIFEST.md
A  docs/remediation/STAGE9_PHASE_A_EVALUATION_READINESS_AUDIT.md
A  docs/remediation/STAGE9_PHASE_B_STRUCTURAL_INVENTORY.md
A  docs/remediation/STAGE9_PHASE_E0_COMPLETION_REPORT.md
AM docs/remediation/heldout_review/HUMAN_REVIEW_GUIDE.md
A  docs/remediation/heldout_review/REVIEW_PROGRESS_REPORT_TEMPLATE.md
M  eval/framework/__init__.py
M  eval/framework/cli.py
A  eval/framework/frozen_manifest.py
A  eval/framework/hashing.py
M  eval/framework/integrity.py
M  eval/framework/safety.py
A  eval/phase35/frozen_manifest.json
M  eval/phase35/run_eval.py
MM run_tests.py
A  test_stage9_e0_frozen_manifest.py
A  test_stage9_e0_runner_gate.py
?? docs/remediation/STAGE9_PHASE_B_PROGRESS_REPORT.md
?? docs/remediation/dev_review/README.md
?? docs/remediation/dev_review/dev_review_sheet.xlsx
?? docs/remediation/heldout_review/REVIEWER_CHECKLISTS.md
?? eval/review/__init__.py
?? eval/review/checks.py
?? eval/review/cli.py
?? eval/review/dev_artifact.py
?? eval/review/progress.py
?? eval/review/sources.py
?? eval/review/workbook.py
?? requirements-dev.txt
?? test_stage9_b_review_tools.py
```

## 8. Limitations

- **Sign-off labels:** the validator finds sign-off fields by their `Sign-off - …` labels. A reviewer who renames a label would hide that field from the check.
- **Excel resaving:** the workbooks were never opened in Excel here. Resaving in Excel can restyle the file or reorder its XML; the content checks are unaffected, but the hash changes (expected).
- **Span lookup** uses the PyMuPDF text layer with whitespace and case collapsed. A span split by hyphenation or an unusual layout could be reported as "not found" even though it is visible in the PDF. All 152 current references were found.
- **Independence** cannot be verified by tooling; only the owner's confirmation and the reviewer's sign-off establish it.
- **`openpyxl`** is installed only in this Mac's `.venv`; other environments need `pip install -r requirements-dev.txt`.
- **Full-suite run:** `run_tests.py` was not run, because it opens a database connection.

**Stop:** the remaining Phase B work requires human judgment: naming the reviewers, the review decisions and the correction approvals.
