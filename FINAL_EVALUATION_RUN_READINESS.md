# Final evaluation run readiness

2026-11-18 · **BLOCKED_BY_POLICY** · official scorer **v1** · no held-out/all evaluation executed.

Synthetic guard verification passes and the committed freeze reproduces. Formal execution remains inactive: the existing owner/reviewer decisions, approved official integration and specific run-bound authorization are absent. The sprint authorization permits live Gemini and preparation; it is not a forged signed or consumed held-out token. Missing review and historical provenance are additional dependencies, not evidence of a failing scorer implementation.

## Verified boundary

| Requirement | Actual official path | Development preparation / disposition |
|---|---|---|
| Frozen integrity and dataset revision | `eval/framework/frozen_manifest.py:151` rebuilds frozen content; all declared assets, dataset and thresholds reproduce. Dataset `phase35-corrected-2026-11-12`, identity `5c58796af13ffe296a08421d9119bbb7f23430d7070d4ace3b281a82e9a7d6a1`. | Committed manifest content identity `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`; 27 manifest asset records. The wider 44-asset protection set is checked by the integration lead separately. |
| Scorer and annotation binding | `eval/phase35/run_eval.py:78` uses v1 `score_generic`; v1 scorer/runner files are freeze-bound. No independent v2 annotation selection is active in this runner. | `eval/runner_preparation/selection.py:4` allows v2.1 only for explicit development plus caller annotations. `eval/runner_preparation/offline.py:50` hashes actual module/annotation bytes; `:89` loads a pinned dataset. These are not official adoption. |
| Runtime configuration and contexts | `eval/phase35/run_eval.py:174` and `:245` retain result/reference/usage fields, not the complete resolved config and distinct exact prompt/scoring-context evidence required by the proposed adoption contract. | `eval/acceptance_preparation/provenance/runtime.py:122` captures supplied exact contexts/config/header identities; `:173` verifies consistency. It is detached, unsigned preparation, not installed in official execution and not proof of historical authenticity. |
| Explicit split | `eval/phase35/run_eval.py:286` defaults to dev; `:274` gates heldout/all before bootstrap. `eval/framework/safety.py:164` rejects heldout/all limits and verifies the freeze. | The future official contract requires explicit selection. Preparation comparison accepts only explicit dev (`eval/runner_preparation/offline.py:68`). Default-dev does not silently select held-out. |
| Approval authenticity / consumption | `eval/framework/safety.py:90` binds JSON marker, nonempty approver/date, split, tiers, canonical output paths and manifest digest. `:111` reads it. No signature/authenticated principal check, expiry or one-time consumption exists. | Genuine authorization must be recorded by the owner. Do not treat a self-authored fixture or nonempty name as an authenticated decision. Future authentication/consumption semantics require the pending gate-policy decision and reviewed integration. |
| Run once and publication | `eval/framework/safety.py:71` refuses an already existing output during preflight. `eval/phase35/run_eval.py:305` has resumable/fresh behavior and `:335` appends records. No atomic cross-process claim or final no-replace bundle is installed in official execution. | `eval/runner_preparation/artifacts.py:137` claims/stages a development run and uses native exclusive publication (`:74`), exclusive metadata writes (`:109`) and fsync. It rejects the official results tree (`:152`). Passing those tests does not certify official publication. |
| Errors, outage and interruption | `eval/phase35/run_eval.py:325` catches case exceptions, records an error row and continues. A crash may leave a partial append file; held-out preflight refuses an existing file. `eval/framework/safety.py:58` reports incomplete totals, not an approved full V9 outage/fallback protocol. | Development comparison refuses error rows lacking exact context (`eval/runner_preparation/offline.py:99`). Adopt a specific owner-approved error/incomplete/interruption policy before official activation; do not resume/retry held-out as development feedback. |
| Deterministic rollback | Official path remains v1; no scorer migration happened. | `eval/acceptance_preparation/adoption.py:103` returns the exact frozen v1 callable; `:111` rollback does the same. Official non-v1 adoption is always refused (`:94`). Tests verify identity without deleting artifacts or mutating configuration. |
| Directory isolation | Historical official results remain untouched. | Development bundles are versioned under `development-comparisons/scorer-2.1.0`; official directory, symlink-parent, duplicate-target and concurrent-claim refusals pass. |

No frozen semantics were patched. Authentic approval/consumption, official atomic publication, runtime capture and outage handling affect the protected acceptance contract; their activation cannot be inferred from general reversible-engineering authorization. The existing decision/adoption boundary explicitly retains those items pending (`eval/acceptance_preparation/readiness.py:21`, `eval/acceptance_preparation/adoption.py:12`).

## Executed verification

Read-only live-state command:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B check_stage9_readiness.py
```

Exit 0: **0 problems, 0 warnings**. Manifest/dataset/historical hashes match. Workbooks remain `NOT_STARTED`: heldout 0 reviewed / 113 pending; dev 0 reviewed / 7 pending. Reading did not alter workbook bytes. This is metadata/integrity inspection, not held-out answer execution.

With the same four environment variables, each exact command below ran serially. All **7/7 scripts passed, 66 unittest methods plus 134 printed PASS checks, no failures/skips**. Counts are heterogeneous and not a claim of 200 unique tests.

| Command | Result |
|---|---|
| `.venv/bin/python -B test_stage9_e0_frozen_manifest.py` | 24 printed PASS checks |
| `.venv/bin/python -B test_stage9_e0_runner_gate.py` | 110 printed PASS checks |
| `.venv/bin/python -B test_stage9_wp7_artifacts.py` | 17 unittest methods |
| `.venv/bin/python -B test_stage9_wp7_provenance.py` | 11 unittest methods |
| `.venv/bin/python -B test_phase_e2_provenance.py` | 11 unittest methods |
| `.venv/bin/python -B test_phase_e2_integration.py` | 15 unittest methods |
| `.venv/bin/python -B test_stage9_wp8_adoption.py` | 12 unittest methods |

Runner guards use temporary manifests/fake bound approvals and tripwires replacing database, providers and case execution. Publication tests use temporary development-only trees, including native no-replace and concurrent/failure injection. No real evaluation questions, live providers or database were executed in this workstream. Detailed output: `/private/tmp/final-runner-focused-results.json`; read-only state output: `/private/tmp/final-runner-live-readiness.log`.

## Required next actions

The lead's final completion report owns the single actionable blocker list. This readiness verdict depends on its genuine independent review/annotation dispositions, recorded SC/V5/V9/scorer-specific threshold decisions, custody or explicit limitation disposition for missing historical originals/runtime evidence, and owner-approved official integration/re-freeze lineage. Only afterward can an authenticated exact run authorization be supplied for the selected split, tier, scorer/threshold identity and unused output. No approval or human review record was created here.

`eval/acceptance_preparation/provenance/historical_limitations.json` preserves the factual limit: reconstructed 42 Tier2 development rows are internally consistent, while original resolved config, row order, prompt bytes/header and original-upload equality are not established. Current matching hashes do not repair those historical facts or establish independent review.

## Actual source identities

Current Git HEAD `690fcfbbf0abdf43b274161a5e6545f7ad11c325`; working-tree source hashes below identify the inspected bytes rather than claiming a clean committed revision.

| File | Raw SHA-256 |
|---|---|
| `eval/phase35/run_eval.py` | `9d4670ce5488499ec79f0cc50598993fc2594ba9d1edb95555b1a6ae379ace94` |
| `eval/framework/safety.py` | `8413ca631990c969add60034b948fd1b684a3feadf3a7362b4266281b079ca68` |
| `eval/framework/frozen_manifest.py` | `4e2869ffbd7c3bcd9a25c84ba684b0ac61632e88b140e6600eac51c2689e9ba9` |
| `eval/phase35/frozen_manifest.json` | `6a66745490cebe050e1318e6ec959ce4cf6d708a10957604b7e193018d0a8648` |
| `eval/runner_preparation/artifacts.py` | `d9266ff7c5510ab6283b6ca7b4857427decb8f227e0a6ac9e1ea4b2dd306666d` |
| `eval/acceptance_preparation/provenance/runtime.py` | `8bf01f6d7e23774dde1eb24272471a1d40a36971cf4e4850822574883c48d1e2` |

**Decision:** do not execute a formal run now. Keep official v1, frozen thresholds and historical outputs intact. Engineering preparation has passed focused verification; policy/review/provenance prerequisites and protected official integration remain pending. Formal acceptance is not established.
