# Targeted abstention contract fix

2026-11-19 · **PASS — deterministic fix verified. Original live evaluation remains AI_TECHNICAL_EVALUATION_FAIL (3/4).** No new live experiment was needed or executed.

The synthetic source says **“The policy does not provide a fax number.”** This establishes missing document information, not that the observatory has no fax service. Its cited response paraphrased that absence, but the old phrase classifier missed it and returned `answered`. The classifier also conflated any cited insufficiency with `partial`. The original development policy independently required every abstention to have zero citations, which is too strict for a valid citation supporting document omission.

`retrieval_status` was not the cause: the original experiment used supplied Tier-1 context without retrieval. RAG continues returning retrieval/reranking status independently and propagating the answer service's status; no retrieval policy or route was changed.

The fix uses narrow sentence/clause analysis in `services/answer_semantics.py`, shared by answer status and citation coverage. Document-omission statements and the same omitted object in a sentence's **actually cited** source can indicate missing evidence. An incidental word such as fees or rate inside a coverage/refund benefit does not. There is no blanket “does not provide” abstention rule.

| Response meaning | Result |
|---|---|
| Explicit source-supported negative fact, including no fax service, no latex or unavailable access | `answered`; valid factual citations remain required |
| Pure missing-information response | `abstained`; a valid document-omission citation may remain |
| Supported requested facts plus an unavailable part | `partial`; factual claims still need citations |
| Uncited factual negative, invalid reference or unsupported-number failure | Existing validation/repair safeguards remain enforced |

**Deterministic replay of the saved fax answer text:** `abstained`, original text unchanged, valid `[S1]` citation retained. This uses a fake generation callback and the saved source; it is not a new provider response, live evaluation or historical rescore. Explicit negative services/coverage remain answered, and ordinary/polite uncited refusals remain abstained. Mixed clauses do not exempt their factual content from citation checks. These are bounded reporting/coverage heuristics, not a general semantic-entailment validator.

A separate **unexecuted, DEVELOPMENT_ONLY** contract is recorded at `ai_review/development_v2/policy.json` (`ai-kestrel-abstention-contract-v2`). It permits validated citations for missing-information abstentions, preserves cited negative answers and requires partial status for mixed information. Its helper checks predeclared response kinds/status/citation identities, not factual truth or formal acceptance. The original policy is untouched; its zero-citation condition would still reject a cited replay. No new 4/4 result is claimed. Frozen v1 scoring and official thresholds remain unchanged.

All nine commands `.venv/bin/python -B <file>` ran with `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch`, `TESTSAFE_BLOCK_NETWORK=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`; `LOCAL_V1_PROFILE=1` for the two local-v1 files and `0` for the others.

| Executed file | Exact result |
|---|---|
| `test_abstention_contract.py` | 16 methods PASS |
| `test_abstention_policy.py` | 7 methods PASS |
| `test_context_and_citations.py` | 62 printed checks PASS |
| `test_answer_phase3.py` | 69 printed checks PASS |
| `test_stage6_answer.py` | 66 printed checks PASS |
| `test_b3_answer_reliability.py` | 35 printed checks PASS |
| `test_local_v1_retrieval.py` | 13 methods PASS |
| `test_local_v1_api.py` | 9 methods PASS |
| `test_live_gemini_policy.py` | 6 offline fault-policy methods PASS |

**9/9 scripts, 51 unittest methods and 232 printed checks passed**, all exit 0. Tests cover the observed replay, explicit negatives, omitted information, same-source/object alignment, partials, polite refusals, invalid refs, uncited facts and existing API/retrieval behavior. A caught MIXED/refund-window regression was corrected before the final run. Evidence: `/private/tmp/abstention-fix-tests.json`, SHA-256 `e3b3d33bc20b93952be163829e13dcdbd2ca03f2be973d3f509ffa9f74200326`. No unchanged full suite or database lifecycle was repeated.

| Immutable original artifact | Unchanged SHA-256 |
|---|---|
| Development policy | `2d20349207a7af3c0938985a836117e69e43f979a68d25238193fd94ed4e014f` |
| Dataset | `aa8422abed8dd48dcc800e3a626da8b2ba776ad48e1aaf6e4c2c494695e9a4f4` |
| Raw results | `e613e4ceee92ed17a036d195e9faf1d0fb093f3a466f3f59c18d3b0dc1563ad3` |
| Run evidence | `f211b13dddaddb1d8a333a233ae39cc078ce0459f99dc56feecc7e3ff9309381` |

The historical application source is reproducible from `dec09f664bd7bba978ac02a5da7b24186821eea1`: original `answer_service.py` SHA-256 `efb7071f9ca34c8eb83ad397c88fbbe2f096a4e3bd3a809966949e219ceab1b6` matches the original run record. Current application bytes intentionally differ; original run hashes were not regenerated. New policy SHA-256: `8683ab27e30d7a3c3d4cf0062531a21cfce98a20c3328390a89f6a2115fa75c9`.

Changed application files: `services/answer_service.py`, `services/citation_service.py`, new `services/answer_semantics.py`. New focused tests and the separate development-v2 policy/helper accompany this report. Branch `main`, HEAD and staged bytes remain unchanged; final tree has four modified tracked files (two pre-existing) and 36 untracked files (30 pre-existing). All other 611 pre-existing Git-listed files, all 44 protected assets, original AI/human-review records, held-out safeguards and prior user changes remain intact. `git diff --check` passes.

No `rag_db` access, database/provider calls, production migration/quarantine, held-out execution, dependency installation, staging, commit, push, reset, clean or stash occurred. The targeted fix is complete; original formal human-certified acceptance remains pending under its unchanged gate.
