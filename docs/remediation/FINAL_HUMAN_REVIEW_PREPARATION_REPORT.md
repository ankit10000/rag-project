# Final Human Review Package Preparation Report

Date: 2026-11-12. Status: package prepared; independent human review and sign-off remain outstanding.

## Package prepared

Created `docs/remediation/heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx` with three tabs:

- **Read Me & Sign-off** — current dataset scope, review instructions, hashes, frozen thresholds, historical dev-results caveat, and blank sign-off fields.
- **Held-out Cases** — exactly 113 current held-out cases and all requested question, history, category, current expected facts/alternatives, forbidden strings, source/page/span evidence, abstain/partial/conflict expectations, tier eligibility, author context, previous values for corrected cases, reviewer attention flags, and blank reviewer decision/rationale/name/date fields. Decisions have a `VALID` / `NEEDS REVISION` / `EXCLUDE` dropdown.
- **Correction Ledger** — 26 correction entries: the 24 earlier field edits across 22 cases plus the two subsequent case corrections. These entries cover 24 distinct case IDs. The distinction is recorded because the request describes 26 “corrected cases” while its parenthetical identifies 24 earlier edits across 22 cases plus two later cases. A-conflict-02 is included in this ledger but not in the 113 held-out rows because it belongs to dev.

A-conflict-03 and D-conflicting-02 are flagged in the held-out sheet for reviewer attention. Their dataset definitions were not changed. The package identifies Claude’s prior review as AI-assisted and **not independent human sign-off**; no reviewer decisions or identity fields were filled in.

## Source and data checks

- Read current `data_A.py` through `data_D.py`, the correction report, threshold freeze, original blank review sheet, AI-assisted review sheet, `source_pages.md`, and all 12 source PDFs.
- Confirmed the source-PDF package has 12 PDFs covering the dataset’s 56 pages. Checked all **139 cited source spans** across held-out cases against the corresponding PDF page text; all were present after whitespace normalization. This mechanical match is preparation evidence, not human sign-off on question quality or answer fairness.
- Built the held-out sheet from the current dataset modules and split rule, then exported and reopened the workbook. The round-trip check confirmed all 113 case rows and all current cell values matched the generated dataset payload; all reviewer decision fields remained blank. The correction tab round-tripped all 26 entries.
- Held-out eligibility is Tier 1 **113** and Tier 2 **106**; the 7 `answer_only` cases remain Tier 1 only.
- The original blank sheet SHA-256 remains `9bd0072096be02a254fa810c7268c6529dc4ce81b113fdc5b502c8ddc6b6cf77`. The AI-assisted sheet remains `fbe1426efb8ca6dfb89206cdad01e5974b0aa1c801a647fe6aad544798a299ca`. Neither existing review sheet was modified.
- `source_pages.md` remains SHA-256 `0a3a22e2ffe5517351286399cd0b139edba787c7b8fddea26306961326049d84`.

## Thresholds and development-results caveat

The frozen thresholds are unchanged: Tier 1 **97/113** and Tier 2 **69/106**.

A-conflict-02 belongs to the **development split**. Its correction changes the current dataset. Historical development evaluation results remain historical results from the pre-correction dataset and must not be represented as scores obtained from the corrected dataset. This preparation did not rerun development evaluation or assert any corrected-dataset development score.

## Current corrected dataset hashes

These current SHA-256 values match the canonical correction report and threshold freeze:

| Dataset file | SHA-256 |
|---|---|
| `eval/phase35/data_A.py` | `c204fd037d653a27dfed00f7d9b9ad0b38dea4d20f578145aa7bc9b15201714c` |
| `eval/phase35/data_B.py` | `f58fc8041bed81682e0bc22be6123364f963b170db5a409204b60922aa5a3548` |
| `eval/phase35/data_C.py` | `6fc3ca44254f4dc536b2bde59d355134ccdee284ff359c4a6f3ebe7deb6cfea6` |
| `eval/phase35/data_D.py` | `6341a55f5307cf9cc47fbf1608e7dc26e3041793f6e0184528f1a3b9249d8f64` |

Package workbook SHA-256: `300dc43fb76b1884015583d60e12834f7e50086c0afbaad765ad536e8c491467`.

## Safety and files

No held-out result file was created; no held-out evaluation, Gemini/API call, database access, or validation run was performed. Dataset definitions, PDFs, source text, scorer, validator, runner, split logic, thresholds, and evaluation results were not edited for package preparation. Nothing was staged, committed, or pushed.

Files created: `heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx`, this report. File updated: `docs/remediation/heldout_review/README.md`. The README now describes the current corrected dataset and new workbook, and explicitly distinguishes current expectations from the preserved old review sheets.

**STOP:** package preparation is complete. Independent human review must now be performed by the reviewer; this report does not claim that review or sign-off has occurred.
