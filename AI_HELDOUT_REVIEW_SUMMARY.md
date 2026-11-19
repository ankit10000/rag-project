# AI review of 113 held-out case definitions

2026-11-19 · **AI_REVIEW_COMPLETE** · **OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING**

All 113 original held-out definitions have three source-evidenced AI reviews and a consolidated disposition. This is review of definitions and source material, not execution of those questions. Human review remains **0/113**. No original dataset, scorer, threshold, annotation or human-review field was changed.

| Consolidated judgment | Cases |
|---|---:|
| AI_PASS | 83 |
| AI_CORRECTION_RECOMMENDED | 22 |
| AI_AMBIGUOUS | 8 |
| AI_INSUFFICIENT_EVIDENCE | 0 |
| Total | **113** |

These counts measure source/rubric review judgments, **not answer accuracy or an evaluation pass rate**. AI_PASS can retain an explicitly classified v1 limitation. Recommendations are not adopted corrections or owner decisions.

## Source work and provenance

Three isolated AI specialists began with original case definitions, actual PDF pages and frozen scorer source as appropriate. Initial records disclose prior exposure: they did not read previous correction recommendations or other agent judgments before recording their initial assessments. The assignment named two known problem IDs; that exposure is recorded. The lead already knew earlier Phase D/E2 findings and discloses that separately in post-initial adjudication.

- Source verification: all 12 PDFs and 56 actual pages read; 98 pass, 11 recommendations, 4 ambiguities.
- Expected-answer/label review: all 113 definitions against actual pages; 83 pass, 29 recommendations, 1 ambiguity.
- Static scoring fairness: all 113; 87 pass, 19 recommendations, 7 ambiguities. No scorer or provider was run on protected cases.
- All 339 initial records validate against actual PDF hashes, page bounds and quotations or explicit full-source absence scopes. Normalized PDF page text also matches the original dataset pages and existing source extracts.
- Initial byte streams remain separate, read-only and hash-sealed in `ai_review/initial_manifest.json`. The final JSONL embeds the initial records and their identities; adjudication does not overwrite them.
- AI author runtime model identifiers are unavailable and recorded as null/unknown, never invented. Actual agent execution identities and zoned timestamps are recorded. The evaluated Gemini model is separately known from real SDK responses.

Source support is established within the **retained frozen repository corpus**. Matching those PDFs, dataset pages and extracts does not authenticate unavailable historical original-upload bytes or reconstruct missing historical runtime/prompt evidence. No such provenance gap was filled by inference.

The three passes agreed on judgment for 85 cases and differed on 28. The lead inspected 38 initial issue cases plus two additional prior-proposal cases: **40 itemized dispositions**, with source-based rationales and preserved initial assessments. Final states are 73 initial-consensus records, 32 resolved AI dispositions and 8 explicitly unresolved policy interpretations. A recommendation being resolved as an AI finding does not make its proposed edit approved.

## Findings

| Classification | Cases |
|---|---:|
| Supported strict rubric | 44 |
| V1 matching/association limitation | 39 |
| Source-label defect | 2 |
| Missing required facts/conditions | 13 |
| Unit/context completeness recommendation | 6 |
| Overbroad alternative recommendation | 1 |
| Unresolved interpretation | 8 |

The two source-label defects are `A-conflict-03` (an explicit update makes cancellation notice 48 hours) and `D-conflicting-02` (errata instructs current terminal-cover torque of 31 Nm). Both current rubrics require superseded and current values as an unresolved conflict. These are AI recommendations to correct labels, **not edits to the frozen dataset**.

Completeness findings include both interview dates, both visiting windows, non-patient adult accompaniment, full walk-in/end times, both warranty part classes and the replacement whichever-longer condition, the credit formula, claim-reference digit count, strict spill-reporting condition, and both written lock-removal approvers with full PPE requirements. Six unit/context recommendations concern source-supported numeric facts whose bare rubric could accept an incorrect unit. They are rubric improvements rather than invented source values.

V1 limitations are separately retained: substring/negation false positives, relation/criterion swaps, numerical formatting, and false negatives when a correct correction mentions a forbidden old value. Removing forbidden strings can permit hedged wrong answers; no blanket removal or scorer rewrite was adopted. Tightening one literal alternative does not prove general semantic entailment.

## Eight preserved ambiguities

| Case | Unresolved interpretation |
|---|---|
| A-direct-03 | A “bad reaction” does not establish the source's specific allergic-reaction observation exception. |
| A-compound-04 | The campsite question omits the well's more-than-ten-person service threshold. |
| A-conflict-04 | Responsible institution and triggering event distinguish the 24-hour and 48-hour duties. |
| A-injection-02 | Campground status alone does not establish the well-testing population threshold. |
| B-conf-01 | Later official call versus handbook date/update pointer lacks an explicitly reconciled precedence record. |
| C-no_answer-02 | A specific data-breach penalty schedule versus general liability consequences changes the meaning of abstention. |
| C-conflicting-03 | Later finance summary and operative payment clause do not state amendment precedence. |
| D-compound-02 | The gland-bolt torque varies by maintenance task, but the question does not name the task. |

The referee-grace question `B-page-04` was resolved through the original source: its specific seven-day grace explicitly applies to referees rather than applicants. That exception is preserved alongside the initial fairness concern instead of silently deleting it.

## Comparison with previous proposals

Initial judgments were sealed before comparison. All eleven revised held-out TA items and ten applicable TP groups are linked case by case in `AI_CORRECTION_DISPOSITIONS.csv`. Original proposals retain their original pending states; the new CSV records **AI dispositions only** for all 113 cases.

| Prior item | AI comparison |
|---|---|
| TA-01 / TA-02 | Source update/errata concern confirmed; no frozen edit applied. |
| TA-03 / TA-04 | Keep valid current facts; do not automatically remove raw prohibitions that also block hedged wrong answers. Context-sensitive false negatives remain disclosed. |
| TA-05 | Contextual annual-visit tightening is supported. The separate £40 comparison tradeoff is not silently removed. |
| TA-06 | A general negation/association defect has no demonstrated universal data-only repair; no automatic rewrite. |
| TA-07 | Recommend strict threshold/recipient completeness; do not treat whitespace-anchored alternatives as a universal fix. |
| TA-08 / TA-09 | Full accompaniment/windows and joint written approvers/PPE are supported completeness findings. |
| TA-10 | Both interview days are required; a one-day OR alternative is incomplete. |
| TA-11 | Both part classes and the replacement remainder/90-days-whichever-longer condition matter. |

Potential issues remain source- or interpretation-specific. Older seven-case development/TA-D proposals are outside this 113-case held-out review; they were not relabelled held-out. The original 25-item AI revision list was not reapplied: its already-applied history remains intact.

## Reproduction and validation

```sh
.venv/bin/python -B -m ai_review.consolidate
TESTSAFE_BLOCK_NETWORK=1 DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m unittest test_ai_heldout_review test_ai_development_evaluation -v
```

Final combined check: **20/20 tests passed**, 1.126 seconds, exit 0. The fourteen ledger tests cover exact coverage/identities, actual-page evidence, negative scopes, immutable initial hashes, missing/duplicate/mismatched records, false human labels, altered proof and exclusive publication. Six development guards cover new-input collisions, identities, completeness and no-overwrite. No database/provider is used by these tests. The final published JSONL was separately compared exactly with a fresh deterministic build, and the CSV round-trip preserves all 113 IDs and eleven columns.

The CSV was authored/inspected using Artifact Tool cells and serialized as RFC 4180 from verified values because the documented exporter has no CSV format. No extra workbook or human-review copy was created. A representative preview was inspected; CSV itself carries no formatting or formulas.

| Evidence artifact | SHA-256 |
|---|---|
| Final JSONL | `0d81459e5edab0471e5b3119e7226ae6dd6c5971e3ccf13b09a0c51d499f6746` |
| Correction CSV | `3bb0c9bdaf160f31ca5cabb1327ebc0d82c76a3b6f720dfdcd70bd805a65445f` |
| Lead adjudications | `096aacb2baba2f2ab4886d2b5f2a637d887c0371725cfe0be2afda8f1436d47f` |
| Final test log (`/private/tmp/ai-review-final-tests.log`) | `1738b221fb990b15741a09c4f7164a189742c6914ea9c0a3cff7937eb27d538d` |

The separate permitted development result is **AI_TECHNICAL_EVALUATION_FAIL, 3/4**, based on four real Gemini calls on wholly new synthetic inputs. The source-supported fax-absence response failed the recorded abstention/status criteria; the FAIL was preserved without a rerun. See `AI_EVALUATION_RESULT.md` for its policy, raw evidence and limits. It is not performance evidence on these 113 cases.

## Official status

**OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING.** AI review is complete; the original human-specific freeze remains unsatisfied. Human reviewer identity/signature, itemized reviewer/owner data dispositions and genuine exact run authorization remain absent. Conditional retention is not acceptance of all labels. No protected question was executed, no held-out case was moved into development, and all 44 protected assets and original human records remain unchanged.
