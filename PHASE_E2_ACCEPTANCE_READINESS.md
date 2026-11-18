# Phase E2 acceptance readiness, governance and candidate re-freeze

2026-11-18. Project root: `/Volumes/Storage/rag-project`. Coordinator-facing preparation; do not expose AI mechanics to independent reviewers before their own judgments are recorded.

**Engineering preparation complete** does not mean **evaluation accepted**. **Candidate re-freeze prepared** does not mean **official re-freeze authorized**. **Independent review package prepared** does not mean **independent review completed**.

V1 remains official. V2.1 remains development-only. No independent review, owner decision, acceptance, adoption or re-freeze is claimed. The dashboard has 35 requirements and zero ACCEPTED items. All safe work in this handoff is complete; pending decisions and missing external evidence do not block the completed engineering preparation.

## Initial and final repository state

Branch `main`, HEAD `690fcfbbf0abdf43b274161a5e6545f7ad11c325`. Initial: 8 modified tracked files, 101 untracked files, empty staged diff. Final: 8 modified tracked files, 148 untracked files (47 new files). Two pre-existing Finder `.DS_Store` changes remain byte-identical to the initial snapshot, as do all other pre-existing files except six additive registrations in `run_tests.py`. Removing exactly those six lines reproduces its baseline SHA-256. The other 509 pre-existing files and the index were preserved. Nothing was staged, committed or pushed.

Baseline and all 510 original file hashes: `docs/remediation/phase_e2_acceptance_evidence/baseline.json`. `git diff --check` passed. All 44 protected raw hashes remain unchanged; the frozen-manifest verifier reports REPRODUCED, with content identity `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.

## Completed work and ownership

| Workstream | Delivered | New tests |
|---|---|---:|
| Agent 1 — independent review | `independent_review/flip_review_package/`: four full-context/citation/source bundles, neutral post-judgment mechanics, eight historical occurrences, hashes, blank decision template and pending index; blind-first exposure instructions | 8 |
| Agent 2 — clarification governance | `eval/acceptance_preparation/clarifications/`: overlay of the unchanged canonical eight-item register; SC-01–05 retained as unadopted engineering resolutions; SC-06–08 alternatives and required future tests | 7 |
| Agent 3 — gate policy | `eval/acceptance_preparation/gate_policy/`: exact identity, content-bound threshold/gate contracts, unknown/missing/mismatched/error/incomplete refusal, compatibility and eight blank owner decisions | 13 |
| Agent 4 — provenance | `eval/acceptance_preparation/provenance/`: resolved-config allowlist, ordered scoring context, separate prompt bytes/truncation, detached base-header binding, original-upload and historical-limit registers | 11 |
| Agent 5 — integration | `eval/acceptance_preparation/integration/`: candidate/validator, existing v1/dev selection reuse, rollback, future selection contract and re-freeze checklist | 15 |
| Lead | `eval/acceptance_preparation/dashboard.py`, `phase_e2_acceptance_status.json`, this report, evidence ledger and six additive test registrations | 5 |

Only `run_tests.py` changed among pre-existing files. No scorer implementation, frozen asset, annotation, correction ledger, review workbook or historical evidence was modified. The complete created-file inventory and hashes are recorded in `docs/remediation/phase_e2_acceptance_evidence/verification.json`.

## Specification and review boundaries

All four case/tier changes remain PENDING_INDEPENDENT_REVIEW. The reviewer first receives Stage A raw answer/context/source/citation records, records a judgment and rationale in a working copy, and only then sees Stage B scores and neutral mechanics. This is an exposure instruction, not an authenticated filesystem gate. D-conflicting-01 is the highest-priority item; no sentence-scope rule was changed.

SC-06 documents comma/adversative scope and exact boundary alternatives; SC-07 documents narrow compounds versus tens-plus-one expansion and idempotence; SC-08 provides known/unknown/missing/null/non-string status contracts and error alternatives. No option is selected or implemented. The dev-only lexical impact scan found no affected candidates in the 89 existing development rows under the documented conservative criteria; this does not predict zero future scoring impact. No held-out case was evaluated.

## Identity and reproducibility

The development replay binding uses historical annotation hash `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a`, dataset revision `c1bbcae9a21e389c16c3f1587de5acc1b5209e37`, and hardened scorer hash `0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf`. The current package annotation has raw hash `d3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0`, its separate current dataset pin, and scorer aggregate `9648c71d1743a85a595db0175c89e5d38f8ccf3470f11c1f7145e753c369a237`. These bindings are not merged or approved. HEAD is revision context; uncommitted module bytes are bound by their actual hashes.

The new candidate validates 27 preserved parent assets, 20 current candidate snapshots and two separate annotation bindings. Its full digest and validation are in `eval/acceptance_preparation/integration/candidate_manifest.json` and `candidate_validation_report.json`. Approved scorer, threshold, gate, header and future patched-source identities remain unset. Future dependency scope is listed for review with no invented post-integration hashes. The validator rejects stale/tampered candidates and candidate writes into the official `eval/phase35/` subtree.

The seven exact `(1)` upload names are registered with retained paths and hashes; original bytes remain unavailable and equality is NOT_ESTABLISHED. Only the annotation advertised upload hash is known. Historical Tier 2 reconstruction is retained as reconstruction: original runtime overrides, database order and exact prompt bytes remain unproven. The runtime contract accepts explicit supplied values and exact contexts; an origin label is always an unverified caller claim. No synthetic test is relabelled as a captured original runtime.

## Validation

Final integrated suite: **18 commands, all exit 0; 107 test methods (59 new, 48 retained WP8), 289 existing regression checks, 110 dual-scorer probes; zero failures or skipped tests.** Frozen-manifest verification REPRODUCED and revised proposal validation VALID. Earlier 168 methods / 471 checks / 110 probes remain historical evidence in `docs/remediation/phase_e2_engineering/v21_development_verification/verification.json`; that full suite was not repeated.

All final commands ran with `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch`, `TESTSAFE_BLOCK_NETWORK=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `PYTHONDONTWRITEBYTECODE=1`. The URL is a safety guard; no database connection was made. Gate tests use mocks/tripwires, not a held-out evaluation.

Exact final commands (full stdout/stderr and exit codes are preserved in the evidence ledger):

```sh
.venv/bin/python -B test_phase_e2_dashboard.py
.venv/bin/python -B test_phase_e2_flip_review.py
.venv/bin/python -B test_phase_e2_clarification_decisions.py
.venv/bin/python -B test_phase_e2_gate_policy.py
.venv/bin/python -B test_phase_e2_provenance.py
.venv/bin/python -B test_phase_e2_integration.py
.venv/bin/python -B test_stage9_wp8_annotations.py
.venv/bin/python -B test_stage9_wp8_flips.py
.venv/bin/python -B test_stage9_wp8_clarifications.py
.venv/bin/python -B test_stage9_wp8_adoption.py
.venv/bin/python -B test_stage9_wp8_readiness.py
.venv/bin/python -B test_stage9_v1_immutability.py
.venv/bin/python -B test_stage9_scorer_probes.py
.venv/bin/python -B test_stage9_e0_runner_gate.py
.venv/bin/python -B test_stage9_e0_frozen_manifest.py
.venv/bin/python -B -m eval.probes.scorer_regression --v2 eval.scoring_v2.score --validate-proposals
.venv/bin/python -B -m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json
.venv/bin/python -B docs/remediation/phase_e2_engineering/wp4/validate_revised_proposals.py
git diff --check
```

## Requirement dashboard and next actions

Owner roles are identified where source evidence provides a role; no person has been invented or assigned. The historical owner-decision report remains unchanged as historical evidence. Every unresolved requirement below has an explicit next action. Full evidence paths and SHA-256 values are in the machine-readable status register and repeated below.

| Requirement | State | Owner role | Next action |
|---|---|---|---|
| scorer_engineering | ENGINEERING_COMPLETE | Engineering lead | Revisit scorer only for a demonstrated defect or an authorized versioned policy change. |
| flip_review_package | PREPARED_FOR_REVIEW | Independent review coordinator (not named) | Assign an independent reviewer and provide Stage A only before judgments are recorded. |
| flip_review/tier1_D-conflicting-01 | PENDING_INDEPENDENT_REVIEW | Independent development reviewer (not named) | Record an independent Stage A judgment before viewing Stage B; prioritize D-conflicting-01. |
| flip_review/tier1_B-comp-04 | PENDING_INDEPENDENT_REVIEW | Independent development reviewer (not named) | Record an independent Stage A judgment before viewing Stage B; prioritize D-conflicting-01. |
| flip_review/tier1_B-conf-04 | PENDING_INDEPENDENT_REVIEW | Independent development reviewer (not named) | Record an independent Stage A judgment before viewing Stage B; prioritize D-conflicting-01. |
| flip_review/tier2_B-conf-04 | PENDING_INDEPENDENT_REVIEW | Independent development reviewer (not named) | Record an independent Stage A judgment before viewing Stage B; prioritize D-conflicting-01. |
| annotation_review | PENDING_INDEPENDENT_REVIEW | Independent annotation reviewer (not named) | Review original annotation/source evidence and record independent dispositions without overwriting originals. |
| reviewer_assignment | PENDING_OWNER_DECISION | Evaluation owner (not named) | Designate independent development/annotation reviewers and apply the existing S-2 exposure policy. |
| SC-01 | PREPARED_FOR_REVIEW | Scoring-policy owner and independent reviewer (not named) | Review the existing resolution and record formal disposition separately. |
| SC-02 | PREPARED_FOR_REVIEW | Scoring-policy owner and independent reviewer (not named) | Review the existing resolution and record formal disposition separately. |
| SC-03 | PREPARED_FOR_REVIEW | Scoring-policy owner and independent reviewer (not named) | Review the existing resolution and record formal disposition separately. |
| SC-04 | PREPARED_FOR_REVIEW | Scoring-policy owner and independent reviewer (not named) | Review the existing resolution and record formal disposition separately. |
| SC-05 | PREPARED_FOR_REVIEW | Scoring-policy owner and independent reviewer (not named) | Review the existing resolution and record formal disposition separately. |
| SC-06 | PENDING_OWNER_DECISION | Scoring-policy owner and independent reviewer (not named) | Select exact wording and versioned tests in the canonical decision overlay. |
| SC-07 | PENDING_OWNER_DECISION | Scoring-policy owner and independent reviewer (not named) | Select exact wording and versioned tests in the canonical decision overlay. |
| SC-08 | PENDING_OWNER_DECISION | Scoring-policy owner and independent reviewer (not named) | Select exact wording and versioned tests in the canonical decision overlay. |
| gate_contract | ENGINEERING_COMPLETE | Engineering lead | Maintain deterministic refusal tests; no production gate activation. |
| gate_decision/threshold-sharing | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/unknown-identity | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/annotation-mismatch | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/missing-provenance | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/V9-errors-incomplete | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/hard-metrics | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/rollback | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| gate_decision/versioning | PENDING_OWNER_DECISION | Evaluation and gate-policy owner (not named) | Record a decision, rationale, exact content identity and review evidence; recommendations are non-binding. |
| V5_official_scorer | PENDING_OWNER_DECISION | Evaluation owner (not named) | Choose the exact scorer/annotation/dataset identity and approve the reviewed integration only after prerequisite decisions. |
| runtime_capture_contract | ENGINEERING_COMPLETE | Engineering lead | Use synthetic fixtures to verify the contract; installing capture in frozen paths needs separate authorization. |
| original_uploads | PENDING_EXTERNAL_EVIDENCE | Artifact custodian (not named) | Supply original bytes and trusted provenance to compare against the registered retained hashes; never infer equality from names. |
| historical_tier2_runtime | PENDING_EXTERNAL_EVIDENCE | Original run operator / artifact custodian (not named) | Recover genuine original runtime records if available; otherwise preserve the limitation. Do not reconstruct missing facts as runtime evidence. |
| candidate_refreeze | PREPARED_FOR_REVIEW | Evaluation owner and integration reviewer (not named) | Review candidate scope and dependency closure; choose approved identities only after all prerequisites. |
| correction_set | PENDING_OWNER_DECISION | Dataset owner and independent reviewer (not named) | Disposition only the independently reviewed correction set through a separately authorized controlled process. |
| official_integration | BLOCKED_BY_APPROVAL | Evaluation owner (not named) | Approve exact integration patches and dependency scope after review/policy decisions; retain deterministic v1 rollback. |
| official_refreeze | BLOCKED_BY_APPROVAL | Evaluation owner (not named) | Obtain explicit re-freeze authorization, regenerate actual post-approval hashes, review lineage and verify the new freeze separately. |
| heldout_execution | BLOCKED_BY_APPROVAL | Evaluation owner (not named) | Keep evaluation inactive; any future run requires a separate explicit authorization and readiness decision. |
| dashboard_engineering | ENGINEERING_COMPLETE | Engineering lead | Rebuild the status register after genuine new evidence or authenticated decisions arrive. |

## Evidence identities

| Path | Raw SHA-256 |
|---|---|
| `docs/remediation/phase_e2_engineering/PHASE_E2_REMAINING_DECISIONS.md` | `8a880cf84ec74970098471967f7b56be1687db726621aa9ece2fc2c1725327c0` |
| `docs/remediation/phase_e2_engineering/TIER2_V21_DEVELOPMENT_VALIDATION.md` | `98deaea6c1c83c5d086bc2552fa24463235717e863037d8cd29bffd2f9752e87` |
| `docs/remediation/phase_e2_engineering/V21_DEVELOPMENT_IMPLEMENTATION_REPORT.md` | `8abde952ff37cb3468d576abc0fc8d5ed2e78f3163a1342dec80db62a064c9e2` |
| `docs/remediation/phase_e2_engineering/WP8_ANNOTATION_REVIEW_LEDGER.csv` | `c873b6936654e3ee10bdac15f49ca8ec7df7bbbe8a80c083b396739a0b98ef2b` |
| `docs/remediation/phase_e2_engineering/WP8_ANNOTATION_REVIEW_REPORT.md` | `83d5f0eaa75d97630ef10948b252ef888d897ec52596a1e6dce22f59699122b6` |
| `docs/remediation/phase_e2_engineering/WP8_SPECIFICATION_CLARIFICATION_REGISTER.md` | `00fce37da9336a1773daabe01b98c2529c7ff23c5ddcb7379a5e5103537ac18b` |
| `docs/remediation/phase_e2_engineering/v21_development_verification/verification.json` | `fbb993201486760ec39d8d16c67df3891c022ec42bd2e3e97dd9e5379e3d8755` |
| `docs/remediation/phase_e2_engineering/wp4/REVISED_DEV_CORRECTION_PROPOSALS.csv` | `986b40f21852c49b24ef36192512878bafde31c7ef0d9fc7911c9e13db2a0727` |
| `eval/acceptance_preparation/clarifications/decision_package.json` | `f966bf0453ee0b4bf0f9798c4d1064599ac04b965b81812ca63f1cc889860170` |
| `eval/acceptance_preparation/dashboard.py` | `7634fef290b6ebf7beeed191725e704da269ccdc79c8f205cecadff6f11247f8` |
| `eval/acceptance_preparation/gate_policy/decision_register.json` | `10310635cbb4b8630d0cdef9ed4af7003d04c408256d805d5d5235b7d22f2401` |
| `eval/acceptance_preparation/gate_policy/policy.py` | `e9eff83f64de8dd83e6b70cda0a389119f74c16a1e2b95289245268a79087bde` |
| `eval/acceptance_preparation/gate_policy/schema.md` | `e8bc39b70bef2adf0b96e73c0b6f9a195b6a0b60b79190b0a1b4d2a48a23b1ca` |
| `eval/acceptance_preparation/integration/candidate_manifest.json` | `bbd89b928d37baf51b237243c23d81a8822b64e5cd122c81b6ce396d917b0d9b` |
| `eval/acceptance_preparation/integration/candidate_validation_report.json` | `f62f65e04499292cd1b2abe2b3c473e1a7c4f28e75ddfb8a5f4c433de7ca4c72` |
| `eval/acceptance_preparation/integration/refreeze_checklist.md` | `d84238fc52a17193654b06700456ccc7d2677153571c80a7d6a1af077c15258c` |
| `eval/acceptance_preparation/integration/selection_contract.md` | `373d6d9af900bf3e0d9d5f2d37c1ad88421d12b9a9d4437f1e5bfcba605ab9ad` |
| `eval/acceptance_preparation/provenance/historical_limitations.json` | `90d4897f91f96b18cac010651b551e682b0cffef1129f9b88dff6f78c0505aaa` |
| `eval/acceptance_preparation/provenance/runtime.py` | `8bf01f6d7e23774dde1eb24272471a1d40a36971cf4e4850822574883c48d1e2` |
| `eval/acceptance_preparation/provenance/schema.md` | `11496f823c28abbbb7fde377d9d52d66d217e8555f60621ec5b7e75c95caeac6` |
| `eval/acceptance_preparation/provenance/upload_identity_register.json` | `2d2a96538e6e916abd49d1f57959a3101d4bf39bfb58877dd2413b8a40353f04` |
| `independent_review/flip_review_package/README.md` | `f8b0d698ce0e1458b316023b0e1d6e081960fd7bd4a6662ce0ed576ed0365921` |
| `independent_review/flip_review_package/package_manifest.json` | `4cad22792f7369d7289145822dda8021a5f9cc23bbff074257bffb32cf90bb6f` |
| `independent_review/flip_review_package/records/tier1_B-comp-04/stage_a_blind.json` | `7a50cba15d82e8958bce3c0f789bbad9931a9a31dce92524f31f93cdf2bbcb42` |
| `independent_review/flip_review_package/records/tier1_B-conf-04/stage_a_blind.json` | `d9f6a7168c525509018d181a77ca9f467a27bc9cd3c0f77a6cffea2a1a9043b4` |
| `independent_review/flip_review_package/records/tier1_D-conflicting-01/stage_a_blind.json` | `b5271654878b45aeaef1bbb7b809947e02f219fc1d668f50272582c569c8506b` |
| `independent_review/flip_review_package/records/tier2_B-conf-04/stage_a_blind.json` | `53ec88113228a530a6b8e9ab76dbe3bf991642c65cddc1e2cf375897134daa38` |
| `independent_review/flip_review_package/review_status_index.json` | `db0aed9fdf4262c2e545ec1dd8ddd8fbafdecbe1fada018cca1a390f894ec925` |
| `test_phase_e2_dashboard.py` | `1e558300cc6ce3629c4ec427ea0bb30fbde3e99bcc0d65e6d655cb5c54230ab7` |
| `test_phase_e2_gate_policy.py` | `74a49a219d221b4e5a1b46beaab4a76e5e0f114cb5765f318e37a7c5bab379d9` |
| `test_phase_e2_provenance.py` | `fe84f31fa9fbe8cb956e42d8acab8e012b5b568025e5e0faa18f6e8b75922201` |

## Safety and remaining limits

No database operations or writes to `rag_db`; no production-memory operations, backfills, migrations, schema changes, quarantine, provider/API calls, held-out/full-split evaluation, production evaluation, official gate changes or scorer adoption occurred. No reset, clean, stash, staging, commit or push occurred. Frozen assets and pre-existing staged/unstaged/untracked work remain intact.

Independent annotation/flip review, SC-06/07/08 decisions and formal disposition of SC-01–05, V-5 adoption, scorer-specific thresholds and metric roles, V-9/error policy, correction-set disposition, approval authenticity/run-once policy, actual frozen integration, explicit re-freeze approval and any future held-out authorization remain external gates. Native publication certification remains limited to macOS. Original uploads and historical runtime evidence remain external limitations, not engineering defects.

Next: the owner designates independent reviewers and a coordinator; reviewers record Stage A judgments before AI mechanics, with D-conflicting-01 prioritized. Owners then record exact policy decisions in working copies of the prepared overlays. After genuine decisions arrive, prepare only the authorized versioned changes and reviewed integration patch, regenerate actual hashes and seek a separately authorized freeze. Completed scorer work need not be reopened without a demonstrated defect or an approved policy change.
