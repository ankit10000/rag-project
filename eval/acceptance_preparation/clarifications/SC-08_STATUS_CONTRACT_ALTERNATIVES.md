# SC-08 — Explicit status contract decision

**Decision status: PENDING_OWNER_DECISION. No alternative is selected.**

Known result status strings in the existing development/offline contract: `answered`, `abstained`, `partial`, `conflict`, `unverified`, `error`. The pure scorer currently preserves v1-style status-only rules for unknown strings and absent/null fact statuses; non-string non-null values raise ValueError. Missing does not mean a fabricated answered/error state.

## Current synthetic matrix

| Input category | Fact | Abstention | Partial | Conflict |
|---|---|---|---|---|
| known-answered | True | True | False | True |
| known-abstained | False | True | True | False |
| known-partial | True | True | True | True |
| known-conflict | True | True | False | True |
| known-unverified | False | True | False | False |
| known-error | False | False | False | False |
| unknown | True | True | False | True |
| empty | True | True | False | True |
| missing | True | True | False | True |
| null | True | True | False | True |
| integer | ValueError | ValueError | ValueError | ValueError |
| boolean | ValueError | ValueError | ValueError | ValueError |
| list | ValueError | ValueError | ValueError | ValueError |
| object | ValueError | ValueError | ValueError | ValueError |

Table cells are current correctness booleans or the exception class. The JSON preserves the actual raw input, presence/absence of the status field, and all abstain/partial/conflict result fields.

## Unselected contracts

### A — Explicitly retain v1 compatibility

Keep current matrix, including unknown/empty strings and missing/null fact status behavior; retain ValueError for non-string non-null values.

### B — Strict structural status contract

Accept only six known strings; reject unknown, empty, missing, null and non-string statuses with ValueError before scoring. No canonical error row is inferred.

### C — Explicit invalid-status error-row adapter

In a separately versioned adapter only, preserve raw invalid status in diagnostics, supply a canonical error result, and record the conversion. Exact error-row boolean/denominator policy remains V-9 and cannot be assumed.

B must define invalid input failure before scoring; C must be a separately identified adapter preserving original invalid input and explicit conversion evidence. A canonical error row cannot silently settle V-9 denominator/run validity policy. Either B or C requires a separately authorized and versioned behavior change, exact tests for every invalid category and downstream compatibility review.

## Annotation and historical compatibility

Annotation schema does not depend on result status. Do not rewrite annotation bytes or values; strict contracts can reject historical result rows previously scored without invalidating their annotations. A canonical-error adapter changes result handling, not annotation provenance.

Tier 1 has 36 answered, nine abstained, one conflict and one partial record. Tier 2 has 29 answered, six abstained, one conflict and six partial records. All 89 records have known strings; none have missing/null/unknown-string status. This evidence does not choose an invalid-status policy or justify silently treating synthetic failures as successful acceptance.
