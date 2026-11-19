# Official v1 runner verification

2026-11-18 · `main` at `dec09f664bd7bba978ac02a5da7b24186821eea1` · **NOT READY FOR AUTHORIZED FORMAL RUN**

The official v1 scorer and frozen runner remain unchanged. One confirmed mechanical security defect was fixed within the existing no-overwrite contract: `eval/framework/safety.py:74` now uses `os.path.lexists`, refusing a dangling output symlink rather than treating it as an unused result path. This does not select a scorer, change any threshold or activate evaluation. `scripts/formal_v1_runner_candidate.patch` is the review representation of that one-line fix, not an alternate executable evaluation runner.

## Verification and exact scope

| Concern | Current official v1 evidence and disposition |
|---|---|
| Split/tier/manifest/output approval scope | `safety.py:90–133` binds the marker, approver/date presence, explicit split/tier lists, canonical output paths and manifest digest. `runner_gate:164–192` checks heldout/all before runner bootstrap and refuses partial held-out limits. Synthetic tripwires confirm no database/provider/case execution when the guard refuses. |
| Genuine approval identity | A nonempty JSON name is not authenticated reviewer/owner evidence. No genuine run-specific owner approval is present. Obtain an owner-origin approval with verifiable custody in the existing format; do not assume a particular signature scheme is required by the old freeze or treat a synthetic fixture as approval. Any new authentication mechanism requires explicit integration review. |
| One-time execution | Existing output refuses another preflight, including dangling symlinks after this fix. There is no one-time approval consumption or atomic interprocess reservation; preflight alone cannot prevent a competing writer after checking. Current sprint requires a satisfactory run-once mechanism before execution; this line fix does not provide it. |
| Exclusive publication/interruption | `run_eval.py:305–336` uses resumable/fresh handling and append writes, not atomic no-replace final publication. Interrupted runs may leave partial output; the next held-out preflight refuses existing output. Do not delete/resume an interrupted held-out artifact or silently recycle approval. Owner-approved handling/integration is still required before Phase D. |
| Provider errors/incomplete rows | `run_eval.py:325–334` records exception rows and continues. `safety.threshold_result:58` distinguishes an incomplete denominator. The final acceptance contract must explicitly disposition error/interrupted outputs; no new V9 policy was activated. |
| Identity/provenance | Frozen manifest binds v1 scorer and dataset. Current result rows retain citations, usage and latency, but not complete resolved configuration, ordered scoring-context text and distinct exact prompt-context identities. Historical reconstructed context cannot be relabelled as runtime capture. Required capture or explicit owner disposition remains pending. V2 annotation identity is not an input to official v1. |
| Deterministic scorer preservation | `run_eval.py:78` still calls the original v1 scorer; `eval/answer_scoring.py` and frozen thresholds are unchanged. No v2 selector, annotation overlay or adoption dependency was activated. |

Existing development-only atomic publication/context utilities remain separate and are not claimed to satisfy official execution. Neither SC-01–08 nor the nine v2 adoption approvals become mandatory solely because v2 exists. The selected v1 path must instead satisfy its actual freeze's independent review, dataset disposition and separate execution approval, plus this sprint's explicit operational requirements.

## New regression and integration checks

Exact new test command:

```sh
.venv/bin/python -B test_formal_v1_runner_candidate.py -v
```

**PASS: 6 tests, 0.013 seconds, no skips.** Tests reproduce the prior dangling-link acceptance, apply the one-line patch only to a temporary baseline copy, require equivalence with the actual fixed source, reject links/files/directories without mutation, preserve valid unused paths and empty/missing-parent refusals, and verify request-level refusal before any execution side effect. No database/provider imports or evaluation cases are used. The temporary test replay does not apply a patch to the repository.

Only affected existing guards were rerun for this actual source change:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B test_stage9_e0_runner_gate.py
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B test_p4_eval_framework.py
```

**PASS: 110 and 22 printed checks respectively, both exit 0.** Fake approvals and temporary manifests replace real authority; database, provider and case boundaries are tripwired. Detailed outputs: `/private/tmp/formal-v1-gate-checks.log`, `/private/tmp/formal-v1-framework-checks.log`. No full unchanged regression suite was repeated.

## Reviewable identities

| Source/artifact | Current raw SHA-256 |
|---|---|
| `eval/framework/safety.py` (one-line guard fix) | `33d7e1d3c7cd790c45d7761eab9663ec4388065587cab0559321b4fa80883cc1` |
| `eval/phase35/run_eval.py` (unchanged) | `9d4670ce5488499ec79f0cc50598993fc2594ba9d1edb95555b1a6ae379ace94` |
| `eval/answer_scoring.py` (unchanged) | `c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af` |
| `scripts/formal_v1_runner_candidate.patch` | `70f41f828c74503c4f7bf59bef493c5cdd349b0ff969f3b34ddeb5b62504bb8a` |
| `test_formal_v1_runner_candidate.py` | `f44a16b5231f656b73f1a57d6f43b862f6d4ba3da671f29b977579c3074e2899` |

The guard source is outside the 44 protected assets and declared frozen asset list; the patch changes no frozen input or scorer semantics. No production database, quarantine, migration, provider call, held-out/full-split execution, staging or Git mutation occurred. Human review, owner decisions and actual run-bound authorization remain absent; do not execute a held-out run. The lead owns the single consolidated decision request and final acceptance verdict.
