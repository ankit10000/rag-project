"""D4 regression: decide_memories_to_delete() fails safe (UNCERTAIN, no ids) on any LLM error or bad response.

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


EXIST = [(1, "SECRET-MEMORY-A lives in Delhi"), (2, "User likes Python"), (3, "User keeps goats")]
UNC = {"status": "UNCERTAIN", "memory_ids": []}
NOM = {"status": "NO_MATCH", "memory_ids": []}


def call(existing=EXIST, **patch_kwargs):
    buf = io.StringIO()
    with mock.patch.object(mds, "generate_answer", **patch_kwargs) as m:
        with contextlib.redirect_stdout(buf):
            try:
                result = mds.decide_memories_to_delete("SECRET-REQUEST-TEXT", existing)
            except BaseException as error:  # nothing may escape
                result = error
    return result, buf.getvalue(), m


def js(**kw):
    return json.dumps(kw)


# --- valid responses unchanged ----------------------------------------------
r, out, m = call(return_value=js(status="DELETE", memory_ids=[1, 3]))
check("[valid] DELETE [1,3] unchanged",
      r == {"status": "DELETE", "memory_ids": [1, 3]} and m.call_count == 1 and "failed" not in out)
r, *_ = call(return_value=js(status="NO_MATCH", memory_ids=[1]))
check("[valid] NO_MATCH unchanged (ids forced [])", r == NOM)
r, *_ = call(return_value=js(status="UNCERTAIN", memory_ids=[1]))
check("[valid] UNCERTAIN unchanged (ids forced [])", r == UNC)
r, *_ = call(return_value="```json\n" + js(status="delete", memory_ids=[2]) + "\n```")
check("[valid] fenced + lower-case status still parsed", r == {"status": "DELETE", "memory_ids": [2]})
r, *_ = call(return_value=js(status="DELETE", memory_ids=[99]))
check("[valid] foreign id only -> NO_MATCH unchanged", r == NOM)
r, *_ = call(return_value=js(status="DELETE", memory_ids=[3, 1, 1, 99]))
check("[valid] order kept, duplicates and foreign ids dropped", r == {"status": "DELETE", "memory_ids": [3, 1]})
r, *_ = call(return_value=js(status="MAYBE", memory_ids=[1]))
check("[valid] unknown status -> UNCERTAIN unchanged", r == UNC)
for empty in ([], None):
    r, _, m = call(empty, side_effect=RuntimeError("never called"))
    check(f"[unchanged] existing={empty!r} -> NO_MATCH without LLM call", r == NOM and m.call_count == 0)

# --- LLM exceptions -> UNCERTAIN, nothing escapes ----------------------------
for exc in (RuntimeError("quota exceeded sk-FAKEKEY"), ConnectionError("net down"), TimeoutError("slow"),
            ValueError("bad"), KeyError("k"), OSError("io"), Exception("generic"), AttributeError("x"),
            TypeError("t"), json.JSONDecodeError("m", "d", 0)):
    r, out, _ = call(side_effect=exc)
    check(f"[exception] {type(exc).__name__} -> UNCERTAIN, ids [], not raised", r == UNC)
    check(f"[exception] {type(exc).__name__} log has type only (no message, request or memory text)",
          type(exc).__name__ in out and "sk-FAKEKEY" not in out and "SECRET-REQUEST-TEXT" not in out
          and "SECRET-MEMORY-A" not in out and "Delhi" not in out)

# --- bad responses -> UNCERTAIN ----------------------------------------------
bad = [("None", None), ("empty string", ""), ("whitespace", "  \n"), ("int", 5), ("float", 1.5),
       ("bool True", True), ("bool False", False), ("list", ["DELETE"]),
       ("dict (valid-looking)", {"status": "DELETE", "memory_ids": [1]}),
       ("bytes", b'{"status":"DELETE","memory_ids":[1]}'), ("object", object()),
       ("malformed JSON", '{"status": "DELETE", "memory_ids": [1]'), ("prose", "delete memory 1 please"),
       ("JSON list", "[]"), ("JSON null", "null"), ("JSON string", '"DELETE"'), ("JSON number", "12"),
       ("memory_ids a string", js(status="DELETE", memory_ids="1")),
       ("memory_ids an object", js(status="DELETE", memory_ids={"a": 1})),
       ("memory_ids null", js(status="DELETE", memory_ids=None)), ("missing status", js(memory_ids=[1])),
       ("null status", js(status=None, memory_ids=[1])), ("status list", js(status=["DELETE"], memory_ids=[1]))]
for label, resp in bad:
    r, out, _ = call(return_value=resp)
    check(f"[bad response] {label} -> UNCERTAIN, ids [], not raised", r == UNC)

# --- every failure mode: never DELETE, never ids -----------------------------
modes = [dict(side_effect=e) for e in (RuntimeError("x"), TimeoutError("x"), ConnectionError("x"), Exception("x"))]
modes += [dict(return_value=v) for _, v in bad]
results = [call(**kw)[0] for kw in modes]
check("[never DELETE] every failure mode returns UNCERTAIN with no ids",
      all(r == UNC for r in results) and not any(isinstance(r, BaseException) for r in results))

# --- returned fallback is not shared state ------------------------------------
a, _, _ = call(side_effect=RuntimeError("x"))
if isinstance(a, dict):
    a["status"] = "DELETE"
    a["memory_ids"].append(1)
b, _, _ = call(side_effect=RuntimeError("x"))
check("[safety] mutating a returned fallback does not affect later results", b == UNC)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
