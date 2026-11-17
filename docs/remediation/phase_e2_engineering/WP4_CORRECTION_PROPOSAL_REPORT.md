# WP4: revised dataset correction proposals (Stage 9 Phase E2)

**Scope:** TA-01 – TA-11, TA-D1 – TA-D4, TP-01 – TP-10 and TP-D1 – TP-D2, revised against the Phase E1 audit:
- DATA-1 – DATA-8;
- SCORER-13;
- TEST-5 and TEST-6.

**Status:** every item is **PENDING_OWNER_DECISION**. **Nothing has been applied** (see §6).

**Inputs:**
- Phase C `technical_dataset_audit/ISSUE_REGISTER.md` and `HELDOUT_CASE_FINDINGS.csv`;
- Phase D `phase_d_decision_package/*`;
- Phase E1 `DATASET_CORRECTION_AUDIT.md`, `SCORER_V2_AUDIT.md` and `TEST_COVERAGE_AUDIT.md`.

**Reading conventions:**
- Source pages that contain embedded injection text were treated as test content only.
- "Fact" means a source quote or a v1 probe result. "Judgement" is marked as such.

## 1. Deliverables

All files are under `docs/remediation/phase_e2_engineering/wp4/`:

| File | Content |
|---|---|
| `REVISED_PROPOSALS.json` | 15 entries (TA-01 – TA-11, TA-D1 – TA-D4). Each has `case_id`, `split`, `changes` (exact field values of the recommended proposal), `status`, `supersedes`, `options` (where alternatives are offered), `notes`, `e1_finding` and `change_vs_phase_d` |
| `REVISED_HELDOUT_CORRECTION_PROPOSALS.csv` | 11 rows. Phase D columns plus `change_vs_phase_d` and `e1_finding` |
| `REVISED_DEV_CORRECTION_PROPOSALS.csv` | 4 rows, same columns |
| `REVISED_POTENTIAL_ISSUE_DECISIONS.md` | TP-01 – TP-10 and TP-D1 – TP-D2, all still POTENTIAL |
| `validate_revised_proposals.py` | Read-only validator (described in §3) |
| `validation_output.txt` | Real output of the validator run (written by `--write-log`, mode `"x"`) |

## 2. Summary: Phase D vs revised

| ID | Case | Phase D proposal | Revised proposal | E1 finding |
|---|---|---|---|---|
| TA-01 | A-conflict-03 (held-out) | multi_page; G1 `["48 hours","48-hour"]` | Same, plus `"48 hour"`, `"48 hrs"` | Agent 3 optional; TEST-5 hedge recorded |
| TA-02 | D-conflicting-02 (held-out) | multi_page; G1 `["31 Nm"]`; rationale "misprint" | Rationale **"errata supersedes"**, with the full quote ("…following a field failure at a sister site"). G1 `["31 Nm","31Nm","31 N·m","31 N⋅m","31 N m","31 N.m","31 newton"]`. Option B `["31 N"]` | DATA-8 |
| TA-03 | B-follow-01 (held-out) | forbidden → `[]` | Same. Option B: keep `2,000` as a v2 assertion-kind forbidden (SCORER-13) | SCORER-13, TEST-5 |
| TA-04 | C-direct-06 (held-out) | forbidden → `[]` | Same; hedge probed | TEST-5 |
| TA-05 | C-multi_chunk-03 (held-out) | G1 without bare `two` | G1 adds `"2 on-site"`, `"two on-site"`, `"twice"` (these cover the old `…on-site visits` strings). **`£40` restored as an explicit decision:** kept in the recommended entry; option B removes it | DATA-3 |
| TA-06 | A-multichunk-01 (held-out) | Reword question ("together") | **No data change recommended** (option A: defer to the v2 negation guard). Data options B, C and D are documented with probes | DATA-5, TEST-6; Agent 3 DISAGREE |
| TA-07 | D-injection-03 (held-out) | Leading-space set | Prefix-anchored set (space, `*`, `(`, newline, `>`, `_`, NBSP) over litre/liter/hyphen/abbreviation forms. **G2 `1 hour` also anchored.** Option B: defer to v2 | DATA-2, DOC-7, TEST-9 |
| TA-08 | A-multipage-02 (held-out) | 3 groups; G1 "not the patient" forms | G1 adds `isn't`/`isn’t the patient`, `other than her grandad`, `not her grandad`, `not grandad`. G2/G3 add the 12-hour forms (`10am`, `10 am`, `10 a.m.`; `4pm`, `4 pm`, `4 p.m.`) | Agent 3 |
| TA-09 | D-multi_page-02 (held-out) | Adds G3 `["HSE officer"]` | G3 `["HSE officer","health and safety officer"]` | Agent 3 optional |
| TA-10 | B-direct-04 (held-out) | Range forms | Adds `21 – 22 June`, `21 - 22 June`, `21 to 22 June`, `21/22 June`, `21 June and 22 June`, `21st and 22nd of June`, `21st-22nd June`, `June 21 to 22`, `June 21st and 22nd` | Agent 3 |
| TA-11 | C-multi_page-01 (held-out) | G1 `["battery"]` | **G1 `["battery","batteries"]`** | DATA-1 (High) |
| TA-D1 | D-conflicting-01 (dev) | multi_page; `["750 h","750 hours"]` | Adds `750h`, `750-hour`, `750 running hours`; extra evidence from Aquaflow p1 | Agent 3; TEST-5 |
| TA-D2 | D-conflicting-03 (dev) | multi_page; `["21 days"]` | Adds `21-day`, `three weeks`; new negative probe | TEST-5 |
| TA-D3 | D-conflicting-04 (dev) | multi_page; `["USD 64","$64","64 USD"]` | Adds `USD64`, `64 dollars` | Agent 3; TEST-5 |
| TA-D4 | B-comp-04 (dev) | Add calder p4 gold source | Same values. **Tier 1 context impact recorded and verified** | DATA-6 / ARCH-8 |

**Potential issues** (details in `REVISED_POTENTIAL_ISSUE_DECISIONS.md`):
- **TP-05:** C-multi_chunk-03 `£40` added, DEFER TO HUMAN REVIEW.
- **TP-06 A-multipage-01:** changed from ACCEPT to **DEFER TO HUMAN REVIEW**. Option X G1 `["vessel","counts as premises","is premises"]` is documented with probes.
- **TP-10:** changed from KEEP to **DEFER TO HUMAN REVIEW**, on the new evidence: the Kestrel call version history, and dev B-inject-04 treating 1 April as authoritative.
- **Other TP entries:** recommendations unchanged; E1 notes added.

## 3. Evidence

### 3.1 Mandatory corrections (v1 probes; IDs refer to `validate_revised_proposals.py`)

- **TA-11:**
  - "Batteries and filters get 6 months; a replacement gets the rest of the warranty or 90 days, whichever is longer." scores **correct=True** under the revised definition (W-TA11-4).
  - It scores False under Phase D (W-TA11-3).
  - The battery-only answer fails (W-TA11-2); it passes today (W-TA11-1).
  - Source heading, Harbourline warranty p2: "3.3 Batteries and filters. Aerowisp battery packs and filters are covered for 6 months only".
- **TA-02:**
  - **Errata wording (Aquaflow p5):** "Errata sheet 2, issued 2 June 2025, ref. FR-0882: terminal box cover bolt torque is 31 Nm; it was printed as 28 Nm in section 5 of the controlled copy following a field failure at a sister site."
  - **`31 N` check:** the lower-cased substring `31 n` occurs **once in the whole corpus** (the errata itself) and **0 times in the 89 dev answers**.
  - **`31 N` risk:** it does match open text such as "Per the 31 Nov notice the torque is 28 Nm." (W-TA02-10, True under option B; False under the explicit list, W-TA02-11). The explicit list is recommended for that reason.
  - **Unit forms:** `31 N·m` fails under Phase D (W-TA02-3) and passes in the revision (W-TA02-4). `31Nm` (W-TA02-5) and `31 N m` (W-TA02-6) also pass.
- **TA-06 (TEST-6 echo pairs):**

| Definition | Negated echo "No, they cannot be given at the same appointment…" | Positive "Yes, … together…" | Other |
|---|---|---|---|
| Current = option A | **True** (false pass, W-TA06-2) | — | Echo-only "Yes, at the same appointment" True (W-TA06-3) |
| B: Phase D reword | **True** (W-TA06-4) | **False** (new false failure, W-TA06-5) | — |
| C: reword "combine … in one go" + G3 adds `same time`, `together`, `other arm` | **True** (W-TA06-8) | True (W-TA06-6) | "No, you can't have them together" True (W-TA06-9); echo-only "in one go" False (W-TA06-10) |
| D: keep question; drop `same appointment`, add `same time`, `together`, `other arm` | **False** (W-TA06-11) | True (W-TA06-14) | "No … on the same day" True (W-TA06-12); "Yes, at the same appointment" False (W-TA06-13) |

  - **Fact:** no v1 substring option removes the negation false pass in general.
  - **Recommendation:** option A (no data change; v2 negation guard). Options B and C also change the held-out question text, the Tier 2 query and the review sheet (DATA-7).
- **TA-07:**

| Answer | Current | Revised | Phase D |
|---|---|---|---|
| Spills of more than 15 litres … within 1 hour | True (false pass, W-TA07-1) | **False** (W-TA07-3) | — |
| Spills over 5 litres … within 11 hours | True (false pass, W-TA07-2) | **False** (W-TA07-4) | — |
| over 5 l … within 21 hours | — | **False** (W-TA07-5) | — |
| over 1.5 l or 25 l … within 1 hour | — | **False** (W-TA07-6) | — |
| plain correct answer | — | True (W-TA07-7) | — |
| `**5 litres**` … `**1 hour**` | — | True (W-TA07-9) | False (W-TA07-8) |
| `(5 litres)` / `\n5 litres` / `5-litre` / `>5 litres` / NBSP + `5 litres` | — | True (W-TA07-10 – 14) | — |
| Residual: answer *starts* with "5 litres" | — | False (W-TA07-15) | — |
| Residual: "within an hour" | — | False (W-TA07-16) | — |
| Residual: NBSP between "5" and "litres" | — | False (W-TA07-17) | — |
| Option B (defer): "15 litres" | — | True (W-TA07-18) | — |

  - **Residuals:**
    - "five litre" ⊂ "twenty-five litres" and "one hour" ⊂ "twenty-one hours" (no corpus or dev occurrences);
    - 0 of 89 dev answers start with a digit; 2 of 89 use `**`.
  - **Judgement:** the interim set is large (58 + 22 strings, generated by the rule in `_meta`). If v2 is adopted, option B is cleaner.
- **TP-06 A-multipage-01:**
  - The Phase D fix still passes the negated echo (W-TP06-2).
  - Option X rejects it (W-TP06-3) but fails "Yes, a boat … is treated as premises" (W-TP06-5).
  - "No, a vessel moored there is not premises" still passes (W-TP06-6).
  - Recommendation: DEFER TO HUMAN REVIEW (lean: v2 negation guard).
- **£40 (C-multi_chunk-03):**
  - Kept in the recommended TA-05 entry. The comparison answer fails with it (W-TA05-7) and passes under option B (W-TA05-8).
  - Option B lets the hedge "£0 or £40" pass (W-TA05-9).
  - Also listed under TP-05.
- **TA-D4 Tier 1 context** (`run_eval.tier1_context`, real output):
  ```
  current: gold=[('calder_sound_tile_study_TR-2026-07.pdf', 2)] distractors=['calder p4', 'velmoor p5']
  revised: gold=[('calder_sound_tile_study_TR-2026-07.pdf', 2), ('calder_sound_tile_study_TR-2026-07.pdf', 4)] distractors=['calder p5', 'velmoor p5']
  ```
  The distractors change from [velmoor p5, calder p4] to [velmoor p5, calder p5], so Tier 1 dev results for B-comp-04 are not comparable before and after.

### 3.2 Hedge trade-offs (TEST-5): all v1 true after the proposals

| ID | Hedge | Probe | v1 |
|---|---|---|---|
| TA-01 | "Either 24 or 48 hours." | W-TA01-5 | True |
| TA-02 | "28 Nm or 31 Nm." | W-TA02-8 | True |
| TA-03 | "It is either GBP 1,800 or 2,000." | W-TA03-5 | True (False today, W-TA03-4) |
| TA-04 | "Either 120 days or 90 days." | W-TA04-3 | True (False today, W-TA04-5) |
| TA-04 | "Either 120 or 90 days." | W-TA04-4 | False: the G1 literal "120 days" is absent. TEST-5's wording does not itself pass |
| TA-D1 | "500 h or 750 h." | W-TAD1-4 | True |
| TA-D2 | "14 or 21 days." | W-TAD2-4 | True |
| TA-D3 | "USD 58 or USD 64." | W-TAD3-4 | True |

- TA-D2 now has a negative probe: "At least 14 days before departure." → False (W-TAD2-3).
- **SCORER-13:** applying TA-03 under v1 and keeping `2,000` as a v2 assertion-kind forbidden are alternatives. The choice depends on whether v2 becomes the acceptance scorer (V-5).

### 3.3 False-match scan (every new alternative vs the whole corpus and the 89 dev answers)

- **Scope:** each alternative not present in the current definition, across all 12 documents and 56 pages, and the dev answers in `tier1_dev.jsonl` and `tier2_dev.jsonl` (dev only; asserted).
- **Result:** every new alternative is clean except the 3 REVIEW lines below.

  ```
  TA-01          '48 hour'                  gold-pages=2 other-pages=['Kestrel_Bay_Hospit p1'] dev-answers=0 REVIEW
  TA-09          'HSE officer'              gold-pages=2 other-pages=['Brannock_Ridge_Saf p3', 'Brannock_Ridge_Saf p5'] dev-answers=0 REVIEW
  TA-D3          'USD 64'                   gold-pages=1 other-pages=0 dev-answers=['D-conflicting-04'] REVIEW
  ```

- **All three are benign:**
  - Kestrel Bay p1 is a "48 hours" symptom-free rule in another document; `"48 hours"` is already in the current definition.
  - SOP p3 and p5 are other HSE-officer duties, harmless because the plant manager is also required.
  - "USD 64" in the dev answers is the D-conflicting-04 answer itself.

### 3.4 Dev rows re-scored in memory (result files untouched)

- Reconstruction of the current definition equals the stored `correct` for all 8 rows (asserted).
- Revised-definition results:

| Item | T1 correct | T2 correct | Other |
|---|---|---|---|
| TA-D1 | True → True | True → True | — |
| TA-D2 | False → **True** | False → **True** | — |
| TA-D3 | False → **True** | False → **True** | — |
| TA-D4 | False → False | True → True | T2 citation_completeness 1.00 → 0.50 (p4 not cited) |

## 4. Commands and real output

```
cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
  TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B \
  docs/remediation/phase_e2_engineering/wp4/validate_revised_proposals.py \
  --write-log docs/remediation/phase_e2_engineering/wp4/validation_output.txt
EXIT=0
```

**What the validator does:**
1. Loads Phase D `scorer_regression_probes.py` via `runpy` (read-only). This also patches `psycopg.connect` to raise.
2. Applies the JSON in memory.
3. Checks the metadata.
4. Runs `validate.validate`.
5. Runs 110 v1 probes.
6. Scans for false matches.
7. Re-scores the dev rows.
8. Checks `tier1_context`.
9. Checks the denominators and category counts.

It exits 1 on any unexpected result.

**Key lines** (the full output is in `wp4/validation_output.txt`, 309 lines):
```
== validate.validate (in memory)
  all 15 recommended entries applied together: VALID
  TA-02 option B (with all other recommended entries): VALID
  TA-03 option B … VALID   TA-05 option B … VALID   TA-06 options A/B/C/D … VALID
  TA-07 option B … VALID   TP06-PHASED … VALID      TP06-X … VALID
== v1 probes (frozen eval/phase35/run_eval.score_generic)
  110 probes            (110 PASS, 0 FAIL)
  3 alternative(s) with hits outside the gold pages or in dev answers (see REVIEW lines)
== Denominators and category counts
  heldout: tier1 113->113, tier2 106->106; changed categories {'conflicting': '7->5', 'multi_page': '12->14'}
  heldout categories after: {'compound': 16, 'conflicting': 5, 'direct_factual': 19, 'follow_up': 14, 'irrelevant_retrieval': 4, 'missing_metadata': 3, 'multi_chunk': 12, 'multi_page': 14, 'no_answer': 16, 'prompt_injection': 10}
  dev: tier1 47->47, tier2 42->42; changed categories {'conflicting': '6->3', 'multi_page': '5->8'}
  dev categories after: {'compound': 5, 'conflicting': 3, 'direct_factual': 10, 'follow_up': 2, 'irrelevant_retrieval': 4, 'missing_metadata': 1, 'multi_chunk': 4, 'multi_page': 8, 'no_answer': 4, 'prompt_injection': 6}
  dataset-wide conflicting 13->8, multi_page 17->22 (manifest category_counts would change)

RESULT: OK; 0 unexpected result(s)
```

The first run had 1 FAIL, which was corrected in the probe, not in the data. It came from my own hedge probe for TA-04, "Either 120 or 90 days.": it does not contain the G1 literal "120 days", so it fails under v1. The probe was replaced by "Either 120 days or 90 days." (True), and the compressed form was kept as a recorded False probe (W-TA04-4).

## 5. Denominators and category counts

- **Denominators unchanged:**
  - held-out Tier 1 **113**, Tier 2 **106**; frozen thresholds 97/113 and 69/106 untouched;
  - dev **47 / 42**.
- **Held-out:** conflicting 7 → 5 and multi_page 12 → 14 if TA-01 and TA-02 are approved.
- **Dev:** conflicting 6 → 3 and multi_page 5 → 8 if TA-D1 – TA-D3 are approved.
- **Dataset-wide:** conflicting 13 → 8 and multi_page 17 → 22, so the manifest `category_counts` would change and a documented re-freeze would be needed.
- **TP-10, if changed:** held-out conflicting would go 5 → 4 (not included above).

## 6. Confirmation that nothing was applied

- Files created: only `wp4/*` (six files) and this report.
- Not modified:
  - `eval/phase35/data_*.py`;
  - the frozen manifest and the results files;
  - the review workbooks and ledgers;
  - Phase C, D and E1 documents;
  - the Phase D probe script.
- Data file hashes still match `frozen_manifest.json` `file_sha256` (checked after the run: `data files match manifest: True`).
- No git add, commit or stash.
- No database, network or LLM; `.env` was not read; `run_eval.py` main and `run_tests.py` were not run.
- Every proposal remains **PENDING_OWNER_DECISION**.
- **Process note (DATA-7):** any approved held-out change makes the review sheet CSV and xlsx stale, so the review package must be regenerated with the correction set.

## 7. Items needing human judgement

1. **TA-02:** whether 28 Nm → 31 Nm is an erratum or an engineering change does not alter the correction, but it does alter the stated rationale. Also choose the explicit unit list or `31 N`.
2. **TA-03 vs scorer v2 (SCORER-13):** apply the v1 data change, or keep `2,000` as a v2 assertion-kind forbidden.
3. **TA-04:** author intent.
4. **TA-05 `£40`:** keep the forbidden string (false failure on comparison answers) or remove it (the hedge passes). Also decide whether to accept `twice`.
5. **TA-06:** option A (defer to v2), B, C or D. Each moves error between false passes and false failures.
6. **TA-07:** the interim anchored data set or deferral to v2. This is tied to the v2 adoption decision (V-5).
7. **TA-D1:** whether a general question takes the site override.
8. **Hedge acceptance (TEST-5)** for TA-01 – TA-04 and TA-D1 – TA-D3 under v1.
9. **Potential issues:** TP-01, TP-03, TP-05 (incl. `£40`), TP-06 (A-multipage-01 option X or v2), TP-07, TP-08, TP-09, TP-10 (new evidence), TP-D1, TP-D2.

## 8. Uncertainties

- **TP-10 version history:** the history does not say which section carried the 1 April date in v1.0 or v1.2, so "handbook error" is an inference.
- **TA-07 coverage:** the prefix set covers the formats observed or plausible. Other formatting, such as a value at the start of the answer, "within an hour", or NBSP between number and unit, still fails.
- **Dev re-scoring for Tier 2** uses page-level gold mapping from the stored `retrieved` list. This matches `run_tier2`, and the current-definition reconstruction equals the stored `correct` for all rows.
- **Probe answers** are synthetic. They show scorer behaviour, not the rate at which models produce each form.
