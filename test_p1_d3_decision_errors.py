"""D3 regression: decide_memory_action() fails safe (UNCERTAIN) on any LLM error or bad response.

generate_answer is always mocked; no network, no database writes.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import json
import sys
from unittest import mock

import services.memory_decision_service as mds

FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


EXIST = [(1, "User lives in Delhi"), (2, "User likes Python")]
UNC = {"action": "UNCERTAIN", "memory_id": None, "updated_memory": None}


def call(**patch_kwargs):
    """Run decide_memory_action with a mocked LLM; return (result_or_exception, stdout, mock)."""
    buf = io.StringIO()
    with mock.patch.object(mds, "generate_answer", **patch_kwargs) as m:
        with contextlib.redirect_stdout(buf):
            try:
                result = mds.decide_memory_action("SECRET-NEW-MEMORY-TEXT", EXIST)
            except BaseException as error:  # the point of D3: nothing may escape
                result = error
    return result, buf.getvalue(), m


# --- valid classifications unchanged ---------------------------------------
for action, mid, upd in (("NEW", None, None), ("DUPLICATE", 1, None), ("UPDATE", 1, "User lives in Mumbai"),
                         ("DELETE", 2, None), ("UNCERTAIN", None, None)):
    r, out, m = call(return_value=json.dumps({"action": action, "memory_id": mid, "updated_memory": upd}))
    check(f"[valid] {action} returned unchanged", r == {"action": action, "memory_id": mid, "updated_memory": upd}
          and m.call_count == 1 and "failed" not in out)
r, _, _ = call(return_value="```json\n" + json.dumps({"action": "update", "memory_id": 1, "updated_memory": "x"}) + "\n```")
check("[valid] fenced + lower-case still parsed", r == {"action": "UPDATE", "memory_id": 1, "updated_memory": "x"})

# --- LLM exceptions -> UNCERTAIN, nothing escapes ---------------------------
for exc in (RuntimeError("quota exceeded sk-FAKEKEY"), ConnectionError("net down"), TimeoutError("slow"),
            ValueError("bad"), KeyError("k"), OSError("io"), Exception("generic"), AttributeError("x"),
            TypeError("t"), json.JSONDecodeError("m", "d", 0)):
    r, out, _ = call(side_effect=exc)
    check(f"[exception] {type(exc).__name__} -> UNCERTAIN, not raised", r == UNC)
    check(f"[exception] {type(exc).__name__} log has type only (no message, prompt or memory text)",
          type(exc).__name__ in out and "sk-FAKEKEY" not in out and "SECRET-NEW-MEMORY-TEXT" not in out
          and "Delhi" not in out)

# --- bad responses -> UNCERTAIN ---------------------------------------------
bad = [("None", None), ("empty string", ""), ("whitespace", "   \n"), ("int", 5), ("float", 1.5), ("bool True", True),
       ("list", ["NEW"]), ("dict (valid-looking)", {"action": "DELETE", "memory_id": 1}), ("bytes", b'{"action":"NEW"}'),
       ("object", object()), ("malformed JSON", '{"action": "DELETE"'), ("prose", "Sure, delete it"),
       ("unknown action", json.dumps({"action": "MERGE"})), ("missing action", "{}"),
       ("null action", json.dumps({"action": None})), ("int action", json.dumps({"action": 5})),
       ("list action", json.dumps({"action": ["DELETE"]})), ("JSON list", "[]"), ("JSON null", "null"),
       ("JSON string", '"DELETE"'), ("JSON number", "12")]
for label, resp in bad:
    r, out, _ = call(return_value=resp)
    check(f"[bad response] {label} -> UNCERTAIN, not raised", r == UNC)

# --- failures never become DELETE (or any positive action) -------------------
failing = [dict(side_effect=exc) for exc in (RuntimeError("x"), TimeoutError("x"), Exception("x"))]
failing += [dict(return_value=v) for _, v in bad]
check("[never DELETE] every failure mode returns UNCERTAIN with no id / replacement text",
      all(call(**kw)[0] == UNC for kw in failing))

# --- unchanged short-circuit and the returned dict is not shared state -------
buf = io.StringIO()
with mock.patch.object(mds, "generate_answer", side_effect=RuntimeError("never called")) as m, contextlib.redirect_stdout(buf):
    r = mds.decide_memory_action("x", [])
check("[unchanged] no existing memories -> NEW without any LLM call", r["action"] == "NEW" and m.call_count == 0)
a, _, _ = call(side_effect=RuntimeError("x"))
a["action"] = "DELETE"
b, _, _ = call(side_effect=RuntimeError("x"))
check("[safety] mutating a returned fallback does not affect later results", b == UNC)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
