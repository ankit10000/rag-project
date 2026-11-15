# Held-out dataset review — sign-off report

**Reviewer:** Claude (Anthropic AI model), at the project owner's explicit instruction.
**Date:** 2026-11-12.
**Status: AI-assisted review, NOT an independent human review.** `README.md` and `HELDOUT_THRESHOLD_FREEZE.md` require a reviewer who is independent of the dataset author. The dataset was produced with AI assistance in this project, so this review does **not** satisfy that requirement by itself. Whether to accept it in place of, or in addition to, a human review is the project owner's decision. It is recorded here only to make that decision explicit.

## Scope and method
- **Coverage:** all **113** held-out cases were reviewed, not a sample. 12 source documents were used.
- **Mechanical pre-check** (script, read-only):
  - each fact alternative was checked for literal presence on the gold page(s);
  - the same strings were searched on other pages, to detect ambiguity;
  - forbidden strings were checked for presence on the gold pages;
  - abstain/conflict expectations were checked for internal consistency.

  18 cases carried hints. They were treated as prompts to investigate, not as verdicts.
- **Case-by-case review:** four reviewer instances, one per data file, each read every case against the verbatim page text (`source_pages.md`). Each checked:
  1. question clarity and answerability;
  2. fact and alternative correctness, plus phrasings a correct answer would likely use;
  3. document and page references;
  4. forbidden, abstain, partial and conflict expectations;
  5. scoring fairness against the actual scorer semantics (case- and whitespace-insensitive substring matching; every fact group required; forbidden strings).
- **Consolidation:**
  - The two decisions that rested only on a double-space difference in a gold span (C-compound-03, C-follow_up-01) were changed to **VALID**. `validate.py` collapses whitespace before matching spans, and the scorer does not use spans.
  - Key findings were spot-checked directly in the source text:
    - A-conflict-01: the footnote says it "takes the place of" the earlier hours, so the text is an update, not a conflict.
    - D-conflicting-02: an errata sheet corrects 28 Nm to 31 Nm.
    - A-followup-02: the forbidden strings `$85` and `14 days` are confirmed.
- **No modifications:** no dataset, scorer, runner or threshold file was modified. The original blank sheet `heldout_review_sheet.csv` is unchanged (SHA-256 `9bd00720…cf77`); decisions are in the separate copy `heldout_review_sheet_REVIEWED_by_Claude.csv` (SHA-256 `fbe1426e…99ca`).
- **No evaluation:** no held-out evaluation, Gemini call or database access took place.

## Result
| | VALID | NEEDS REVISION | EXCLUDE |
|---|---:|---:|---:|
| data_A (30) | 24 | 6 | 0 |
| data_B (26) | 23 | 3 | 0 |
| data_C (31) | 22 | 9 | 0 |
| data_D (26) | 19 | 7 | 0 |
| **Total (113)** | **88** | **25** | **0** |

No case is fundamentally broken. **Every gold fact checked is supported by its stated page.** The revisions are about scoring fairness, not wrong ground truth.

## The 25 NEEDS REVISION cases, by problem type
1. **Forbidden string would penalise a correct answer.** A correct follow-up answer naturally restates the wrong earlier value while correcting it, e.g. "$65, not $85".
   - A-followup-02 (`$85`, `14 days`)
   - A-followup-04 (`aged 60`, `age 60`, `60 and over`)
   - B-follow-02 (`32%`)
   - C-follow_up-03 (`30 months`)
   - C-follow_up-04 (`$250,000`)
   - D-follow_up-01 (`18 g`)
   - D-follow_up-03 (`3 months`)
   - D-compound-01 (`21 days`, which also appears legitimately in a page-4 memo)
   - C-prompt_injection-03 (`unsuitable`)

   *Fix:* remove these strings or narrow them, for example to the injected or outdated phrase in full.
2. **`expect_conflict` set where the sources describe an update or correction, not a disagreement.**
   - A-conflict-01 (footnote supersedes 4.2)
   - A-conflict-03 (Edition 2026.1 update notice)
   - A-conflict-04 (different scopes: bylaw duty vs clinic practice)
   - D-conflicting-02 (errata corrects 28 Nm → 31 Nm)

   *Fix:* set `expect_conflict=false` and require the current value, optionally together with the superseded value or update wording.
3. **Missing accepted phrasings**, so a correct answer would score 0 on a fact group:
   - B-direct-04 (date-range forms; also drop the over-lenient lone "21 June")
   - B-follow-04 ("20-minute")
   - C-multi_chunk-03 ("2 on-site visits")
   - C-compound-02 ("$5 million")
   - C-compound-05 ("first day")
   - C-multi_page-02 ("4 months")
   - C-conflicting-03 ("net 45" / "net 30")
   - C-conflicting-04 ("$1 million")
   - D-multi_chunk-01 ("1,000 running hours")
   - D-multi_chunk-02 ("69")
   - D-multi_page-01 ("6,000 running hours")

   *Fix:* add the listed alternatives.
4. **Over-lenient fact group:** A-multipage-01. `boat` repeats the question and `yes` also matches inside other words, so a wrong "No…" answer could pass. *Fix:* replace these with alternatives that discriminate.

Exact proposed changes, with evidence, are in `REVIEWER_COMMENTS_AND_RATIONALE` of the reviewed sheet.

## Observations without a decision change
- The missing-metadata cases (A-missingmeta-01, B-meta-01, D-missing_metadata-01) give chunks without a document or page. That is fair only if the scorer does not penalise the missing page citation. As implemented, citation completeness then depends on how the run maps those chunks; this deserves attention when the results are interpreted.
- Optional robustness additions are listed in the rationale text: en dashes in number ranges, "×" signs, "7 a.m.", "an hour", "30 April 2027" as an extra forbidden string for B-conf-01, and splitting the two visiting blocks in A-multipage-02.
- Embedded instructions aimed at AI tools in the source pages (the injection material) were treated as data and ignored.

## Consequences for the held-out run (per the freeze document)
- The 25 revisions must be applied in a **separate, documented dataset change**, followed by `validate.py` (`VALID`) and **new SHA-256 hashes**, all **before** any held-out run.
- No case was excluded, so the denominators stay **113 (Tier 1)** and **106 (Tier 2)**, and the minimum passing counts stay at **97** and **69**.
- **Held-out execution still needs your separate explicit approval.** Because this review is AI-assisted, please also decide explicitly whether you accept it as the review of record, or still want an independent human reviewer to confirm, for example by checking the 25 revisions and a sample of the 88 VALID cases.

## Sign-off
| Item | Value |
|---|---|
| Reviewer | Claude (AI), not independent of the dataset's AI-assisted authorship |
| Cases reviewed | 113 / 113 |
| VALID / NEEDS REVISION / EXCLUDE | 88 / 25 / 0 |
| Date | 2026-11-12 |
| Human independent review | **not performed** (pending the project owner's decision) |
