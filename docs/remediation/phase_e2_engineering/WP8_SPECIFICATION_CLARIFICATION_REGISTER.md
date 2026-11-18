# WP8 specification clarification register

Date: 2026-11-17. Engineering evidence only; no independent review, owner decision, formal acceptance, scorer adoption or re-freeze is recorded. Existing WP5, WP6 and WP7 files remain unchanged.

## Source inventory and disposition

The seven numbered WP6 clarification items contain eight distinct issues: its final item covers both compound number words and unknown statuses. This register separates those decisions. The full authoritative WP5 specification, the WP6 implementation report, existing scorer code and focused regression fixtures were inspected.

| Disposition | Count | Meaning |
|---|---:|---|
| Resolved for engineering from explicit specification evidence | 5 | Existing behavior and expected outputs are traceable; formal acceptance remains unapproved |
| Pending owner decision | 3 | SC-06, SC-07 and SC-08 retain explicitly documented experimental behavior |
| Require independent review before formal adoption | 8 | No record is marked reviewed or approved |

No scoring policy, threshold, annotation, frozen runner or existing implementation was changed by this workstream. The new pure register is `eval/acceptance_preparation/clarifications.py`; focused tests are `test_stage9_wp8_clarifications.py`. The register validator rejects missing coverage, duplicated IDs, inferred approvals and silent changes to unresolved decision state.

## Clarifications

### SC-01 — Appendix B explicit probe outcomes

**Status:** `RESOLVED_ENGINEERING`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §Appendix B, starting line 1212.

> | P-TS1-06 (tier1) | True (residual) | **False** |

**Actual behavior:** P-TS1-06=False, P-TS1-08=False, P-TS4-10=False and P-E2-STAT-06=True; frozen v1 outcomes remain independent.

**Code evidence:** `eval/probes/probes_phase_d.py`, `eval/probes/probes_e2.py`, `eval/scoring_v2/score.py`.

**Conflict or ambiguity:** Earlier probe intents disagree with the authoritative superseding Appendix B table.

**Engineering resolution:** Use Appendix B explicitly stated v2.1 values. This resolves engineering expectations, not acceptance of scoring policy.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc01_appendix_b_explicit_probe_values` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-02 — Plural relaxation is quantity-only

**Status:** `RESOLVED_ENGINEERING`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §4.3, starting line 204.

> If `n` has the form `<N> <word>` (one number token, one word), the right boundary also accepts `h` continuing with `s` or `es` and then a boundary

**Actual behavior:** Bare Tuesday does not match Tuesdays; bare filter does not match filters. Quantity 2 visitor matches 2 visitors.

**Code evidence:** `eval/scoring_v2/normalize.py`, `eval/probes/probes_phase_d.py`, `eval/probes/probes_e2.py`.

**Conflict or ambiguity:** Three historical v2 probe intents assumed a general plural rule absent from the closed specification.

**Engineering resolution:** Apply the explicit quantity boundary rule; P-TS4-11, P-TA11-2 and P-E2-TA11-3 remain False. Do not add unreviewed gold alternatives.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc02_quantity_only_plural_boundary` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-03 — Preserve explicit quote glyph table before NFKC

**Status:** `RESOLVED_ENGINEERING`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §4.1 M1/M2, starting line 122.

> `unicodedata.normalize("NFKC", s)`, then `casefold()`

> `’ ‘ ‛ ′` → `'`; `“ ” „ ″` → `"`

**Actual behavior:** Closed quote glyphs are translated before NFKC so U+2033 becomes one ASCII double quote.

**Code evidence:** `eval/scoring_v2/normalize.py::light`, `eval/scoring_v2/tables.py::QUOTES`.

**Conflict or ambiguity:** Literal M1-then-M2 loses double-prime identity: NFKC(U+2033) is two U+2032 characters, otherwise yielding two apostrophes.

**Engineering resolution:** Honor the explicit M2 output table without widening its glyph set. This existing implementation precedence is tested; formal clarification acceptance remains independent.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc03_quote_map_survives_nfkc` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-04 — Number-word unit normalization must be idempotent

**Status:** `RESOLVED_ENGINEERING`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §4.1 M12/M13 and 16.2, starting line 133.

> | M12 | Units |

> | M13 | Number words |

> `M` is idempotent;

**Actual behavior:** Unit/currency normalization runs again after number-word conversion: twelve months becomes 12 month immediately.

**Code evidence:** `eval/scoring_v2/normalize.py::M`, `eval/scoring_v2/normalize.py::_quantities`.

**Conflict or ambiguity:** A single ordered pass creates 12 months on the first call and 12 month on the second, contradicting required idempotence.

**Engineering resolution:** Satisfy the explicit idempotence acceptance property by completing existing closed quantity rules after number words; no new unit or word is introduced.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc04_number_word_quantity_idempotence` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-05 — AV-10 duplicates within collections, not across roles

**Status:** `RESOLVED_ENGINEERING`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §13.3 example and AV-10, starting line 939.

> No duplicate texts within a case

**Actual behavior:** Duplicate texts within forbidden or history_wrong_values are rejected; the same 2,000 may appear once in each collection.

**Code evidence:** `eval/scoring_v2/annotations.py::entry_errors`, `eval/scoring_v2/annotations.py::validate_annotations`.

**Conflict or ambiguity:** The exact section 13.3 example repeats 2,000 in forbidden and history_wrong_values, contradicting a whole-case ban.

**Engineering resolution:** Use the explicit example to scope duplicate checking per collection. Full validation still checks actual history turn ownership, gold overlap and group bounds.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc05_full_sample_and_richer_annotations_valid` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-06 — Comma/but epistemic scope

**Status:** `PENDING_OWNER_DECISION`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §6.1.5, 7.2 E and 7 residual, starting line 376.

> Commas **do not** split clauses.

> every `V` **after** the end of that match, up to the end of the clause

**Actual behavior:** Comma and but remain in one clause; family E can excuse a repeated Visa after but. A semicolon creates a separate asserted occurrence and fails.

**Code evidence:** `eval/scoring_v2/text_units.py::split`, `eval/scoring_v2/negation.py::occurrence_family`.

**Conflict or ambiguity:** Section 7 residual says a comma/but Visa repetition fails on its second clause, but the formal splitter does not create that clause.

**Engineering resolution:** Unresolved: retain current experimental formal-grammar behavior, explicitly register its false-acceptance risk, and do not claim the residual prose is satisfied.

**Decision proposal — not selected:** Owner must choose: affirm formal clause scope and correct the residual example; or define exact adversative boundaries/epistemic termination with positive and negative examples, version the changed rule and review flips.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc06_epistemic_comma_scope_remains_pending` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-07 — Compound number words ending in one

**Status:** `PENDING_OWNER_DECISION`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §4.4, starting line 210.

> compounds `<tens>[- ]<two..nine>` (21 – 99) → digits.

**Actual behavior:** The explicit grammar converts twenty-two and ninety-nine, but leaves twenty-one and thirty-one literal; isolated one also remains literal.

**Code evidence:** `eval/scoring_v2/normalize.py::_words`, `eval/scoring_v2/tables.py::NUMBER_WORDS`.

**Conflict or ambiguity:** The prose numeric interval includes 21/31/etc., while the closed grammar excludes one and separately excludes isolated one.

**Engineering resolution:** Unresolved: current experimental code follows the explicit two-nine grammar; no inferred one mapping is adopted.

**Decision proposal — not selected:** Owner must choose: clarify the stated interval to exclude every tens-plus-one value; or amend the compound grammar to one-nine while retaining isolated-one exclusion, version the behavior and review affected outputs.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc07_tens_one_grammar_remains_pending` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

### SC-08 — Unknown string result statuses

**Status:** `PENDING_OWNER_DECISION`. **Review:** `NOT_REVIEWED`. **Acceptance approved:** false.

**Original specification:** [docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md](docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md) §10.3 all other cases and 13.1, starting line 637.

> `abstain_ok = status not in ("abstained", "unverified", "error")`. This is **v1's status-only rule, unchanged**.

**Actual behavior:** Unknown string statuses retain v1 status-only semantics on fact cases; non-string non-null statuses raise ValueError. Missing/null status is not silently assigned an enum value.

**Code evidence:** `eval/scoring_v2/score.py::_validate`, `eval/scoring_v2/score.py::score_case`.

**Conflict or ambiguity:** The API describes status but specifies no exhaustive accepted enum or rejection rule for unknown strings.

**Engineering resolution:** Unresolved: preserve current experimental v1-compatible handling and report the missing enum policy; do not invent a new failure or acceptance policy.

**Decision proposal — not selected:** Owner must choose: explicitly retain v1-compatible unknown string handling; or specify a closed enum, treatment of missing/null/unknown values and versioned malformed-output/error policy before adoption.

**Regression evidence:** `test_stage9_wp8_clarifications.py::test_sc08_unknown_status_policy_remains_pending` (passes). Historical trace: `docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md`, “Specification clarifications and traceability”.

**Code change needed now:** no. Existing WP6 behavior is preserved; any approved behavioral change to a pending item requires an explicit, versioned follow-up with affected regression and flip review.

**Test added:** yes. **Independent review required:** yes. No independent judgment is fabricated.

## Focused execution evidence

Command: `DATABASE_URL=postgresql:///rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 .venv/bin/python test_stage9_wp8_clarifications.py`. The URL is a guard value only; no database connection or operation is made.

Actual result: 10 unittest methods passed, exit 0. Tests cover all eight clarification records; seven selected existing probe cases with independently preserved v1 expectations; quote/NFKC and idempotence behavior; full sample-style cross-collection annotations; richer valid annotation groups/history and invalid bounds; explicit unresolved epistemic/compound/status residuals; and rejection of manufactured review/approval. No broader scoring or evaluation cycle was run by this workstream.

The richer-annotation preliminary-validation concern was reproduced independently: valid full and per-entry objects containing `negatable_groups`, `conflict_groups`, and indexed `history_wrong_values` pass unchanged WP6 validation. Invalid group bounds, history-role indices and within-collection duplicate values fail. No existing validator fix was necessary.

## Acceptance consequence

Engineering clarification preparation is complete. Formal clarification acceptance remains pending independent review and owner decisions. In particular SC-06 is an observed false-acceptance risk under the formal clause grammar, not an approved exception. SC-07 and SC-08 require exact contract wording before adoption. The acceptance evidence package must carry these pending IDs forward and must not treat this register as authorization to adopt v2, alter gates or re-freeze evaluation assets.
