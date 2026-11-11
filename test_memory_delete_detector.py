import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import sys
import time

from services.memory_delete_service import (
    is_explicit_memory_delete_request,
)

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


# Original 15 cases (kept verbatim)
tests = [
    ("Forget my Hinglish preference", True),
    ("Forget everything", True),
    ("Please forget my cricket habit", True),
    ("stop remembering my cricket habit", True),
    ("Don't remember my phone number", True),
    ("Delete this memory from your stored memories.", True),
    ("Remove my preference from memory.", True),
    ("Don't forget to cite page numbers", False),
    ("I forget the formula, explain it", False),
    ("I forgot my password", False),
    ("Forget it, move on", False),
    ("Hey, forget my cricket habit", False),  # intentionally conservative
    ("How do I remove a column from the table?", False),
    ("Explain embeddings.", False),
    ("", False),
]

# Additional pinned cases (current behaviour)
tests += [(m, True) for m in [
    "Forget my favourite colour", "forget everything", "Forget all the tests I wrote",
    "Forget me", "forget what I told you", "forget that I use vim",
    "forget the fact that I live in Delhi", "forget our plan", "Forget about my project",
    "Please forget my name", "kindly forget my name", "Can you forget my name?",
    "Could you forget my name", "Would you forget my name", "Will you forget my name",
    "Could you please kindly forget my name",
    "Erase my preferences", "Erase everything", "please erase all",
    "Stop remembering my address", "please stop remembering",
    "Don't remember my password", "Do not remember my password", "Dont remember my name",
    "Don’t remember my name", "Please don't store this", "do not keep it",
    "Don't save that",
    "Delete this memory", "Remove my preference from memory", "Clear my memories",
    "Wipe all memories", "erase this memory", "delete memory",
    "Remove the memory about X",
    "FORGET MY NAME", "  forget   my   name  ", "forget\nmy\tname", "Delete\nthis\nmemory",
]]
tests += [(m, False) for m in [
    "Forget password reset steps", "forgetting my keys", "Forget mystery novels",
    "Don't remember", "Don't keep the logs", "Don't forget to call me",
    "Deleting memory", "memory delete", "Delete the memoryview",
    "I will remember you", "What do you remember about me?",
    "Would you don't remember my name",
]]

for message, expected in tests:
    actual = is_explicit_memory_delete_request(message)
    check(f"{message!r} -> {expected}", actual is expected)

# Falsy / failure inputs
for value in (None, "", "   ", 0, []):
    check(f"falsy input {value!r} -> False", is_explicit_memory_delete_request(value) is False)

# Performance guards (generous bound)
for label, text in (("'a'*100000", "a" * 100000), ("'delete '*2000", "delete " * 2000)):
    started = time.time()
    result = is_explicit_memory_delete_request(text)
    elapsed = time.time() - started
    print(f"timing {label}: {elapsed:.3f}s")
    check(f"perf {label} < 5s", elapsed < 5)
    check(f"perf {label} returns False", result is False)

# P-A false positives (probe only)
for message in [
    "How do I clear memory in Python?", "remove the memory leak",
    "delete memory from the cache", "How do I delete a file from memory?",
    "Don't save it as a PDF", "Why do you stop remembering things?",
    "Forget all the tests I wrote",
]:
    probe(f"P-A false positive: {message!r}",
          lambda m=message: (is_explicit_memory_delete_request(m) is True,
                             f"detector returned True for non-memory request: {m!r}"))

# P-B non-str truthy input (probe only)
for value in (123, ["forget my name"], b"forget my name"):
    probe(f"P-B non-str input {value!r}",
          lambda v=value: (False, f"returned {is_explicit_memory_delete_request(v)!r}"))

# P-C quadratic backtracking
def _slow():
    started = time.time()
    is_explicit_memory_delete_request("delete " * 20000)
    elapsed = time.time() - started
    return elapsed > 2, f"{elapsed:.2f}s for 'delete '*20000"


probe("P-C large repeated input timing", _slow)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
