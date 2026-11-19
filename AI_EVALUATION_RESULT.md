# AI evaluation result

**AI_TECHNICAL_EVALUATION_FAIL** — the permitted new synthetic development run completed with real Gemini outputs: **3/4** cases met its policy. **OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING** — original held-out execution remains unexecuted and gated; human source review remains **0/113**.

## Actual execution

- Run: `ai-kestrel-live-20261119-v1`; dataset: `ai-kestrel-synthetic-answer-v1`; policy: `ai-kestrel-development-policy-v1`, version 1, `DEVELOPMENT_ONLY`.
- UTC execution: 2026-11-19 05:45:15–05:45:53; elapsed 37.9612 seconds.
- Four actual SDK calls; configured primary and returned model on all four: `gemini-3.5-flash-lite`. No fallback, duplicate preflight, rerun, or dependency installation.
- New invented Kestrel Observatory corpus: permit cost 83 credits, validity 17 days, no fax number provided. Original dataset IDs and normalized questions were collision checked; no original case was copied or executed.
- Existing pure context assembly, grounded-answer generation, citation checks, `tier1_context`, and unchanged frozen `score_generic` were reused. The official runner entry point, bootstrap, execution envelope and protected approval path were not activated.
- No database connections: process database URL was overridden to an unreachable scratch destination before service imports, with connection tripwires on psycopg sync/async APIs. Retrieval, ingestion, memory and production database operations were outside this run.

## Predeclared criteria and observed results

Policy and dataset were exclusively created before the first provider call. The toy policy required all four complete/correct outputs, zero fabricated citations, zero scorer-flagged unsupported outputs, actual document citations for answered facts, and proper abstention for unavailable information. These are this new development policy's technical criteria, **not frozen v1 thresholds or formal acceptance criteria**.

| New case | Result | Policy outcome |
|---|---|---|
| Fee | Correct 83 credits; valid source citation | PASS |
| Duration | Correct 17 days; valid source citation | PASS |
| Compound | Both facts complete; valid source citation | PASS |
| Unavailable fax | Cited absence statement; status `answered` | FAIL |

Frozen scorer correctness is 3/4; fabricated citations total **0**; ungrounded numeric values **0**; scorer-flagged unsupported outputs **1/4**. All four returned outputs cite the actual synthetic document/page. The three answerable cases each have citation correctness/completeness 1.0. The unavailable case has frozen citation correctness 0.0 because its expected gold source set is empty.

The saved unavailable answer is: “According to the policy, the Kestrel Observatory does not provide a fax number [S1].” The synthetic source explicitly supports the absence of a provided fax number. The existing status classifier returns `answered`, and the frozen scorer's insufficiency phrases do not include “does not provide”. It therefore records `abstain_ok=false` and `unsupported=true`; this run's stricter policy also requires `abstained` with no citations. This is an observed classifier/phrase/rubric mismatch, not evidence that Gemini invented a fax number. This post-run interpretation does not change the recorded score, policy, source, outputs, or FAIL verdict. No second run was made.

## Reproducible evidence and limits

Exact executed commands, once each:

```sh
.venv/bin/python scripts/ai_development_evaluation.py prepare
.venv/bin/python scripts/ai_development_evaluation.py run
```

Both processes exited 0. The run printed and saved `AI_TECHNICAL_EVALUATION_FAIL`; process exit means execution completed, **not that evaluation passed**. The CLI does not translate its verdict into a nonzero exit. Machine consumers must read `run_evidence.json` and its status. No repeat live execution was used to change the result.

- `ai_review/development/policy.json`: pre-run versioned scope and complete criteria.
- `ai_review/development/dataset.json`: all four new synthetic cases and their source.
- `ai_review/development/results.jsonl`: immutable exclusive-created raw synthetic results, scores and per-case call counts; flushed and synchronized after each case.
- `ai_review/development/run_evidence.json`: code/policy/dataset/result SHA-256 digests, requested/returned models, call outcomes, per-call latency, execution timestamps and scope.
- `scripts/ai_development_evaluation.py`: bounded harness, 12 aggregate SDK call cap, existing request budgets (45 seconds/case, 180 total), no-overwrite/no-resume guard. A repeated run at this identity is refused.
- `test_ai_development_evaluation.py`: **6/6 deterministic tests PASS**, covering original ID/question collisions, duplicate IDs, dataset digest, complete policy, and refusal to overwrite existing artifacts.

Dataset SHA-256: `aa8422abed8dd48dcc800e3a626da8b2ba776ad48e1aaf6e4c2c494695e9a4f4`.

Policy SHA-256: `2d20349207a7af3c0938985a836117e69e43f979a68d25238193fd94ed4e014f`.

Results SHA-256: `e613e4ceee92ed17a036d195e9faf1d0fb093f3a466f3f59c18d3b0dc1563ad3`.

This four-case answer-layer exercise does not establish performance on the 113 source-reviewed cases, retrieval quality, or formal acceptance. Consolidated AI-ledger completeness, evidence coverage, correction dispositions and original-asset preservation are validated separately by the lead integration step. AI review does not satisfy the original human freeze requirement and cannot produce `FORMAL_EVALUATION_ACCEPTED` under that policy.

Final integration: **AI_REVIEW_COMPLETE**, 113 source-evidenced records (83 pass, 22 nonbinding correction recommendations, 8 preserved ambiguities). All 339 initial AI reviews are retained. The focused ledger/development suite passed 20/20 tests; the CSV preserves 113 exact IDs. This review completion does not change the development FAIL or satisfy human sign-off. Original frozen assets and human records remain unchanged; final evidence is in `AI_HELDOUT_REVIEW_SUMMARY.md` and `AI_HELDOUT_113_REVIEW.jsonl`.
