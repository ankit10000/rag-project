# Scorer-specific policy proposal contract

This is an engineering proposal, not an active gate. It imports no production
gate. `evaluate_proposal` always returns `official_acceptance: false`,
`adoption_allowed: false`, `official_default: v1`. A registry and owner claims
supplied by a caller are unverified evidence, never independent authority.

## Exact identity

`validate_identity` requires exactly these keys. All are nonempty strings except
`module_hashes`, a nonempty mapping of repository-relative paths to SHA-256.

| Field | Meaning |
| --- | --- |
| scorer_name, scorer_version | Labels; never sufficient identity |
| scorer_hash | Full aggregate scorer SHA-256 |
| source_revision | Full 40-hex commit context; not proof of clean working-tree content |
| module_hashes | Actual relevant source content hashes; authoritative for uncommitted modules |
| annotation_hash | Exact annotation content SHA-256 |
| dataset_revision, dataset_identity | Full 40-hex dataset commit pin and SHA-256 dataset content identity |
| tier, split | `tier1` or `tier2`; only `dev` accepted by this diagnostic |
| threshold_profile_id, threshold_profile_hash | Versioned label plus canonical content SHA-256 |
| gate_policy_id, gate_policy_hash | Versioned label plus canonical content SHA-256 |
| run_header_hash | Bound run-header SHA-256 |
| acceptance_status | OFFICIAL_V1_BASELINE, DEVELOPMENT_ONLY, or PENDING_OWNER_DECISION; caller claim only |

Hashes are lowercase 64-character hexadecimal. `identity_digest` canonicalizes
sorted JSON with compact separators using the existing repository hash primitive.
`contract_digest` excludes only `identity_digest` and `owner_decision`, avoiding
circular binding while retaining labels, thresholds and gate rules. Changing any
threshold or rule requires a new content identity and exact registry entry.
Byte authenticity and aggregate derivation must be independently verified upstream;
structural validation cannot prove that claimed bytes were actually executed.

## Threshold and gate schemas

Profile exact fields: `id`, `identity_digest`, `metrics`, `owner_decision`.
Metrics map names to exact `{role, operator, value}` records. Roles HARD_GATE or
DIAGNOSTIC. Hard gates support `>=` and `<=`, require finite numeric values and
observations, and reject booleans. Diagnostic records require null operator/value;
missing diagnostic observations do not indicate acceptance or block this structural
check. Actual metric selection and thresholds are owner decisions, not supplied
here. Tests use arbitrary synthetic numbers only.

Gate exact fields: `id`, `identity_digest`, `threshold_profile_id`, `error_policy`,
`incomplete_policy`, `rollback`, `owner_decision`. This proposal only models
BLOCK/BLOCK/KEEP_OFFICIAL_V1. These are fail-closed engineering recommendations,
not adopted V9 policy. Owner alternatives remain in decision_register.json.

Run exact fields: `identity_digest`, `run_header_hash`, `complete`, `errors`,
`invalid_records`, `metrics`. Completion must be literal true; counts must be
integer zero. Missing, invalid, unknown, mismatched or failed evidence blocks.
Unknown scorer identities cannot inherit thresholds, even with matching versions.

## Compatibility and rollback

| Path | Existing status | Proposal behavior |
| --- | --- | --- |
| Frozen v1 official runner/gate | Official, unchanged | Never imported or evaluated by this package |
| v1 development diagnostic | Explicit identity required | Proposal structural checks only |
| v2.1 development comparison | Opt-in development only | Exact identity and profile binding required |
| v2.1 official selection | Not authorized | Always inactive regardless of caller approvals |
| Held-out / all split | Outside this work package | Rejected by diagnostic |

On failure, retain existing official v1 and isolate failed development evidence.
No automatic adoption, threshold fallback, historical rewrite or deployment occurs.
Future authorization must independently authenticate reviewer and owner decisions,
review content-addressed threshold/gate versions, verify runtime provenance,
approve actual frozen integration patches, and authorize a separate re-freeze.
