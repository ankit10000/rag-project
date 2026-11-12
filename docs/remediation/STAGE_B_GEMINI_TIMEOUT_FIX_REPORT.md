# Stage B — Gemini HTTP request timeout fix

Date: 2026-11-12.
- **No Gemini API call was made.** All tests ran with outbound sockets blocked and with httpx `send()` faked.
- Tier 1 was not resumed. Tier 2 and held-out were not run, and `--fresh` was not used.
- The 29 partial results are byte-identical (see the protection checks below).
- No database was modified, nothing was staged, committed or pushed, and the full suite was not run.

## Root cause and evidence
- During the Tier 1 dev run, cases 1–29 finished by 16:32:06 and case 30 (`C-prompt_injection-01`) then made no progress for ~25 minutes. No fallback, quota, retry or error line was logged.
- `services/llm_service.py` created the client as `genai.Client(api_key=api_key)` with no `http_options`.
- In the installed SDK, `BaseApiClient` builds its httpx client with `args['timeout'] = None` when no timeout is given (`google/genai/_api_client.py`, about line 1414). Each request is built with `timeout=http_request.timeout`, which is `None` when `HttpOptions.timeout` is unset (about lines 1756 and 1814).
- With `timeout=None`, httpx waits indefinitely. A stalled connection or a server that stops sending therefore blocks the process forever. The code's own waits are all bounded (at most 30 s for a quota delay, fixed retry counts), which fits a hung HTTP request and nothing else.
- Exactly why the server or network stalled cannot be determined from the logs.

## SDK version and verified timeout interface
- `google-genai` **2.34.0** and `httpx` 0.28.1 are installed; nothing was upgraded or downloaded.
- `google.genai.types.HttpOptions.timeout`: `int | None`, documented as **"Timeout for the request in milliseconds."**
- The SDK's `get_timeout_in_seconds()` converts it with `timeout / 1000.0`. The result is passed to `httpx.Client.build_request(timeout=…)`, and also sent as the `X-Server-Timeout` header, rounded up to seconds.
- A scalar httpx timeout sets the **connect, read, write and pool** timeouts all to that value. The test verified the request extension `{'connect': 120.0, 'read': 120.0, 'write': 120.0, 'pool': 120.0}`.
- **SDK retries:** with no `retry_options`, the SDK's tenacity policy is `stop_after_attempt(1)`, so it makes no hidden retries. The test confirmed one transport attempt per call.
- **Timeout error:** `httpx.TimeoutException` (`ReadTimeout`, `ConnectTimeout`, …). The SDK re-raises it unchanged.

## Implementation (`services/llm_service.py` only)
1. `REQUEST_TIMEOUT_MS = 120_000` (**120 seconds**), and `client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))`.
2. In `generate_answer`'s model loop, a new `except httpx.TimeoutException` handler:
   - records the error;
   - prints `Gemini model '<m>' timed out after 120s (<ExceptionType>); trying next model...`;
   - moves to the next model, the same treatment as a temporary 5xx/empty-reply failure. There is no retry on the same model, because `generate_with_retry` re-raises errors without an HTTP status at once.
   - If every model times out, the last timeout is **raised**, not swallowed. The quota wait-and-retry path is not taken.
3. Unchanged:
   - model configuration (primary and fallbacks from `.env`);
   - 429/404/5xx/empty-reply handling, quota cooldown and the existing retry counts;
   - `rewrite_query` and `classify` (they reuse `generate_answer`);
   - all other modules.

**Worst case per `generate_answer` call:** 3 models × 120 s = 6 min, then an exception.
- In the answer pipeline that exception becomes `generation_error: <Type>`, then a bounded regeneration (`ANSWER_MAX_RETRIES=1`), then `status=error`. So a single answer is bounded at about 12 min. There is no indefinite block.
- The eval runner catches per-case exceptions and records them.

## Focused tests (executed)
Command: `.venv\Scripts\python.exe run_tests.py test_llm_timeout.py test_model_fallback.py test_answer_phase3.py test_b3_answer_reliability.py`

Result: **4/4 PASS**. The runner also reported `rag_db` fingerprint unchanged: True.

New `test_llm_timeout.py` (unit, registered in `run_tests.py`): **19 PASS, 0 FAIL**. It covers:
1. **Client configuration:** `REQUEST_TIMEOUT_MS == 120000`; the application client's `HttpOptions.timeout == 120000`.
2. **Real SDK request path down to httpx (transport faked):**
   - per-request timeout `{connect, read, write, pool} = 120.0`;
   - `X-Server-Timeout: 120`;
   - exactly one attempt;
   - a timeout surfaces as `httpx.TimeoutException`.
3. **Fallback after a timeout:**
   - primary timeout → B answers, with no same-model retry and no sleep, and a log line naming the model and the duration;
   - connect timeout then read timeout → C answers.
4. **Bounded:**
   - all models time out → raises after exactly one request per model, with no quota wait;
   - quota on the primary then timeouts on the fallbacks → raises, with no extra primary retry;
   - in the answer pipeline, repeated timeouts → `status=error` with exactly `1 + ANSWER_MAX_RETRIES` attempts and `issues=['generation_error: ReadTimeout']`.
5. **No live call:** the socket guard was installed and never triggered.
6. **Model configuration unchanged:** `gemini-3.5-flash-lite` / `gemini-3.1-flash-lite, gemini-2.5-flash`. Existing behaviour is pinned too: persistent 503, non-switch 400 and normal success.

Existing tests passed unchanged: `test_model_fallback.py`, `test_answer_phase3.py` and `test_b3_answer_reliability.py`.

**Mutations (executed; repo untouched, module loaded from modified source):**
| Mutation | Result |
|---|---|
| client created without timeout | caught, 3 FAIL |
| timeout written in seconds by mistake (`120` → 0.12 s) | caught, 5 FAIL |
| timeout not handled (no fallback) | caught, 5 FAIL |

## Protection of partial results and baselines (verified before and after)
| Item | Before | After |
|---|---|---|
| `eval/phase35/results/tier1_dev.jsonl` | 29 rows, SHA-256 `638494fc17735234edb40200fc40f08770ffa075b8b8736b4bb7afb226c60923` | **29 rows, identical hash** |
| `eval/phase35/results/log_tier1_dev_stageB.txt` | `c06a55af0e2f790e527aa5b51dc284210e56383800226a036ed37043a65765f0` | **identical** |
| Backup `backups/phase35_results_20261112_160951/` | 4/4 match the manifest | 4/4 match the manifest |
| `rag_db` fingerprint | post-Tier-1 capture | **identical**; the runner also reported unchanged |

## Git state (unchanged by any Git command)
- HEAD is `aa6a876`, and nothing is staged.
- **Modified:** `services/llm_service.py` (+24/−2), `run_tests.py` (registration) and `eval/phase35/results/tier1_dev.jsonl`. The last one holds the partial `--fresh` output from before this task and is unchanged by it.
- **Untracked:** `test_llm_timeout.py`, `log_tier1_dev_stageB.txt`, and the earlier reports plus this one.

## Remaining limitations
- **Not a total-duration limit.** The 120 s is per connect, read, write and pool phase, not a total wall-clock cap. A server that keeps sending a byte every <120 s could in theory stretch a single response further. That is unlikely for this non-streaming `generate_content` call. httpx's synchronous API offers no total-duration timeout, and none was improvised.
- **Worst-case latency.** A single answer can now take up to about 12 min in the worst case: 2 attempts × 3 models × 120 s. That is bounded, but long. Tier 2 adds classify and rewrite calls.
- **Root cause of the stall is unknown.** The fix does not explain why the server stalled. If stalls recur, the run log will now show `timed out after 120s` lines.
- **Not live-verified.** Behaviour against the real API is unverified until the next approved live run; it was tested with fakes at the SDK transport boundary.

STOP. Tier 1 resume needs separate explicit authorization. Tier 2 stays blocked until Tier 1 completes and is reviewed.
