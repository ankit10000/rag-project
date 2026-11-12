# Held-out evaluation: independent human review package

Prepared 2026-11-12 (preparation only).
- No held-out evaluation was run, no Gemini call was made, and no dataset, ground truth, scorer, threshold or result file was changed.
- **All reviewer fields are empty. No review has taken place.**

## What is in this folder
| File | Purpose |
|---|---|
| `heldout_review_sheet.csv` | one row per held-out case (113 rows), UTF-8 with BOM so it opens directly in Excel. The reviewer fills the last four columns. |
| `source_pdfs/` (12 files) | the source documents, rendered exactly the way the Tier 2 runner builds them (`run_eval.build_scratch_corpus`: one data page per PDF page, same text box, 9 pt). Every page fit; nothing was cut off. |
| `source_pages.md` | the verbatim page text of every document, taken from `eval/phase35/data_A..D.py`. This is the canonical text the validator and Tier 1 use; use it to confirm a span or fact exactly. |
| `README.md` | these instructions, the counts and the integrity hashes |

## Dataset and split (computed from the data, not assumed)
- **Totals:** 12 documents, 56 pages, **160 cases**. `eval/phase35/validate.py` → `VALID`.
- **Split rule** (`run_eval.split_of`): `sha1(case_id) % 10 < 3` → dev, otherwise held-out.

| Split | Cases | Tier 1 eligible | Tier 2 eligible (`tier == "both"`) | Tier 1 only (`answer_only`) |
|---|---|---|---|---|
| dev | 47 | 47 | 42 | 5 |
| **held-out** | **113** | **113** | **106** | 7 |

- Tier 1 runs **every** case of the split. Held-out Tier 1 eligibility is therefore **113**, not 66.
- Held-out cases by category: direct_factual 19, no_answer 16, compound 15, follow_up 14, multi_chunk 12, multi_page 11, prompt_injection 10, conflicting 9, irrelevant_retrieval 4, missing_metadata 3.
- Held-out cases by data file: A 30, B 26, C 31, D 26.

## Columns of the sheet
1. **Case:** `case_id`, `data_file`, `category`, `eligibility` (Tier 1 + Tier 2, or Tier 1 only).
2. **Prompt:** `history` (earlier turns given with the question; "(none)" if empty) and `question`.
3. **Expected answer:**
   - `expected_facts`. **Every group in parentheses is required. Inside a group, `|` separates accepted alternative wordings**, and one alternative is enough. The scorer matches these strings in the answer (fact recall).
   - `forbidden_strings`: text that must **not** appear in the answer (e.g. an injected payload, an outdated value).
4. **Expected evidence:** `expected_sources`, as document, page and the gold span that must literally be on that page.
5. **Scoring expectations:**
   - `expect_abstain` (the correct answer is "the documents do not say");
   - `expect_partial` (answer part and state that part is missing);
   - `expect_conflict` (the answer must state that sources disagree and cite both);
   - `citation_note`.
6. **Author context:** `author_review_note` is the dataset author's own justification. It is **not** a review.
7. **Tier 1 chunks:** `tier1_chunks`, only for the 7 `answer_only` cases. These are the exact chunks the model receives in Tier 1, with their own document and page labels.
8. **Reviewer (to fill in):** `REVIEWER_DECISION`, `REVIEWER_COMMENTS_AND_RATIONALE`, `REVIEWER_NAME`, `REVIEW_DATE`.

## Instructions for the reviewer
**Independence:** you must not be the author of the dataset.
- That excludes the person who wrote `data_A..D.py` and anyone who prepared them with AI assistance in this project, including Claude.
- Do not look at any evaluation output for these cases. None exists yet, and none should exist before the review is complete.

**Review all 113 cases, not a sample.** For each case:
1. Open the expected source (`source_pdfs/`, or `source_pages.md` for exact text). Check that the **gold span is really on the stated page of the stated document**, and that the page supports the expected facts.
2. Check that the **question is unambiguous**: a careful reader of the documents should reach one answer. Consider the conversation history for follow-up cases.
3. Check that the **expected facts are correct and complete**, and that their alternatives are **fair**. A correct answer worded reasonably should not be scored wrong; for example, check number and date formats and units. Check that `forbidden_strings` would not penalise a correct answer.
4. Check the **abstention, partial and conflict expectations**:
   - `expect_abstain` only if the documents really do not contain the answer;
   - `expect_conflict` only if two sources really disagree;
   - `expect_partial` only if exactly part of the question is answerable.
5. For prompt-injection cases, check that the injected instruction is in the document text and that the expected behaviour (ignore it, answer the real question) is right.
6. Choose a decision:
   - **VALID**: question, expected answer, evidence and scoring expectations are all correct.
   - **NEEDS REVISION**: ambiguity, an incorrect or incomplete expected answer, missing or wrong evidence, or an unfair scoring rule. **Describe exactly what to change.**
   - **EXCLUDE**: the case is unsuitable (for example unanswerable as written, or a duplicate). **Give the reason.**
7. **Every NEEDS REVISION and EXCLUDE must have a written rationale.** VALID needs no comment, but one is welcome.
8. Fill in your name and the review date on every row.

**After the review (by the project owner, not the reviewer):**
- Apply the revisions to the dataset in a separate, recorded change. Exclusions must be documented, not silently deleted.
- Re-run `validate.py`.
- **Freeze** the dataset by recording new SHA-256 values for `data_A..D.py`.
- Only then may the held-out evaluation be approved. It is run once, with the already frozen thresholds; no tuning happens afterwards.

## Integrity record
SHA-256, identical before and after this package was prepared:

| File | SHA-256 |
|---|---|
| `eval/phase35/data_A.py` | `b4d8b3516a777c59a280d6cb9b5bbb23aefaf40459130bf46fc4e1d8c51cbf65` |
| `eval/phase35/data_B.py` | `a3434f5b6ad1fbd3da30f2413f9f855595f6ec09278afb296b28e5f7d82b1778` |
| `eval/phase35/data_C.py` | `67bc2b5e1ea01e27516c6fb61809efe6c90573630498e3384408dd8c4ad3b647` |
| `eval/phase35/data_D.py` | `655be7b3c60cd13af50c2e15d1c9346b727ad3f57998233ffebc43d934b2306e` |
| `eval/phase35/run_eval.py` | `3b066a5b3b4c1de908cb5a555db17762af2bd70606f0854d5f2ba0ce7106e989` |
| `eval/phase35/validate.py` | `1727a33421202da3bd0d52aabcf0bf11dd9515c16c73a8b10e385aa356fe1a7d` |
| `eval/phase35/summarize.py` | `379d144d65cc44c05a21859bc1841677a7c18dd05fb34397fea77f9956e80705` |
| `eval/answer_scoring.py` | `c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af` |
| `eval/harness.py` | `6e3ba55e9f18c68af33bde2eaa97399b27e20a906cb33d7d36cdfa2da9c8f86d` |
| `results/tier1_dev.jsonl` (Stage B) | `6e89c07ca77201d65a1c1e469e32fd22fe687ca5248a9736d54c58c0d62ac60b` |
| `results/tier2_dev.jsonl` (Stage B) | `51ebe8365c53ad6df4ff11d798565bb391137f9e9af41161d6d614487c16aa79` |
| `results/log_tier1_dev.txt` / `log_tier2_dev.txt` (originals) | `57c95ec9…13a10` / `853eee37…cb05` |
| `results/log_tier1_dev_stageB.txt` / `log_tier2_dev_stageB.txt` | `51f1d4cb…cfe8` / `91fce59d…a2e` |

Package files:

| File | SHA-256 |
|---|---|
| `heldout_review_sheet.csv` | `9bd0072096be02a254fa810c7268c6529dc4ce81b113fdc5b502c8ddc6b6cf77` |
| `source_pages.md` | `0a3a22e2ffe5517351286399cd0b139edba787c7b8fddea26306961326049d84` |

**Thresholds:**
- The development thresholds are frozen: Tier 1 ≥ 41/47, Tier 2 ≥ 28/42.
- **Held-out thresholds are frozen** (2026-11-12, before any held-out result): Tier 1 ≥ 85% = at least **97/113**; Tier 2 ≥ 65% = at least **69/106**. The 7 answer-only cases are excluded from the Tier 2 denominator. See [`../HELDOUT_THRESHOLD_FREEZE.md`](../HELDOUT_THRESHOLD_FREEZE.md).

## Reviewer sign-off
| Item | Value |
|---|---|
| Reviewer name | |
| Relationship to dataset author | (must be: independent) |
| Cases reviewed (of 113) | |
| VALID / NEEDS REVISION / EXCLUDE counts | |
| Date completed | |
| Signature | |
