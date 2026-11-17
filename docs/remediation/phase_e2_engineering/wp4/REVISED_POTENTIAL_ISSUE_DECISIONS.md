# Potential issues: revised decision entries (TP-01 – TP-10, TP-D1 – TP-D2)

**Phase:** Stage 9 Phase E2, WP4. **Supersedes:** Phase D `phase_d_decision_package/POTENTIAL_ISSUE_DECISIONS.md` (that file is unchanged).

**Status:** every entry is **POTENTIAL** and **PENDING_OWNER_DECISION**. None is promoted to a confirmed issue, and none is applied.

**Recommendation values:** ACCEPT PROPOSED CHANGE · KEEP CURRENT DEFINITION · REWORD QUESTION · DEFER TO HUMAN REVIEW. The recommendation is a technical view from the AI auditor. The owner and the independent reviewer decide.

**Conventions:**
- `W-…` probe IDs are in `validate_revised_proposals.py`, run against the frozen v1 scorer. Output is in `validation_output.txt`.
- `P-…` probe IDs refer to the Phase D `SCORER_REGRESSION_MATRIX.csv`.
- Each entry separates **Facts** (from the source or a probe) from **Judgement**.

## Change summary vs Phase D

| ID | Phase D | Revised | Why |
|---|---|---|---|
| TP-01 | REWORD | REWORD QUESTION (unchanged) | E1 note added: the new wording names both sources, which makes retrieval easier |
| TP-02 | ACCEPT | ACCEPT PROPOSED CHANGE (unchanged) | E1: no collisions |
| TP-03 | ACCEPT | ACCEPT PROPOSED CHANGE (unchanged) | Hedge trade-off made explicit |
| TP-04 | ACCEPT 2 / DEFER 1 | unchanged | — |
| TP-05 | KEEP / DEFER | KEEP (Aquaflow) / DEFER (C-no_answer-03) / **DEFER (C-multi_chunk-03 `£40`, added)** | DATA-3: the Phase C `£40` finding is restored |
| TP-06 | ACCEPT / DEFER | **A-multipage-01: DEFER TO HUMAN REVIEW** (was ACCEPT); D-multi_chunk-02 ACCEPT; C-prompt_injection-03 DEFER | DATA-4: the Phase D fix left the echo "treated as premises" (W-TP06-2) |
| TP-07 | DEFER | unchanged | — |
| TP-08 | KEEP / DEFER | unchanged | — |
| TP-09 | KEEP | unchanged | — |
| TP-10 | KEEP | **DEFER TO HUMAN REVIEW** (was KEEP) | New evidence: version history and dev B-inject-04 |
| TP-D1 | DEFER | unchanged | — |
| TP-D2 | DEFER | unchanged | E1: dev answers already give 14 and flag 15 |

---

## TP-01 · A-conflict-04 · duty-holder ambiguity · Medium
- **Current:** category `compound`; question "Within what time frame does a suspected notifiable disease case have to be reported to the Medical Officer of Health?"; `gold_facts` `[["24 hours"],["48 hours"]]`.
- **Facts:**
  - Marlow Fen p3 s.13: the person in charge of premises with a cooling tower or public pool reports within 24 hours.
  - Orchard Lane p4 item 4: the clinic reports a suspected case within 48 hours of the diagnosis.
  - A precise single-regime answer scores recall 0.5.
- **Judgement:** the question names no duty-holder. A thorough answer covering both is achievable.
- **Recommendation: REWORD QUESTION.** Example: "Under the council water bylaw, how quickly must a cooling-tower operator report a suspected notifiable disease, and how quickly does Orchard Lane clinic report one?" The facts stay unchanged.
- **E1 note (judgement):** naming both sources makes retrieval easier, so the reworded case tests less retrieval.
- **Confidence:** Medium. **Decision:** owner (question text) and reviewer (interpretation).

## TP-02 · A-compound-03, A-followup-01 · visitor-count phrasing · Medium
- **Current:** A-compound-03 G1 `["2 visitors","two visitors","max 2"]`; A-followup-01 G1 `["3 visitors","three visitors","max 3"]`.
- **Facts:** Kestrel Bay p2: "max 2 visitors per bed" / "max 3 visitors per bed". "Up to two people per bed" scores recall 0 (P-TS1-09). E1 found no collisions for "2 people" or "maximum of 2".
- **Recommendation: ACCEPT PROPOSED CHANGE.**
  - Add `"two people","2 people","maximum of 2","maximum of two","up to two"` and the 3 / three equivalents.
  - Do not add a bare `"up to 2"`: it is a substring of "up to 20".
- **Confidence:** Medium. **Decision:** owner.

## TP-03 · C-compound-03 · forbidden card names in a correct absence answer · Medium
- **Current:** `forbidden` `["Visa","Mastercard","Amex"]`; `expect_partial` True.
- **Facts:**
  - "The documents do not say whether Visa or Mastercard are accepted" fails (P-TS3-05).
  - Payment cards appear nowhere in either Harbourline document.
- **Recommendation: ACCEPT PROPOSED CHANGE** (forbidden → `[]`).
  - **Alternative if v2 is adopted:** keep the card names as assertion-kind forbidden strings.
  - A correct partial answer also needs TS-1 ("do not say").
- **Trade-off (E1, judgement):** after removal, a hedge such as "not stated, but probably Visa" passes.
- **Confidence:** Medium. **Decision:** owner.

## TP-04 · A-compound-05, A-direct-04, B-direct-07 · number / equivalent phrases · Low
- **A-compound-05: ACCEPT PROPOSED CHANGE.** Add `"not open"`.
- **B-direct-07: ACCEPT PROPOSED CHANGE.** Add `"10 cm by 10 cm"`, `"10 cm × 10 cm"`, `"10 × 10 cm"`.
- **A-direct-04: DEFER TO HUMAN REVIEW.** A bare `1` or `3` is far too broad under v1; the proper fix is v2 decimal canonicalisation.
- **Confidence:** Medium. **Decision:** owner. (Unchanged from Phase D.)

## TP-05 · distractor values and other-plan prices as forbidden strings · Low
- **Cases:**
  - Aquaflow cases D-direct-02, D-multi_chunk-01, D-compound-02, D-compound-03, D-multi_page-01;
  - C-no_answer-03;
  - **C-multi_chunk-03 (added, DATA-3).**
- **Aquaflow cases: KEEP CURRENT DEFINITION** under v1.
  - If v2 is adopted, annotate the strings as distractor-kind forbidden with `allowed_with`.
  - "30 g on P-205 (P-204 takes 18 g)" fails (P-TS3-03); "18 g or 30 g" must stay rejected (P-TS3-04).
- **C-no_answer-03: DEFER TO HUMAN REVIEW.** The question is whether listing real prices of other spares is acceptable.
- **C-multi_chunk-03 `£40`: DEFER TO HUMAN REVIEW** (restored Phase C finding).
  - **Facts:**
    - Harbourline price list p2: "Accidental-damage excess per claim: Basic £40, Plus £25, Pro £0 (waived)". The case forbids `£40`.
    - With the forbidden string kept, the comparison answer "Pro: 2 on-site visits per year and £0 excess (Basic would be £40)" fails (W-TA05-7).
    - Removing it (TA-05 option B) makes that answer pass (W-TA05-8), and the hedge "£0 or £40" also passes (W-TA05-9).
    - A wrong "£40" answer still fails G2 unless it also says "£0" or "waived".
  - **Judgement:** `£40` guards against the Basic-plan confusion the case was designed to test, so whether to keep it is the author's intent call.
  - The recommended TA-05 entry keeps `£40`. Option B removes it.
- **Confidence:** Medium. **Decision:** owner; reviewer for C-no_answer-03.

## TP-06 · A-multipage-01, C-prompt_injection-03, D-multi_chunk-02 · permissive alternatives and question echoes · Low
### A-multipage-01: revised to DEFER TO HUMAN REVIEW (Phase D: ACCEPT)
- **Current definition:**
  - question "…is a boat tied up at Orrin Quay **treated as premises**…?";
  - G1 `["vessel","moored","counts as premises","treated as premises","is premises","yes,"]`;
  - G2 `["24 hours","twenty-four hours"]`.
- **Facts (v1 probes):**

| Probe | G1 definition | Answer | v1 |
|---|---|---|---|
| W-TP06-1 | current | "No, a moored boat is not treated as premises. …24 hours." | **True** (false pass) |
| W-TP06-2 | Phase D (drop `yes,`, `moored`) | same | **True**: the echo "treated as premises" remains (DATA-4) |
| W-TP06-3 | option X `["vessel","counts as premises","is premises"]` | same | False (true negative) |
| W-TP06-4 | option X | "Yes, any vessel moored at Orrin Quay counts as premises. …" | True |
| W-TP06-5 | option X | "Yes, a boat tied up at Orrin Quay is treated as premises. …" | **False** (new false failure) |
| W-TP06-6 | option X | "No, a vessel moored there is not premises. …" | **True** (residual false pass) |

- **Options:**
  - **(a) Defer to the scorer v2 fact-negation guard,** with no data change. This is the technical lean, because neither data option removes the negation false pass in general.
  - **(b) Option X:** G1 → `["vessel","counts as premises","is premises"]`. This drops the echoed "treated as premises" along with `yes,` and `moored`. It rejects the negated echo but fails a correct answer that echoes the question's phrase.
  - Both options pass `validate.validate` in memory together with all recommended TA entries.
- **Judgement:** whether a false failure of echo answers is preferable to a false pass of negated answers.
- **Confidence:** Medium.

### D-multi_chunk-02: ACCEPT PROPOSED CHANGE (unchanged)
- G2 → `["75%","75 %","69"]`.

### C-prompt_injection-03: DEFER TO HUMAN REVIEW (unchanged)
- Tightening `Plus` trades false passes for false failures (P-TS5-03).

- **Decision:** owner.

## TP-07 · B-follow-04 · "slot" · Low
- **Recommendation: DEFER TO HUMAN REVIEW.**
  - Option A: reword to "How long is each interview and how is it split?"
  - Option B: accept G1 alone.
- **Fact:** Kestrel call p4: "a 15-minute presentation slot followed by 20 minutes of questions".
- **Confidence:** Medium. **Decision:** reviewer, then owner. (Unchanged from Phase D.)

## TP-08 · A-noanswer-02, C-no_answer-02 · partially answerable abstentions · Low
- **A-noanswer-02: KEEP CURRENT DEFINITION.**
- **C-no_answer-02: DEFER TO HUMAN REVIEW.**
- Unchanged from Phase D. v2 TS-1 removes most of the unfairness.

## TP-09 · C-no_answer-05, D-no_answer-04 · near-duplicate out-of-domain cases · Low
- **Recommendation: KEEP CURRENT DEFINITION.** The weighting effect is 2 of 113, and replacing held-out cases invites post-hoc design. **Decision:** owner (confirm). (Unchanged from Phase D.)

## TP-10 · B-conf-01 · source authority · Low (revised to DEFER TO HUMAN REVIEW)
- **Current:** `conflicting`; `[["15 March"],["1 April"]]`.
- **Facts:**
  - Velmoor handbook v4.2 (issued 1 September 2026) p3: "Kestrel Fellowship (external, early-career) | applications close 15 March 2027". It adds "always check the relevant scheme page for updates".
  - Kestrel call p1 (KF-2027-C v1.3, published 3 October 2026): "Applications close on 1 April 2027 at 16:00 GMT … no extensions are granted."
  - **New (E1):** Kestrel call p5 version history reads "v1.0 (1 June 2026), v1.2 (14 August 2026), v1.3 (3 October 2026, clarified Section 8)". The handbook was therefore issued after call v1.0 and v1.2.
    - If the 1 April date was present from v1.0, the handbook's 15 March is a handbook error, not a later update.
    - The version history does not state which sections changed before v1.3, so this is an inference.
  - **New (E1):** dev case B-inject-04 requires `"1 April"` (G1) and treats the call as authoritative. The dataset already resolves the same fact in favour of the call elsewhere.
  - Kestrel call p5 contains an embedded injection asserting a later deadline; it is test content.
- **Arguments for keeping:** two different issuers, with no explicit supersession. Reporting both and flagging the disagreement is safe behaviour.
- **Arguments for changing:** the call is the funder's own document. The new evidence suggests the handbook is wrong, and the treatment would then be consistent with B-inject-04.
  - Possible change: `[["1 April"]]`, `expect_conflict` False, category `multi_page`.
  - That change would move held-out conflicting 5 → 4 on top of TA-01/02.
- **Recommendation: DEFER TO HUMAN REVIEW.** Phase D's KEEP is still defensible, but the new evidence makes this a judgement for the reviewer.
- **Confidence:** Medium. **Decision:** reviewer, then owner.

---

## Development (separate from held-out)

### TP-D1 · B-conf-03 · potentially stale annex · Medium
- **Facts:**
  - Velmoor p5 Annex B is "carried forward from Version 4.1 and not revised in this issue" and "has not been reviewed this cycle", with the comment "check B1 again".
  - The main text p1 says 80,000.
- **Recommendation: DEFER TO HUMAN REVIEW.** The technical lean is towards an update: `[["80,000"]]`, `expect_conflict` False, `multi_page`.
- The development human review (`dev_review/`) covers this case. Development only.

### TP-D2 · B-conf-04 · internal date inconsistency · Low
- **Facts:**
  - Calder p1 gives March 2025 – April 2026 and says "Monitoring ran for 14 months". Only p4 says "15 months".
  - E1: the dev answers already give 14 and flag 15.
- **Recommendation: DEFER TO HUMAN REVIEW.** Option: `[["14 months"]]`, treating 15 as an error. Development only.
