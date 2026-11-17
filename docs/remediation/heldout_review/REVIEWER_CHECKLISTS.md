# Held-out review: checklists and procedures

Companion to `HUMAN_REVIEW_GUIDE.md`, which defines the criteria and decisions. These checklists organise the work; they make no decision about any case. The same checklists apply to the separate development review (`../dev_review/`), with the substitutions noted there.

**Status at preparation (2026-11-17):** reviewer not yet identified; 0 of 113 cases reviewed.

## 1. Onboarding (before opening any case)

The project owner completes this checklist:

- [ ] Reviewer named: ____________________
- [ ] The reviewer confirms all three independence conditions in guide §1:
  - did not author the dataset or take part in its AI-assisted preparation;
  - did not take part in the earlier AI-assisted review;
  - will form each decision independently.
- [ ] The reviewer has the package:
  - `heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx`;
  - `source_pdfs/` (12 PDFs) and `source_pages.md`;
  - `HUMAN_REVIEW_GUIDE.md` and this file.
- [ ] Workbook identity recorded before review starts: SHA-256 `300dc43fb76b1884015583d60e12834f7e50086c0afbaad765ad536e8c491467` (command in §5).

The reviewer completes this checklist:

- [ ] Read guide §2: the workbook layout, and how the scorer matches facts (case-insensitive exact substring; whitespace is **not** normalized).
- [ ] Read guide §3–§4: the ten criteria and the three decisions.
- [ ] Read guide §6: corrections are **proposed** in the ledger (rows 27+, `PROPOSED (not applied):`); columns A–X are never edited.
- [ ] Agreed with the project owner whether AI assistance may be used for evidence lookup. If it is used, it is recorded per row (guide §1).

## 2. Preventing anchoring on the earlier AI-assisted review

An earlier review by Claude (AI) exists: 88 VALID / 25 NEEDS REVISION / 0 EXCLUDE. Its corrections were already applied to the dataset. To keep your review independent:

1. **Do not open, before you finish your own decisions:**
   - `heldout_review_sheet_REVIEWED_by_Claude.csv`;
   - `REVIEW_SIGNOFF_REPORT.md` (especially its per-case sections);
   - `../HELDOUT_DATASET_CORRECTIONS.md`;
   - the Stage 9 audit reports (`../STAGE9_*.md`);
   - the Stage 9 analysis folders, which hold AI-written per-case verdicts, issue findings and proposed answers:
     - `../technical_dataset_audit/` (Phase C);
     - `../phase_d_decision_package/` (Phase D, including the correction-proposal CSVs);
     - `../phase_e1_multi_agent_audit/` (Phase E1);
     - `../phase_e2_engineering/` (Phase E2, including revised correction proposals).
2. **Treat the correction-history columns as history, not as a verdict.** These are `correction_status`, `previous_*` and `correction_summary` in the workbook. A corrected case can still be wrong; an uncorrected case is not presumed right.
3. **Judge the current definition only:** columns A–R against the source PDF.
4. **If you consult AI material after deciding** and then change a decision, write "changed after consulting the AI review" and the reason in the rationale.
5. **If an AI assistant helps you** (evidence lookup only), mark the row's rationale with "AI-assisted lookup". The decision and rationale wording must be yours.
6. **The source-lookup tool (§6) is mechanical.** It tells you where text is, not whether it is right evidence. Its output is not a review finding.

## 3. Per-case completion checklist (all 113 rows)

- [ ] Read `question` and `history_json` (criterion 1).
- [ ] Opened every source in `expected_sources_json` in the PDF (`source_pdfs/<document>`, the stated page), and found the span (criterion 6). The lookup tool (§6) gives the PDF path, page and the `source_pages.md` line.
- [ ] Checked the fact groups and alternatives (criteria 2–3), the forbidden strings (4) and the expect flags (5).
- [ ] If conflicting: a genuine disagreement, not an update (7). If compound: every part covered (8).
- [ ] Evidence is specific and unambiguous (9). The lookup tool lists other pages carrying the same text.
- [ ] `reviewer_decision` (Y) chosen from the dropdown (10).
- [ ] `reviewer_rationale` (Z): **required** for NEEDS REVISION / EXCLUDE, and names the field, the problem, the evidence and the proposed fix.
- [ ] `reviewer_name` (AA) and `review_date` (AB, `YYYY-MM-DD`) entered.
- [ ] For NEEDS REVISION / EXCLUDE: a `PROPOSED (not applied):` row was added to `Correction Ledger` with the next `change_no`.
- [ ] Attention rows (`A-conflict-03`, `D-conflicting-02`): the rationale explicitly addresses the flag, whatever the decision.
- [ ] Columns A–X untouched. No rows sorted, inserted, deleted or hidden.

## 4. Sign-off checklist

- [ ] All 113 rows have a decision. The validator (§5) reports `pending: 0`.
- [ ] The validator reports **0 errors** and **0 incomplete** items, apart from the sign-off fields being completed now.
- [ ] Ledger: historical entries 1–26 are unchanged (validator with `--baseline-git HEAD`); every NEEDS REVISION / EXCLUDE has a PROPOSED entry; no PROPOSED entry exists for a VALID case.
- [ ] `Read Me & Sign-off` column B, rows 19–24, filled (guide §7):
  - name;
  - independence statement, including AI-assistance use;
  - cases reviewed (113);
  - VALID / NEEDS REVISION / EXCLUDE counts, which must equal the validator counts;
  - date;
  - signature.
- [ ] The dataset hashes on rows 14–17 still match the four data files (§5, "dataset check").
- [ ] Final workbook SHA-256 recorded in the progress report.
- [ ] Understood: sign-off does **not** authorize any held-out evaluation, and any dataset correction needs the project owner's approval and a documented re-freeze.

## 5. Generating a progress report (procedure)

These commands only read the workbook. `--output` / `--json` create **new** files and refuse to overwrite. Run them from the repository root with the development tools installed (`.venv/bin/python -m pip install -r requirements-dev.txt`):

```bash
# validation summary: status, counts, errors, incomplete items
.venv/bin/python -m eval.review.cli validate --kind heldout --baseline-git HEAD
#   add --all to list every incomplete item; --json FILE to save the full report

# Markdown progress report (fields of REVIEW_PROGRESS_REPORT_TEMPLATE.md, computed from the file)
.venv/bin/python -m eval.review.cli progress --kind heldout --baseline-git HEAD \
    --output docs/remediation/heldout_review/progress_YYYY-MM-DD.md

# workbook identity
shasum -a 256 docs/remediation/heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx

# dataset check: the frozen manifest. After the workbook is edited, this reports exactly one
# mismatch, the workbook itself, which is expected until the documented re-freeze
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
    .venv/bin/python -m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json
```

- `--baseline-git HEAD` compares the ledger history against the committed workbook. Use the revision that holds the **pre-review** workbook.
- The **status values** are:
  - `NOT_STARTED`: no decision yet;
  - `IN_PROGRESS`: decisions or fields outstanding;
  - `NEEDS_RESOLUTION`: an integrity error needs a human, for example an edited definition or a bad ledger reference;
  - `COMPLETE`: every case decided, every required field and the sign-off filled, and no errors.
- `COMPLETE` is a structural result only. It does not make the review independent; only the sign-off and the project owner's confirmation do.

## 6. Source lookup (mechanical)

```bash
.venv/bin/python -m eval.review.cli locate --kind heldout --case <CASE_ID>
.venv/bin/python -m eval.review.cli check-sources --kind heldout
```

**`locate`** prints, for each expected source of the case:
- the PDF path, page count and whether the page exists;
- the `source_pages.md` line;
- whether the span text occurs on that page (in the PDF text and in the dataset page text, ignoring case and whitespace);
- other pages where the same text occurs.

**`check-sources`** lists lookup problems across the workbook.

**What the lookup tool does not do:**
- It does **not** decide whether the evidence supports the fact.
- It does **not** suggest a decision or write anything.

It prints no case text; read the span in the workbook.
