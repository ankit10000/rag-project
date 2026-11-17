# Development ground-truth review package (SEPARATE from the held-out review)

**Prepared:** 2026-11-17 (Stage 9 Phase B), by Claude (AI), at the project owner's request. **No review has taken place.** Every reviewer field is blank, and nothing here is a decision.

| Item | Value |
|---|---|
| Workbook | `dev_review_sheet.xlsx` (this folder): tabs `Read Me & Sign-off`, `Development Cases`, `Correction Ledger` |
| Cases | **7 development-split cases** named by the project owner: `B-comp-04`, `B-conf-02`, `B-conf-03`, `B-conf-04`, `D-conflicting-01`, `D-conflicting-03`, `D-conflicting-04` |
| ID check | All 7 exist in the current dataset and are `dev` under the split rule (`sha1(id) % 10 < 3`); none was substituted or invented. The builder refuses ids that are missing or not dev |
| Evidence | `../heldout_review/source_pdfs/` and `../heldout_review/source_pages.md` (they cover all 56 dataset pages, including development pages) |
| Dataset | `phase35-corrected-2026-11-12`; frozen manifest `content_sha256` `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97` |

## Separation from the held-out review

- **The 7 cases are not in, and must not be added to,** the 113-case held-out workbook.
- **Outcomes here do not change:**
  - any held-out case;
  - the held-out denominators (113 / 106);
  - the frozen thresholds;
  - the held-out sign-off.
- **The development thresholds** (Tier 1 41/47, Tier 2 28/42) are historical results and are not re-decided here.
- **Reviewer independence:**
  - the development reviewer may be the same person as the held-out reviewer, or a different one; the project owner decides;
  - either way, the same independence conditions apply (held-out guide §1);
  - the development review is signed off separately.

## How to review

The principles, criteria and decision meanings are **identical** to the held-out review. Use `../heldout_review/HUMAN_REVIEW_GUIDE.md` (§2–§4, §6) and `../heldout_review/REVIEWER_CHECKLISTS.md` (§2–§4), with these substitutions:

| Held-out | Development |
|---|---|
| `Held-out Cases`, 113 rows (2–114) | `Development Cases`, 7 rows (2–8) |
| Attention flags on 2 rows | **every** row is flagged; column AD `review_focus` holds the owner's question for that case |
| Ledger rows 1–26 are history; proposals from 27 | Ledger is empty; proposals start at `change_no` 1 |
| Sign-off rows 19–24 | Sign-off rows at the bottom of `Read Me & Sign-off` (the "Sign-off - …" labels) |
| `--kind heldout` | `--kind dev` |

**The review questions (column AD) are the owner's questions, not answers:**
- `B-comp-04`: should `calder_sound_tile_study_TR-2026-07.pdf` page 4 be included as an expected source for the missing production-cost information?
- The six conflict cases: does the expected conflict represent a genuine disagreement between sources, rather than an ordinary update or correction?

**What to enter:** answer each question in your rationale, then choose VALID / NEEDS REVISION / EXCLUDE on the full criteria. A rationale is expected on **every** row here, because every row carries a review question.

**Anti-anchoring:** these cases appear in Stage 9 audit documents (`../STAGE9_PHASE_A_EVALUATION_READINESS_AUDIT.md`), which contain AI-written analysis of them. Do not read those sections before recording your own decisions.

The same applies to the Stage 9 analysis folders. They hold AI-written per-case findings and proposed corrections, and several cover these seven cases. Do **not** open them before recording your own decisions:
- `../STAGE9_*.md`;
- `../technical_dataset_audit/` (Phase C);
- `../phase_d_decision_package/` (Phase D, including `DEV_CORRECTION_PROPOSALS.csv`);
- `../phase_e1_multi_agent_audit/` (Phase E1);
- `../phase_e2_engineering/` (Phase E2, including revised correction proposals).

The held-out exclusions in `../heldout_review/REVIEWER_CHECKLISTS.md` §2 also apply.

## Tools (read-only)

```bash
.venv/bin/python -m eval.review.cli validate --kind dev --all
.venv/bin/python -m eval.review.cli progress --kind dev
.venv/bin/python -m eval.review.cli locate --kind dev --case B-comp-04
.venv/bin/python -m eval.review.cli check-sources --kind dev
```

`--baseline-git` applies only once the workbook is committed. The ledger has no history entries to protect.

## Regenerating the workbook

```bash
.venv/bin/python -m eval.review.cli build-dev-review --output <NEW PATH>
```

- The builder writes a **new** file only; it refuses to overwrite an existing workbook, which could hold review work.
- Contents: case definitions copied from the current dataset; every reviewer field blank; the decision dropdown on `Y2:Y8`.

## After the review

Proposed corrections go to the project owner for approval. Only an approved set is applied to `data_B.py` / `data_D.py`, through the documented correction procedure.

**Re-freeze needed:** these files are frozen-manifest inputs, so any change also needs a documented re-freeze, even for development cases. The manifest hashes the whole dataset.
