# Integration compatibility matrix — proposal only

Engineering snapshots are not acceptance authority. This package adds no frozen runner flags, gate rules or threshold values.

| Path | Version and identity | Annotations and dataset | Outputs | Current authority |
|---|---|---|---|---|
| Frozen `eval.phase35.run_eval.score_generic` | Original v1 callable, five arguments | Frozen v1 case contract | Existing official runner remains unchanged | Existing v1 baseline |
| `eval.runner_preparation.selection.select_scorer()` | Returns the identical v1 callable by default | No fabricated v2 binding | Selection performs no execution | Preserves v1 default |
| `select_scorer("2.1.0", development=True, annotations=...)` | Explicit version and supplied annotations; full aggregate identity must be recorded by the diagnostic caller | Complete dataset-pinned annotations required by offline wrapper | Development only | Not official adoption |
| Existing WP7 `prepare_comparison` / integration rehearsal re-export | Exact source/module/annotation identity, not version label alone | Exact context and source/header/pin validation; no held-out or fallback execution | Versioned, exclusively published development bundle; false acceptance eligibility | Diagnostic engineering evidence |
| Historical development annotations with current hardened source | `0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf` | `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a`, dataset `c1bbcae9a21e389c16c3f1587de5acc1b5209e37` | Existing diagnostic comparisons preserved | Unapproved diagnostic identity |
| Current package annotations with current hardened source | `9648c71d1743a85a595db0175c89e5d38f8ccf3470f11c1f7145e753c369a237` | `d3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0`, current dataset at `690fcfbbf0abdf43b274161a5e6545f7ad11c325` | Candidate input inventory only; not a historical flip replay | Unapproved candidate identity |
| Proposed future official v2.1 path | Full owner-approved identity plus threshold/gate/header identities; currently null | Reviewed real-case annotations, approved dataset/review/manifest lineage | New official run identity and protected exclusive outputs | Blocked; no activation API here |

The two 2.1.0 aggregates above intentionally differ because annotation bytes differ. Candidate source metadata records working-tree module bytes; Git HEAD alone does not claim those uncommitted modules are present at that commit. A later source or annotation change requires a new snapshot and review, not an update to an old evidence identity.

`candidate_validation_report.json` proves consistency of a 27-asset parent plus 20 existing WP6/WP7 snapshots and two separate annotation bindings. It does not approve either scorer identity or certify that future frozen integration is complete.
