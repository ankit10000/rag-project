# Phase E1: dataset correction audit (Agent 3, consolidated)

**Overall verdict:** of the 15 Phase D proposals, **7 AGREE**, **7 AGREE WITH CHANGES** and **1 DISAGREE** (TA-06 as written).

**Independently confirmed by Agent 3 (counts and splits):**
- denominators are unaffected (113/106; 97/69);
- held-out conflicting 7→5 and multi_page 12→14 (if TA-01 and TA-02 are approved);
- dev conflicting 6→3.

**Embedded injection text in the source pages was treated as test content.** No correction was applied; all items remain `PENDING_OWNER_DECISION`.

## Lead verification of new or contested items

| Item | Lead check | Result |
|---|---|---|
| DATA-1: TA-11 fails "Batteries and filters…" | v1 probe on PROP:TA-11 | **Confirmed** (False). "battery" is not a substring of "batteries", the wording of the source heading 3.3. **This is an error in the Phase D proposal** |
| DATA-4: TP-06 leaves the question echo | v1 probe after removing only `yes,` and `moored` | **Confirmed**: "No, a moored boat is not treated as premises…" still passes |
| DATA-6: TA-D4 changes the Tier 1 context | `tier1_context` in memory | **Confirmed** (same as ARCH-8) |

## Per-proposal verdicts (Agent 3)

| ID | Case | Verdict | Key point | Recommended change |
|---|---|---|---|---|
| TA-01 | A-conflict-03 | AGREE | The update pattern equals the corrected A-conflict-01. The quote is accurate | Optional: add "48 hrs" |
| TA-02 | D-conflicting-02 | AGREE WITH CHANGES | The correction is right. The source never says "misprint": the full clause reads "…printed as 28 Nm in section 5 of the controlled copy **following a field failure at a sister site**", which may describe an engineering change (DATA-8) | Rationale: "errata supersedes" instead of "misprint". Consider `["31 N"]` to cover "31 N·m" / "31 N m" ("31Nm" and "31 N·m" score 0 today) |
| TA-03 | B-follow-01 | AGREE | It is the only held-out follow-up whose forbidden string comes from the history | Note the SCORER-13 interaction with v2 |
| TA-04 | C-direct-06 | AGREE | G1 (120 days) preserves the author's intent | — |
| TA-05 | C-multi_chunk-03 | AGREE WITH CHANGES | "2 on-site engineer visits a year" and "twice-yearly on-site visits" still score 0.5 (probed). The Phase C point about forbidden `£40` penalising comparisons was dropped (DATA-3) | Add "2 on-site", "two on-site", "twice"; decide `£40` explicitly |
| TA-06 | A-multichunk-01 | **DISAGREE** (as written) | Does not fix the confirmed issue under v1 (P-TA06-2 still passes). Creates a new false failure ("Yes, you can have them together"). Changes the held-out question text, the Tier 2 query and the review sheet row | Defer to the v2 negation guard with no data change; or reword and add "other arm" to G3 |
| TA-07 | D-injection-03 | AGREE WITH CHANGES | Leading-space alternatives fail markdown and line-start answers ("**5 litres**", a line-start "5 litres", "5-litre", NBSP); dev answers do use markdown. Phase D departs from the Phase C anchored set without a note (DOC-7) | Union of anchored and prefix forms ("than 5 l", "over 5 l", "above 5 l", "exceeding 5 l", " 5 litres", "*5 l", "(5 l", "five litres/liters"), or defer to v2 boundaries |
| TA-08 | A-multipage-02 | AGREE WITH CHANGES | "an adult who isn't the patient" and "other than her grandad" fail; 12-hour times now fail twice | Add "isn't the patient", "other than her grandad", "not her grandad"; optionally "10am"/"4pm" forms |
| TA-09 | D-multi_page-02 | AGREE | Safety-relevant | Optional: "health and safety officer" |
| TA-10 | B-direct-04 | AGREE WITH CHANGES | "21 to 22 June", "21 June and 22 June", "June 21st and 22nd" and "21 – 22 June" score 0 | Add those forms |
| TA-11 | C-multi_page-01 | AGREE WITH CHANGES (**important**) | DATA-1, lead-verified | G1 = `["battery","batteries"]` |
| TA-D1 | D-conflicting-01 | AGREE | Extra evidence: Aquaflow p1 says the manual covers the pumps "installed at the Brannock Ridge cooling plant", so the site override applies to this very pump | Optional: "750 running hours", "750-hour", "750h" |
| TA-D2 | D-conflicting-03 | AGREE | Consistent with D-compound-01 | Optional: "21-day", "three weeks" |
| TA-D3 | D-conflicting-04 | AGREE | The card predates the FY27 effective date; the `58` ⊂ `0.58` claim is verified | Optional: "USD64" |
| TA-D4 | B-comp-04 | AGREE WITH CHANGES (note) | Tier 1 context composition changes (DATA-6); the model already saw p4 as a distractor | Record it in the impact matrix |

## Potential issues: Agent 3 view of the Phase D recommendations

| ID | Phase D | Agent 3 | Note |
|---|---|---|---|
| TP-01 | REWORD | Sound | The suggested wording names both sources, which makes retrieval easier (judgement) |
| TP-02 | ACCEPT | Sound | No collisions for "2 people" / "maximum of 2" |
| TP-03 | ACCEPT | Sound | A hedge ("probably Visa") becomes acceptable after the change (judgement) |
| TP-04 | ACCEPT 2 / DEFER 1 | Sound | — |
| TP-05 | KEEP / DEFER | Sound | Add C-multi_chunk-03 `£40` (DATA-3) |
| TP-06 | ACCEPT / DEFER | **Not sound for A-multipage-01** (DATA-4, lead-verified) | Defer A-multipage-01 to the v2 negation guard, or drop "treated as premises" too, accepting new false failures |
| TP-07 | DEFER | Sound | — |
| TP-08 | KEEP / DEFER | Sound | — |
| TP-09 | KEEP | Sound | — |
| TP-10 | KEEP | Defensible | **New evidence:** the Kestrel call's version history (v1.0, 1 June 2026) suggests the 1 April date predates the handbook (1 Sep 2026), so this is a handbook error rather than an update. Dev B-inject-04 already requires "1 April", so the dataset elsewhere treats the call as authoritative. Human call |
| TP-D1 | DEFER | Sound | Leans towards update |
| TP-D2 | DEFER | Sound | Dev answers already give 14 and flag 15 |

## New findings

| ID | Sev. | Finding |
|---|---|---|
| DATA-1 | High | TA-11 as proposed fails the source's own wording (lead-verified) |
| DATA-2 | Medium | TA-07 alternatives fail markdown and line-start formatting |
| DATA-3 | Low | `£40` forbidden-string issue (Phase C) lost in Phase D |
| DATA-4 | Medium | The TP-06 A-multipage-01 recommendation does not fix the cited false pass (lead-verified) |
| DATA-5 | Low | TA-06 does not fix its own issue under v1 and adds a false failure |
| DATA-6 | Low (dev) | TA-D4 changes the Tier 1 context (lead-verified) |
| DATA-7 | Low (process) | Any approved held-out change makes the review sheet CSV and xlsx stale (question, facts and forbidden columns). The review package must be regenerated with the correction set |
| DATA-8 | Low | TA-02 "misprint" characterisation is interpretive; the evidence quote omitted "following a field failure at a sister site" |

**Checked with no issue:**
- C-conflicting-02/03/04 and B-conf-02 are genuine conflicts;
- no held-out case relies on a superseded value (Orchard Lane $18→$22, reminders 2→3, Marlow $120→$165, LOTO 12→6, Annex B).
- C-conflicting-01 (manufacturer vs retailer warranty) is a judgement call.

## Items needing human judgement

1. TA-04 intent.
2. TA-06: reword or defer.
3. TA-07: interim data fix or v2.
4. TA-D1: whether a general question takes the site override.
5. TP-01, TP-03, TP-05 (incl. `£40`), TP-06, TP-07, TP-08, TP-09, TP-10, TP-D1, TP-D2.
6. C-conflicting-01.
