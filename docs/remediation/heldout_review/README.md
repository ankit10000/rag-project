# Final independent human review package — CURRENT DATASET

Prepared 2026-11-12 for an independent human review. The workbook was generated from the current corrected `eval/phase35/data_A.py` through `data_D.py` dataset.

**No human review or sign-off has occurred.** The prior Claude review was AI-assisted and is **not independent human sign-off**. All reviewer fields in the new workbook are blank.

## Package contents

| File | Purpose |
|---|---|
| `heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx` | New review workbook. `Held-out Cases` contains exactly 113 current held-out cases; `Correction Ledger` lists all 26 correction entries; `Read Me & Sign-off` contains instructions, hashes, thresholds, and blank sign-off fields. |
| `source_pdfs/` | Twelve source PDFs for direct page-level human review. |
| `source_pages.md` | Verbatim page text corresponding to the dataset source documents; useful for searching exact evidence and checking spans. |
| `heldout_review_sheet.csv` | Original empty review sheet, preserved unchanged. It contains the old expectations and is not the current review copy. |
| `heldout_review_sheet_REVIEWED_by_Claude.csv` | Existing AI-assisted technical review, preserved unchanged. It is not independent human sign-off. |
| `REVIEW_SIGNOFF_REPORT.md` | Prior AI-assisted review record; not a human sign-off. |

## Current dataset and eligibility

- 12 documents, 56 pages, 160 total cases.
- Split rule: `sha1(case_id) % 10 < 3` → dev; otherwise held-out.
- 47 dev cases; 113 held-out cases.
- Tier 1 held-out eligibility: **113**.
- Tier 2 held-out eligibility (`tier == "both"`): **106**.
- Seven held-out cases are `answer_only`; they are Tier 1 only and excluded from Tier 2 eligibility.

Current held-out category counts: direct_factual 19, no_answer 16, compound 16, follow_up 14, multi_chunk 12, multi_page 12, prompt_injection 10, conflicting 7, irrelevant_retrieval 4, missing_metadata 3. Cases by data file: A 30, B 26, C 31, D 26.

## How to review the workbook

1. Start on `Read Me & Sign-off`; note the data hashes and frozen thresholds.
2. Review all 113 rows on `Held-out Cases`. Check the question and history, current category, expected facts and alternatives, forbidden strings, conflict/abstain/partial expectations, and each source document/page/span against `source_pdfs/` and `source_pages.md`.
3. `expected_facts_json` is a list of groups: every group is required, while one alternative within a group is sufficient. `expected_sources_json` gives document, page, and source span. For the seven `answer_only` cases, `tier1_chunks_json` contains the supplied Tier 1 chunks.
4. The rows for A-conflict-03 and D-conflicting-02 are flagged for special attention. Their dataset definitions have not been changed.
5. Corrected held-out rows include their previous category/facts/forbidden/conflict values where applicable. Use `Correction Ledger` for the complete change history.
6. Choose `VALID`, `NEEDS REVISION`, or `EXCLUDE` in the decision dropdown. Give a rationale for every `NEEDS REVISION` or `EXCLUDE`. Enter reviewer name and date for each row. Do not fill these fields on behalf of the reviewer.
7. Complete the sign-off section only after the independent review is finished. State the reviewer’s independence from the dataset author and its AI-assisted preparation.

The ledger contains **26 correction entries**: 24 earlier field edits across 22 cases plus two subsequent case corrections. Those entries cover 24 distinct case IDs. A-conflict-02 is one of the two later corrections but belongs to the **dev** split, so it appears in the ledger and not among the 113 held-out review rows.

## A-conflict-02 development-results note

A-conflict-02’s expected answer was corrected to the current $165 first-breach fine. Existing development evaluation results are historical results from the earlier dataset and **must not be represented as scores obtained from the current corrected dataset**. No corrected-dataset dev result is asserted in this package.

## Thresholds and evaluation safety

The approved held-out thresholds remain frozen:

- Tier 1: **97/113** minimum passing cases (85%).
- Tier 2: **69/106** minimum passing cases (65%).

No held-out results exist or were created for this package. No held-out evaluation, Gemini/API call, or database access was performed while preparing it. The new review is a prerequisite for any later separately approved held-out evaluation.

## Current corrected dataset hashes (SHA-256)

These hashes describe the current dataset and match both `../HELDOUT_DATASET_CORRECTIONS.md` and `../HELDOUT_THRESHOLD_FREEZE.md`.

| File | SHA-256 |
|---|---|
| `eval/phase35/data_A.py` | `c204fd037d653a27dfed00f7d9b9ad0b38dea4d20f578145aa7bc9b15201714c` |
| `eval/phase35/data_B.py` | `f58fc8041bed81682e0bc22be6123364f963b170db5a409204b60922aa5a3548` |
| `eval/phase35/data_C.py` | `6fc3ca44254f4dc536b2bde59d355134ccdee284ff359c4a6f3ebe7deb6cfea6` |
| `eval/phase35/data_D.py` | `6341a55f5307cf9cc47fbf1608e7dc26e3041793f6e0184528f1a3b9249d8f64` |

## Reviewer sign-off

| Item | Reviewer completion |
|---|---|
| Reviewer name | |
| Independence from dataset author and AI-assisted preparation confirmed | |
| Cases reviewed (of 113) | |
| VALID / NEEDS REVISION / EXCLUDE counts | |
| Date completed | |
| Signature | |
