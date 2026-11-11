"""Model fallback tests (Gemini client mocked; no API calls)."""
from unittest import mock

from google.genai import errors

import sys

import services.llm_service as llm
import services.gemini_retry_service as retry


def api(code, msg="x"):
    return errors.APIError(code, {"error": {"code": code, "message": msg, "status": "S"}})


class FakeResp:
    def __init__(self, text): self.text = text


def fake_client(behaviour):
    """behaviour: {model: [outcome,...]}; outcome = Exception or text."""
    calls = []
    queues = {m: list(v) for m, v in behaviour.items()}

    def generate_content(model, contents):
        calls.append(model)
        outcome = queues[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResp(outcome)

    client = mock.Mock()
    client.models.generate_content.side_effect = generate_content
    return client, calls


def check(name, cond):
    print(("PASS" if cond else "FAIL"), "|", name)
    assert cond, name


def run(behaviour, **patches):
    llm._quota_cooldown_until.clear()
    client, calls = fake_client(behaviour)
    with mock.patch.object(llm, "client", client), \
         mock.patch.object(llm, "MODEL_NAME", "A"), \
         mock.patch.object(llm, "FALLBACK_MODELS", ["B", "C"]), \
         mock.patch.object(llm.time, "sleep") as sleep:
        try:
            out = llm.generate_answer("hi")
        except Exception as e:
            out = e
    return out, calls, sleep


q = api(429, "quota. retryDelay: 22s")

out, calls, sleep = run({"A": [q], "B": ["from B"], "C": []})
check("429 on primary -> falls back to B instantly (no sleep)", out == "from B" and calls == ["A", "B"] and sleep.call_count == 0)

out, calls, sleep = run({"A": [q], "B": [api(429)], "C": ["from C"]})
check("A and B exhausted -> C answers", out == "from C" and calls == ["A", "B", "C"])

out, calls, sleep = run({"A": [api(404)], "B": ["from B"], "C": []})
check("404 (model gone) -> next model", out == "from B")

out, calls, sleep = run({"A": [api(503), api(503)], "B": ["from B"], "C": []})
check("persistent 503 -> next model after one retry", out == "from B" and calls == ["A", "A", "B"])

out, calls, sleep = run({"A": [api(503), "from A"], "B": [], "C": []})
check("transient 503 recovers on same model", out == "from A" and calls == ["A", "A"])

out, calls, sleep = run({"A": [api(400)], "B": ["from B"], "C": []})
check("non-switch error (400) raises, no fallback", isinstance(out, errors.APIError) and calls == ["A"])

out, calls, sleep = run({"A": [None_ := FakeResp] and [""], "B": ["from B"], "C": []})
check("empty response -> next model", out == "from B")

out, calls, sleep = run({"A": [q, "late A"], "B": [api(429)], "C": [api(429)]})
check("all models out of quota -> waits server delay then retries primary",
      out == "late A" and calls == ["A", "B", "C", "A"] and [c.args[0] for c in sleep.call_args_list] == [22.0])

out, calls, sleep = run({"A": [api(503), api(503)], "B": [api(503), api(503)], "C": [api(503), api(503)]})
check("all models 503 -> raises last error", isinstance(out, errors.APIError) and out.code == 503)

# cooldown: after A hits 429, the next call skips A first
llm._quota_cooldown_until.clear()
client, calls = fake_client({"A": [q], "B": ["one", "two"], "C": []})
with mock.patch.object(llm, "client", client), mock.patch.object(llm, "MODEL_NAME", "A"), \
     mock.patch.object(llm, "FALLBACK_MODELS", ["B", "C"]), mock.patch.object(llm.time, "sleep"):
    llm.generate_answer("1"); llm.generate_answer("2")
check("cooldown: second call goes straight to B", calls == ["A", "B", "B"])

# ---- deletion classifier through a forced primary 429 --------------------
from services.memory_decision_service import decide_memories_to_delete

CLASSIFIER_MEMORIES = [
    (1, "The user's RAG project uses Python and PostgreSQL"),
    (2, "The user prefers Hinglish explanations"),
    (3, "The user has experience with React and Node.js"),
    (4, "The user prefers concise answers"),
    (5, "The user has a cricket hobby"),
    (6, "The user's grandfather has a medical condition"),
]


def classify_with(behaviour):
    """Run the real classifier with primary 'A' failing as configured."""
    llm._quota_cooldown_until.clear()
    client, calls = fake_client(behaviour)
    with mock.patch.object(llm, "client", client), \
         mock.patch.object(llm, "MODEL_NAME", "A"), \
         mock.patch.object(llm, "FALLBACK_MODELS", ["B", "C"]), \
         mock.patch.object(llm.time, "sleep"):
        result = quiet_call(
            decide_memories_to_delete,
            "Forget my technology preferences",
            CLASSIFIER_MEMORIES,
        )
    return result, calls


def quiet_call(fn, *args):
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


result, calls = classify_with(
    {"A": [q], "B": ['{"status": "DELETE", "memory_ids": [1, 3]}'], "C": []}
)
check("classifier: primary 429 -> fallback B used, correct IDs",
      calls == ["A", "B"]
      and result == {"status": "DELETE", "memory_ids": [1, 3]})

result, calls = classify_with(
    {"A": [q], "B": ['```json\n{"status": "DELETE", "memory_ids": [1, 3]}\n```'], "C": []}
)
check("classifier: fallback JSON in ``` fences still parsed",
      result == {"status": "DELETE", "memory_ids": [1, 3]})

result, calls = classify_with(
    {"A": [q], "B": ['{"status": "DELETE", "memory_ids": [1, 3, 99]}'], "C": []}
)
check("classifier: fallback returns unknown ID -> filtered out",
      result == {"status": "DELETE", "memory_ids": [1, 3]})

result, calls = classify_with(
    {"A": [q], "B": ["Sure! I would delete 1 and 3."], "C": []}
)
check("classifier: fallback returns invalid JSON -> UNCERTAIN, nothing selected",
      result == {"status": "UNCERTAIN", "memory_ids": []})

result, calls = classify_with(
    {"A": [q], "B": ['{"status": "DELETE", "memory_ids": "1,3"}'], "C": []}
)
check("classifier: fallback returns non-list ids -> UNCERTAIN",
      result == {"status": "UNCERTAIN", "memory_ids": []})

# ---- optional live check: primary forced to 429, fallback is the REAL API --
if "--live" in sys.argv:
    real_client = llm.client
    primary = llm.MODEL_NAME
    served = []

    class ForcedQuotaClient:
        class models:
            @staticmethod
            def generate_content(model, contents):
                if model == primary:
                    raise api(429, "forced test quota. retryDelay: 22s")
                served.append(model)
                return real_client.models.generate_content(
                    model=model, contents=contents)

    live_cases = [
        ("Forget my technology preferences", "DELETE", {1, 3}),
        ("Forget my Hinglish preference", "DELETE", {2}),
        ("Forget my cricket hobby", "DELETE", {5}),
        ("Forget everything", "UNCERTAIN", set()),
        ("Forget my favorite color", "NO_MATCH", set()),
    ]

    llm._quota_cooldown_until.clear()
    with mock.patch.object(llm, "client", ForcedQuotaClient):
        for request, status, ids in live_cases:
            llm._quota_cooldown_until.clear()
            served.clear()
            res = quiet_call(decide_memories_to_delete, request, CLASSIFIER_MEMORIES)
            check(
                f"LIVE forced-429: {request!r} -> {res['status']} {sorted(res['memory_ids'])} "
                f"via {served[-1] if served else 'NONE'}",
                served and served[-1] != primary
                and res["status"] == status
                and set(res["memory_ids"]) == ids,
            )

print("\nALL PASSED")
