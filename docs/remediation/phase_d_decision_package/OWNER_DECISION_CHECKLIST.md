# Owner decision checklist: Stage 9 Phase D

**How to use this checklist:**
- Set each **Decision** to `APPROVE`, `REJECT` or `DEFER`. Every entry is pre-filled `PENDING_OWNER_DECISION`.
- Claude has decided nothing.
- An approval authorises **preparing** the change under the documented correction procedure, not silently applying it.
- An approved data change then needs: an applied change, `validate.py` → VALID, a new frozen manifest (documented re-freeze), and a report. Each step happens before any held-out result.

Details: `HELDOUT_CORRECTION_PROPOSALS.csv`, `DEV_CORRECTION_PROPOSALS.csv`, `POTENTIAL_ISSUE_DECISIONS.md`, `SCORER_V2_DESIGN.md`, `PHASE_D_IMPACT_MATRIX.md`.

## 0. Sequencing (decide first)

| # | Question | Decision |
|---|---|---|
| S-1 | Proceed with corrections before, after, or in parallel with the independent human review? (Reviewer decisions remain authoritative; reviewer anti-anchoring is in `REVIEWER_CHECKLISTS.md` §2) | PENDING_OWNER_DECISION |
| S-2 | May the human reviewer see this package, and when? (Recommendation: only after the reviewer's own decisions are recorded) | PENDING_OWNER_DECISION |

## 1. Held-out corrections (confirmed issues)

| ID | Case | Proposal (short) | Severity | Decision |
|---|---|---|---|---|
| TA-01 | A-conflict-03 | Update, not conflict: `multi_page`, no conflict, facts 48 hours | High | PENDING_OWNER_DECISION |
| TA-02 | D-conflicting-02 | Erratum: `multi_page`, no conflict, facts 31 Nm | High | PENDING_OWNER_DECISION |
| TA-03 | B-follow-01 | Remove forbidden `2,000` | Medium | PENDING_OWNER_DECISION |
| TA-04 | C-direct-06 | Remove forbidden `90 days` | Medium | PENDING_OWNER_DECISION |
| TA-05 | C-multi_chunk-03 | Replace bare `two` with context-specific alternatives | Medium | PENDING_OWNER_DECISION |
| TA-06 | A-multichunk-01 | Reword the question to remove the echoed phrase (full fix needs v2) | Medium | PENDING_OWNER_DECISION |
| TA-07 | D-injection-03 | Interim boundary-safe alternatives for "5 litres" (full fix needs v2) | Medium | PENDING_OWNER_DECISION |
| TA-08 | A-multipage-02 | Escort must not be the patient; both visiting blocks required | Medium | PENDING_OWNER_DECISION |
| TA-09 | D-multi_page-02 | Add the HSE officer as a required approver | Medium | PENDING_OWNER_DECISION |
| TA-10 | B-direct-04 | Require both interview dates | Low | PENDING_OWNER_DECISION |
| TA-11 | C-multi_page-01 | Require battery and filter separately | Low | PENDING_OWNER_DECISION |

## 2. Development corrections (separate; no held-out effect)

| ID | Case | Proposal (short) | Decision |
|---|---|---|---|
| TA-D1 | D-conflicting-01 | Site override: `multi_page`, no conflict, 750 h | PENDING_OWNER_DECISION |
| TA-D2 | D-conflicting-03 | Superseding memo: `multi_page`, no conflict, 21 days | PENDING_OWNER_DECISION |
| TA-D3 | D-conflicting-04 | Stale card: `multi_page`, no conflict, USD 64 | PENDING_OWNER_DECISION |
| TA-D4 | B-comp-04 | Add Calder p4 as a gold source | PENDING_OWNER_DECISION |

## 3. Potential issues (not confirmed; recommendation shown for reference)

| ID | Case(s) | Technical recommendation | Decision |
|---|---|---|---|
| TP-01 | A-conflict-04 | REWORD QUESTION | PENDING_OWNER_DECISION |
| TP-02 | A-compound-03, A-followup-01 | ACCEPT PROPOSED CHANGE | PENDING_OWNER_DECISION |
| TP-03 | C-compound-03 | ACCEPT PROPOSED CHANGE | PENDING_OWNER_DECISION |
| TP-04 | A-compound-05, B-direct-07 / A-direct-04 | ACCEPT / DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |
| TP-05 | Aquaflow cases / C-no_answer-03 | KEEP CURRENT DEFINITION / DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |
| TP-06 | A-multipage-01, D-multi_chunk-02 / C-prompt_injection-03 | ACCEPT / DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |
| TP-07 | B-follow-04 | DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |
| TP-08 | A-noanswer-02 / C-no_answer-02 | KEEP CURRENT DEFINITION / DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |
| TP-09 | C-no_answer-05, D-no_answer-04 | KEEP CURRENT DEFINITION | PENDING_OWNER_DECISION |
| TP-10 | B-conf-01 | KEEP CURRENT DEFINITION | PENDING_OWNER_DECISION |
| TP-D1 | B-conf-03 (dev) | DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |
| TP-D2 | B-conf-04 (dev) | DEFER TO HUMAN REVIEW | PENDING_OWNER_DECISION |

## 4. Scorer v2

| # | Question | Decision |
|---|---|---|
| V-1 | Build scorer v2 as a separate versioned package (design §1), leaving v1 untouched? | PENDING_OWNER_DECISION |
| V-2 | Scope: TS-1 / TS-2 / TS-3 / TS-4 / TS-5 (all or a subset)? | PENDING_OWNER_DECISION |
| V-3 | Per-case v2 annotations (forbidden kinds, `allowed_with`, negatable groups) in scope? | PENDING_OWNER_DECISION |
| V-4 | Supplementary prompt-injection suite outside the acceptance set? | PENDING_OWNER_DECISION |
| V-5 | Acceptance scorer for the held-out run: v1 or v2. Must be frozen before any held-out result; may require a threshold review, which is not proposed here | PENDING_OWNER_DECISION |

## 5. After decisions

| # | Step | Decision |
|---|---|---|
| R-1 | Authorise the implementation phase for the approved items (data edits, v2 build), with its own handoff | PENDING_OWNER_DECISION |
| R-2 | Authorise the documented re-validation and re-freeze after the approved data changes | PENDING_OWNER_DECISION |

**Not decided by this checklist:**
- any held-out evaluation, which needs its own separate approval after the human review;
- any threshold change, which is not proposed.
