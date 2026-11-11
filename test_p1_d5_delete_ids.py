"""D5 regression: decide_memories_to_delete() never coerces invalid ids into valid memory ids.

ID contract (documented in docs/remediation/D5_FIX_REPORT.md):
  * genuine JSON integers are accepted if they belong to the supplied memories
  * numeric strings ("2") remain accepted (existing, pinned contract)
  * bool, float (incl. 2.0), null, list, dict and non-numeric strings are skipped
  * zero / negative / unknown ids are dropped by the existing "in provided list" filter
  * order of first appearance kept, duplicates removed (unchanged)
generate_answer is mocked; no network, no database writes.
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


EXIST = [(1, "A"), (2, "B"), (3, "C")]
NOM = {"status": "NO_MATCH", "memory_ids": []}


def ids(raw_ids, existing=EXIST):
    """Run the classifier with a raw (already-JSON) id list; return the result dict."""
    response = '{"status": "DELETE", "memory_ids": %s}' % raw_ids
    with mock.patch.object(mds, "generate_answer", return_value=response) as m:
        with contextlib.redirect_stdout(io.StringIO()):
            result = mds.decide_memories_to_delete("Forget A", existing)
    assert m.call_count == 1
    return result


def D(lst):
    return {"status": "DELETE", "memory_ids": lst}


# --- genuine integers --------------------------------------------------------
check("[int] [1] -> DELETE [1]", ids("[1]") == D([1]))
check("[int] [1, 3] -> DELETE [1, 3]", ids("[1, 3]") == D([1, 3]))
check("[order] [3, 1, 2] keeps order", ids("[3, 1, 2]") == D([3, 1, 2]))
check("[dupes] [1, 1, 2, 1] -> [1, 2]", ids("[1, 1, 2, 1]") == D([1, 2]))
check("[dupes] [2, 1, 2] keeps first appearance order", ids("[2, 1, 2]") == D([2, 1]))
check("[int] unknown id [99] -> NO_MATCH", ids("[99]") == NOM)
check("[int] zero [0] -> NO_MATCH (not a provided id)", ids("[0]") == NOM)
check("[int] negative [-1] -> NO_MATCH", ids("[-1]") == NOM)
check("[int] mixed [1, 0, -3, 99] -> DELETE [1]", ids("[1, 0, -3, 99]") == D([1]))
check("[int] zero is valid only when it is a provided id", ids("[0]", [(0, "Z"), (1, "A")]) == D([0]))

# --- booleans -----------------------------------------------------------------
check("[bool] [true] never becomes id 1", ids("[true]") == NOM)
check("[bool] [false] never becomes id 0", ids("[false]", [(0, "Z"), (1, "A")]) == NOM)
check("[bool] [true, false] -> NO_MATCH", ids("[true, false]") == NOM)
check("[bool] [true, 2] keeps only the real id 2", ids("[true, 2]") == D([2]))

# --- floats -------------------------------------------------------------------
check("[float] [2.7] never becomes id 2", ids("[2.7]") == NOM)
check("[float] [1.0] whole-number float rejected", ids("[1.0]") == NOM)
check("[float] [2.0] whole-number float rejected", ids("[2.0]") == NOM)
check("[float] [-1.5] rejected", ids("[-1.5]") == NOM)
check("[float] [0.0] rejected even with a provided id 0", ids("[0.0]", [(0, "Z"), (1, "A")]) == NOM)
check("[float] [1e0] exponent float rejected", ids("[1e0]") == NOM)
check("[float] [2.5e0, 3] keeps only 3", ids("[2.5e0, 3]") == D([3]))
check("[spec] [true, 2.7] (audit repro) -> NO_MATCH, not [1, 2]", ids("[true, 2.7]") == NOM)

# --- strings (existing contract: numeric strings accepted) ---------------------
check("[str] ['2'] numeric string still accepted (pinned contract)", ids('["2"]') == D([2]))
check("[str] ['1', 3] mixed string/int accepted in order", ids('["1", 3]') == D([1, 3]))
check("[str] ['2', 2] string and int duplicates collapse", ids('["2", 2]') == D([2]))
check("[str] ['3.0'] not an integer string -> rejected", ids('["3.0"]') == NOM)
check("[str] ['abc'] rejected", ids('["abc"]') == NOM)
check("[str] [''] rejected", ids('[""]') == NOM)
check("[str] ['1,2'] rejected", ids('["1,2"]') == NOM)
check("[str] ['true'] rejected", ids('["true"]') == NOM)
check("[str] ['-1'] negative string not a provided id", ids('["-1"]') == NOM)

# --- other raw types ------------------------------------------------------------
check("[null] [null] rejected", ids("[null]") == NOM)
check("[list] [[1]] rejected (nested list not unwrapped)", ids("[[1]]") == NOM)
check("[dict] [{\"id\": 1}] rejected", ids('[{"id": 1}]') == NOM)
check("[empty] [] -> NO_MATCH", ids("[]") == NOM)

# --- mixed valid + invalid ---------------------------------------------------------
check("[mixed] all invalid types alongside 3 -> DELETE [3]",
      ids('[true, 2.7, 2.0, null, [1], {"a": 1}, "abc", 3]') == D([3]))
check("[mixed] valid ids around invalid ones keep order",
      ids('[3, true, 1, 2.0, "2"]') == D([3, 1, 2]))
check("[mixed] every entry invalid -> NO_MATCH, never DELETE",
      ids('[true, false, 1.5, 2.0, null, [], {}, "x"]') == NOM)

# --- invalid values never become any other id; never authorise deletion -------------
big = [(i, f"M{i}") for i in range(0, 12)]
bad_values = ["true", "false", "1.0", "2.0", "2.7", "0.5", "-1.5", "null", "[1]", "{}", '"x"', '"3.0"', "1e1"]
check("[never valid] no invalid value selects any id from a list containing 0..11",
      all(ids("[%s]" % v, big) == NOM for v in bad_values))
check("[never delete] all-invalid lists never return status DELETE",
      all(ids("[%s]" % v)["status"] != "DELETE" and ids("[%s]" % v)["memory_ids"] == [] for v in bad_values))

# --- untouched behaviour around the id list ----------------------------------------------
for label, response, expected in (
    ("NO_MATCH forces ids []", '{"status": "NO_MATCH", "memory_ids": [1]}', NOM),
    ("UNCERTAIN forces ids []", '{"status": "UNCERTAIN", "memory_ids": [1]}', {"status": "UNCERTAIN", "memory_ids": []}),
    ("non-list memory_ids -> UNCERTAIN", '{"status": "DELETE", "memory_ids": 5}', {"status": "UNCERTAIN", "memory_ids": []}),
    ("string memory_ids -> UNCERTAIN", '{"status": "DELETE", "memory_ids": "1,2"}', {"status": "UNCERTAIN", "memory_ids": []}),
):
    with mock.patch.object(mds, "generate_answer", return_value=response), contextlib.redirect_stdout(io.StringIO()):
        check(f"[unchanged] {label}", mds.decide_memories_to_delete("x", EXIST) == expected)
with mock.patch.object(mds, "generate_answer", return_value='{"status": "DELETE", "memory_ids": [1]}'), \
        contextlib.redirect_stdout(io.StringIO()):
    check("[unchanged] non-numeric existing id -> UNCERTAIN (existing behaviour)",
          mds.decide_memories_to_delete("x", [("x", "A")]) == {"status": "UNCERTAIN", "memory_ids": []})

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
