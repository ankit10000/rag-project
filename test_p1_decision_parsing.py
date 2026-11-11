import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import json
import sys
from unittest import mock

import services.memory_decision_service as mds

FAILURES = []
FINDINGS = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def probe(label, fn):
    try:
        is_defect, detail = fn()
    except Exception as error:
        FINDINGS.append(label)
        print(f"FINDING | {label} | raised {type(error).__name__}: {error}")
        return
    if is_defect:
        FINDINGS.append(label)
        print(f"FINDING | {label} | {detail}")
    else:
        print(f"PROBE-OK | {label} | {detail}")


def run(fn, response, *args):
    """Call fn with generate_answer mocked; return (result, call_count, prompt, stdout)."""
    buf = io.StringIO()
    with mock.patch.object(mds, "generate_answer", return_value=response) as m:
        with contextlib.redirect_stdout(buf):
            result = fn(*args)
    prompt = m.call_args.args[0] if m.call_args else None
    return result, m.call_count, prompt, buf.getvalue()


def js(**kw):
    return json.dumps(kw)


EXIST = [(1, "User lives in Delhi"), (2, "User likes Python")]
UNC = {"action": "UNCERTAIN", "memory_id": None, "updated_memory": None}
NEW = {"action": "NEW", "memory_id": None, "updated_memory": None}


def act(response, existing=EXIST):
    return run(mds.decide_memory_action, response, "User moved to Mumbai", existing)


# ---------------- 2a decide_memory_action: positives ----------------
r, *_ = act(js(action="NEW", memory_id=None, updated_memory=None))
check("NEW parsed", r == NEW)
r, *_ = act(js(action="DUPLICATE", memory_id=1, updated_memory=None))
check("DUPLICATE parsed with memory_id 1", r == {"action": "DUPLICATE", "memory_id": 1, "updated_memory": None})
r, *_ = act(js(action="UPDATE", memory_id=1, updated_memory="User lives in Mumbai"))
check("UPDATE preserves id and updated_memory",
      r == {"action": "UPDATE", "memory_id": 1, "updated_memory": "User lives in Mumbai"})
r, *_ = act(js(action="DELETE", memory_id=2, updated_memory=None))
check("DELETE parsed", r == {"action": "DELETE", "memory_id": 2, "updated_memory": None})
r, *_ = act(js(action="UNCERTAIN"))
check("UNCERTAIN parsed", r == UNC)
r, *_ = act(js(action="update", memory_id=1, updated_memory="x"))
check("lower-case 'update' upper-cased", r["action"] == "UPDATE")
r, *_ = act(js(action="Delete", memory_id=2))
check("mixed-case 'Delete' upper-cased", r["action"] == "DELETE")
r, *_ = act("```json\n" + js(action="NEW") + "\n```")
check("```json fenced parsed", r["action"] == "NEW")
r, *_ = act("```\n" + js(action="DUPLICATE", memory_id=1) + "\n```")
check("bare ``` fenced parsed", r["action"] == "DUPLICATE")
r, *_ = act(js(action="UPDATE", memory_id=1, updated_memory="a"))
check("memory_id int passthrough", r["memory_id"] == 1)
r, *_ = act(js(action="UPDATE", memory_id="7", updated_memory="a"))
check("memory_id string '7' passthrough", r["memory_id"] == "7")
r, *_ = act(js(action="UPDATE", memory_id=None, updated_memory="a"))
check("memory_id null passthrough", r["memory_id"] is None)
r, *_ = act(js(action="UPDATE", memory_id=99, updated_memory="a"))
check("memory_id not in list (99) returned as-is", r["memory_id"] == 99)

for empty in ([], None):
    r, calls, *_ = act("ignored", empty)
    check(f"existing={empty!r} -> NEW", r == NEW)
    check(f"existing={empty!r} -> generate_answer call_count 0", calls == 0)

r, calls, prompt, _ = act(js(action="NEW"))
check("generate_answer called exactly once", calls == 1)
for needle in ["User moved to Mumbai", "ID: 1 | Memory: User lives in Delhi",
               "ID: 2 | Memory: User likes Python", "Never invent a memory ID",
               "Only use DELETE for an explicit request", "I no longer use X",
               "Return valid JSON only"]:
    check(f"decide_memory_action prompt contains {needle!r}", needle in prompt)

# ---------------- 2a negatives -> UNCERTAIN ----------------
bad_actions = [
    ("unknown action MERGE", js(action="MERGE")),
    ("empty object", "{}"),
    ("empty action", js(action="")),
    ("padded ' UPDATE ' (no strip)", js(action=" UPDATE ")),
    ("null action", js(action=None)),
    ("int action", js(action=5)),
    ("list action", js(action=["NEW"])),
    ("empty string response", ""),
    ("prose", "Sure, I think NEW"),
    ("truncated JSON", '{"action": "NEW"'),
    ("prose + JSON", "Here you go: " + js(action="NEW")),
    ("JSON + trailing prose", js(action="NEW") + " hope that helps"),
    ("JSON array []", "[]"),
    ("JSON array ['NEW']", '["NEW"]'),
    ("JSON string", '"NEW"'),
    ("JSON null", "null"),
    ("JSON number", "12"),
]
for label, resp in bad_actions:
    r, calls, _, out = act(resp)
    check(f"{label} -> UNCERTAIN", r == UNC)
    check(f"{label} -> parse failure printed", "Memory decision parsing failed." in out)

# ambiguous pins
r, *_ = act(js(action="UPDATE"))
check("UPDATE with no id/updated_memory returned as-is", r == {"action": "UPDATE", "memory_id": None, "updated_memory": None})
r, *_ = act(js(action="DELETE", memory_id="abc"))
check("DELETE memory_id 'abc' returned verbatim", r["memory_id"] == "abc")
r, *_ = act('{"action": "NEW", "action": "DELETE", "extra": 1, "memory_id": 2}')
check("duplicate keys: last wins, extra keys ignored",
      r == {"action": "DELETE", "memory_id": 2, "updated_memory": None})

# D3: LLM failures in decide_memory_action are now assertions
r, *_ = act(None)
check("decide_memory_action generate_answer returns None -> UNCERTAIN", r == UNC)
with mock.patch.object(mds, "generate_answer", side_effect=RuntimeError("quota")):
    with contextlib.redirect_stdout(io.StringIO()):
        r = mds.decide_memory_action("x", EXIST)
check("decide_memory_action generate_answer raises RuntimeError -> UNCERTAIN", r == UNC)

# ---------------- 2b decide_memories_to_delete ----------------
DEX = [(1, "A"), (2, "B"), (3, "C")]


def dele(response, existing=DEX):
    return run(mds.decide_memories_to_delete, response, "Forget A", existing)


def D(ids):
    return {"status": "DELETE", "memory_ids": ids}


NOM = {"status": "NO_MATCH", "memory_ids": []}
UNCD = {"status": "UNCERTAIN", "memory_ids": []}

r, *_ = dele(js(status="DELETE", memory_ids=[1, 3]))
check("DELETE [1,3]", r == D([1, 3]))
r, *_ = dele(js(status="DELETE", memory_ids=[3, 1]))
check("order preserved [3,1]", r == D([3, 1]))
r, *_ = dele(js(status="DELETE", memory_ids=[1, 1, 2]))
check("duplicates removed [1,1,2] -> [1,2]", r == D([1, 2]))
r, *_ = dele(js(status="NO_MATCH", memory_ids=[1]))
check("NO_MATCH forces ids []", r == NOM)
r, *_ = dele(js(status="UNCERTAIN", memory_ids=[1]))
check("UNCERTAIN forces ids []", r == UNCD)
r, *_ = dele(js(status="delete", memory_ids=[1]))
check("status 'delete' normalised", r == D([1]))
r, *_ = dele(js(status=" no_match "))
check("status ' no_match ' normalised (stripped)", r == NOM)
r, *_ = dele(js(status="Uncertain"))
check("status 'Uncertain' normalised", r == UNCD)
r, *_ = dele("```json\n" + js(status="DELETE", memory_ids=[2]) + "\n```")
check("fenced JSON parsed", r == D([2]))
r, *_ = dele(js(status="DELETE", memory_ids=["2"]))
check("string id '2' coerced to 2", r == D([2]))
for empty in ([], None):
    r, calls, *_ = dele("ignored", empty)
    check(f"existing={empty!r} -> NO_MATCH", r == NOM)
    check(f"existing={empty!r} -> call_count 0", calls == 0)

r, calls, prompt, _ = dele(js(status="NO_MATCH"))
check("delete: generate_answer called once", calls == 1)
for needle in ["Forget A", "ID: 1 | Memory: A", "ID: 2 | Memory: B", "ID: 3 | Memory: C",
               '"Forget everything about me" is broad',
               "Never select memories from outside the provided list",
               "If status is NO_MATCH or UNCERTAIN, memory_ids MUST be []"]:
    check(f"decide_memories_to_delete prompt contains {needle!r}", needle in prompt)

# negatives
r, *_ = dele(js(status="DELETE", memory_ids=[99]))
check("DELETE only foreign id [99] -> NO_MATCH", r == NOM)
r, *_ = dele(js(status="DELETE", memory_ids=[]))
check("DELETE [] -> NO_MATCH", r == NOM)
r, *_ = dele(js(status="DELETE"))
check("DELETE without memory_ids -> NO_MATCH", r == NOM)
r, *_ = dele(js(status="DELETE", memory_ids=[1, 99]))
check("mixed [1,99] -> DELETE [1]", r == D([1]))
for label, val in [("string '1,2'", "1,2"), ("object", {"a": 1}), ("int 5", 5), ("null", None)]:
    r, *_ = dele(js(status="DELETE", memory_ids=val))
    check(f"non-list memory_ids {label} -> UNCERTAIN", r == UNCD)
r, *_ = dele(js(status="MAYBE", memory_ids=[1]))
check("unknown status MAYBE -> UNCERTAIN", r == UNCD)
r, *_ = dele(js(memory_ids=[1]))
check("missing status -> UNCERTAIN", r == UNCD)
r, *_ = dele(js(status=None, memory_ids=[1]))
check("null status -> UNCERTAIN", r == UNCD)
r, *_ = dele('{"status": "DELETE", "memory_ids": ["abc", null, [1], {"x": 1}, 2]}')
check("unselectable items skipped -> DELETE [2]", r == D([2]))
for label, resp in [("malformed JSON", '{"status": "DELETE"'), ("prose", "delete 1 please"),
                    ("empty string", ""), ("JSON list", "[]"), ("JSON string", '"DELETE"'),
                    ("JSON null", "null")]:
    r, _, _, out = dele(resp)
    check(f"{label} -> UNCERTAIN", r == UNCD)
    check(f"{label} -> parse failure printed", "Memory deletion decision parsing failed." in out)
r, *_ = dele(None)
check("generate_answer returns None -> UNCERTAIN (TypeError caught)", r == UNCD)
r, *_ = dele(js(status="DELETE", memory_ids=[1]), [("x", "A")])
check("non-numeric existing id -> UNCERTAIN", r == UNCD)

# D5: unsafe id coercion is now asserted (full matrix in test_p1_d5_delete_ids.py)
for label, val in (("bool True", True), ("float 2.7", 2.7), ("string '3.0'", "3.0")):
    r, *_ = dele(js(status="DELETE", memory_ids=[val]))
    check(f"{label} is not coerced into a memory id -> NO_MATCH", r == NOM)


# D4: LLM failure in decide_memories_to_delete is now an assertion
with mock.patch.object(mds, "generate_answer", side_effect=RuntimeError("quota")):
    with contextlib.redirect_stdout(io.StringIO()):
        r = mds.decide_memories_to_delete("x", DEX)
check("decide_memories_to_delete generate_answer raises RuntimeError -> UNCERTAIN", r == UNCD)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
