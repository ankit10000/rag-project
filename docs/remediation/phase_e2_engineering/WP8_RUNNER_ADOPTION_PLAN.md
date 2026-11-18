# WP8 runner and gate adoption preparation

**Engineering preparation: implemented and tested. Official integration and adoption: PENDING_OWNER_DECISION.** This plan neither changes a frozen interface nor authorizes an evaluation. The current manifest remains `phase35-frozen-manifest/1`, content SHA-256 `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`. V1 remains the official default.

## Implemented boundary

New module: `eval/acceptance_preparation/adoption.py`. Existing WP6/WP7 code is unchanged.

| Interface | Behavior |
|---|---|
| `build_adoption_plan(manifest, evidence)` | Pure, deterministic plan. Records internally computed manifest digest and unverified caller claims; every adoption requirement remains pending, `official_default="v1"`, `activation_allowed=false`. It does not perform filesystem verification or authenticate a reviewer. |
| `assert_official_adoption_allowed(...)` | Always raises `AdoptionBlockedError`, including when a caller supplies a purported approval, complete review, eligible sidecar or proposed format-2 manifest. This preparation module has no activation capability. |
| `select_official_scorer()` | Returns exactly the existing frozen five-argument `eval.phase35.run_eval.score_generic` function. Any explicit official version other than `v1` is refused. No frozen caller was redirected to this helper. |
| `rollback_to_v1()` | Returns that same v1 callable; writes no files, changes no gate and deletes no artifacts. |
| `rehearse_development_comparison(...)` | Requires literal `development=True`, version `2.1.0`, tier 1/2, dev split, annotations and one dataset pin. Delegates unchanged WP7 `prepare_comparison`; it is an offline diagnostic rehearsal, not an official evaluation. |

There is no acceptance, caller-approval or live-provider option on the rehearsal interface. Existing WP7 checks reject held-out/full-split execution, fabricated annotations, invalid provenance, mismatched reconstruction, unsafe output roots and existing run IDs. Its output remains exclusively:

```text
<physical-output-root>/development-comparisons/scorer-2.1.0/<run-id>/
```

WP7 seals comparison JSONL, versioned scoring sidecar, difference report and provenance proof, then binds them with `artifact-manifest.json` and `COMPLETED.json`. `verify_bundle` checks hashes; a completion marker by itself is insufficient. All resulting metadata denies acceptance eligibility. Physical paths are required because symlink components are deliberately refused. Ordinary failures clean only owned incomplete resources; native publication and durability semantics remain WP7's unchanged contract.

## Required frozen changes after owner decisions

The following are review targets, **not applied changes**. Named interfaces are stable code locations; line numbers describe the current baseline and can move in a later approved patch.

| Current code location | Future reviewed integration | Required authority |
|---|---|---|
| `eval/phase35/run_eval.py:284`, `main`; `:272`, `enforce_split_gate` | Add an explicit scorer/version interface that retains v1 default; bind official selection to an approved manifest before bootstrap or output creation. Keep development comparisons separate from official outputs. | V-5, approved output/run-once policy, re-freeze |
| `eval/phase35/run_eval.py:163`, `run_tier1`; `:212`, `run_tier2` | Capture the exact scoring context/hash and ordered chunk identities at execution time, plus explicit user/assistant history, models/configuration and input identity. Reuse WP7 context records behind the approved runtime schema. Historical reconstruction must never be relabelled as runtime capture. | Runtime header/config/model policy and approved frozen integration |
| `eval/phase35/run_eval.py:259`, `bootstrap_execution`; `main` error/write loop | Introduce only the approved provider preflight, outage/error policy, durable output and library-level isolation behavior. This preparation performs no provider/DB work. | V-9 and the separately reviewed reliability/isolation policy |
| `eval/framework/safety.py:164`, `runner_gate`; `:128`, `check_run_request`; `:111`, `approval_problems`; `:71`, `protect_output` | Bind approved scorer identity, review completion, manifest lineage and output claim. Implement the chosen consumed-approval/run ledger policy, including concurrent claims, stale claims and retry semantics. Preserve refusal before any side effect. | Owner choices in `PHASE_E2_REMAINING_DECISIONS.md` §1.D; no choice inferred here |
| `eval/framework/safety.py:31`, `FROZEN_THRESHOLDS`; `:58`, `threshold_result` | Add scorer-keyed policy only after a separate threshold review. Never reuse v1 limits for v2 merely because an implementation exists. | V-5 and explicit threshold approval |
| `eval/framework/frozen_manifest.py:25`, `MANIFEST_FORMAT`; `:30`, `FROZEN_ASSETS`; `:77`, `build_content`; `:132`, `load_frozen_manifest` | Prepare a reviewed format/lineage transition, `scorer_v2` assets, annotation identity, accepted scorer and approved runtime/gate scope. Produce a new manifest; retain the old manifest and expected hash. | Approved correction/review package and re-freeze authorization |
| `eval/framework/cli.py:73`, `cmd_report` | Require explicit version-aware reporting for v2, verify its sidecar, and keep v1 stored/current/v2 distinctions. An observed flip is not a golden-list approval. | Approved reporting/acceptance contract |
| `eval/review/cli.py:26`, `DATASET_VERSION`; `_manifest_sha`, `cmd_build_dev_review` | Bind future review packages to the approved dataset/manifest lineage; create new reviewed artifacts without rewriting frozen workbooks or ledgers. | Independent review, correction decisions and reviewed package authorization |

No speculative patch is supplied: unresolved gate/error/output/approval policies would make a runnable frozen patch imply decisions that have not been made. The actual safe code is the preparation boundary above; future frozen edits need a reviewed concrete patch, affected tests and a new lineage-bound manifest.

## Acceptance checkpoints

These remain independent requirements, even if a caller claims they are complete:

1. Independent real-case annotation review with exact source/provenance linkage and correction decisions, including the TA-03/V-5 dependency.
2. Human-approved complete flip golden list; reproducible exact dev reconstruction and zero v1 drift are supporting engineering evidence only.
3. Formal disposition of specification clarifications and applicable V-6–V-11 scoring semantics. The formal-grammar residuals cannot be silently widened during integration.
4. Explicit V-5 scorer adoption, separate scorer-keyed threshold review and V-9 error/outage policy.
5. Approved frozen gate/output/approval/review-completion policies, runtime provenance schema and deployment-platform checks.
6. Independent acceptance/readiness review, approved manifest lineage and authorization to re-freeze. A prepared manifest proposal is not an accepted manifest.
7. A future held-out readiness review and separate explicit evaluation authorization. Neither this plan nor passing its tests authorizes held-out or `--split all` execution.

The acceptance-readiness workstream may consume this plan as diagnostic evidence. Caller fields such as `approved=true`, `review_status=COMPLETE` or `acceptance_eligible=true` never supply human authority to this module.

## Test coverage and evidence

Command, with no external services or database operations:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B -m unittest test_stage9_wp8_adoption
```

**12 unittest methods passed, exit 0.** Tests cover current-manifest refusal, deterministic plans, fake owner/reviewer claims, forged future manifests and eligible sidecars, exact v1 callable identity/results, malformed evidence, explicit opt-in/version/dev-only selection, unchanged WP7 delegation, absent acceptance switches, native synthetic publication, official-result namespace rejection and rollback preserving artifact bytes. The integration uses one synthetic case and mocks only WP6's dataset loader; it performs no live or historical full-split evaluation.

The suite also checks all 44 protected raw hashes and the pre-WP7 WP6 pins (70 unique protected/WP6 assets), and confirms that the frozen runner imports neither preparation code nor v2. Lead-level baseline verification covers unchanged WP7 files and the complete pre-WP8 working state. Passing tests establish engineering behavior; they do not certify human review, scoring policy or another platform's native publication.

## Rollback without resets or overwrites

At this milestone no adoption occurred. `rollback_to_v1()` deterministically returns the original `score_generic` callable, so there is no file or manifest rollback to execute. Existing v1 runner/gate paths remain active; rehearsal bundles and historical results stay intact.

For a future authorized integration, the reviewed release must retain an explicit v1 selection and its own manifest/threshold lineage. A rollback would select that preserved v1 path and create new, separately identified results; it must not overwrite v2 artifacts, rewrite past scores, reclaim consumed approvals, reuse official run identities, or change a frozen manifest in place. The exact deployment change and rollback test must be reviewed with that future patch. No `git reset`, cleanup, broad staging, commit or push is part of this procedure.

**Current disposition:** safe development rehearsal is available. Official runner/gate adoption, formal acceptance and re-freezing remain blocked on the owner and independent-review checkpoints above.
