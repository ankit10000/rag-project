# Proposed official selection contract

Current integration is a re-export of existing preparation components, not a new execution infrastructure. `select_official_scorer()` and `rollback_to_v1()` return the exact v1 callable. `rehearse_development_comparison` delegates to unchanged WP7 `prepare_comparison` through the existing adoption boundary. Every official v2 request is refused, including caller-supplied `approved=true`, an eligible sidecar, a candidate manifest or purported reviewer signature.

The future mechanism must be a separately reviewed change. Before selecting a non-v1 official scorer it must independently verify:

1. All nine owner/review decisions enumerated by unchanged `readiness.REQUIRED_DECISIONS`: real-case annotation review, independent human review, human-approved flip golden list, specification clarification acceptance, V-5 adoption, scorer-keyed threshold review, V-9 error/gate policy, frozen runner/gate integration approval and re-freeze approval.
2. Full scorer name, version, aggregate and module hashes; actual source revision/working-tree provenance; raw/portable annotation identity and dataset revision/identity.
3. The independently approved threshold profile and gate policy identities. An unknown hash must not inherit v1 thresholds merely because its version string is 2.1.0. No thresholds are chosen in this package.
4. Required run-header and resolved-runtime provenance, ordered scoring context and separately identified prompt context; no reconstructed historical evidence may be relabelled runtime-captured.
5. Approved manifest lineage and actual post-integration source hashes, review-completion evidence, approved output/run-once/approval-consumption policy, and tested failure/rollback behavior.

These are review requirements, not an assertion that a local JSON field authenticates a human or permits execution. The candidate keeps `approved_acceptance_scorer`, `approved_v2_thresholds`, future patched runner/gate hashes and threshold/gate/header approval identities null. Even satisfying local shape/hash validation cannot activate this preparation package.

Exact frozen review targets remain `run_eval.main/enforce_split_gate/run_tier1/run_tier2`, `safety.runner_gate/check_run_request/approval_problems/FROZEN_THRESHOLDS`, `frozen_manifest.MANIFEST_FORMAT/FROZEN_ASSETS/build_content/load_frozen_manifest`, `framework.cli.cmd_report` and `review.cli.DATASET_VERSION`. Consult the preserved `WP8_RUNNER_ADOPTION_PLAN.md` for their detailed review and test contracts; no patch is applied here.
