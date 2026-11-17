# Held-out ground-truth review: guide for the independent human reviewer

**Prepared:** 2026-11-17 (Stage 9 Phase B), by Claude (AI) at the project owner's request. This guide explains **how** to review. It contains no decision, recommendation or opinion about any case. **Every decision in the workbook must be yours.**

| Item | Value |
|---|---|
| Workbook to complete | `heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx` (this folder) |
| Cases | **113 held-out cases**, one per row on the `Held-out Cases` tab (rows 2–114) |
| Evidence | `source_pdfs/` (12 PDFs, the primary evidence) and `source_pages.md` (the same page text, searchable) |
| Dataset version | `phase35-corrected-2026-11-12` |
| Dataset identity | file hashes on the workbook's `Read Me & Sign-off` tab (rows 14–17); frozen manifest `eval/phase35/frozen_manifest.json`, `content_sha256` `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97` |

**Companion:** `REVIEWER_CHECKLISTS.md` has the onboarding, anti-anchoring, per-case and sign-off checklists. It also gives the commands for the progress report and for the mechanical source lookup.

## 1. Who may review (independence)

You are independent if **all** of the following are true. Confirm each in the sign-off (§7):

1. You did not write the dataset cases (`eval/phase35/data_A.py` … `data_D.py`) and did not take part in their AI-assisted preparation.
2. You did not take part in the earlier AI-assisted review (`heldout_review_sheet_REVIEWED_by_Claude.csv`, `REVIEW_SIGNOFF_REPORT.md`).
3. You form each decision yourself from the case and the source evidence.

**To avoid anchoring:**
- Do **not** open `heldout_review_sheet_REVIEWED_by_Claude.csv` or the per-case sections of `REVIEW_SIGNOFF_REPORT.md` before you have recorded your own decisions.
- For the same reason, do **not** open the Stage 9 audit material before you have recorded your own decisions. It contains AI-written per-case verdicts, issue findings and proposed answers:
  - `../STAGE9_*.md`;
  - `../technical_dataset_audit/`;
  - `../phase_d_decision_package/`;
  - `../phase_e1_multi_agent_audit/`;
  - `../phase_e2_engineering/`.
- The full list of material to avoid is in `REVIEWER_CHECKLISTS.md` §2.
- If you consult them afterwards and then change a decision, say so in that row's rationale.

**If you ask an AI assistant for help:**
- AI help is limited to locating evidence and explaining these criteria.
- Write your decision in your own words, and record in the rationale that AI assistance was used for that row.
- An AI-produced decision is **not** an independent decision.

## 2. Workbook layout

**Columns A–X: case definition and context. Read them; do not edit them.**

| Column(s) | Meaning |
|---|---|
| `case_id`, `data_file`, `split`, `category`, `tier` | Identity. `split` is always `heldout` here |
| `tier1_eligible`, `tier2_eligible` | 7 `answer_only` cases are Tier 1 only (they come with hand-built chunks in `tier1_chunks_json`) |
| `question`, `history_json` | What the system is asked, and the prior conversation turns (if any) |
| `expected_facts_json` | A list of **fact groups**. **Every group is required**; within a group, **any one alternative** is enough |
| `forbidden_strings_json` | Strings that must **not** appear in a correct answer |
| `expected_sources_json` | The document, page and verbatim evidence span for the expected facts. The header calls the span `gold_span`; the JSON key is `span` |
| `expect_abstain` / `expect_partial` / `expect_conflict` | Whether the correct behaviour is to say the information is absent, to answer partly and say what is missing, or to report a disagreement between sources |
| `citation_note`, `author_review_note` | Author context. Not a review |
| `correction_status`, `previous_*`, `correction_summary` | History for the 23 held-out rows corrected before this review (see the `Correction Ledger` tab) |

**Columns Y–AC: yours.**

| Column | Entry |
|---|---|
| Y `reviewer_decision` | Dropdown: `VALID`, `NEEDS REVISION` or `EXCLUDE`. Exactly one per row |
| Z `reviewer_rationale` | **Required** for `NEEDS REVISION` and `EXCLUDE`; optional for `VALID` |
| AA `reviewer_name` | Your name, on every row |
| AB `review_date` | The date you decided, as `YYYY-MM-DD` |
| AC `reviewer_attention` | Pre-set on two rows (§5). Leave the flag in place; answer it in your rationale |

**How the frozen scorer reads the expectations.** Knowing this helps you judge whether the criteria are fair (`eval/answer_scoring.py`, `eval/phase35/run_eval.py`):

- **Facts:** a group is satisfied when one of its alternatives appears **as a substring** of the answer.
  - The match is **case-insensitive**, otherwise exact: whitespace, punctuation and number formatting are **not** normalized.
  - For example, `$1,200` does not match `$1200`, and `3 days` does not match `three days`.
- **Forbidden strings:** a case fails if any of them appears as a case-insensitive substring. This includes appearing in a sentence that negates it.
- **Abstain:** an answer counts as abstaining if the system's status is `abstained`, or if the answer contains one of a fixed list of "not enough information" phrases.
- **Partial:** the case requires at least one expected fact **and** an abstention signal.
- **Conflict:** the case requires a disagreement phrase **and** a citation of every expected source page.

## 3. What to check for every case

Assess all ten points before deciding.

1. **Question and history:** understandable and answerable as written. With history, is the referent clear?
2. **Fact groups:** together, they represent the information the question asks for: nothing missing, nothing extra required.
3. **Alternatives:** each alternative in a group is genuinely equivalent. Are reasonable correct phrasings missing? Remember that matching is substring-based (§2).
4. **Forbidden strings:** each names something a correct answer must not say. Could a correct answer contain it innocently?
5. **`expect_abstain` / `expect_partial` / `expect_conflict`:** each flag matches what the sources support.
6. **Sources:** each expected document and page exists, and each `gold_span` appears on that page (check the PDF) and supports the corresponding fact.
7. **Conflict cases** (`expect_conflict` true, or category `conflicting`): the sources genuinely **disagree**. An ordinary update or correction is not a conflict; for example, a later revision, an errata sheet or a clause that "replaces" an earlier one.
8. **Compound questions:** each part has its own fact group, and the expectations are complete for every part.
9. **Evidence quality:** the source evidence is specific and unambiguous. Could another page support a different answer?
10. **Decision:** `VALID`, `NEEDS REVISION` or `EXCLUDE` (§4).

## 4. Decisions

| Decision | Use when |
|---|---|
| **VALID** | The question, expected answer, criteria and cited source evidence are acceptable as they stand |
| **NEEDS REVISION** | There is a **correctable** problem: an ambiguity, a missing or wrong fact or alternative, an incorrect source, a wrong flag, or an incomplete criterion |
| **EXCLUDE** | The case is unsuitable for the frozen evaluation set and cannot reasonably be fixed. It would be removed through the documented correction process |

**Every `NEEDS REVISION` and `EXCLUDE` needs a specific rationale:**
- name the field (for example `expected_facts_json` group 2, or the `expect_conflict` flag);
- say what is wrong;
- cite the evidence (document and page);
- for `NEEDS REVISION`, give the proposed fix.

"Unclear" or "wrong" alone is not enough.

**Effect of exclusions:** an `EXCLUDE` reduces the held-out denominators (Tier 1 113; Tier 2 106). The minimum passing counts are then recomputed with the **same frozen percentages** (85% / 65%, rounded up), before any evaluation (`../HELDOUT_THRESHOLD_FREEZE.md`, rule 2). Decide on the merits; don't let the counts influence you.

## 5. Cases needing explicit attention

**Held-out (in the workbook):**
- `A-conflict-03`
- `D-conflicting-02`

Both carry a `reviewer_attention` flag. Give each an explicit decision and a rationale that addresses the flag, even if the decision is `VALID`. If you cannot resolve one, record `NEEDS REVISION` and state what remains open.

**Development split (NOT in this workbook; do not add them to it).** These questions are separate from the 113 held-out cases:
- `B-comp-04`: should `calder_sound_tile_study_TR-2026-07.pdf` page 4 be an expected source for the missing production-cost information?
- Development conflict cases `B-conf-02`, `B-conf-03`, `B-conf-04`, `D-conflicting-01`, `D-conflicting-03`, `D-conflicting-04`: do the expected conflicts represent genuine disagreements?

A development review needs its own approval and a **separate** review artefact. Record nothing about these cases in the held-out workbook.

## 6. Corrections: record, do not apply

- **Do not change columns A–X**, and do not sort, delete, insert or hide rows. The workbook must stay a faithful copy of the dataset under review.
- **Record every proposed correction on the `Correction Ledger` tab as a new row below the existing 26 entries**, using the next `change_no` (27, 28, …):
  - `case_id`, `split`, `data_file`: from the case row;
  - `changed_field`: the field (for example `gold_facts`, `forbidden`, `expect_conflict`, `gold_sources`, `exclude`);
  - `previous_value_json_or_text`: the current value;
  - `current_value_json_or_text`: **your proposed value**;
  - `source_or_rationale`: start with **`PROPOSED (not applied):`**, then your evidence.
- **Ledger rows 1–26 are history** (corrections applied before this review). Do not edit them.
- **Corrections are applied only later:** after your review, the proposed corrections are presented to the project owner. Only an **approved** set is applied to the dataset files, followed by validation and a documented re-freeze. Nothing you enter changes the dataset by itself.

## 7. Sign-off

When all 113 rows have a decision, complete rows 19–24 on the `Read Me & Sign-off` tab (column B):

| Row | Entry |
|---|---|
| 19 | Reviewer name |
| 20 | Independence confirmation: a statement that the three conditions in §1 hold, including whether AI assistance was used and for which rows |
| 21 | Cases reviewed (of 113) |
| 22 | VALID / NEEDS REVISION / EXCLUDE counts |
| 23 | Date completed (`YYYY-MM-DD`) |
| 24 | Signature (typed name is acceptable unless the project owner requires otherwise) |

Also confirm in row 20 that you reviewed the dataset identified by the hashes in rows 14–17. These must still match the four files at sign-off.

## 8. Practical notes

- Save as `.xlsx`, keeping the same file name and location. Keep the decision dropdown intact.
- Changing the workbook changes its hash. The frozen manifest will then report a mismatch, which is **expected**. The manifest is regenerated only in the documented re-freeze after review, never to hide a change.
- Completing the review does **not** authorize any held-out evaluation. That needs a separate, explicit approval from the project owner.
