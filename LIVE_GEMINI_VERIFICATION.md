# Live Gemini verification

**LIVE_GEMINI_PASS — 2026-11-18.** The configured primary `gemini-3.5-flash-lite` actually answered the synthetic document question, follow-up and memory question; unsupported document questions abstained. All successful responses returned that exact model identity. No fallback was needed live. This verifies the bounded development corpus and current credential/model availability, not formal evaluation acceptance or arbitrary-corpus quality.

## Executed flow and results

A fresh dedicated `rag_local_v1_test_live_7ad96bc66d5e` was created through the existing scratch helper, with actual `current_database()` checks and approved schema 000–003. No application database or existing conversation was used. A generated one-page synthetic PDF was uploaded through the authenticated FastAPI `TestClient`. Actual locally cached `all-MiniLM-L6-v2` embeddings, hybrid search, `cross-encoder/ms-marco-MiniLM-L-6-v2` reranking, PostgreSQL/pgvector and Gemini executed. No retrieval/provider mock supplied the answer. Temporary upload and bearer-token state were isolated.

| Check | Actual result |
|---|---|
| Authentication/minimal answer | PASS; READY response on configured primary |
| PDF ingestion | HTTP 201, nonzero chunks |
| Document question | HTTP 200, answered; known 65-dollar fact with uploaded PDF citation on page 1 |
| Same-conversation follow-up | HTTP 200, answered; known 30-day fact with citation |
| Memory extraction | Checkpoint advanced; user preference stored with supported sources |
| Memory follow-up | HTTP 200, answered from remembered concise-explanation preference |
| Unsupported street address | HTTP 200, `abstained`, zero citations |
| Invalid credential | Separate fake-key client rejected with HTTP 400; real credential unchanged |
| Duplicate write check | Exactly eight messages for four turns |
| Conversation deletion | HTTP 200 followed by read 404; zero remaining messages/memories for that ID |

Synthetic raw prompts/answers, private credentials and bearer tokens are not included in this evidence. Disposable synthetic document rows remain only in the dedicated scratch database for inspection; the conversation was deleted.

## Call accounting and latency

- One sandbox-denied connectivity attempt ended in `ConnectError` before a successful provider exchange (0.097 s); not counted as a successful Gemini call.
- One escalated standalone connectivity request succeeded in 1.167 s (15 input tokens, one output token).
- The subsequent complete flow used **15 actual provider requests: 14 valid successful requests and one isolated invalid-key request**. Total flow elapsed 23.188 s, below a 28-call application-level cap. Aggregate valid SDK call time was 14.448 s. No calls were repeated to correct the harness assertion described below.
- **Total application-level provider requests: 16, including one deliberately invalid credential.** All 15 successful responses across preflight and flow used the configured primary. The SDK's server-internal execution/retry behavior is not represented as additional application calls.
- Configured fallbacks: `gemini-3.1-flash-lite`, `gemini-2.5-flash`. Their availability was not separately probed; switching behavior was verified deterministically.

| Flow call | Outcome | HTTP code | Seconds | Returned model |
|---|---|---:|---:|---|
| 1 | success | 200 | 0.740 | gemini-3.5-flash-lite |
| 2 | isolated invalid credential | 400 | 0.136 | not returned |
| 3 | success | 200 | 1.251 | gemini-3.5-flash-lite |
| 4 | success | 200 | 1.443 | gemini-3.5-flash-lite |
| 5 | success | 200 | 1.147 | gemini-3.5-flash-lite |
| 6 | success | 200 | 0.963 | gemini-3.5-flash-lite |
| 7 | success | 200 | 1.435 | gemini-3.5-flash-lite |
| 8 | success | 200 | 1.889 | gemini-3.5-flash-lite |
| 9 | success | 200 | 0.704 | gemini-3.5-flash-lite |
| 10 | success | 200 | 1.086 | gemini-3.5-flash-lite |
| 11 | success | 200 | 1.210 | gemini-3.5-flash-lite |
| 12 | success | 200 | 0.622 | gemini-3.5-flash-lite |
| 13 | success | 200 | 0.600 | gemini-3.5-flash-lite |
| 14 | success | 200 | 0.784 | gemini-3.5-flash-lite |
| 15 | success | 200 | 0.574 | gemini-3.5-flash-lite |

## Exact commands and evidence correction

Executed live command (with authorized network/local-DB sandbox escalation):

```sh
.venv/bin/python -B scripts/live_gemini_verification.py --confirm-live --results-file /private/tmp/live-gemini-verification-1.json
```

The initial harness exited 1 because it expected the nonexistent public status `refused`; the existing application correctly returned `abstained`. Its original JSON remains unchanged (SHA-256 `a23b315886944ec2cc20e687eef767226aad31aefb5e64a80c09c46c18799e36`). **This was a harness expectation defect, not a live application failure.** The helper now checks the established abstained/no-citation contract. Saved evidence was rechecked without issuing any further provider call. `/private/tmp/live-gemini-verification-analysis.json` is explicitly marked `POST_ANALYSIS_OF_SAVED_LIVE_EVIDENCE_NOT_A_NEW_RUN`, records the original exit and corrected 14/14 checks, and is not presented as a second live run. The final helper was tested offline; a fresh live rerun was unnecessary.

Deterministic fault matrix command:

```sh
TESTSAFE_BLOCK_NETWORK=1 DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch .venv/bin/python -B test_live_gemini_policy.py
```

**6/6 tests passed, 0.011 s**: established abstention contract; HTTP 400/401/403 no retry/fallback; 429 switches immediately without sleeping on the exhausted model; 503 retries once then falls back; timeout advances without retrying the same model; total budget prevents a transient retry. All provider faults are synthetic and network is blocked.

The retained `test_local_v1_journey.py` tests provider failures with actual SQL and verifies safe error answers, no secret persistence, exactly one user/assistant pair per turn, no memory writes and an unchanged extraction checkpoint. `test_local_v1_deadlines.py` covers actual per-attempt timeout propagation, late response fencing, quota waits and middleware behavior. Their final sprint revalidation is recorded by the integration lead; this report does not turn deterministic faults into claimed live outages.

## Source identity and changes

Base HEAD: `690fcfbbf0abdf43b274161a5e6545f7ad11c325`, with the existing local-v1 working tree. Provider production source was unchanged during this track. SHA-256:

| File | SHA-256 |
|---|---|
| `services/llm_service.py` | `6cfd17c7ca6bcb13987c0f8c26a94dcff91d764cc21f0211703071725b7a24c2` |
| `services/gemini_retry_service.py` | `af1d9d1e0dcd3e3ae4a0b2936777749f2a174766986997fd2e6a67b2beb09aad` |
| `services/embedding_service.py` | `3092cd0fbcc7d8adde648b36c9a69b36b935b39d9fed970a8e5cd7b7cbcc7623` |
| Initially executed live helper | `457e695efc444c0f6d64c581913028c64b63f1ad3091dcacc6619155ad56b1fd` |
| Corrected helper | `8dbd78232d5d0e770532e8c3ccad7adc0942b60b53aa2cd6b3855864475415e8` |
| `test_live_gemini_policy.py` | `132ca5673dc8998042e1acced1116a397f4e08d80a4ff70173ed819dd09fd2ba` |

No scorer, frozen thresholds, evaluation datasets, production data or existing application memories were changed. No held-out/full-split evaluation occurred. The Gemini request budget remains cooperative as documented by local v1; this evidence does not certify hard preemption of CPU/native work or future provider availability.
