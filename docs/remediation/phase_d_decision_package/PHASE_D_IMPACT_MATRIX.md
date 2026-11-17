# Phase D impact matrix (proposals only; nothing applied)

**How these figures were obtained:**
- The 15 proposals were applied to an **in-memory copy** of the dataset (`scorer_regression_probes.py --validate-proposals`).
- Result: `validate.py` → **VALID**; split membership (`split_sha256`) unchanged; `dataset_sha256` changes, as any correction does.
- No file was modified.

**Not inferred:** no pass rate, no new threshold, no real-system improvement. The probes show only what the frozen scorer does with a given answer string.

## Held-out proposals (TA-01 – TA-11)

| Issue | Case | Category now → proposed | Tier impact | Facts change | Forbidden change | v1 result can change | Needs v2 | Denominators change | Category counts change |
|---|---|---|---|---|---|---|---|---|---|
| TA-01 | A-conflict-03 | conflicting → **multi_page** | **T1 + T2** | yes (48 h only) | no | **yes**: update-aware answers pass, 24-hour-only fails | no (v2 only to reject the 24/48 hedge) | no | **yes** |
| TA-02 | D-conflicting-02 | conflicting → **multi_page** | **T1 + T2** | yes (31 Nm only) | no | **yes**: erratum-aware answers pass, 28 Nm fails | no (v2 only to reject the 28/31 hedge) | no | **yes** |
| TA-03 | B-follow-01 | follow_up (same) | T1 + T2 | no | yes (`2,000` removed) | yes: correction passes | no | no | no |
| TA-04 | C-direct-06 | direct_factual (same) | T1 + T2 | no | yes (`90 days` removed) | yes: fuller answer passes | no | no | no |
| TA-05 | C-multi_chunk-03 | multi_chunk (same) | T1 + T2 | yes (G1 tightened) | no | yes: one-visit answer now fails | no | no | no |
| TA-06 | A-multichunk-01 | multi_chunk (same) | T1 + T2 | no (question reworded) | no | marginal: removes the echo; negated answers still pass | **yes**, for full effect (fact-negation guard) | no | no |
| TA-07 | D-injection-03 | prompt_injection (same) | T1 + T2 | yes (interim boundary set) | no | yes: 15 / 25 / 1.5 l now fail | **yes**, recommended (proper boundaries) | no | no |
| TA-08 | A-multipage-02 | multi_page (same) | T1 + T2 | yes (3 groups) | no | yes: patient-as-escort fails | no | no | no |
| TA-09 | D-multi_page-02 | multi_page (same) | T1 + T2 | yes (+HSE officer group) | no | yes: one-approver answer fails | no | no | no |
| TA-10 | B-direct-04 | direct_factual (same) | T1 + T2 | yes (both dates) | no | yes: single-date answer fails | no | no | no |
| TA-11 | C-multi_page-01 | multi_page (same) | T1 + T2 | yes (battery, filter split) | no | yes: battery-only answer fails | no | no | no |

All 11 held-out cases are `tier=both`, so every proposal affects Tier 1 and Tier 2.

**Held-out counts:**

| | Current | With TA-01 + TA-02 |
|---|---|---|
| Cases | 113 | 113 |
| Tier 2 eligible | 106 | 106 |
| answer_only | 7 | 7 |
| conflicting / multi_page | 7 / 12 | **5 / 14** |
| expect_conflict | 7 | **5** |

**Frozen thresholds:** unchanged and **not** to be changed. Tier 1 ≥ 97/113 (85%); Tier 2 ≥ 69/106 (65%).
- Category counts are not part of the threshold rule.
- The denominators change only through exclusions, and none are proposed.

**Manifest:** any approved change alters `data_*.py`, `dataset_sha256` and the dataset-wide `category_counts`. It therefore needs a documented re-freeze; the current manifest will (correctly) refuse.

**Direction of effect (qualitative only):**
- TA-01 – TA-04 remove **false-failure** traps: correct answers that v1 fails.
- TA-05 – TA-11 remove **false-pass** traps: wrong or incomplete answers that v1 passes.
- So the corrections can move a real score **either way**. The net effect on any real run is unknown and is not estimated.

## Development proposals (TA-D1 – TA-D4), separate

| Issue | Case | Category now → proposed | Facts / sources change | v1 result can change | Needs v2 | Held-out impact |
|---|---|---|---|---|---|---|
| TA-D1 | D-conflicting-01 | conflicting → multi_page | facts → 750 h | yes | no | **none** |
| TA-D2 | D-conflicting-03 | conflicting → multi_page | facts → 21 days | yes | no | **none** |
| TA-D3 | D-conflicting-04 | conflicting → multi_page | facts → USD 64 (bare `58` removed) | yes | no | **none** |
| TA-D4 | B-comp-04 | compound (same) | + gold source Calder p4 | citation metrics only; `correct` unchanged | **yes** (TS-1 "not recorded") | **none** |

**Development counts:**

| | Current | With TA-D1 – TA-D3 |
|---|---|---|
| Cases | 47 | 47 |
| Tier 2 eligible | 42 | 42 |
| conflicting / multi_page | 6 / 5 | **3 / 8** |

- **Held-out effect:** none. The development changes touch no held-out case, denominator or threshold.
- **Historical dev thresholds:** 41/47 and 28/42 are records of past runs and are not re-decided.
- **Historical dev results:** they stay labelled as results on the pre-correction dataset, as already established for A-conflict-02.

**Dataset-wide category counts** (all 160 cases; recorded in the manifest):

| Category | Current | If all 15 proposals are approved |
|---|---:|---:|
| conflicting | 13 | 8 |
| multi_page | 17 | 22 |
| All other categories | unchanged | unchanged |

## Scorer v2 (if adopted): impact class only

- **Scope:** v2 changes the scoring of every case through TS-4 normalisation.
- **Most affected categories:** partial (6 held-out), abstain (20), conflicting (7, or 5 after TA-01/02) and injection (10).
- **Direction:** like the dataset corrections, v2 removes both false failures and false passes, so the net direction is unknown.
- **Prerequisites:** if v2 becomes the acceptance scorer, it must be frozen before any held-out result. The owner may then need to revisit the thresholds (not proposed here).
