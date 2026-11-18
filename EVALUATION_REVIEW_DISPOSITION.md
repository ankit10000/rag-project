# Evaluation review disposition

2026-11-18 · **AI_TECHNICAL_REVIEW** · **PENDING_INDEPENDENT_REVIEW**

The existing four case/tier evidence bundles are reproducible and ready for a designated independent reviewer. No human review or acceptance is established. This document contains AI technical analysis and must be withheld from that reviewer until their initial judgments are recorded. Official v1 and all original review records remain unchanged.

## Reviewer handoff: evidence before outcomes

Reuse `independent_review/flip_review_package/README.md:7`–`28`. A coordinator gives the reviewer only the following Stage A files first, together with the applicable specification sections identified below, without revealing scorer outcomes or AI explanations. The original answer, question, citations, complete scoring context and source pages are already included; do not generate another workbook.

| Priority | Stage A file | Question/answer lines | Supporting evidence | Applicable specification |
|---|---|---|---|---|
| 1 | `independent_review/flip_review_package/records/tier1_D-conflicting-01/stage_a_blind.json` | 59–60 | Source pages from line 79; SOP p3 and OEM manual p2 | `docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md:667`, §11 disagreement |
| 2 | `independent_review/flip_review_package/records/tier1_B-comp-04/stage_a_blind.json` | 52–53 | Source pages from line 67; tile report p2 and p4 | Same specification, §10.1–10.3, lines 602–643 |
| 3 | `independent_review/flip_review_package/records/tier1_B-conf-04/stage_a_blind.json` | 59–60 | Source pages from line 79; tile report p1 and p4 | Same specification, §11, line 667 |
| 4 | `independent_review/flip_review_package/records/tier2_B-conf-04/stage_a_blind.json` | 45–46 | Source pages from line 65; tile report p1 and p4 | Same specification, §11, line 667 |

Reviewer records a judgment, rationale, identity/date and prior exposure in a **working copy** of the supplied CSV. The coordinator confirms the judgment predates Stage B exposure, then supplies each `after_independent_judgment.json`. Preserve initial and post-analysis judgments separately. The package staging is an exposure instruction, not authenticated proof of independence. This AI review has read Stage B and cannot serve as the required blind human review.

Use the existing source-bound workbooks for dataset decisions: `docs/remediation/dev_review/dev_review_sheet.xlsx` (7 development rows) and `docs/remediation/heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx` (113 held-out rows). Their decisions remain blank; neither workbook is a substitute for new-scorer annotation/flip review. Source: `docs/remediation/phase_e2_engineering/WP8_ANNOTATION_REVIEW_REPORT.md:22`–`33`. Do not expose held-out answers for development feedback.

## AI_TECHNICAL_REVIEW: disposition matrix

Four unique case/tier records each retain two historical comparison occurrences, hence eight artifact occurrences. They are not eight independent judgments. The outcomes below describe saved development behavior, not an accepted golden list.

| Occurrence | Saved correctness v1 → v2.1 | Mechanically correct behavior | Semantic policy concern | Annotation/data concern | Required human disposition |
|---|---|---|---|---|---|
| Tier 1 D-conflicting-01 | True → False | §11 requires both fact groups in one sentence or list-introduction scope. 750 hours and 500 hours occur in separate sentences; `disagreement_signals` correctly returns no scope. | **Priority:** an adjacent “However” contrast with correctly attributed sources and explicit SOP precedence is semantically meaningful. Rejection is a likely false-negative hypothesis, not an implementation/spec mismatch. | Whether this is genuine disagreement or an ordinary authoritative site override is itself an unresolved dataset question. Both original source pages and citations are present. | Independently judge the answer and conflict label, then owner explicitly retains §11 or authorizes a versioned cross-sentence policy. Recommendation: request a narrowly defined adjacent-sentence adversative exception with required group/source linkage, rather than unrestricted whole-answer lexicon matching; do not activate without approval. |
| Tier 1 B-comp-04 | False → True | Available fact is matched; separate missing-cost clauses generate A1/A2 signals under §10.2, so partial answer succeeds. | No mechanical semantic defect established: “not recorded” is supported by report p4. | Gold source list includes p2 only although the answer cites p4 for missing cost. Both scorers retain citation correctness 0.5. This is the existing TA-D4 expected-source proposal, not evidence that the answer fabricated p4. | Judge p4 as an expected source for missing-cost information and partial-answer adequacy. Recommendation: approve p4 inclusion only through the documented dataset correction/re-freeze process if the reviewer agrees. |
| Tier 1 B-conf-04 | False → True | A qualifying sentence contains both 14 and 15 months plus “Although”; both gold pages cited. v1 lacks this connective. | The answer privileges the executive summary; reviewer must determine whether acknowledgment adequately communicates the unresolved 14/15 discrepancy. No mechanical false positive established. | The source report genuinely contains both durations; whether one is a correction rather than a conflict needs judgment. No frozen label changed. | Independently judge conflict/answer adequacy. Recommendation: retain the specified connective detection while reviewing the source-label question separately. |
| Tier 2 B-conf-04 | False → True | A single parenthetical sentence contains both durations plus “though”; both pages cited. | Same discrepancy, expressed more directly. No mechanical semantic defect established. | Tier 2 retrieved chunk context differs from Tier 1; do not merge contexts or assume identical runtime provenance. | Independently judge this occurrence separately. Recommendation: retain specified detection subject to review. |

Mechanical source: `eval/scoring_v2/signals.py:40`–`69`; §11 scope/group tests are lines 51–69. Saved explanations, complete score objects, annotations and source hashes are in the corresponding Stage B files. Existing detailed occurrence evidence: `docs/remediation/phase_e2_engineering/WP8_SCORER_FLIP_ANALYSIS.md:32`–`86`; CSV `WP8_SCORER_FLIP_LEDGER.csv`. The cross-sentence behavior is explicitly specified, so no scorer edit is justified by this review alone.

## Provenance and annotation boundaries

- All four Stage A contexts and Stage B source/module hashes reproduce byte-for-byte through the existing package generator. Current v2.1 aggregate is `0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf`; each module is pinned separately. HEAD is `690fcfbbf0abdf43b274161a5e6545f7ad11c325`; uncommitted scorer bytes are bound by hashes, not by HEAD alone.
- Historical source results are Tier 1 SHA-256 `4c1a6416f2603f7c0744533b6c3ee99570827aaefbdca003bbe346ea2bfd0988` and Tier 2 `b2c92e582c8e9ddb75e6adc6661a200ab294bc4956002c54f2c6258fb63f4962`. Historical annotation SHA-256 `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a` belongs to the `c1bbcae` dataset pin, not the current corrected dataset. The current annotation raw hash is `d3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0`.
- Reconstruction establishes the recorded scoring contexts, not original runtime row order/configuration or exact prompt bytes. Seven unavailable `(1)` uploads remain unverified as original uploads; repository snapshots are named honestly. Every historical comparison is `acceptance_eligible: false`. Equal current result dictionaries do not prove execution of unavailable historical scorer code. See package README lines 35–42 and flip analysis lines 16–26.
- Current 160 annotation entries are structurally valid but all 160 remain `NEEDS_INDEPENDENT_REVIEW`; literal-only baseline adequacy is not independent semantic acceptance. The historical annotation baseline is separate. These limitations do not prevent reviewer inspection of the four bundles, but prevent promotion of reconstructed historical evidence into formal acceptance.

## Executed verification

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B -m unittest test_phase_e2_flip_review test_stage9_wp8_annotations -v
```

**PASS: 15 tests in 2.150 seconds, exit 0; no skips.** Eight package tests verify deterministic payloads, source/context/scorer hashes, four distinct contexts, eight historical occurrences, Stage A exposure structure, exclusive publication and blank approval fields. Seven annotation tests cover AV-1–AV-10 rejection families, source links, immutable original values, pin mismatches and read-only OOXML review-cell counting. Local library deprecation/telemetry-persistence warnings do not represent provider calls. No database, provider, held-out or full-split evaluation executed.

## Decision

Review preparation is complete; **independent review remains pending**. Required external action is a designated reviewer’s source-first judgments for these four occurrences and the applicable annotation/dataset decisions, followed by explicit owner policy/adoption decisions. No reviewer fields, annotations, workbooks, frozen labels, source implementations or historical results were edited. This document alone changes no acceptance dashboard state and authorizes no official run.
