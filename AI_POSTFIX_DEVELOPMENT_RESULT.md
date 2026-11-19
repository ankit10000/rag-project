# Post-fix live development verification

2026-11-19 · **AI_TECHNICAL_EVALUATION_FAIL — 3/4 predeclared cases passed.**

This is a new development-only run, not a rerun or reinterpretation of the original Kestrel 3/4 FAIL. **OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING** remains unchanged; no protected question or official runner was executed.

## Actual scope and execution

- Run `ai-lumen-postfix-live-20261119-v1`; dataset `ai-lumen-postfix-synthetic-v1`; policy `ai-lumen-postfix-behavior-policy-v1`.
- Policy and dataset were exclusively saved before provider execution. All four questions and IDs were checked against original evaluation inputs and the earlier synthetic experiment; no case was copied into a development split.
- A new fictional Lumen Observatory source states a 71-token permit cost, no fax service, and document omission of telephone number and mailing address. These distinguish factual negation, unavailable information, and a mixed answer.
- Four real SDK calls, each requesting and returning **`gemini-3.5-flash-lite`**. No fallback, duplicate preflight or second live run. Maximum predeclared cap: 12 calls.
- Measured run latency: **28.6852 seconds**. UTC start/end: `2026-11-19T08:39:36.790071+00:00`–`2026-11-19T08:40:05.533356+00:00`.
- No database connection. The process used an unreachable scratch URL and connection tripwires on psycopg synchronous/asynchronous entry points before application imports. No ingestion, retrieval, memory or production data operation was needed.

| New case | Expected / observed status | Citations | SDK calls | Seconds | Outcome |
|---|---|---:|---:|---:|---|
| Permit cost | answered / answered | 1 valid | 1 | 2.5977 | PASS |
| Explicit no-fax-service fact | answered / answered | 1 valid | 1 | 5.2977 | PASS |
| Missing telephone number | abstained / abstained | 1 valid | 1 | 11.3693 | PASS |
| Cost plus missing mailing address | partial / answered | 1 valid | 1 | 9.4167 | FAIL |

The source-supported negative answer remained answered. The missing-number answer now correctly abstained **with its valid citation retained**, demonstrating the targeted contract change on a real response. The mixed response returned:

> According to the Lumen Observatory policy, a visitor permit costs 71 tokens [S1]. Regarding the mailing address, the policy does not provide a mailing address [S1].

Its factual part and document omission are supported, but the application reported `answered`; the predeclared partial-information contract required `partial`. Subsequent deterministic investigation isolated a narrower parser defect: the information-object regex `addresses?` matched plural “addresses” but missed singular “address”. The bare omission clause failed too; the topic preface was not the cause. The one-pattern correction to `address(?:es)?` preserves existing source-alignment handling and negative-fact behavior. A new regression covers bare singular omission, prefaced cited omission, plural addresses, and replay of this exact saved mixed response, which now reports `partial` with the answer and valid citation retained. The executed helper snapshot remains unchanged; the later corrected helper SHA-256 is `3f3bcdff4f3871774a480478ccf647823fbe8ecf4b9af95ae5756847c268d4e8`. All 17 abstention-contract tests pass. This is deterministic post-run evidence, not a new live score: the recorded live FAIL remains 3/4, and no provider rerun occurred.

## Predeclared measurement contract

This new policy reused `ai_review/development_v2/contract.py`: source kind is specified before execution, legitimate negative facts need valid citations, pure missing information may retain valid citations, and mixed responses must be partial. Required fact recall is 1.0; factual citations must be complete; fabricated references, ungrounded numbers and forbidden hits must be zero. These are bounded toy technical criteria, not an adopted acceptance policy or inherited 97/113 or 69/106 thresholds.

Frozen `score_generic` remained unchanged and was explicitly diagnostic from policy preparation onward. Its whole-case result was also **3/4**, including `partial_ok=false` on the mixed case. No old lexical rule, criterion or threshold was changed after results. All four outputs had required fact recall 1.0, zero fabricated references, zero ungrounded numbers and zero forbidden hits. Factual cases had structural citation correctness/completeness 1.0. The omission case's diagnostic citation correctness was 0.0 because that case has an empty gold-source set; its citation still identifies the actual provided synthetic source.

The technical checks do not prove general semantic entailment. Source/policy/dataset/code/output hashes were captured, but **exact provider-prompt body hashes were not instrumented in this experiment**. No reconstructed prompt is presented as runtime capture. The candidate acceptance policy's full provenance requirements remain separate.

## Commands and evidence

```sh
TESTSAFE_BLOCK_NETWORK=1 DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch .venv/bin/python -B test_ai_postfix_development.py
.venv/bin/python -B scripts/ai_postfix_development_evaluation.py prepare
.venv/bin/python -B scripts/ai_postfix_development_evaluation.py run
```

Prepare exited 0. The live command exited **1**, recording four completed cases, three passes and four SDK calls. Six harness guards passed before execution. A seventh guard added after the observed failure confirms that an `answered` mixed response is rejected as a status mismatch; it does not relabel or accept the wrong status. The final focused file passed **7/7 tests**, 0.017 seconds. No policy or live-harness implementation changed after the run.

| Immutable new artifact (`ai_review/postfix_development/`) | SHA-256 |
|---|---|
| `policy.json` | `959ed19bb7c34f8260bc1ff6758f7af2e182a0ca29779f3f636333c521b47d79` |
| `dataset.json` | `cd2092dd25057a5544c8b1f6906cfb1c609dc7d2c8d2849308d741f4f73f0f04` |
| `attempt.json` | `89617bd42458fd2dfad87d85c29a486e9383fd992363619456a9c9828f523a44` |
| `results.jsonl` | `0a9daf7e1fda00b8e4cfa87cca9a2a82769971ddaa7362ae5f158d1789f8159b` |
| `run_evidence.json` | `5759c9ad9e9a05c4db39df05886afd537d1520e49e18f597fa7374971bd0339a` |

The run evidence binds actual source revisions, including the post-fix answer/citation helpers and frozen scorer. Exact executed `answer_semantics.py`, `answer_service.py`, `citation_service.py` and harness bytes are preserved read-only in `ai_review/postfix_development/source_snapshot/`; their hashes were checked against the recorded run hashes before any subsequent repair. The executed semantics helper hash is `cbc16e5be352a13b350fdfeee2524cba0cdae26d8bdcff1d25ea9b4ce6edeb9f`.

All artifacts are exclusive-created; the attempt marker prevents automatic resume or replay at this identity. The original Kestrel policy/dataset/results/evidence and 3/4 FAIL remain untouched. No human reviewer, signature, owner disposition or protected authorization was manufactured. This live outcome is a diagnostic FAIL, not formal human certification.
