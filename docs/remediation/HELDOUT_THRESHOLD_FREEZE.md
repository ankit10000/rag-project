# Held-out evaluation thresholds: FROZEN

**Frozen:** 2026-11-12 17:28 +0530, approved by the project owner.
**Frozen before any held-out result was observed.**
- No held-out evaluation has ever been run: no `eval/phase35/results/tier*_heldout.jsonl` exists, and no held-out Gemini call has been made.
- The independent human review has not yet taken place: all reviewer fields in `heldout_review/heldout_review_sheet.csv` are empty.

## Approved thresholds (do not change)
| Tier | Eligible held-out cases | Required percentage | Minimum passing cases | Check |
|---|---:|---:|---:|---|
| Tier 1 | 113 | ≥ 85% | **97** | 97/113 = 85.84% passes; 96/113 = 84.96% **fails** |
| Tier 2 | 106 | ≥ 65% | **69** | 69/106 = 65.09% passes; 68/106 = 64.15% **fails** |

- **Pass criterion:** a tier passes only if `correct ≥ minimum passing cases`. The scorer's `correct` field, as defined in `eval/phase35/run_eval.py:score_generic`, is used unchanged.
- **Exact counts:** the minimum counts are exact. A score is never rounded up to claim a pass; for example, 96/113 is a **fail**, not "≈85%".
- **Separate evaluation:** each tier is judged separately against its own minimum.

## Eligible cases and the seven Tier 1-only cases
- The split is computed by `run_eval.split_of`: `sha1(case_id) % 10 < 3` → dev, otherwise held-out. Over the 160 cases this gives **113 held-out cases**.
- **Tier 1** (`run_eval.py --tier 1`) evaluates **every** held-out case → denominator **113**.
- **Tier 2** (`run_eval.py --tier 2`) evaluates only cases with `tier == "both"` (`run_eval.py:269-270`) → denominator **106**.
- **The other 7 cases have `tier == "answer_only"`:**
  - they come with hand-built chunks (`tier1_chunks`) and are not meaningful end to end;
  - they run in Tier 1 only and **must not enter the Tier 2 denominator**.
  - They are marked "Tier 1 only (answer_only)" in the review sheet's `eligibility` column.
- **If the reviewer excludes cases,** the denominators change only through the documented correction procedure below, never by silently dropping cases.

## Rules after freezing
1. **No changes after results.** The held-out dataset, the split logic, the scoring rules (`score_generic`, `eval/answer_scoring.py`) and these thresholds **must not be changed after any held-out result is seen**.
2. **Dataset corrections before evaluation.** A legitimate correction found by the independent reviewer, whether a revised expected answer, fixed evidence or an exclusion, must be:
   - made in a separate, documented change that lists every case affected and the reason, as recorded in the review sheet;
   - re-validated with `eval/phase35/validate.py`, which must print `VALID`;
   - frozen again by recording new SHA-256 hashes of `data_A..D.py`.

   All of this happens **before** the held-out run. If a correction changes an eligible-case count, the minimum passing count is recomputed with the **same frozen percentages** (85% / 65%, rounded **up** to the next whole case) and recorded in that change, still before evaluation.
3. **Run once.** The held-out evaluation is run once per tier, with no re-runs to improve a score and no tuning of prompts, retrieval or configuration in between.
4. **Separate approval.** Held-out execution still requires **separate, explicit approval from the user after the independent human review is complete**. This freeze document does not authorise any run.

## Frozen inputs at the time of freezing (SHA-256)
| File | SHA-256 |
|---|---|
| `eval/phase35/data_A.py` | `b4d8b3516a777c59a280d6cb9b5bbb23aefaf40459130bf46fc4e1d8c51cbf65` |
| `eval/phase35/data_B.py` | `a3434f5b6ad1fbd3da30f2413f9f855595f6ec09278afb296b28e5f7d82b1778` |
| `eval/phase35/data_C.py` | `67bc2b5e1ea01e27516c6fb61809efe6c90573630498e3384408dd8c4ad3b647` |
| `eval/phase35/data_D.py` | `655be7b3c60cd13af50c2e15d1c9346b727ad3f57998233ffebc43d934b2306e` |
| `eval/phase35/run_eval.py` (split and scoring) | `3b066a5b3b4c1de908cb5a555db17762af2bd70606f0854d5f2ba0ce7106e989` |
| `eval/answer_scoring.py` | `c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af` |
| `eval/phase35/validate.py` | `1727a33421202da3bd0d52aabcf0bf11dd9515c16c73a8b10e385aa356fe1a7d` |

## Related documents
- The review package is `docs/remediation/heldout_review/` (README, `heldout_review_sheet.csv`, `source_pdfs/`, `source_pages.md`).
- The development thresholds are frozen separately and already used: Tier 1 ≥ 41/47 (passed with 41/47) and Tier 2 ≥ 28/42 (passed with 28/42). See `STAGE_B_DEV_LIVE_EVALUATION_REPORT.md`.
- The pre-registration gap `P35-04` is recorded in `MASTER_GAP_REGISTER.md` as "NOT STARTED". That register was not edited in this documentation-only task; this file is the record that resolves it.
