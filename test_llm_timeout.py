"""Gemini request timeout (no live API call: sockets blocked, httpx send() faked)."""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import socket
import sys
from unittest import mock

import httpx
from google.genai import errors


NETWORK_ATTEMPTS = []


def _no_network(*args, **kwargs):
    NETWORK_ATTEMPTS.append(args[:1])
    raise AssertionError("network access attempted during a unit test")


socket.socket.connect = _no_network          # belt and braces: nothing may leave the process
socket.create_connection = _no_network

import services.llm_service as llm           # noqa: E402
from services import answer_service           # noqa: E402
from services.context_assembly_service import assemble_context  # noqa: E402

FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


# ---------------------------------------------------------------- 1. client configuration
api_client = llm.client._api_client
check("REQUEST_TIMEOUT_MS is 120000 (milliseconds, i.e. 120 s)", llm.REQUEST_TIMEOUT_MS == 120_000)
check("the application's genai client carries HttpOptions.timeout = 120000 ms", api_client._http_options.timeout == 120_000)

# Drive a real generate_content call through the SDK down to httpx; capture the per-request timeout and
# make the transport raise a read timeout, as a stalled server would.
captured, headers = [], []


def fake_send(request, *args, **kwargs):
    captured.append(request.extensions.get("timeout"))
    headers.append(request.headers.get("x-server-timeout"))
    raise httpx.ReadTimeout("simulated stalled read", request=request)


with mock.patch.object(api_client._httpx_client, "send", side_effect=fake_send):
    try:
        llm.client.models.generate_content(model="gemini-3.5-flash-lite", contents="hi")
        sdk_error = None
    except Exception as error:  # noqa: BLE001
        sdk_error = error
check("SDK passes 120 s to httpx for connect/read/write/pool on every request",
      captured and captured[0] == {"connect": 120.0, "read": 120.0, "write": 120.0, "pool": 120.0})
check("SDK makes exactly one attempt on timeout (no hidden SDK retry loop)", len(captured) == 1)
check("a transport timeout surfaces as httpx.TimeoutException (not swallowed, not converted)",
      isinstance(sdk_error, httpx.TimeoutException))
check("X-Server-Timeout header sent with the request is 120 (seconds)", headers == ["120"])

# ---------------------------------------------------------------- generate_answer behaviour with fake models


class FakeResp:
    def __init__(self, text):
        self.text = text


def run(behaviour):
    """behaviour: {model: [outcome, ...]}; outcome = Exception or text."""
    llm._quota_cooldown_until.clear()
    calls, queues = [], {m: list(v) for m, v in behaviour.items()}

    def generate_content(model, contents):
        calls.append(model)
        outcome = queues[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResp(outcome)

    fake = mock.Mock()
    fake.models.generate_content.side_effect = generate_content
    out_buffer = io.StringIO()
    with mock.patch.object(llm, "client", fake), mock.patch.object(llm, "MODEL_NAME", "A"), \
            mock.patch.object(llm, "FALLBACK_MODELS", ["B", "C"]), mock.patch.object(llm.time, "sleep") as sleep, \
            contextlib.redirect_stdout(out_buffer):
        try:
            out = llm.generate_answer("hi")
        except Exception as error:  # noqa: BLE001
            out = error
    return out, calls, sleep, out_buffer.getvalue()


def timeout():
    return httpx.ReadTimeout("stalled")


# 2. simulated timeout handled; 3. fallback still works
out, calls, sleep, log = run({"A": [timeout()], "B": ["from B"]})
check("timeout on primary -> next model answers", out == "from B" and calls == ["A", "B"])
check("timeout is NOT retried on the same model and causes no sleep", calls.count("A") == 1 and sleep.call_count == 0)
check("timeout is logged with model name and duration (not silent)",
      "Gemini model 'A' timed out after 120s (ReadTimeout); trying next model..." in log)
out, calls, sleep, log = run({"A": [httpx.ConnectTimeout("no connect")], "B": [timeout()], "C": ["from C"]})
check("connect timeout and read timeout both fall through to the next model", out == "from C" and calls == ["A", "B", "C"])

# 4. bounded
out, calls, sleep, log = run({"A": [timeout()], "B": [timeout()], "C": [timeout()]})
check("all models time out -> raises the timeout (bounded: exactly one request per model)",
      isinstance(out, httpx.TimeoutException) and calls == ["A", "B", "C"])
check("all-timeout case does not trigger the quota wait/retry path", sleep.call_count == 0)
out, calls, sleep, log = run({"A": [errors.APIError(429, {"error": {"code": 429, "message": "quota", "status": "S"}})],
                              "B": [timeout()], "C": [timeout()]})
check("quota on primary then timeouts on fallbacks -> raises (no extra primary retry)",
      isinstance(out, httpx.TimeoutException) and calls == ["A", "B", "C"])

# existing behaviour preserved
out, calls, sleep, log = run({"A": [errors.APIError(503, {"error": {"code": 503, "message": "x", "status": "S"}})] * 2, "B": ["from B"]})
check("unchanged: persistent 503 -> one retry on the same model, then fallback", out == "from B" and calls == ["A", "A", "B"])
out, calls, sleep, log = run({"A": [errors.APIError(400, {"error": {"code": 400, "message": "bad", "status": "S"}})]})
check("unchanged: non-switch error (400) raises without fallback", isinstance(out, errors.APIError) and calls == ["A"])
out, calls, sleep, log = run({"A": ["from A"]})
check("unchanged: normal success uses the primary only", out == "from A" and calls == ["A"])

# answer pipeline: a timeout becomes a bounded generation error, never a hang or crash
bundle = assemble_context([{"chunk": (1, "p.pdf", 1, "Refunds take 30 days.", 0.5), "rrf_score": 0.1, "rerank_score": 1.0}])
attempts = []


def always_timeout(prompt):
    attempts.append(prompt)
    raise httpx.ReadTimeout("stalled")


result = answer_service.generate_grounded_answer("q?", bundle, "DOCUMENT", always_timeout)
check("answer pipeline: repeated timeouts -> status error, ERROR_MESSAGE, bounded attempts",
      result["status"] == "error" and result["answer"] == answer_service.ERROR_MESSAGE
      and len(attempts) == 1 + answer_service.cfg.ANSWER_MAX_RETRIES
      and result["issues"] == ["generation_error: ReadTimeout"])

# 6. model configuration unchanged (comes from .env / defaults exactly as before)
check("model configuration unchanged: primary gemini-3.5-flash-lite, fallbacks gemini-3.1-flash-lite, gemini-2.5-flash",
      llm.MODEL_NAME == "gemini-3.5-flash-lite" and llm.FALLBACK_MODELS == ["gemini-3.1-flash-lite", "gemini-2.5-flash"])

# 5. no live call: the socket guard would have raised inside one of the checks above
check("no network access was attempted (socket guard installed and never triggered)",
      socket.socket.connect is _no_network and NETWORK_ATTEMPTS == [])

print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
