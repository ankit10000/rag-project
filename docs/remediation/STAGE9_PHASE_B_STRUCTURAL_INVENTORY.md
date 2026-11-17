# Stage 9 Phase B: review package structural inventory

**Date:** 2026-11-17. **Scope:** structural inspection and reviewer-guide preparation only.
**Status:** **human review is awaiting assignment of an independent reviewer.** No reviewer has been identified, and no review has started.

**Content protection:**
- No held-out question, history, expected fact, forbidden string, span or AI-review decision was read or displayed for this report.
- Consistency and span checks were computed by a read-only script that printed only counts and case ids.
- The per-case sections of `REVIEW_SIGNOFF_REPORT.md` (lines 42–84) were not read.

## 1. Baseline (Step A)

| Check | Result |
|---|---|
| Branch / HEAD | `audit/stage9-evaluation-readiness` / `69e8b8ec6822959a72d40a18688442808540f3c8` (= `main` = `origin/main`) |
| Phase E0/E0.1 changes | Present (6 modified, 8 untracked files, as reported at E0.1) |
| Staged changes | none |
| Frozen manifest | `eval/phase35/frozen_manifest.json`, `content_sha256` `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`; `verify-frozen-manifest` → **REPRODUCED** |
| `HELDOUT_THRESHOLD_FREEZE.md` | Identical to HEAD (SHA-256 `3e4bd5d7…be66`) |

## 2. Workbook (`heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx`)

The workbook was read with a stdlib-only XML reader. `openpyxl` is not installed, and installing it was not authorized. The workbook SHA-256 is `300dc43f…1467`, as recorded in the frozen manifest and in `FINAL_HUMAN_REVIEW_PREPARATION_REPORT.md`.

| Tab | Rows | Structure |
|---|---|---|
| `Read Me & Sign-off` | 24 | Instructions; dataset hashes (rows 14–17, **equal** to the current `data_A..D.py` hashes); sign-off rows 19–24. Rows 19 and 21–24 are blank; row 20 holds only the prompt "To be completed by the independent human reviewer:" |
| `Held-out Cases` | 1 header + **113** | 29 columns: `case_id` … `correction_summary` (A–X, definition and context); `reviewer_decision` (Y), `reviewer_rationale` (Z), `reviewer_name` (AA), `review_date` (AB), `reviewer_attention` (AC) |
| `Correction Ledger` | 1 header + **26** | `change_no`, `case_id`, `split`, `data_file`, `changed_field`, `previous_value_json_or_text`, `current_value_json_or_text`, `source_or_rationale` |

### Held-out case rows

| Check | Result |
|---|---|
| Case rows / unique ids | 113 / 113; no duplicates |
| vs. dataset held-out set (`split_of`) | **exact match**: none missing, none extra |
| `split` column | `heldout` on all 113; agrees with the split rule |
| Per data file | A 30, B 26, C 31, D 26 (as the README states) |
| Tier eligibility | Tier 1: Yes 113. Tier 2: Yes 106, "No - answer_only" 7. `tier`: both 106, answer_only 7 |
| Workbook vs. current dataset | **0 mismatches** in category, question, history, fact groups, forbidden strings, the three expect flags, tier and sources (document, page, span) |
| Decision dropdown | List validation `"VALID,NEEDS REVISION,EXCLUDE"` on `Y2:Y114` (exactly the 113 rows) |
| Reviewer fields filled | decision **0**, rationale **0**, name **0**, date **0** (of 113) |
| Attention flags | `A-conflict-03`, `D-conflicting-02` (both preserved) |
| `correction_status` | `Corrected` 23, blank 90 |

### Source references

| Check | Result |
|---|---|
| References | 139 (document, page, span) |
| Document exists as a PDF and in the dataset | 139 / 139 |
| Page within the document's range | 139 / 139 |
| Span present on that page in `source_pages.md` (whitespace-normalized, case-insensitive) | 139 / 139 |
| Span present on that page in the dataset page text | 139 / 139 |
| Source PDFs | 12; names equal the 12 dataset documents |
| `source_pages.md` page blocks | 56 = dataset pages |

Span matching was done against the text, not by rendering the PDFs. The preparation report states that the spans were also matched against the PDF page text. The human reviewer checks the PDFs directly.

### Correction ledger

| Check | Result |
|---|---|
| Entries / distinct case ids | 26 / 24 |
| Unknown case ids | none |
| `split` column vs. split rule | all agree |
| Ids by split | held-out 23, dev 1 (`A-conflict-02`, by design; not in the held-out tab) |
| Held-out ledger ids present in the workbook | all |
| Rows marked `Corrected` vs. held-out ledger ids | identical sets (23) |
| `change_no` | 1–26, sequential |
| Changed fields | gold_facts 13, forbidden 9, category 1, expect_conflict 1, combined case corrections 2 |

## 3. Package documents

| File | Status |
|---|---|
| `heldout_review/README.md` | Current. Describes the workbook, 113 / 106 / 7 eligibility and the frozen thresholds; blank sign-off |
| `FINAL_HUMAN_REVIEW_PREPARATION_REPORT.md` | States that the package was prepared with no human review or sign-off |
| `heldout_review/REVIEW_SIGNOFF_REPORT.md` | AI-assisted review (88 / 25 / 0), **explicitly not independent** |
| `HELDOUT_DATASET_CORRECTIONS.md` | Canonical record of the 26 applied corrections |
| `eval/phase35/validate.py` | Dataset is **valid** (the manifest build runs `validate.validate` plus the extra checks: `valid=true`, 0 errors, 0 warnings) |

**One factual inaccuracy found in the package** (not corrected; the file is frozen):
- `REVIEW_SIGNOFF_REPORT.md` describes the scorer as "case- and whitespace-insensitive substring matching".
- `eval/answer_scoring.py` (`fact_recall`, `forbidden_hits`) is case-insensitive but does **not** normalize whitespace.
- `HUMAN_REVIEW_GUIDE.md` §2 states the actual behaviour.

## 4. Deliverables in this phase

| Deliverable | Status |
|---|---|
| `heldout_review/HUMAN_REVIEW_GUIDE.md` | **Created**: process, the ten criteria, decision definitions, attention cases, correction-ledger convention (`PROPOSED (not applied):`, rows 27+), sign-off |
| Structural inventory | **This document** |
| `heldout_review/REVIEW_PROGRESS_REPORT_TEMPLATE.md` | **Created**: all outcome fields blank |
| Validation report | Not started: requires a completed human review |
| Correction proposal | Not started: requires a completed human review |
| Re-freeze report | Not started: requires approved, applied corrections |

**Current progress (computed from the workbook, 2026-11-17):** 113 held-out cases; 0 reviewed, 113 pending; 0 attention cases resolved; reviewer not identified.

**Manifest impact:**
- The new files are outside the manifest's asset list (`frozen_manifest.FROZEN_ASSETS` + `source_pdfs/*.pdf`), and no manifest input was changed. The manifest still reports **REPRODUCED**.
- Once the reviewer saves the workbook, the manifest will report a mismatch. That is expected and is resolved only by the documented re-freeze.

## 5. Safety

- **No modifications** to the workbook, either review CSV, the review README/sign-off report, `source_pages.md`, the PDFs, `data_A..D.py`, `validate.py`, the scorer, the thresholds, the E0 gate or the manifest.
- **No evaluation activity:** no held-out or `all` run, no `run_eval.py` invocation, no LLM call.
- **No database:** no connection opened.
- **No approval file** created.
- **No git changes:** nothing staged, committed or pushed.

## 6. Decisions required from the project owner

1. **Identify the independent reviewer**, and confirm their independence from the dataset authoring and its AI-assisted preparation (guide §1).
2. Whether a **development** review is wanted for `B-comp-04` and the six dev conflict cases. If yes, it needs a separate artefact and separate approval.
3. Optional: installing `openpyxl` (a dev-only dependency) would make the post-review validation easier. The stdlib reader used here is sufficient for the checks.
