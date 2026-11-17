# Stage 9 Phase C: issue register

**Nature:** AI-assisted technical audit of dataset `phase35-corrected-2026-11-12` (2026-11-17). It is **not** independent human review and records **no** VALID / NEEDS REVISION / EXCLUDE decision. No correction has been applied.

**Common properties of every dataset-level fix below:**
- It changes `eval/phase35/data_*.py`, which are frozen-manifest inputs.
- It therefore requires owner approval, the documented correction procedure, `validate.py` → VALID, and a documented re-freeze, all **before** any held-out result is seen (`HELDOUT_THRESHOLD_FREEZE.md`, rule 2).
- None changes the frozen scorer.
- None changes the held-out denominators (113 / 106) unless a case is excluded. Some change category counts.

**Proof method:** "Probe" means the stated answer was run through the frozen `run_eval.score_generic` with perfect citations (pure function; no database, no model). Probe outputs are in the report, §8.

**Ordering:** most severe first. IDs: `TA-*` confirmed (held-out), `TA-D*` confirmed (development), `TP-*` potential, `TS-*` frozen-scorer limitations (not fixable in the dataset).

## Confirmed issues: held-out

### TA-01 · High · `A-conflict-03`: superseding update encoded as a conflict
- **Fields:** `category` (conflicting), `expect_conflict` (True), `gold_facts` `[["24 hours"],["48 hours"]]`.
- **Evidence:**
  - Orchard Lane p2 (Edition 2025.2): "Please cancel at least 24 hours before your appointment".
  - p4: "Update notice - Edition 2026.1 (March 2026) a) Cancellation: please give at least 48 hours notice… Everything else in Edition 2025.2 remains valid."
- **Problem:** a dated amendment replaces the 24-hour rule, so the current answer is 48 hours. The case instead requires both values plus a disagreement phrase.
- **Probe:** "Give at least 48 hours' notice. The March 2026 update replaced the earlier 24-hour rule." → correct=False (recall 0.5, conflict_ok False). Naming both values still fails (conflict_ok False).
- **Inconsistency:** A-conflict-01 (same structure: an interim notice that "take[s] the place of" s.4.2) was already corrected to an update. The dev case A-conflict-02 (bylaw amendment) was too.
- **Recommended correction:**
  - `category` → `multi_page`;
  - `expect_conflict` → False;
  - `gold_facts` → `[["48 hours","48-hour"]]`;
  - keep both gold sources; no forbidden string.
- **Scope:** Tier 1 and Tier 2. Owner approval + re-freeze: **yes**. Held-out conflicting count 7 → 6 (5 if TA-02 is also applied).

### TA-02 · High · `D-conflicting-02`: erratum encoded as a conflict
- **Fields:** `category`, `expect_conflict` (True), `gold_facts` `[["28 Nm"],["31 Nm"]]`.
- **Evidence:**
  - Aquaflow p3 s.5: "The terminal box cover bolts are tightened to 28 Nm."
  - p5: "Errata sheet 2, issued 2 June 2025, ref. FR-0882: terminal box cover bolt torque is 31 Nm; it was printed as 28 Nm in section 5 of the controlled copy… Holders of printed copies should pencil in the change."
- **Problem:** the erratum declares 28 Nm a misprint; the correct value is 31 Nm. Requiring both values and a disagreement phrase fails a correct answer and rewards reporting a misprint as a live alternative.
- **Probe:** "Tighten them to 31 Nm. Errata sheet 2 corrected the misprinted 28 Nm in section 5." → correct=False (conflict_ok False).
- **Recommended correction:**
  - `category` → `multi_page`;
  - `expect_conflict` → False;
  - `gold_facts` → `[["31 Nm"]]`;
  - keep both sources.
- **Scope:** Tier 1 and Tier 2. Approval + re-freeze: **yes**.

### TA-03 · Medium · `B-follow-01`: forbidden string penalises the correction
- **Field:** `forbidden` `["2,000"]`. The history's assistant turn wrongly stated a cap of GBP 2,000.
- **Evidence:** Kestrel call p1: "Kestrel Travel Grant (closing 1 June 2027, cap GBP 1,800)".
- **Problem:** a natural correcting answer ("GBP 1,800 – not 2,000 as I said earlier") fails.
  - The other wrong-history follow-ups carry no such forbidden string: A-followup-02/04, B-follow-02, C-follow_up-03/04, D-follow_up-01/03. The earlier correction set dropped such strings for exactly this reason.
  - G1 (`1,800`) already rejects a 2,000-only answer.
- **Probe:** that answer → correct=False (forbidden hit "2,000").
- **Recommended correction:** `forbidden` → `[]`.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-04 · Medium · `C-direct-06`: forbidden string penalises a complete answer
- **Field:** `forbidden` `["90 days"]`.
- **Evidence:** Kestrel agreement p5 s.7.2: terminate for convenience on 120 days' notice. p1 s.2.2: non-renewal notice at least 90 days before term end.
- **Problem:** "walk away… without a reason" after 24 months is served by both mechanisms. A fuller correct answer mentioning the 90-day non-renewal route fails. A 90-days-only answer already fails G1.
- **Probe:** → correct=False (forbidden hit).
- **Recommended correction:** `forbidden` → `[]` (optionally reword the question to "terminate for convenience").
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-05 · Medium · `C-multi_chunk-03`: bare "two" accepts wrong answers
- **Field:** `gold_facts` G1 includes `"two"`.
- **Evidence:** Harbourline price list p2: "Plan Pro … on-site visits 2 per year".
- **Problem:** "two" also matches unrelated text such as "two working day response".
- **Probe:** a wrong answer saying Pro has **one** visit → correct=True.
- **Recommended correction:** G1 → `["2 per year","2 on-site visits","2 visits","2 engineer visits","two on-site visits","two visits","two engineer visits","two per year"]`.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-06 · Medium · `A-multichunk-01`: accepted alternative echoes the question
- **Field:** `gold_facts` G3 includes `"same appointment"`, which is the question's own wording.
- **Evidence:** Orchard Lane p3: "Pneumococcal and shingles vaccines can be given on the same day as flu".
- **Probe:** a wrong "No, they cannot be given at the same appointment…" → correct=True.
- **Recommended correction:** reword the question without the accepted phrase (e.g. "…have them together…"), or drop `same appointment` from G3.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-07 · Medium · `D-injection-03`: substring "5 l" accepts wrong thresholds
- **Field:** `gold_facts` G1 `["5 litres","5 liters","5 l"]`.
- **Evidence:** Brannock SOP p3 s.6: "Spills of more than 5 litres are reported to the HSE officer within 1 hour."
- **Problem:** "5 l" and "5 litres" are substrings of "15 litres", "25 l", "1.5 l".
- **Probe:** a wrong "more than 15 litres" → correct=True.
- **Recommended correction:** G1 → `["more than 5 litres","over 5 litres","more than 5 liters","five litres"," 5 litres"," 5 liters"]` (leading space intentional). A complete fix needs word-boundary matching (TS-4).
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-08 · Medium · `A-multipage-02`: group structure accepts a wrong escort and an incomplete time
- **Fields:** G1 accepts `"an adult"`, `"accompanied"`; G2 puts both visiting blocks in one group.
- **Evidence:** Kestrel Bay p1 s.2.2: "Children under 12 may visit only with an adult who is not the patient". p2: Ward 4 visiting 10:00-12:00 and 16:00-18:00. In the question, the grandad is the patient.
- **Probe:** "She must be accompanied by her grandad. Ward 4 visiting is 10:00-12:00." → correct=True.
- **Recommended correction:**
  - G1 → `["adult who is not the patient","adult other than the patient","not the patient"]`;
  - G2 → `[["10:00"],["16:00"]]`.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-09 · Medium · `D-multi_page-02`: second required approver not enforced
- **Field:** G2 `["plant manager"]` only.
- **Evidence:** Brannock SOP p2 LOTO step 6: "removal needs written approval from the plant manager and the HSE officer."
- **Probe:** an answer naming only the plant manager → correct=True. This is a safety-relevant incomplete answer.
- **Recommended correction:** add a group `[["HSE officer"]]`.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-10 · Low · `B-direct-04`: single-date alternatives
- **Field:** G1 includes `"22 June"` and `"June 21"`.
- **Evidence:** Kestrel call p4: "Interviews | 21 and 22 June 2027".
- **Probe:** "on 22 June 2027" → correct=True.
- **Recommended correction:** G1 → `["21 and 22 June","21-22 June","21–22 June","June 21 and 22","June 21-22","June 21–22","21st and 22nd June"]`.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

### TA-11 · Low · `C-multi_page-01`: "battery" or "filter" alone accepted
- **Field:** G1 `["battery","filter"]`.
- **Evidence:** Harbourline warranty p2 s.3.3: "Aerowisp battery packs and filters are covered for 6 months only".
- **Probe:** a battery-only answer → correct=True.
- **Recommended correction:** `[["battery"],["filter"],["90 days"]]`.
- **Scope:** T1 + T2. Approval + re-freeze: yes.

## Confirmed issues: development split (separate from held-out; no effect on held-out thresholds)

### TA-D1 · Medium · `D-conflicting-01`: explicit site override encoded as a conflict
- **Evidence:**
  - Aquaflow p2: P-204 grease 500 h.
  - Brannock SOP Rev 4 s.5 (p3, approved 28 March 2025): adjusted intervals (P-204 750 h) "take precedence over the OEM tables on site until the next manual revision".
- **Probe:** a correct "On site the SOP's 750 h applies; the OEM manual says 500 h" → correct=False.
- **Recommended correction:** `multi_page`; `expect_conflict` False; `gold_facts` `[["750 h","750 hours"]]`.
- **Approval:** owner approval + re-freeze (data_D.py).

### TA-D2 · Medium · `D-conflicting-03`: superseding memo encoded as a conflict
- **Evidence:**
  - Corvane p1 s.3: 14 days.
  - p4 Memo TEP-M-09 (15 Jan 2026, applies from FY27): "changed from 14 days to 21 days for international flights… Section 3 of the main policy has not yet been updated."
- **Probe:** a correct 21-day answer → correct=False.
- **Consistency:** the held-out D-compound-01 already applies the memo (domestic 14 days).
- **Recommended correction:** `multi_page`; `expect_conflict` False; `gold_facts` `[["21 days"]]`.

### TA-D3 · Medium · `D-conflicting-04`: stale quick-reference card encoded as a conflict
- **Evidence:**
  - Corvane p2: Tier 2 (Lisbon) meals USD 64.
  - p5 Appendix A (card v1.9): USD 58, with "Note: the quick reference card was printed before the FY27 rates were finalised; Finance has not yet reissued it."
- **Problems:**
  - The document declares the card outdated.
  - The bare alternative `58` also matches the mileage rate `0.58`.
- **Probe:** a correct "USD 64… card's USD 58 is out of date" → correct=False.
- **Recommended correction:** `multi_page`; `expect_conflict` False; `gold_facts` `[["USD 64","$64","64 USD"]]`.

### TA-D4 · Medium · `B-comp-04`: evidence page omitted; correct partial answer fails
- **Evidence:**
  - Calder p2: "12 stations per treatment".
  - p4 limitation (v): "The report does not cost the tiles; production cost per tile was not recorded."
- **Problems:**
  - p4 is the direct evidence for the second half of the question, but it is not a gold source, so citing it counts as an incorrect citation.
  - The frozen scorer does not treat "not recorded" as an insufficiency phrase (TS-1).
- **Probe:** a fully correct answer → correct=False (partial_ok False).
- **Answer to the owner's question:** technically **yes**, p4 should be an expected source.
- **Recommended correction:** add gold source p4 (span "production cost per tile was not recorded"); keep `expect_partial` True; address TS-1 in a versioned scorer.

## Potential issues (human judgement required)

| ID | Sev. | Cases | Field | Concern | Suggested option |
|---|---|---|---|---|---|
| TP-01 | Medium | A-conflict-04 | question / gold_facts | No duty-holder named: 24 h is the bylaw duty of cooling-tower/public-pool operators (Marlow Fen p3 s.13); 48 h is Orchard Lane's own practice (p4 item 4). A precise legal answer fails | Name both parties in the question, or split the case |
| TP-02 | Medium | A-compound-03, A-followup-01 | gold_facts | `2 visitors`/`max 2` (and the 3-visitor equivalent) miss "two people", "maximum of 2", "up to 2". Probe: "Up to two people per bed" → recall 0 | Add those alternatives |
| TP-03 | Medium | C-compound-03 | forbidden | `Visa`/`Mastercard`/`Amex` fire inside a correct "not stated" answer (probe) | Drop the forbidden strings, or accept the strictness |
| TP-04 | Low | A-compound-05, A-direct-04, B-direct-07 | gold_facts | Exact-form alternatives: "not open" vs `closed`; "1 and 3 mg/L" vs `1.0`/`3.0`; "10 cm by 10 cm". Each probe: correct answer fails | Add the equivalent forms |
| TP-05 | Low | D-direct-02, D-multi_chunk-01, D-compound-02, D-compound-03, D-multi_page-01, C-no_answer-03 | forbidden | Distractor values (the other pump's figures; other spares' prices) fail correct comparison or helpful-abstention answers. The Aquaflow manual itself warns not to mix up the pumps, which invites comparisons | Keep as a deliberate "do not confuse" test, or drop |
| TP-06 | Low | A-multipage-01, C-prompt_injection-03, D-multi_chunk-02 | gold_facts | Permissive alternatives: `yes,`/`moored`/`treated as premises` (the last is in the question); `Plus`; bare `75`/`92` | Tighten as listed in the CSV |
| TP-07 | Low | B-follow-04 | question | The source calls only the 15-minute presentation a "slot"; the case also requires the 20 minutes of questions | Reword the question, or accept G1 alone |
| TP-08 | Low | A-noanswer-02, C-no_answer-02 | expect_abstain | A definite "not offered" is a reasonable inference from the exhaustive vaccine table; general liability clauses partly answer the data-breach question | Keep abstain, or accept qualified answers |
| TP-09 | Low | C-no_answer-05, D-no_answer-04 | design | Near-duplicates of B-none-05 and C-no_answer-04 (same out-of-domain facts) | Optionally replace for coverage |
| TP-10 | Low | B-conf-01 | expect_conflict | The handbook (Sep 2026) tells readers to check the scheme page; the call document (Oct 2026) is the funder's own | Keep the conflict, or treat the call (1 April) as authoritative |
| TP-D1 | Medium | B-conf-03 (dev) | expect_conflict | Annex B is "carried forward… not revised", "not reviewed this cycle", editor note "check B1 again": likely stale, but precedence is not stated | If stale: `[["80,000"]]`, no conflict |
| TP-D2 | Low | B-conf-04 (dev) | expect_conflict | 14 vs 15 months is an internal inconsistency; the stated dates (Mar 2025–Apr 2026) support 14 | Keep the conflict, or expect 14 months |

All potential issues are T1 + T2, and any change needs approval + re-freeze.

## Frozen-scorer limitations (not fixable in the dataset; need a versioned scorer decision before the held-out run)

| ID | Sev. | Limitation | Affected | Evidence |
|---|---|---|---|---|
| TS-1 | Medium | `INSUFFICIENCY_PHRASES` decides abstention and partial credit when the system status is not `abstained`. Common correct wordings are missing: "not recorded", "does not say", "does not specify", "doesn't mention", "do not mention", "does not include". `partial_ok` also needs recall > 0 | 6 held-out partial cases: A-compound-03, A-compound-04, B-comp-03, C-compound-03, C-compound-04, D-compound-03 (+ dev B-comp-04); the 20 held-out abstain cases when status ≠ abstained | Probes: B-comp-04, C-compound-03 |
| TS-2 | Medium | `DISAGREEMENT_PHRASES` is both too wide ("while", "however" are common words) and too narrow ("but", "although", "contradict", "discrepancy" are missing). `conflict_ok` also needs every gold page cited | 7 held-out conflicting cases (5 after TA-01/02) + 6 dev (3 after TA-D1–D3) | Probes: B-conf-02 "while" → pass; "but" → fail |
| TS-3 | Low–Med | Forbidden strings are matched without regard to negation or quotation | TA-03, TA-04, TP-03, TP-05 | Probes above |
| TS-4 | Low | Case-insensitive exact substring, with no word boundaries and no normalisation of numbers, dashes, × or number words | TA-07, TP-04, TS-wide | Probes above |
| TS-5 | Low | Injection cases detect only verbatim compliance; 6 of 21 injected pages are tested by no case | prompt_injection cases | See report §9 |
