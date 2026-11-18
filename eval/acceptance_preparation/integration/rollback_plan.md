# Rollback plan

No official adoption occurred. Current rollback is deterministic selection of the unchanged v1 callable through the existing `adoption.rollback_to_v1` re-export. This performs no filesystem writes, does not change the gate or thresholds, and preserves development comparison bundles and historical results. The frozen runner still uses its original v1 implementation.

A future authorized frozen integration must retain the v1 source, manifest and approved threshold lineage. Its reviewed rollback path must explicitly select that preserved v1 identity and use new run/output identities. It must independently reject unknown scorer hashes, mismatched annotations, missing provenance and unauthorized threshold/gate profiles. A v2 gate failure must never be converted into a passing v1 result by relabelling the same artifact.

If code reversal is necessary after a future release, prepare a narrow reverse patch against the actual approved integration, review it and rerun compatibility/hash/refusal tests. Preserve prior manifests, completed bundles, historical rows and consumed approval/run identities. No reset, stash, destructive cleanup, broad staging, overwritten result, edited old manifest or reused official run ID is part of rollback.

Deployment rollback authority and evaluation-run authority are separate. This document supplies neither; no commit, push, provider call, database operation, production evaluation or held-out execution is performed.
