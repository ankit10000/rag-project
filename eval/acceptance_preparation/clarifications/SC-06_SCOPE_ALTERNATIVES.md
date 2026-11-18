# SC-06 — Comma and adversative epistemic scope

**Decision status: PENDING_OWNER_DECISION. No alternative is selected.**

The formal §6 splitter does not split commas or standalone adversative words. §7.2 family E covers values after an A/B/C epistemic match through the current clause. The §7 residual comma/but Visa example claims a second clause that this grammar does not create.

## Complete directly relevant example/reference inventory

| Specification location | Line | Role |
|---|---:|---|
| §6.1.5 | 376 | formal comma clause definition |
| §7.2 E | 420 | Visa/Mastercard epistemic scope positive |
| §7.5 C-14 | 461 | Visa/Mastercard expected positive |
| §7.5 C-15 | 462 | affirmative Visa negative |
| §7 residual | 470 | comma/but repeated Visa claimed negative conflicts with formal grammar |
| Appendix B P-TS3-05 | 1226 | C-14 repeated expected positive |

The A2 epistemic-verb table and general traceability mentions define the signal family; they do not supply additional comma/adversative contrast examples. C-14 and Appendix B P-TS3-05 are the same positive example. C-15 is the affirmative-payment negative control.

## Unselected alternatives

### A — Affirm formal grammar

Clarify residual comma/but prose; no executable scoring change.

No behavioral widening; owner-approved specification wording still required.

### B — Introduce E-specific adversative termination

Proposed only: stop family-E scope at first standalone but/however/whereas/while/although/though/yet after the epistemic match, with or without a comma. Do not change the global splitter or other negation families.

Behavior change requires separately reviewed exact wording, tests, minor-version/source identity update and flip review; not implemented.

Proposed exact precedence (not implemented):

1. Apply existing protected spans and sentence/clause splitting first.
2. Find existing A/B/C epistemic matches without broadening their tables.
3. Within that clause only, terminate E at first boundary-delimited proposed adversative token after the match; do not treat and or butterfly as a terminator.
4. Apply per-occurrence forbidden and full polarity recall requirements unchanged.
5. Keep all other families, typed grounding, gold matching and disagreement scope unchanged.

Alternative B is an E-specific termination proposal, not a general punctuation/contrast rewrite. Global clause splitting or wider semantic boundaries would be a separate option requiring explicit cases and review. Both alternatives retain literal-kind behavior, per-occurrence handling and full gold-recall requirements.

## Required regression expectations

| Example | Current / A correct | Proposed B correct | Answer |
|---|---|---|---|
| SC06-SPEC-E | True | True | Basic is £4.99 a month. The documents do not say whether Visa or Mastercard are accepted. |
| SC06-SPEC-C15 | False | False | Basic is £4.99 a month. You can pay by Visa. |
| SC06-SPEC-RESIDUAL | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, but Visa is fine. |
| SC06-ADV-but | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, but Visa is fine. |
| SC06-ADV-however | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, however Visa is fine. |
| SC06-ADV-whereas | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, whereas Visa is fine. |
| SC06-ADV-while | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, while Visa is fine. |
| SC06-ADV-although | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, although Visa is fine. |
| SC06-ADV-though | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, though Visa is fine. |
| SC06-ADV-yet | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted, yet Visa is fine. |
| SC06-BUT-NO-COMMA | True | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted but Visa is fine. |
| SC06-AND | True | True | Basic is £4.99 a month. The documents do not say whether Visa is accepted, and Visa is fine. |
| SC06-SEMICOLON | False | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted; but Visa is fine. |
| SC06-PERIOD | False | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted. Visa is fine. |
| SC06-DASH | False | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted - but Visa is fine. |
| SC06-PAREN | False | False | Basic is £4.99 a month. The documents do not say whether Visa is accepted (Visa is fine). |
| SC06-ASSERT-FIRST | False | False | Basic is £4.99 a month. Visa is fine; the documents do not say whether Visa is accepted. |
| SC06-NO-EPI | False | False | Basic is £4.99 a month. The price list is not available here, but Visa is fine. |
| SC06-NON-TOKEN | True | True | Basic is £4.99 a month. The documents do not say whether Visa or butterfly cards are accepted. |

The current comma/but acceptance is an observed residual risk, not an approved exception. The and/non-token controls prevent an adversative proposal from silently becoming arbitrary sentence splitting. Development-only candidate counts are zero across 89 tier-specific records; this does not bound future or richer-annotation impact.
