# Clarification decision preparation

This is a reference snapshot and decision overlay for the existing canonical register, not a competing clarification register. `eval.acceptance_preparation.clarifications` still imports `clarifications.py`; this documents/JSON directory deliberately has no `__init__.py`.

Canonical sources: `eval/acceptance_preparation/clarifications.py` and `docs/remediation/phase_e2_engineering/WP8_SPECIFICATION_CLARIFICATION_REGISTER.md`. Their hashes and complete imported snapshot are recorded in `decision_package.json`. All eight original records, original language, source references, implementation evidence and review states are preserved.

| Items | Existing engineering state | Formal adoption |
|---|---|---|
| SC-01 Appendix B, SC-02 boundary, SC-03 quotes, SC-04 idempotence, SC-05 AV-10 | Existing engineering resolutions retained | Unreviewed; not adopted |
| SC-06, SC-07, SC-08 | Alternatives prepared; current behavior preserved | PENDING_OWNER_DECISION |

All owner names, selections, rationales, dates, reviewer names and approval references are blank (`null`). No alternative is selected. V1 remains official; v2.1 remains experimental.

## Package contents

- `decision_package.json`: canonical snapshot, source hashes, pending decision fields, alternatives, exact synthetic current-result fixtures and conservative development-only impact counts.
- `SC-06_SCOPE_ALTERNATIVES.md`: every directly relevant specification example/reference and explicit proposed precedence.
- `SC-07_NUMBER_WORD_ALTERNATIVES.md`: narrower grammar versus compound-one expansion and idempotence requirements.
- `SC-08_STATUS_CONTRACT_ALTERNATIVES.md`: known/unknown/missing/null/non-string result matrix and unselected error contracts.

## Historical impact scope

Only the 47 Tier 1 and 42 Tier 2 development result records were inspected. There were zero same-clause epistemic-then-adversative lexical candidates, zero tens-plus-one candidates in inspected answer/gold/forbidden/history text, and zero missing/null/unknown-string statuses. These are candidate estimates, not a prediction of correctness changes under unimplemented proposals. They do not establish zero future impact. No held-out case was scored, no alternative policy was executed, and no historical evidence was rewritten. The full counts, tier separation, source paths, source hashes and limitations are in the JSON.

## Validation

`DATABASE_URL=postgresql:///rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 .venv/bin/python test_phase_e2_clarification_decisions.py` exited 0: seven tests passed. The URL is a test guard value only; no database connection was made. Tests verify 19 epistemic-boundary examples, 11 number-word examples, 56 current status/case outputs, the proposal structure, canonical import identity, source hashes and dev-only lexical impact counts. Proposed alternatives are checked as data contracts; no alternate scorer is implemented or invoked.

Next step: the responsible scoring-policy owner and independent reviewer must select and document exact contract wording and the relevant version/review procedure. Approval to change behavior, approve flips, adopt v2.1 or re-freeze assets is not supplied by this package.
