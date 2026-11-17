# Stage 9 Phase C: audit completion checklist

**Date:** 2026-11-17. **Nature:** AI-assisted technical audit, not independent human review.

## Coverage

- [x] **Held-out: 113 / 113 cases** have an explicit status in `HELDOUT_CASE_FINDINGS.csv`. The CSV has exactly 113 rows, unique ids, equal to the dataset's held-out split.
  - CONFIRMED_ISSUE 11;
  - POTENTIAL_ISSUE 22;
  - NO_ISSUE_FOUND 80;
  - UNABLE_TO_VERIFY 0.
- [x] **Development: 7 / 7 cases** have an explicit status in `DEV_CASE_FINDINGS.csv` (exactly 7 rows; all dev under the split rule).
  - CONFIRMED_ISSUE 4;
  - POTENTIAL_ISSUE 2;
  - NO_ISSUE_FOUND 1;
  - UNABLE_TO_VERIFY 0.
- [x] Development findings are kept separate from held-out findings: separate CSV, separate register section, separate report section.

## Evidence checks

- [x] **Primary evidence:** for all 56 pages of the 12 PDFs, the text layer is identical (whitespace-normalized) to the dataset page text.
  - 3 pages were rendered and inspected visually.
  - The Tier 2 PDF rebuild is lossless (no overflow).
- [x] **Source references:** 152 / 152 spans were found on their cited PDF pages (139 held-out, 13 dev). Every fact group has an alternative verbatim on a cited page.
- [x] **Context:** every case was read against its whole document, including updates, errata, amendments, footnotes, annexes and memos, and against related documents for cross-document statements.
- [x] **Absence checks:** every no-answer, irrelevant-retrieval and partial case had its requested information confirmed absent across all 56 pages (keyword search).

## Scoring and special cases

- [x] **Scorer semantics:** the actual frozen code was read: `answer_scoring.py` (full phrase lists, `fact_recall`, `forbidden_hits`) and `run_eval.score_generic`.
- [x] **Probes:** 25 probes were run through the frozen scorer, demonstrating false failures and false passes (report §8).
- [x] **Special-attention cases** (`A-conflict-03`: superseding update; `D-conflicting-02`: erratum) were analysed from the sources (report §10, TA-01, TA-02).
- [x] **The owner's development questions** were answered:
  - `B-comp-04`: p4 should be a source;
  - conflict cases: genuine vs update / override / stale (report §7).
- [x] **Cross-domain consistency:** updates vs conflicts, corrections, partial and abstention cases, formats, forbidden strings, spans, injection coverage (report §9).

## Outputs (all in `docs/remediation/technical_dataset_audit/`)

- [x] `STAGE9_PHASE_C_TECHNICAL_AUDIT_REPORT.md`
- [x] `HELDOUT_CASE_FINDINGS.csv`
- [x] `DEV_CASE_FINDINGS.csv`
- [x] `ISSUE_REGISTER.md`
- [x] `AUDIT_COMPLETION_CHECKLIST.md` (this file)

## Safety

- [x] **Unchanged:** `data_A..D.py`, the scorer, thresholds, the frozen manifest (still REPRODUCED), the runner, both workbooks, the correction ledgers.
- [x] **No reviewer data:** no VALID / NEEDS REVISION / EXCLUDE decision, reviewer name, date, signature or independence confirmation was entered.
- [x] **No external access:** no database connection; no provider/LLM call.
- [x] **No execution:** no held-out or `--split all` run; no approval file.
- [x] **No git operations:** no commit, push, stash, reset, checkout or staging. The existing staged work was preserved as found.

## Limitations and remaining work

- **Not independent review:** this audit is AI-produced and does not replace the independent human review. The human reviewer should record their decisions before reading it (`REVIEWER_CHECKLISTS.md` §2).
- **Potential vs confirmed:** the line between them involves judgement about answer likelihood. Probes show scorer behaviour, not system behaviour.
- **Out of scope:** the 40 other development cases were not audited.
- **Owner decisions still needed:**
  - which corrections (TA-*, TP-*) to approve;
  - whether to adopt a versioned scorer (TS-1 – TS-4);
  - the documented re-freeze afterwards.
- **Not started**, as instructed: human review, the correction proposal and the re-freeze.
