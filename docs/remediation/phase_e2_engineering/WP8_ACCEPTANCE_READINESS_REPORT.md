# WP8 — acceptance readiness and controlled re-freezing preparation

Date: 2026-11-17. **Engineering preparation complete; formal acceptance, adoption and re-freezing remain pending.** This report is evidence for review, not a sign-off or authorization. The new readiness helper and proposed inventory cannot activate scorer v2, modify a gate or produce an accepted frozen manifest.

## Baseline and protected identity

The recovered baseline is local `main` at `690fcfb`, with six WP6-modified tracked files, 31 existing untracked WP6/WP7 files and no staged changes. The WP8 baseline snapshot records 440 existing working files and 44 protected raw-byte hashes. Frozen manifest content identity remains:

`1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.

Its 27 frozen asset entries, dataset hashes, thresholds, review workbooks, correction ledgers, source PDFs and historical results are not changed. Prior WP6/WP7 implementation is retained; this work adds evidence and preparation interfaces only.

## Acceptance evidence checklist

| Evidence | Current engineering evidence | Acceptance boundary |
|---|---|---|
| WP5 contract | Authoritative scorer v2.1 specification and eight-item clarification register | Three unresolved rules require an explicit disposition; engineering resolutions are not formal approval |
| WP6 implementation | Pure scorer, AV-1–AV-10, 120 normative examples, typed/history/polarity rules, pinned reconstruction and sidecars | Still experimental; no accepted scorer identity is frozen |
| WP7 preparation | Exact provenance capture, explicit selector, isolated output bundles, native no-replace publication and retry tests | Frozen live runner/gate integration is not activated |
| Annotation completeness | 160/160 records structurally VALID; 66 literal forbidden entries; zero malformed/missing/duplicate records in the current baseline | All 160 records need independent annotation review; literal defaults do not establish semantic sufficiency |
| Existing review evidence | Read-only workbook inventory: 113 held-out and seven development case rows have blank decisions | Historical AI-assisted review explicitly is not independent human review |
| Flip accounting | Four available files, 178 row occurrences, eight flip occurrences and four unique tier/case/source-result flips, all inventoried and archived | Every flip remains PENDING_INDEPENDENT_REVIEW; this is not an approved golden list |
| Flip interpretation | Three unique False→True changes and one unique True→False change follow formal rules | The narrowing of cross-sentence contrast is flagged as a possible semantic false negative, not adjudicated truth |
| Context reproduction | All 178 archived contexts and v1 stored/current results reproduce; 89 final-identity v2 rows replay exactly | Old-identity 89 v2 results are recorded historical evidence, not falsely replayed as current code |
| Clarifications | Five engineering resolutions have tests; three precise owner proposals remain pending | All eight clarification records remain NOT_REVIEWED for formal acceptance |
| V1 compatibility | Frozen v1 source/AST/phrase/probe invariants and unchanged default callable are covered by existing and new suites | No hidden adoption of v2 or reinterpretation of v1 records |
| V2 opt-in and isolation | Development version, pin and annotations must be explicit; comparisons occupy a separate namespace | Official adoption API always refuses in this preparation package |
| Manifest integrity | Current manifest hash and protected assets are verified; proposed assets are separate candidate snapshots | Existing expected hash is not regenerated or replaced |
| Rollback | Before activation, deterministic rollback is the unchanged v1 callable and retained frozen assets | Any later activated frozen patch needs a separately approved reverse patch and lineage procedure |

Detailed evidence is in `WP8_ANNOTATION_REVIEW_REPORT.md`, `WP8_ANNOTATION_REVIEW_LEDGER.csv`, `WP8_SCORER_FLIP_ANALYSIS.md`, `WP8_SCORER_FLIP_LEDGER.csv`, `WP8_SPECIFICATION_CLARIFICATION_REGISTER.md`, and `WP8_RUNNER_ADOPTION_PLAN.md`. The lead's `WP8_ACCEPTANCE_EVIDENCE_LEDGER.json` binds final commands/results and produced artifacts. It must not be interpreted as independent human review.

## Exact formal prerequisites

### 1. WP6 formal acceptance

1. Preserve and reproduce the WP5 normative/unit/property/API/annotation/isolation/sidecar evidence (§16).
2. Obtain independently reviewed real-case annotation decisions and their exact dataset/source identities. Resolve TA-03 together with the annotation/scorer policy; do not silently retype literal defaults.
3. Obtain a human-approved golden list covering all observed v1→v2 flips. The ledger must retain source/scorer/annotation/context provenance and every recorded occurrence.
4. Formally disposition specification clarifications and any resulting versioned contract changes. A formal-rule match is not sufficient to approve semantic correctness.

### 2. V2 scorer adoption

1. Satisfy WP6 formal acceptance.
2. Record V-5's acceptance-scorer selection, separate scorer-keyed threshold review, and applicable V-6–V-11 choices.
3. Bind the chosen scorer name/version/hash and reviewed annotation hash to an approved future freeze.
4. Keep v1 the official default until the controlled transition is explicitly approved; retain v1 compatibility and deterministic rollback evidence.

### 3. Frozen runner/gate integration

1. Resolve the official error/provider-outage policy (V-9), run-once/consumed-approval/output policies, review-completion requirements, runtime config/model binding and approval provenance.
2. Review the exact isolated integration changes and their tests at the locations listed in `WP8_RUNNER_ADOPTION_PLAN.md`.
3. Capture actual hashes of the approved patched files; current preparation code cannot fabricate those future hashes.
4. Verify refusal behavior, version selection, provenance, exclusive official outputs and rollback before any activation. No gate or default is changed by the preparation code.

### 4. Evaluation re-freezing

1. Complete required independent human review and owner decisions. Apply only the explicitly approved correction set through the documented controlled process.
2. Validate the resulting dataset and reviewed annotation set; regenerate a new review package without overwriting original review records.
3. Populate the owner-reviewed asset scope, scorer identity, thresholds, runtime binding and approved integration hashes.
4. Generate a **new** lineage-bound manifest, preserve the prior manifest/history, and verify all new hashes. WP5 §15 proposes format 2; this preparation does not activate that format.
5. Authorize re-freezing separately. A completed re-freeze or readiness report does not authorize held-out execution; that requires its own explicit authorization.

## Runnable readiness and proposal interfaces

`eval.acceptance_preparation.readiness.assess_readiness(evidence, review_records=None)` validates a finite engineering checklist: known requirement IDs; PASS/FAIL/NOT_RUN states; nonempty summaries; and traceable relative-path/SHA-256 artifacts. Missing, failed and not-run evidence stays visible. It does not authenticate filesystem truth or human authority; that evidence must be supplied and verified by the caller.

Even a well-formed claimed APPROVED record remains **UNVERIFIED**. Boolean approvals and malformed records are rejected. `formal_acceptance_ready`, `adoption_allowed` and `refreeze_allowed` are always false; `accepted_default` remains `v1`. This is a diagnostic, not a replacement adoption gate.

`propose_refreeze(frozen_manifest, sources)` verifies the parent manifest content identity and all existing asset hashes from explicit source bytes. It creates a deterministic **proposal** with 27 preserved asset snapshots and 20 additional WP6/WP7 candidate snapshots. Portable source hashing is CRLF-neutral; any substantive candidate change changes the proposal identity.

The checked-in `WP8_PROPOSED_REFREEZE_PLAN.json` has schema `phase35-wp8-refreeze-proposal/1`, status PENDING_OWNER_REVIEW, parent lineage identity, and:

- `activation_allowed: false`
- `refreeze_executed: false`
- `accepted_default: "v1"`
- `approved_acceptance_scorer: null`
- `approved_v2_thresholds: null`
- `future_patched_runner_gate_hashes: null`

It deliberately has neither the `content` nor `content_sha256` shape of an accepted frozen manifest. The candidate snapshots are **not** approved future hashes. Expanded service/gate asset scope and actual patched hashes remain review dependencies. Proposal SHA-256: `047d0f57a952d12b18f05e874052a45e80f55011dfd0a38128849474a0fe8ce3`.

## Validation performed for this workstream

Actual command:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B test_stage9_wp8_readiness.py
```

Result: **10/10 unittest methods passed**, exit 0. Tests cover missing/failed evidence, malformed states, fake approval claims, deterministic/detached outputs, portable candidate hashes, changed/missing frozen sources, unsafe candidates, real 27+20 inventory, all 44 protected source hashes, and fresh import without file/network/services access. `git diff --check` passed. No test was skipped by this suite. Final integrated command results belong in the lead's evidence ledger; this report does not manufacture results for commands not executed by this workstream.

No database operations, provider/API calls, held-out/full-split evaluation, production-memory operations, schema changes, staging, commits, pushes or re-freezing occurred. Original annotations, review records, proposals and historical results were preserved.

## Decision and next permissible work

**WP8 engineering preparation is complete, while formal acceptance/adoption/re-freezing remain PARTIALLY COMPLETE and owner-controlled.** Independent reviewers must first record their own judgments under the existing reviewer-exposure rules; these AI-assisted ledgers must not be supplied early as a substitute for that review. At the permitted review stage, the possible cross-sentence false negative warrants attention. The owner can disposition the explicit unresolved policies and integration plan. Completed WP6/WP7 engineering need not be reopened unless those decisions require a versioned change. No official scorer/gate activation or frozen asset update is authorized by this package.

## Final integrated validation

The lead reproduced **24 commands, all exit 0**: 48 new WP8 unittest methods, 101 retained WP6/WP7 methods, 471 existing regression checks, 110 dual-scorer probes, frozen-manifest verification and proposal validation. No tests were skipped. This includes actual archived dev-context/v1 reconstruction and exact current-identity v2 replay; it does not claim replay of unavailable older scorer source. Exact commands and results, artifact hashes, the protected-file inventory and unresolved owner requirements are bound in `WP8_ACCEPTANCE_EVIDENCE_LEDGER.json`.
