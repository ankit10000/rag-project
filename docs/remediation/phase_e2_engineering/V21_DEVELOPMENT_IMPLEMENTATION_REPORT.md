# Scorer v2.1 development integration and validation

2026-11-18. Engineering verification complete with provenance limitations; this is not evaluation acceptance.

## Baseline and preserved work

Branch `main`, HEAD `690fcfbbf0abdf43b274161a5e6545f7ad11c325`. Initial state: eight modified tracked files (the previous six plus two pre-existing Finder `.DS_Store` changes), 68 untracked files, no staged changes. The complete byte baseline is in `v21_development_verification/baseline.json`. No historical report or evidence package was rewritten.

The seven `(1)`-named uploads are not present among available attachments. Verification uses the explicitly identified, hash-pinned repository-retained final counterparts in `wp8_evidence/flip_inputs/final/`; equality to unavailable upload bytes is not asserted.

## Implementation and integration

All 15 scorer modules were audited. Before fixes, every module matched the final archived sidecars, aggregate `af81bae9df469cd880c8fec8a970a95bf5e0b275679111b783ee867d4e813a2c`. The initial archived identity `ebc9a15b6706180486f8f813b93bc75383bcac29cecce226b8a143f9b8cc93d9` differs in `score.py`; it is not represented as an exact replay of current source.

Two confirmed input-boundary defects were corrected without changing scoring policy:

- `eval/scoring_v2/rescore.py`: reject duplicate annotation JSON keys at every object level, with exit 7 before scoring or creating outputs. Previously later keys silently replaced original records.
- `eval/scoring_v2/context.py` and the same runner: handle the already-recognized document/page aliases consistently through reconstruction, retrieval metrics and page-superset diagnostics. Conflicting/malformed references and malformed citation arrays return a mismatch instead of an uncaught exception.

The new scorer aggregate identity with the pinned historical annotation bytes is `0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf`. Only `context.py` and `rescore.py` changed among scorer modules; policy tables, version strings, annotations and frozen v1 remain unchanged. Version alone is insufficient to identify a reproducible scorer; use the full hashes.

Existing `eval/runner_preparation/selection.py` and `offline.py` already provide explicit development-only selection, provenance verification, isolated atomic publication and rollback to the original v1 callable. No duplicate integration was added and no frozen runner/gate was activated. Official adoption remains owner-gated.

Three new regression files cover input failures, full current-source replay, and the actual pinned historical ingestion chunk stage. `run_tests.py` registers them. The WP7 integration test records the two reviewed source-hash changes while retaining original pins; the WP8 flip test now separates historical ledger replay status from current implementation identity. Historical ledger bytes remain unchanged; current full-score parity is independently asserted by the new tests. The earlier WP8 evidence ledger and candidate re-freeze proposal are historical snapshots, not current-source approval or refreshed candidates.

## Changed cases

| Tier | Case | v1 → v2 | Finding |
|---|---|---|---|
| 1 | B-comp-04 | false → true | Available station fact plus explicit missing-production-cost statements satisfy §10.2 A1/A2 and §10.3 partial handling. Citation correctness remains 0.5; no label correction applied. |
| 1 | B-conf-04 | false → true | Two duration groups and `Although` occur in one qualifying sentence scope under §11. |
| 1 | D-conflicting-01 | true → false | The 750-hour and 500-hour groups occur in separate sentences; global `However` satisfies v1 but not §11 same-sentence/list scope. This may be a semantic false negative, requiring owner review rather than an unauthorized rule change. |
| 2 | B-conf-04 | false → true | Separate Tier 2 context and answer contain both groups with `though` in the same sentence under §11. |

Detailed raw-answer, context-hash, citation and signal evidence is in `TIER1_V21_DEVELOPMENT_VALIDATION.md`, `TIER2_V21_DEVELOPMENT_VALIDATION.md` and the preserved WP8 flip ledger. All four correctness changes remain development evidence pending independent review.

## Replay and Tier 2 configuration

Both tiers were rerun through the existing offline integration before and after the fixes. All four comparison JSONL outputs are byte-identical to their final archived counterparts: Tier 1 47/47 exact, three flips; Tier 2 42/42 exact, one flip. Each has zero mismatches, errors, fallbacks or v1 drift. Pre-fix sidecars differ from archives only in generation time; post-fix sidecars differ only in generation time and the accurately updated scorer identity. New artifacts are isolated under `v21_development_verification/development-comparisons/scorer-2.1.0/`.

Pinned dataset revision: `c1bbcae9a21e389c16c3f1587de5acc1b5209e37`. Annotation SHA-256: `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a`. Frozen manifest content SHA-256: `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.

Tier 2 reproduces 135 chunks with table hash `29643967a4e3b0e453efa8f44c34cddf7528b4edf3da977140008a2e199b914a`, using 100 words, overlap 20, 10-word page minimum, document-scoped SHA-1 normalized dedup and `get_text(sort=True)`. Independently executing only the pinned ingestion chunk-stage AST confirms all ordered chunk records. No ingestion/database/embedding stage executes.

These settings match the historical source defaults but were environment-overridable. No original run header proves their resolved values. Exact reconstruction establishes consistency with this recorded procedure, not authoritative original runtime configuration, database row order or exact prompt bytes. Future runs should capture resolved configuration, ordered scoring-context hashes and separately identified prompt-context hashes at runtime. Assumptions remain explicitly unverified; no defaults were silently changed.

## Validation and safety

The machine-readable `v21_development_verification/verification.json` contains exact commands, outputs, exit codes, module/input/output hashes and final repository integrity checks. `pre_fix_validation.json` preserves the earlier matching-identity verification separately. All 44 protected assets are checked against their original raw hashes; the frozen manifest is reproduced by its verifier. No held-out/full-split evaluation, live provider call, database operation, production-memory operation, migration, quarantine, staging, commit or push occurred. V1 remains official and all sidecars remain acceptance-ineligible.

Engineering work is complete. Remaining gates are independent annotation/flip review, the documented specification and owner decisions, scorer-keyed thresholds/gate policy, approved frozen integration and re-freezing. Missing original uploads and original Tier 2 runtime/prompt provenance limit historical claims; they do not justify reopening the completed implementation or modifying policy.
