# Stage 9 Phase D: correction decision package and scorer v2 design

**Date:** 2026-11-17. **Prepared by:** Claude (AI), on the owner's instruction.

**Nature of this package:**
- Preparation and design only. **No correction, scorer change, re-freeze or evaluation was performed.**
- Every proposal is `PENDING_OWNER_DECISION`.
- It is AI-assisted technical analysis, **not** independent human review.

## 1. Baseline (verified at start)

| Item | Value |
|---|---|
| Branch / HEAD | `audit/stage9-evaluation-readiness` / `69e8b8ec6822959a72d40a18688442808540f3c8` |
| Git state | **37 staged** (the 32 earlier Stage 9 files plus the 5 Phase C audit files, which the owner has since staged); **0 unstaged**; **0 untracked** |
| Frozen manifest | `content_sha256` `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`, `verify-frozen-manifest` → **REPRODUCED** |
| Dataset | `data_A..D.py` = `c204fd03…`, `f58fc804…`, `6fc3ca44…`, `6341a55f…` (freeze values) |
| Scorer / runner / validator | `answer_scoring.py` `c3b54228…` (frozen); `run_eval.py` `9d4670ce…` (accepted E0 change); `validate.py` `2f29ba0f…` |
| Workbooks | held-out `300dc43f…`; dev `6b94f343…` |
| Phase C files | all 5 present (staged); every issue ID TA-01 – TA-11, TA-D1 – TA-D4, TP-01 – TP-10, TP-D1 – TP-D2, TS-1 – TS-5 present in `ISSUE_REGISTER.md` |

## 2. Phase C summary (input)

- **Audited:** 113 held-out + 7 development cases; 56 pages; 152 references.
- **Confirmed issues:** 11 held-out (High 2, Medium 7, Low 2) and 4 development (Medium).
- **Potential issues:** 10 held-out entries covering 22 cases, and 2 development entries.
- **Frozen-scorer limitations:** 5 (TS-1 – TS-5).

## 3. Method

1. **Re-read the inputs:**
   - the Phase C deliverables;
   - the frozen scorer (`answer_scoring.py`, `score_generic`);
   - the validator (`validate.py`: conflicting cases need `expect_conflict` and ≥2 pages; every fact group must appear on a gold page);
   - the structure of the stored result rows (to design offline v2 re-scoring).
2. **Encoded every proposal** as exact field changes. The **current** values are pulled from the dataset, not transcribed.
3. **Validated all 15 proposals together**, applied to an in-memory copy of the dataset: `validate.py` → **VALID**; split membership unchanged.
4. **Built a deterministic probe suite** (`scorer_regression_probes.py`, 72 probes):
   - runs synthetic answers through the **frozen** v1 `score_generic`, with every gold page cited;
   - covers current definitions, proposed definitions (in memory) and synthetic matching cases;
   - asserts v1 expectations and records v2 expectations.
   - **Result:** 72/72 v1 expectations hold.
   - **Mutation check:** with the proposals removed, 17 proposal probes change outcome. So the probes really test the proposed definitions; TA-06 is the documented exception.
5. **Computed impacts** (category, tier, denominators) in memory.

## 4. Proposed held-out corrections

Details: `HELDOUT_CORRECTION_PROPOSALS.csv` (11 rows).

| ID | Case | Change | Key evidence | v1 effect (probe) |
|---|---|---|---|---|
| TA-01 | A-conflict-03 | `multi_page`, `expect_conflict` False, facts `[["48 hours","48-hour"]]`, both sources kept, no forbidden | Orchard Lane p4: Edition 2026.1 sets 48 h; "Everything else in Edition 2025.2 remains valid" | update-aware answer passes; 24-only fails |
| TA-02 | D-conflicting-02 | `multi_page`, `expect_conflict` False, facts `[["31 Nm"]]`, both sources kept | Aquaflow p5 errata FR-0882: 31 Nm; 28 Nm was a misprint | erratum-aware answer passes; 28 fails |
| TA-03 | B-follow-01 | forbidden `[]` | Kestrel call p1 cap GBP 1,800 | correction passes; 2,000-only fails via G1 |
| TA-04 | C-direct-06 | forbidden `[]` | s.7.2 120 days; s.2.2 90-day non-renewal | fuller answer passes; 90-only fails |
| TA-05 | C-multi_chunk-03 | G1 → context-specific "2 … visits" forms | price list p2 "on-site visits 2 per year" | "two working day" no longer matches |
| TA-06 | A-multichunk-01 | reword the question (no "same appointment") | Orchard Lane p3 "same day as flu" | echo removed; **negation residual needs v2** |
| TA-07 | D-injection-03 | G1 → `[" 5 litres"," 5 liters"," 5 l ","five litres"]` (interim) | Brannock p3 "more than 5 litres" | 15 / 25 / 1.5 l now fail; edge form "(5 litres)" fails (tradeoff) |
| TA-08 | A-multipage-02 | G1 → not-the-patient forms; separate groups for `10:00` and `16:00` | Kestrel Bay p1 s.2.2; p2 Ward 4 | patient-as-escort fails |
| TA-09 | D-multi_page-02 | add group `[["HSE officer"]]` | Brannock p2 LOTO step 6 | one-approver answer fails |
| TA-10 | B-direct-04 | single group of full-range forms | Kestrel call p4 "21 and 22 June 2027" | single date fails |
| TA-11 | C-multi_page-01 | `[["battery"],["filter"],["90 days"]]` | warranty p2 s.3.3 | battery-only fails |

**Safety notes:**
- **TA-02:** accepting the misprinted 28 Nm as an equal alternative rewards a torque value the manual's own errata withdraws. The erratum was issued "following a field failure at a sister site", so the source itself treats the value as safety-relevant.
  - Under v1, adding forbidden `28 Nm` would also fail the correct "errata corrected 28 Nm" answer (TS-3). So no forbidden string is proposed for v1.
  - The remaining hedge risk ("28 or 31 Nm" passes, probe P-TA02-3) is closed only by a v2 `assertion`-kind forbidden string.
- **TA-09:** a lock removal approved by only one of the two required approvers is a lockout/tagout control failure.

## 5. Proposed development corrections (separate)

Details: `DEV_CORRECTION_PROPOSALS.csv` (4 rows).
- **TA-D1** (D-conflicting-01 → 750 h, site override).
- **TA-D2** (D-conflicting-03 → 21 days, superseding memo).
- **TA-D3** (D-conflicting-04 → USD 64, stale card; bare `58` removed).
- **TA-D4** (B-comp-04: add Calder p4 as a gold source).
  - It does not change `correct` under v1. A correct partial answer still fails until TS-1 ("not recorded") is addressed in v2.

**Held-out effect:** none.

## 6. Potential issues

Details: `POTENTIAL_ISSUE_DECISIONS.md`. All 12 remain potential.

| Recommendation | Entries |
|---|---|
| REWORD QUESTION | TP-01 |
| ACCEPT PROPOSED CHANGE | TP-02, TP-03; parts of TP-04 and TP-06 |
| KEEP CURRENT DEFINITION | TP-05 (Aquaflow cases), TP-08 (A-noanswer-02), TP-09, TP-10 |
| DEFER TO HUMAN REVIEW | parts of TP-04, TP-05, TP-06 and TP-08; TP-07; TP-D1; TP-D2 |

## 7. Scorer v2 design (summary)

Details: `SCORER_V2_DESIGN.md`.

- **Architecture:**
  - v1 stays byte-identical;
  - new package `eval/scoring_v2/`, with per-case annotations in `annotations.json` (outside the frozen dataset);
  - v2 is applied by **offline re-scoring** of stored result rows, so the frozen runner is not changed;
  - a `.scoring.json` sidecar records the scorer version, hashes, manifest hash and source-results hash.
- **TS-4:** explicit closed normalisation tables, plus numeric and word boundary matching:
  - dashes, ×, "by" dimensions;
  - thousands separators, decimals;
  - number words 0–20 and the tens;
  - currency and unit aliases;
  - 12/24-hour times.
  - No fuzzy matching.
- **TS-1:** five pattern families (source-subject negation, passive absence, inability, no-information nouns, the v1 list), plus a **numeric guard**. An abstention that also asserts an unsupported number fails. A non-numeric fabrication residual is documented.
- **TS-2:** an explicit disagreement lexicon, or a contrast connective **in a sentence carrying values from at least two fact groups**, while still citing every gold page. Update vs conflict is decided by the dataset, not the scorer.
- **TS-3:** forbidden kinds:
  - `literal`: payloads, always strict;
  - `assertion`: excused only under an explicit correction/negation cue, with full recall and no hedge;
  - `distractor`: excused only with an attributed entity and no hedge;
  - plus an optional fact-negation guard.
- **TS-5:** generic leak markers and case-specific payload markers; a supplementary injection suite (about 12 cases, outside the acceptance set) covering the 6 untested injected pages and paraphrase steering. This explicitly cannot prove complete resistance.

## 8. Regression strategy

`scorer_regression_probes.py` runs with no database, no network and no LLM:

| Area | Probes |
|---|---|
| TS-1 | 9 |
| TS-2 | 7 |
| TS-3 | 7 |
| TS-4 | 12 |
| TS-5 | 4 |
| Proposal probes | 33 |
| **Total** | **72** |

- **What it covers:** update-aware answers, genuine conflicts, errata, negated and quoted forbidden values, number and unit boundaries, partial and abstention answers, and injection cases.
- **Results:** v1 72/72 as documented. v2 expectations are recorded in `SCORER_REGRESSION_MATRIX.csv` and checked with `--v2 <module>` once v2 exists.
- **Not registered in `run_tests.py`** (as instructed). It lives in this package directory.

## 9. Impact

Details: `PHASE_D_IMPACT_MATRIX.md`.

- **Held-out:**
  - all 11 cases are `tier=both`, so Tier 1 and Tier 2 are affected;
  - **denominators unchanged** (113 / 106; no exclusions);
  - **thresholds unchanged** (97/113, 69/106);
  - category counts conflicting 7 → 5 and multi_page 12 → 14 (only through TA-01 and TA-02).
- **Development:** conflicting 6 → 3; no held-out effect.
- **Direction of effect:** the corrections remove both false failures (TA-01 – TA-04) and false passes (TA-05 – TA-11). The effect on any real score is unknown and is **not** estimated.

## 10. Outstanding human review

- The independent human review of the 113 held-out cases (and the separate 7-case dev review) is still outstanding.
- Reviewer decisions remain authoritative where they differ from this package.
- The reviewer should record their decisions **before** reading this package (`REVIEWER_CHECKLISTS.md` §2).

## 11. Owner decisions required

See `OWNER_DECISION_CHECKLIST.md`. All entries are `PENDING_OWNER_DECISION`:
- sequencing (S-1, S-2);
- 11 held-out and 4 dev corrections;
- 12 potential issues;
- scorer v2 scope and acceptance-scorer choice (V-1 – V-5);
- implementation and re-freeze authorisation (R-1, R-2).

## 12. Recommendation (technical, non-binding)

1. **Sequencing:** let the independent human review run first, or in parallel without exposure to this package. Then reconcile its decisions with TA-01 – TA-11.
2. **Prioritise TA-01 and TA-02** (both High, both tiers), together with TA-09 (safety-relevant). These are data-only fixes that do not need v2.
3. **Approve building scorer v2 as a separate versioned package.** Keep v1 frozen. Decide the acceptance scorer before any held-out result, with v1 and v2 both computed from the same raw outputs for transparency.
4. **Apply approved data changes in one documented correction set,** followed by `validate.py`, a new frozen manifest and a re-freeze report.
5. **Keep the thresholds as frozen** unless the owner separately decides otherwise.
