# WP7 — independent engineering preparation

Date: 2026-11-17. **PASS WITH LIMITATIONS.** Independent engineering preparation is complete. **WP7 overall remains partially complete** because frozen live runner/gate integration and acceptance adoption require owner decisions and WP8 re-freezing.

## Baseline and recovered requirements

Verified local `main` at `690fcfb`; six tracked WP6-modified files, 21 untracked WP6 files, no staged changes. No commit or push was performed. The baseline snapshot includes 430 existing working files and 44 protected assets. The WP6 implementation report, WP7/WP8 dependency handoff, WP5 §§12–17, the remaining-decisions WP7 plan, and actual runner/gate code were reviewed before editing.

| Work item | Starting state | Independent work completed | Still owner-controlled |
|---|---|---|---|
| Provenance | WP6 sidecars and pinned reconstruction | Exact context/history capture, strict source/annotation identities, versioned proofs and comparison binding | Production header/model/config policy and real-case annotation review |
| Reconstruction | WP6 Tier 1/Tier 2 helpers tested | Reuse unchanged WP6 functions behind stricter preparation-only validation of missing, duplicate and inconsistent references | Installing capture in the frozen live runner |
| Exclusive output | WP6 exclusive individual files | Versioned comparison bundles, exclusive claims, native no-replace publication, hash-bound completion verification, partial-failure/retry tests | Official run-once ledger, consumed approvals and gate output policy |
| Scorer integration | WP6 explicitly opt-in | Explicit selector and development-only offline wrapper; original five-argument v1 callable remains the default | Acceptance-scorer adoption, keyed thresholds and official reporting |
| Frozen gate/manifest | Existing frozen v1 behavior | Integrity and refusal tests only | Gate behavior, manifest format/lineage changes and re-freeze |

No historical report, pending decision or proposal was rewritten as approved. These new modules are preparation interfaces, not a replacement execution gate.

## Implementation and ownership

New package `eval/runner_preparation/`:

| File | Responsibility |
|---|---|
| `__init__.py` | Side-effect-free namespace; exposes the selector without selecting or running anything |
| `selection.py` | Default returns the exact frozen `score_generic` callable; `2.1.0` requires explicit development mode and caller-supplied schema-valid annotations |
| `provenance.py` | Pure, versioned exact context records; ordered chunk/history hashes; strict source/annotation/pin identities; proof verification; stricter reconstruction validation |
| `artifacts.py` | Versioned development namespace, exclusive claims, sealed file manifest, completion binding, native no-replace directory publication and safe owned-resource cleanup |
| `offline.py` | Development-only CLI/API that delegates unchanged WP6 scoring into staging, validates reconstruction and provenance, rereads inputs/scorer identity before publishing |

Four specialists owned separate provenance, integration preparation, artifact and integration-test files. The lead integrated contracts, registered tests, reviewed edge cases and reproduced final results. Every new package module is under 300 lines.

The only edit to a pre-existing file is four unit-test registrations added to the already-modified `run_tests.py`. All existing WP6 scorer, runner, tests, notes, fixtures and probe edits were preserved byte-for-byte.

### Provenance and reconstruction

- Caller-provided source and annotation bytes are hashed without rewriting them. Annotation provenance additionally records a portable hash compatible with WP6 scorer identity.
- Dataset pins retain revision, version, manifest identity where available, and all four data-file hashes. JSONL row identities/tiers are bound to context records; duplicate and non-finite JSON values are rejected.
- Exact context records retain ordered chunk text, document/page identity, per-chunk SHA-256, exact joined text and digest, explicit ordered user/assistant history and its digest, and a whole-record digest.
- Missing context differs from explicit empty context. Valid empty Tier 2 reconstruction is preserved; missing or inconsistent evidence is refused rather than fabricated.
- Preparation rejects duplicate retrieval/table/citation identities, inconsistent aliases, mismatched chunk text hashes, wrong citation ownership and inconsistent references. Tier 1 supplied citation metadata must agree with its reconstructed reference.
- An integration test exposed missing Tier 1 citation ownership checks; the new preparation validation was corrected. Existing v1/WP6 citation arithmetic and APIs were not changed.
- Additional malformed nested sidecar/source objects now raise explicit validation errors instead of incidental attribute errors.
- Historical reconstructed evidence remains labelled reconstructed. A proof generated now does not manufacture runtime capture or historical per-chunk hashes.

### Output isolation and retry semantics

Bundles are published only under:

```text
<physical-output-root>/development-comparisons/scorer-2.1.0/<run-id>/
```

The bundle contains four builder payloads:

- `comparison.v2.jsonl`
- `comparison.v2.jsonl.scoring.json`
- `comparison.v2.diff.md`
- `provenance.json`

The publisher adds deterministic `artifact-manifest.json` and `COMPLETED.json`. All payload hashes and sizes are sealed; the completion record binds the manifest. Both records explicitly deny acceptance eligibility. `verify_bundle` validates all six files; the presence of a completion marker alone is insufficient.

The publisher refuses official evaluation-result roots, unsafe identifiers, symlink paths, hard-linked/nonregular payloads, existing claims and existing targets, including empty directories and dangling links. Native no-replace publication closes the POSIX empty-directory replacement race; there is no unsafe `os.rename` fallback.

Ordinary failures remove only this invocation's owned staging/claim inodes and allow retry with the same run ID. Crash leftovers are not stolen or automatically deleted. A post-commit parent-fsync failure raises `PublicationDurabilityError` with the committed bundle path: its complete valid output is preserved, and the same run ID must not be reused.

Native no-replace dispatch supports macOS/Linux when the required libc operation exists. Actual native publication was tested on this macOS environment. Unsupported environments fail closed; Windows publication is not implemented or certified. Output roots must be physical paths (for example `/private/tmp`, not the `/tmp` symlink).

File names and scorer/context identities are reproducible. Recorded generation timestamps may differ; a whole-bundle byte-identical claim is not made for reruns containing timestamped WP6 sidecars.

### Explicit development-only interface

```sh
python -m eval.runner_preparation.offline \
  --results DEV.jsonl --tier 1 --split dev \
  --dataset-rev REV --annotations ANNOTATIONS.json \
  --scorer-version 2.1.0 \
  --output-root /private/tmp/comparisons --run-id local-check
```

The input annotations and exactly one dataset pin/run header are mandatory. There is no implicit annotation creation, scorer upgrade, acceptance option, page-superset fallback, held-out split or full-split execution. Error rows are refused by this exact-context preparation path; this does not decide the pending official V-9 error-row policy. Default accepted evaluation remains the unchanged frozen v1 path.

## Validation evidence

All deterministic commands used the unreachable sentinel URL and network guard:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B <script>
```

No database connection, external provider/API call, live evaluation or held-out evaluation was required. `run_tests.py` itself was not executed because its normal execution queries the application database; its registry checker was used without opening a database.

| Final command | Tests/checks passed | Exit |
|---|---:|---:|
| `test_stage9_wp7_provenance.py` | 11 unittest methods | 0 |
| `test_stage9_wp7_artifacts.py` | 17 unittest methods | 0 |
| `test_stage9_wp7_runner.py` | 15 unittest methods | 0 |
| `test_stage9_wp7_integration.py` | 10 unittest methods | 0 |
| `test_stage9_scoring_v2.py` | 18 unittest methods, including 120 normative examples | 0 |
| `test_stage9_v2_runner.py` | 22 unittest methods | 0 |
| `test_stage9_v2_integrity.py` | 8 unittest methods | 0 |
| `test_stage9_v1_immutability.py` | 21 checks | 0 |
| `test_stage9_scorer_probes.py` | 134 checks | 0 |
| `test_stage9_e0_runner_gate.py` | 110 checks | 0 |
| `test_stage9_e0_frozen_manifest.py` | 24 checks | 0 |
| `test_stage9_b_review_tools.py` | 44 checks | 0 |
| `test_stage9_e2_dev_runners.py` | 38 checks | 0 |
| `test_stage9_review_checks_branches.py` | 38 checks | 0 |
| `test_stage9_gate_branches.py` | 40 checks | 0 |
| `test_p4_eval_framework.py` | 22 checks | 0 |
| `-m eval.probes.scorer_regression --v2 eval.scoring_v2.score --validate-proposals` | 110 dual-scorer probes; proposal copies valid | 0 |
| `-m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json` | REPRODUCED | 0 |
| `docs/remediation/phase_e2_engineering/wp4/validate_revised_proposals.py` | OK | 0 |

**19 commands passed:** 53 new WP7 unittest methods, 48 WP6 methods, 471 existing checks and 110 dual-scorer probes. No test was skipped. The four new suites are registered.

The integration suite exercised real native publication using stored dev-only comparisons pinned to `c1bbcae`: **47/47 Tier 1** and **42/42 Tier 2** reconstructed exactly, with **135 Tier 2 chunks** and **zero v1 drift**. It also checked namespace separation, reproducibility, input mutation, strict reconstruction failures, builder/native failure and retry behavior, v1 defaults, opt-in refusal and import/network isolation. Synthetic malformed-input tests did not run any held-out case evaluation.

Actual command arrays, exit codes and log paths are recorded in `/private/tmp/wp7-final-results.json`; logs are `/private/tmp/wp7-final-*.log`. Tests reconstruct temporary fixtures and do not depend on these evidence files.

## Integrity and remaining decisions

All 44 protected files and every existing WP6 source/test/artifact remain byte-identical. The integration suite additionally checks 70 unique protected/WP6 pins. Frozen manifest identity remains `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`. The index is unchanged. No source results, thresholds, datasets, review workbooks or correction ledgers were modified.

No query or write touched `rag_db`; no production-memory operation, quarantine, migration, staging, commit or push was performed.

Still pending: real-case annotation review, a human-approved flip golden list, formal acceptance of WP6 specification clarifications, v2 adoption, official gate/threshold/output/error policies, review completion, production run-header/manifest integration and WP8 re-freeze. Historical context text identity retains WP6's documented limitations. Native publication on other platforms is not certified.

**Final recommendation:** close the independent WP7 engineering-preparation scope. Report WP7 overall as **partially complete**, with frozen runner/gate integration and all acceptance/re-freezing decisions explicitly deferred to their owner-controlled process.
