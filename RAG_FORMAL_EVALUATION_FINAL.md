# RAG formal evaluation final

Updated 2026-11-19 · **FORMAL_EVALUATION_INCOMPLETE**

## Latest AI-reviewed acceptance handoff — 2026-11-19

**LOCAL_V1_RELEASE_READY / LIVE_PROVIDER_VERIFIED / AI_REVIEW_COMPLETE / AI_TECHNICAL_EVALUATION_FAIL / OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING.** Local readiness retains its previously tested single-user, single-process scope; this task did not repeat release engineering or certify production operation. Formal evaluation remains incomplete.

The existing 113-case AI ledger and all 339 initial judgments were preserved: 83 AI_PASS, 22 recommendations, eight ambiguities. `AI_FINAL_DATA_DISPOSITIONS.md` supplies source/page/hash-bound proposed dispositions for all 30 outstanding cases, including the 48-hour notice and 31 Nm torque, plus eleven TA and ten TP comparisons. These remain AI recommendations requiring genuine itemized owner decisions. The owner describes earlier agents as Claude Code; available artifacts record agent identities and unavailable exact model IDs. This handoff does not retroactively attribute those judgments to ChatGPT. The current reviewer designation is AI technical review, never a human signatory.

`AI_ACCEPTANCE_POLICY_CANDIDATE.json` is separately versioned and **CANDIDATE_NOT_ADOPTED**. Execution dataset selection, numerical thresholds and specific owner adoption remain pending. Proposed metrics, ceiling-based minimum derivation, citation/abstention semantics, source provenance, error handling and publication controls are explicit; old v1 thresholds and development-only v2.1 are not automatically adopted. Candidate SHA-256: `34a8aaf5da4429df98326b81cc724bfde4d2a00a0d61b3ffb587a38deb8d1302`.

The new synthetic Lumen run `ai-lumen-postfix-live-20261119-v1` used four actual Gemini calls and separately predeclared dataset/policy identities. Actual model: `gemini-3.5-flash-lite`; elapsed 28.6852 seconds. **New live result: FAIL, 3/4.** Supported positive, explicit no-fax-service negative, and missing-number abstention passed. The mixed fee/missing-address response incorrectly reported `answered` instead of `partial`. Original Kestrel **FAIL, 3/4** remains separately immutable; neither run was rescored or rerun. See `AI_POSTFIX_DEVELOPMENT_RESULT.md` for raw-output identities and limitations. Exact prompt-body hashes were not captured in this development experiment; source hashes are not a substitute.

The observed mixed-answer failure exposed `addresses?` failing to recognize singular “address”. A one-pattern correction to `address(?:es)?` and focused regression now classify the exact saved response as `partial`, retaining the cited answer. Pure singular/plural omissions and explicit negative facts are also covered. This deterministic repair does not turn either historical live FAIL into PASS. Current helper SHA-256: `3f3bcdff4f3871774a480478ccf647823fbe8ecf4b9af95ae5756847c268d4e8`; the executed pre-repair helper remains separately preserved in the new run's read-only source snapshot.

Runtime capture now also binds `services/citation_service.py` and `services/answer_semantics.py`. Eleven capture tests cover actual hashes and dependency drift rejection without final publication. Capture source SHA-256: `be0f617bf71417bdc02d48489ce1d1e68c9f83788e98f0d549b425f23d54ebba`. Existing signed scope, external trust, one-use claims, frozen identity and no-replace publication protections remain in place. Candidate invocation only (not executed; no token created):

```python
execute(
    owner_bound_scope,
    authenticated_owner_approval,
    authority=externally_registered_authority,
    ledger_root=owner_bound_scope["ledger_root"],
    runtime_config=approved_resolved_runtime,
    verify_prerequisites=verify_actual_review_dispositions_and_frozen_runner_gate,
    executor=reviewed_frozen_v1_adapter,
    capture_snapshot=runtime_capture.snapshot,
)
```

The prerequisite callback must establish actual human review, itemized owner decisions and the original frozen-runner gate. Synthetic credentials or AI judgments cannot establish them. Human independent review remains **0/113**. No genuine approval token or owner adoption was fabricated; the original human-certified path remains inactive.

Final deterministic verification against the corrected tree: **nine scripts passed, 51 unittest methods and 232 printed checks**, no failures. Each command below ran with `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 LOCAL_V1_PROFILE=0`:

| Exact command | Result |
|---|---|
| `.venv/bin/python -B test_ai_acceptance_policy.py` | 9 tests PASS |
| `.venv/bin/python -B test_ai_postfix_development.py` | 7 tests PASS |
| `.venv/bin/python -B test_official_v1_capture.py` | 11 tests PASS |
| `.venv/bin/python -B test_abstention_contract.py` | 17 tests PASS |
| `.venv/bin/python -B test_abstention_policy.py` | 7 tests PASS |
| `.venv/bin/python -B test_context_and_citations.py` | 62 checks PASS |
| `.venv/bin/python -B test_answer_phase3.py` | 69 checks PASS |
| `.venv/bin/python -B test_stage6_answer.py` | 66 checks PASS |
| `.venv/bin/python -B test_b3_answer_reliability.py` | 35 checks PASS |

No database operation, protected held-out execution, frozen asset edit, human-record edit, staging, commit or push occurred. The only provider work was the four authorized new synthetic calls. All 44 protected hashes and unrelated baseline files were checked unchanged; the existing staged diff and HEAD were preserved. Historical manifests and the sections below describe earlier revisions and outcomes; they were not regenerated to incorporate this later report. The AI-reviewable handoff is complete with a genuine diagnostic FAIL and a deterministic fix. Policy adoption and original independent-human review/disposition/authorization requirements remain external acceptance prerequisites.

## Historical completed AI review and separate development evaluation

**AI_REVIEW_COMPLETE:** all 113 held-out definitions now have three immutable initial AI reviews and a source-bound consolidated disposition: **83 AI_PASS, 22 AI_CORRECTION_RECOMMENDED, 8 AI_AMBIGUOUS, 0 insufficient-evidence cases**. These are definition-review counts, not model accuracy or human approval. All 339 initial records, source hashes, actual execution identities, unavailable exact reviewer-model IDs and initial exposure disclosures are preserved. Forty lead dispositions cover the initial issue set and two additional prior-proposal cases; all eleven prior held-out TA items and ten applicable TP groups are compared without applying them.

**AI_TECHNICAL_EVALUATION_FAIL:** a separately versioned, predeclared four-case synthetic development exercise produced real Gemini outputs, **3/4 strict-policy passes**, four SDK calls, zero fabricated citations and zero ungrounded numeric values. All returned `gemini-3.5-flash-lite`. The fourth response correctly states that the synthetic policy provides no fax number, but its `answered` status and the v1 insufficiency-phrase criterion fail the predeclared abstention requirements. That FAIL, original score and source-supported semantic interpretation are all preserved. No rerun, scorer edit, post-result threshold change or copied held-out case was used.

**OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING:** the AI-led pathway was explicitly authorized by the owner and is complete within its technical scope. It is not adoption of an AI-based formal acceptance policy. Original human review remains **0/113**, and no protected question was executed. Conditional freeze retention, genuine itemized reviewer/owner decisions, settled activation conditions and exact run authorization remain distinct requirements. No further general approval or reviewer-designation request was made.

Current deliverables:

- [AI_HELDOUT_113_REVIEW.jsonl](AI_HELDOUT_113_REVIEW.jsonl): all 113 source-evidenced AI records, including initial judgments and separate adjudication.
- [AI_HELDOUT_REVIEW_SUMMARY.md](AI_HELDOUT_REVIEW_SUMMARY.md): findings, eight preserved ambiguities, comparison and reproducibility.
- [AI_CORRECTION_DISPOSITIONS.csv](AI_CORRECTION_DISPOSITIONS.csv): 113 case-level AI dispositions and prior-proposal links; no owner or human decisions fabricated.
- [AI_EVALUATION_RESULT.md](AI_EVALUATION_RESULT.md): actual four-case results, recorded failure and evidence hashes.

Final validation: **20/20 focused tests PASS**, 1.126 seconds, no failures/skips; exact published-ledger rebuild equality and 113-ID/eleven-column CSV round-trip also pass. Actual source inspection covered 12 retained PDFs/56 pages, with quotations, PDF/page hashes and full-source absence scopes validated. The initial review hash manifest and `ai_review/final_manifest.json` bind provenance and final artifacts. Neither matching source text nor AI agreement recovers unavailable original-upload/runtime evidence.

Exact current commands:

```sh
.venv/bin/python scripts/ai_development_evaluation.py prepare
.venv/bin/python scripts/ai_development_evaluation.py run
TESTSAFE_BLOCK_NETWORK=1 DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m unittest test_ai_heldout_review test_ai_development_evaluation -v
```

The prepare/run processes exited 0 because the harness reports execution completion through the process code; the saved/printed evaluation status is **FAIL**, not PASS. The offline test command exited 0 with 20 tests. No database connection occurred; only four authorized development Gemini calls occurred. The unchanged application/runner regression suites were not repeated. All 44 protected assets, prior work and human fields remain intact. The sections below retain prior engineering and frozen-policy evidence; they are not an assertion that AI review satisfies human sign-off.

**Selected path: official v1, retaining the current freeze only after itemized reviewer and owner disposition. Phase A decision: `V1_REQUIRES_DATA_DISPOSITION`.** No held-out evaluation was executed. The owner confirms that no independent reviewer, completed 113-case review or signed approval exists. The remaining mechanical execution envelope, runtime capture and reporting integration are now implemented and synthetically tested. Passing those checks is not formal acceptance or permission to activate a protected run.

## Official identities and approved thresholds

Baseline: clean `main` at `dec09f664bd7bba978ac02a5da7b24186821eea1`. The prior sprint's working tree was committed before this task; this task did not create that commit. Branch, HEAD and staged bytes remain unchanged.

The final-execution follow-up began on the same HEAD with the existing safety fix, eight untracked preparation files and an additional pre-existing `eval/.DS_Store` modification. All were preserved. Its baseline contains 591 Git-listed file hashes in `/private/tmp/formal-execution-baseline.json`.

**Confirmed owner authority:** routine engineering, reversible mechanical protections, safe synthetic testing and readiness preparation are authorized. Held-out execution is conditionally authorized only after all genuine frozen-policy prerequisites are satisfied. No further general authorization was requested. That permission supplies neither human review nor disputed-label dispositions, registered trust credentials, settled activation/error policy or an authenticated exact run token.

| Item | Verified identity |
|---|---|
| Official scorer | v1, unchanged `eval/phase35/run_eval.py::score_generic` plus `eval/answer_scoring.py` |
| Runner raw SHA-256 | `9d4670ce5488499ec79f0cc50598993fc2594ba9d1edb95555b1a6ae379ace94` |
| Answer-scoring raw SHA-256 | `c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af` |
| Dataset version | `phase35-corrected-2026-11-12` |
| Dataset identity | `5c58796af13ffe296a08421d9119bbb7f23430d7070d4ace3b281a82e9a7d6a1` |
| Frozen manifest content identity | `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97` |
| Raw manifest SHA-256 | `6a66745490cebe050e1318e6ec959ce4cf6d708a10957604b7e193018d0a8648` |
| Annotation identity | No v2 annotation package is consumed by official v1. Current dataset expectations are freeze-bound. |

Actual frozen-manifest reproduction passed read-only through `scripts.formal_v1_report.current_identity()`; no manifest was rebuilt or replaced. Owner-approved v1 values are recorded in `docs/remediation/HELDOUT_THRESHOLD_FREEZE.md:3–17,56`, the frozen manifest's threshold object, and `eval/framework/safety.py:31–35`:

| Split / tier | Cases | Minimum correct | Current formal comparison |
|---|---:|---:|---|
| Development Tier 1 | 47 | 41 | Historical saved score 41/47; not evidence of a fresh current-dataset run |
| Development Tier 2 | 42 | 28 | Historical saved score 28/42; same provenance limitation |
| Held-out Tier 1 | 113 | 97 | **NOT EVALUATED** |
| Held-out Tier 2 | 106 | 69 | **NOT EVALUATED** |

Exact minimums are not rounded down. The 85%/65% percentages remain frozen. If an approved correction changes eligible counts, the documented pre-run correction procedure requires new denominators/minima rounded upward using those same percentages and a new freeze before results. No such change occurred.

## Genuine review and data decisions

Read-only current-workbook progress reports show **0/113 held-out and 0/7 development reviewed**, with reviewer identity/sign-off blank and no integrity errors. All 26 historical correction ledger entries are preserved; no new reviewer judgment or proposal was invented. The prior Claude sign-off is explicitly AI-assisted and is not the required independent human review. No independent approving authority or final acceptance judgment is recorded.

The actual v1 freeze requires review of **all 113 held-out records**, followed by separate user execution approval (`HELDOUT_THRESHOLD_FREEZE.md:38–40`; current review README). Seven development reviews remain separately commissioned; four development scorer-flip judgments and 160 v2 annotation reviews are **not blanket prerequisites for retaining official v1**. V2.1 remains development-only; SC-01–08/v2 adoption and new v2 threshold approval were excluded from this shortest v1 path.

The original 25-item AI revision list is largely historical: its approved/applied edits are already in the current correction ledger. It was not reapplied. Revised 11 held-out TA proposals and the potential TP findings still need genuine reviewer/owner disposition. Technical validity of the current freeze does not settle source-authority labels, missing required facts or substring-scoring fairness. No individual AI recommendation is an approved correction. See [FINAL_EVALUATION_DECISION_MATRIX.md](FINAL_EVALUATION_DECISION_MATRIX.md) for the source-bound retain/correct alternatives; do not give AI explanations to a reviewer before their independent judgments.

**Owner decision received:** retain the current freeze **only after itemized reviewer and owner disposition of its remaining data concerns**. This chooses conditional retention, not unconditional acceptance of current labels or the alternative correction-candidate route. Keep official v1 and its frozen numbers unchanged. No correction, exclusion, waiver, re-freeze, error-policy or run-specific execution approval was granted. No versioned candidate was created.

## Official runner verification and actual fix

One confirmed mechanical security defect was corrected: `eval/framework/safety.py:74` now uses `os.path.lexists` so a dangling output symlink is refused under the existing no-overwrite contract. This source is outside the 44 protected assets and frozen manifest assets. The one-line fix changes no scorer, dataset, threshold or frozen execution semantics. Its reviewable diff is `scripts/formal_v1_runner_candidate.patch`; it is not a replacement evaluation runner.

The frozen `run_eval.py` entry point remains unchanged, including its original append/error behavior. The earlier verification is retained in [FINAL_V1_RUNNER_VERIFICATION.md](FINAL_V1_RUNNER_VERIFICATION.md). This follow-up adds an **unactivated execution envelope** in `eval/official_v1_execution.py` and scoped capture in `eval/official_v1_capture.py`; neither imports a default protected executor or creates a real approval. There is no new live-run CLI or automatic bypass of the existing frozen runner gate.

| Implemented mechanical control | Tested behavior and boundary |
|---|---|
| Authenticated external approval | HMAC verification uses an explicitly supplied external trust anchor; keys are excluded from object representations. No real key, owner identity, signature or approval is generated. This is a candidate mechanism, not a newly approved official authorization format. |
| Exact scope | Signed manifest, dataset, both v1 source hashes, tier, split, canonical unused output, persistent ledger namespace and resolved-runtime digest are compared before execution. Invalid authentication invokes no external prerequisite, executor or capture callback. Callback/caller mutations cannot change detached signed inputs. |
| Genuine prerequisite boundary | A trusted external verifier must inspect real review and policy evidence; missing/false/true self-attestation flags do not establish approval. Synthetic verifiers/keys are confined to tests. Actual human authenticity and trust registration remain external evidence. |
| One-time execution | Durable exclusive claims reserve both approval ID and output identity before the executor. Competing approvals targeting one output cannot both execute. Claims survive failure/interruption and cannot be replayed through a different signed ledger path. Trusted ledger custody is required; records are never automatically reclaimed. |
| Failure and publication | Private fsynced journals retain partial rows without a completed output. Typed canonical rows, eligible coverage and capture evidence must validate before a sealed 0400 bundle is atomically linked without replacement. Collisions preserve foreign bytes. Post-link durability failure leaves a complete verifiable bundle and consumed claims; retry cannot replace it. |
| Frozen semantics | Canonical v1 error rows and null conditional flags are retained with explicit counts. Completeness and error counts are separate from acceptance. No new V9 invalid-run threshold, retry permission or v2 scoring policy was activated. |
| Runtime provenance | Capture hooks preserve arguments, return objects and exceptions at model attempts, Tier 1/Tier 2 context assembly and frozen scoring. Exact prompt, assembled context and scoring context have distinct ordered hashes; scoring evidence is tied to each non-error case and score digest. Resolved non-secret configuration and source hashes are checked for drift before, during completion and before publication. |

The fresh default identity verifier reproduces the actual freeze, source bytes and eligible IDs before and after the callback execution. Configuration uses a closed allowlist and rejects credentials/DSNs and production database names; this metadata check is not a claim that a real database was opened or verified during these tests. Hooks restore after exceptions and reject overlapping captures. Raw prompts, source text and private document names are absent from capture metadata. Model-attempt capture does not claim visibility into internal SDK HTTP retries. POSIX filesystem mechanics were tested in the current macOS environment.

These controls are implemented and integrated with synthetic execution. **Protected activation is still absent:** a reviewed real executor/approval-custody integration and applicable owner policy/evidence are required before invoking protected cases. The generic callback API is not an execution sandbox or an independent human-review authority. HMAC and bundle checksums do not prove that a human performed a review; self-recomputed checksums establish consistency only.

## Tested reporting procedure

New `scripts/formal_v1_report.py` validates actual frozen identities, raw-result digest, strict JSON, eligible unique IDs, tier/split, typed finite metrics and usage before aggregating existing stored v1 scores. It reuses current metric/threshold definitions without rescoring. It reports correctness, heuristic unsupported claims, structural citation correctness/completeness, abstention and latency; semantic entailment remains unavailable. Canonical exception rows retain their null conditional flags. Complete counts, incomplete runs and errors are reported separately, without inventing a new official V9 policy.

The diagnostic procedure **always** emits `FORMAL_EVALUATION_INCOMPLETE`; caller-supplied reviewer/approval strings cannot establish formal acceptance. It publishes one fully written, fsynced, read-only report via atomic no-replace link, refuses symlink parents/final collisions and the official results directory. A post-link directory-fsync error preserves the complete destination; inspect that file rather than retrying over it. This is report publication, not activation of official result publication.

After an actually authorized run, use `.venv/bin/python -B scripts/formal_v1_report.py --results <raw.jsonl> --metadata <metadata.json> --split heldout --tier <1-or-2> --output <new-diagnostic.json>`. Metadata must match `current_identity()` plus `results_sha256`; hashes establish consistency, not authenticated execution/review. The approving authority must separately establish the final acceptance record. No report containing fabricated formal metrics was generated here.

The new `eval.official_v1_capture.report_from_bundle(path)` bridge verifies the exact saved envelope bytes, scope and capture hashes, reproduces the current frozen identity, and passes the saved rows to the **unchanged** existing reporter. It retains the bundle/rows/runtime/configuration digests and still reports formal acceptance as incomplete. A synthetic 113-row integration produced the expected 97/113 mechanical threshold pass; this is a test fixture, **not held-out performance evidence**.

## Executed verification

**Current final-execution integration command:**

```sh
TESTSAFE_BLOCK_NETWORK=1 DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m unittest test_official_v1_execution test_official_v1_capture -v
```

**PASS: 31/31 methods, 0.146 seconds, exit 0; no failures/skips** — 22 execution-envelope and nine capture/integration tests. This final combined run used settled source bytes after the new modules were integrated. It covers authentication/scope failures before callbacks, replay/concurrency, interruption, incomplete/duplicate/malformed rows, capture substitution, strict JSON, source/configuration drift, collisions, post-link durability and the saved-bundle/report path. It executes only synthetic cases, including the unchanged pure v1 scorer on synthetic definitions. No database or provider was contacted.

Final test log: `/private/tmp/formal-execution-integration-final.log`, SHA-256 `d4c0d1dc51ae55835f1ed3183fba7041c2e091992a6c7a6a9e7c53e11a3890b8`. Standalone workstream runs passed 22/22 and 9/9 before the final combined check; those overlapping counts are not added.

The table below retains **prior acceptance-sprint verification**. Its unchanged tests and review progress commands were not repeated in this follow-up; source hashes and all 37 review/source-first files were compared to the new baseline instead. `git diff --check` was run again for the final edits.

| Exact command / check | Result |
|---|---|
| `.venv/bin/python -B -m eval.review.cli progress --kind heldout --baseline-git HEAD` | Exit 0; 0/113 reviewed, all sign-off blank; 26 historical ledger entries verified; no new proposals/integrity errors |
| `.venv/bin/python -B -m eval.review.cli progress --kind dev --baseline-git HEAD` | Exit 0; 0/7 reviewed, separate sign-off blank; no integrity errors |
| `.venv/bin/python -B test_formal_v1_runner_candidate.py -v` | **6/6** new tests; baseline symlink defect reproduced, final source and temporary patch equivalent, no mutation/side effects |
| `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B test_stage9_e0_runner_gate.py` | **110 printed checks passed**, exit 0 |
| Same four environment variables, `.venv/bin/python -B test_p4_eval_framework.py` | **22 printed checks passed**, exit 0 |
| `TESTSAFE_BLOCK_NETWORK=1 DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch .venv/bin/python -B test_formal_v1_report.py` | Final **10/10** new tests, 0.037 seconds; exact 96/97 and 68/69 boundaries, complete/incomplete/error metrics, malformed inputs, raw-hash/identity binding, publication failures/collisions including post-link durability |
| `git diff --check` and baseline/protected SHA-256 checks | PASS |

Only guards affected by the actual safety fix and the new reporting tests were executed. The unchanged 92-script application suite and live Gemini flow were not repeated. No database or provider call was needed. Existing development result bytes still contain 41/47 and 28/42 stored correct counts: raw hashes `4c1a6416f2603f7c0744533b6c3ee99570827aaefbdca003bbe346ea2bfd0988` and `b2c92e582c8e9ddb75e6adc6661a200ab294bc4956002c54f2c6258fb63f4962`. They were not rescored or falsely represented as current corrected-dataset/runtime evidence.

## Formal execution record

| Required evidence | Actual status |
|---|---|
| Approval identity, provenance and scope | **Absent**; no real approval created, consumed or fabricated |
| Exact held-out command | **None executed**; Phase D not entered |
| Reserved official output | None; do not reserve a run before its actual scope and prerequisites are settled |
| Raw output / log / runtime provenance hashes | **Not available: run not executed** |
| Final tier correctness / unsupported / citation / abstention / latency metrics | **Not available: run not executed** |
| Independent acceptance outcome | **FORMAL_EVALUATION_INCOMPLETE** |

## Owner response and one external blocker

**External blocker: genuine independent human review is unavailable (0/113).** The owner confirms no reviewer has been designated and no completed review or signed approval exists. Existing AI work remains `AI_TECHNICAL_REVIEW`; no human identity, judgments or sign-off fields were fabricated. No repeat decision request or replacement review package is needed. Existing source-first handoff: [FINAL_REVIEW_MISSING_DECISIONS.md](FINAL_REVIEW_MISSING_DECISIONS.md).

The owner selected **conditional retention of the current freeze**. The newly completed AI review supplies separate technical findings, not the required human judgments. When genuine independent human review is available, itemized reviewer and owner dispositions must address the remaining concerns before retention can be finalized. If review contradicts retention, preserve that conflict for owner adjudication rather than silently changing labels or selecting a new candidate. The original decision matrix retains this selection; the separate AI CSV does not overwrite it.

Later run-readiness conditions remain open and are not waived: official run-once/approval custody, error/interruption, publication and runtime-provenance requirements or permitted dispositions, any approved integration, and separate owner-origin authorization bound to the final manifest, tiers, split and unused outputs. These are downstream conditions, not completed evidence or additional requests issued now. Missing historical evidence must not be reconstructed as original runtime proof. V2 adoption is unnecessary for the selected route.

The earlier final-execution follow-up completed the mechanical work above. All 11 TA and 10 applicable TP owner-decision rows remain pending genuine dispositions. The 2026-11-19 AI-review follow-up completed the separately authorized source review and four new synthetic development cases; it did not repeat the old provider smoke, package preparation or broad audit. Initial AI judgments remain immutable, semantic disagreements remain explicit, and only the original human-certified protected run remains gated.

## Integrity and safety

All 44 protected assets, frozen scorer/runner/data/thresholds/manifests, workbooks, original annotations and historical results are byte-identical. The AI-review follow-up recorded **595 pre-existing Git-listed files** at `/private/tmp/ai-review-baseline.json`; only this existing status document was updated. Every other pre-existing file remains byte-identical, including all prior untracked engineering work, the safety fix and `eval/.DS_Store` modification. New files are confined to the requested AI outputs and their review/evaluation/provenance/test implementation. HEAD, branch and staged bytes remain unchanged; exact file lists and hashes are recorded in `ai_review/final_manifest.json`.

Reporting source SHA-256 `4c769ce8f4aa100abada6590380cb63c7d147894d35d7ea7e0eb9ded0b8bcbbd`; reporting tests `4674658326648b5335f47b266ff5eb57117b0eaabc920d31d57c937fcff57bd0`; fixed safety source `33d7e1d3c7cd790c45d7761eab9663ec4388065587cab0559321b4fa80883cc1`.

| New artifact | SHA-256 |
|---|---|
| `eval/official_v1_execution.py` | `f36102cf82b848861adf4cfd8d02a1df64981ea06fa4066e93e648ed02fe9a6f` |
| `eval/official_v1_capture.py` | `16ef1381d6eeac1c8c8e0c063cdfe4aed95c9efc24605871297cd105b815a97c` |
| `test_official_v1_execution.py` | `ddb05bf9374e9ed2f59660c54ae3cc861082781a4338b0d3cfd6e559ed3875b5` |
| `test_official_v1_capture.py` | `e21d7d1eafc9fd36b33465116f2df57c822a563e51915bd8327d306b7a4c4ecb` |

The earlier execution-envelope bundles were temporary **synthetic test artifacts**. The current AI development raw outputs persist separately under `ai_review/development/` with their pre-run dataset/policy identities. No real official held-out raw result, command, approval identifier, runtime artifact or tier metric exists. Test/development evidence is not an immutable official evaluation result.

No `rag_db` access, production quarantine/migrations/backfills, protected held-out/full-split execution, dependency installation, staging, commits, pushes, reset, clean or stash. Four authorized Gemini calls were made only for the distinct new development track; no original case was moved into it. Local application/scorer engineering was not reopened to force a pass. AI-reviewable work is complete; the original human-certified acceptance remains incomplete because its genuine review and approval conditions are unsatisfied.
