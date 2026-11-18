# SC-07 — Compound number words ending in one

**Decision status: PENDING_OWNER_DECISION. No alternative is selected.**

Exact WP5 §4.4 language:

> compounds `<tens>[- ]<two..nine>` (21 – 99) → digits.

`one`, `a`, `an`, `dozen`, `half`, `quarter`, ordinals are excluded.

The stated interval includes 21/31/etc. while the closed two-nine grammar excludes them. Existing code follows that explicit grammar and retains isolated one.

## Unselected alternatives

### A — Affirm narrower explicit grammar

Replace interval shorthand with explicit tens plus two through nine; tens-plus-one stays literal.

No behavior change; independent specification approval required.

### B — Support stated 21–99 range

For compound forms only, allow tens followed by one through nine; keep isolated one and scaled/adjacent phrases literal.

Minor-version/source identity update and focused flip review required; not implemented.

Required precedence/tests:

- Preserve isolation and scale-word blocking.
- Recognize one only as the second token of an approved tens compound.
- Complete existing unit canonicalization after conversion so M(M(x)) == M(x).
- Do not add any number-word token to guard G.

## Exact normalization expectations

| Input | Current / A | Proposed B |
|---|---|---|
| one | one | one |
| twenty-one | twenty-one | 21 |
| twenty one | twenty one | 21 |
| thirty-one | thirty-one | 31 |
| thirty one | thirty one | 31 |
| ninety-one | ninety-one | 91 |
| twenty-two | 22 | 22 |
| ninety-nine | 99 | 99 |
| twenty-one months | twenty-one months | 21 month |
| twenty-two months | 22 month | 22 month |
| one hundred and twenty days | one hundred and twenty days | one hundred and twenty days |

Every proposed result must be idempotent, including unit completion after any approved conversion. Neither option creates new guard G number-word tokens. No compound-one mapping is implemented by this package. Development-only lexical counts are zero; no held-out evaluation or proposed policy scoring was performed.
