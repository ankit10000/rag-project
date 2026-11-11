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
    ("Forget everything", False),                    # D1: no personal stored-memory subject
    ("Please forget my cricket habit", True),
    ("stop remembering my cricket habit", True),
    ("Don't remember my phone number", True),
    ("Delete this memory from your stored memories.", True),
    ("Remove my preference from memory.", True),     # personal-information noun + "from memory"
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
    "Forget my favourite colour",
    "Forget me", "forget what I told you", "forget that I use vim",
    "forget the fact that I live in Delhi",
    "Please forget my name", "kindly forget my name", "Can you forget my name?",
    "Could you forget my name", "Would you forget my name", "Will you forget my name",
    "Could you please kindly forget my name",
    "Stop remembering my address",
    "Don't remember my password", "Do not remember my password", "Dont remember my name",
    "Don’t remember my name",
    "Clear my memories",
    "FORGET MY NAME", "  forget   my   name  ", "forget\nmy\tname",
]]
# D1: previously pinned True, now False (no clear personal stored-memory subject,
# or the subject is not the user's stored memory). Each is a deliberate false negative.
tests += [(m, False) for m in [
    "forget everything", "Forget all the tests I wrote", "forget our plan",
    "Forget about my project", "Erase my preferences", "Erase everything", "please erase all",
    "please stop remembering", "Please don't store this", "do not keep it", "Don't save that",
    "Delete this memory", "Wipe all memories",
    "erase this memory", "delete memory", "Remove the memory about X", "Delete\nthis\nmemory",
]]
# D1 required positives (spec examples)
tests += [(m, True) for m in [
    "Forget what you remember about me.", "Delete my saved memories.",
    "Forget my previous job details.", "Remove the memory about my old project.",
    "Clear all memories you have stored about me.",
    "Please forget the personal details I shared earlier.",
]]
# D1 required negatives (spec examples)
tests += [(m, False) for m in [
    "How do I clear memory in Python?", "Please remove the memory leak in my code.",
    "Delete memory from the cache.", "Forget all the tests I wrote.", "Don't save it as a PDF.",
    "Why do you stop remembering things?", "What is a memory leak?",
    "How much memory does NumPy use?", "I want to forget about my exam.",
    "How can I clear browser memory?", "Remove this memory variable from my React component.",
]]
# D1 variations: capitalisation, punctuation, contractions, length
tests += [(m, True) for m in [
    "FORGET WHAT YOU REMEMBER ABOUT ME!", "forget what you remember about me",
    "Forget what you've stored about me.", "Forget everything you know about me",
    "DELETE MY SAVED MEMORIES", "delete my saved memories!!!", "Please, delete my saved memories?",
    "Could you please delete all my stored memories", "Clear my memory", "Delete your stored memories",
    "clear all the memories you've saved about me", "Wipe all memories you have stored about me",
    "Erase the memories about me", "Remove this memory about my old job",
    "I want you to forget my previous job details.", "Forget my previous job details, please.",
    "forget the personal details i shared", "Forget what I told you earlier",
    "Forget what I shared with you", "Don't save my phone number", "Do not store my personal details",
    "stop remembering what I told you", "Stop remembering things about me",
    "Forget my previous job details and the company I worked for, it is not relevant any more",
]]
# Correction round: technical words alone do not suppress a genuine personal-memory
# instruction; non-memory subjects ("my homework") are not deletion requests.
tests += [(m, True) for m in [
    "Remove my preference from memory.", "Forget my phone number", "Forget my phone number from your memory.",
    "Forget my Python learning goals from your saved memory.",
    "Delete the information you stored about my old project.",
    "Please forget my Python preferences", "Forget my JavaScript experience level from your stored memories",
    "forget my favourite programming language",
    "Remove my email address from your memory", "Forget my home address",
    "Forget my homework from your saved memory", "Can you remove my job details from memory?",
]]
tests += [(m, False) for m in [
    "Forget my homework", "Forget my Python learning goals", "Forget my assignment", "Forget my project",
    "Forget my tasks", "Forget my code", "Forget my cricket match", "Forget my exam schedule",
    "Fix the memory leak in my React code", "Fix the memory leak in my code",
    "Remove my array from memory", "Remove my variable from memory", "Delete my cache from memory",
    "Remove my file from memory", "Clear my python variable from memory", "Forget my variable name",
    "Delete the information stored in the cache", "Delete the information you stored in the database table",
    "Remove the information about the user from the response", "Stop remembering my homework",
    "Don't save my homework", "Delete my React project details",
    # technical uses of memory, by domain
    "How do I free memory in Python?", "Why does my Python script use so much memory?",
    "Delete the memory-heavy variable in my script", "clear memory in JavaScript",
    "How do I clear the browser memory?", "Remove memory leak from my React useEffect",
    "Delete the memory from my React component state", "How does Node.js garbage collect memory?",
    "How do I wipe memory on Linux?", "Clear memory cache on Windows", "free up RAM on my laptop",
    "How do I clear the Redis cache memory?", "Delete memory table from the database",
    "DROP the memory table in PostgreSQL", "Remove the in-memory cache", "Erase memory in C with memset",
    "Clear all memory allocations in my program", "Remove memory from the heap",
    "Delete memory leak detection code", "How to remove memory cache in Docker?",
    "Why is Chrome using so much memory?", "How much RAM does this need?",
    "Forget my React component's state", "Forget my python variable names",
    "Don't save my file as a PDF", "Don't save my work in the browser cache",
    # other uses of forget / save / remove / delete
    "I forgot to save my work", "Don't forget to save my changes", "Save my file",
    "Delete my account from the site", "Remove my name from the list in the file",
    "Delete the tests I wrote", "Remove the duplicate rows", "Forget the previous question",
    "forget about it", "never mind, forget it", "I want to forget about my ex",
    "Is it bad to forget things?", "Why do you forget things?", "Can you remember my name?",
    "Do you remember what I told you?", "What do you remember about me?",
    "Stop remembering to call me", "Stop remembering this", "Please stop remembering things",
    "Don't store it in a variable", "Don't keep the logs", "Don't save my resume as a PDF",
    "Don't save my code", "You always forget my questions in the stack overflow thread",
    "What is a memory leak?", "Explain memory management in Java",
    "Delete", "Forget", "memory", "forget my", "remove memory",
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

# D6: unsupported input types never raise and never match (no conversion to text)
class _Evil:
    def __str__(self):
        raise AssertionError("detector must not call str() on arbitrary objects")
    __repr__ = __str__


for label, value in (("None", None), ("int", 123), ("int 0", 0), ("float", 1.5), ("bool True", True),
                     ("bool False", False), ("list", ["forget my name"]), ("empty list", []),
                     ("tuple", ("forget my name",)), ("dict", {"msg": "forget my name"}), ("empty dict", {}),
                     ("set", {"forget my name"}), ("bytes", b"forget my name"), ("bytearray", bytearray(b"forget my name")),
                     ("object with raising __str__", _Evil()), ("empty string", ""),
                     ("whitespace only", "   \n\t "), ("punctuation only", " ...!? ")):
    try:
        result = is_explicit_memory_delete_request(value)
        raised = None
    except Exception as error:  # noqa: BLE001
        result, raised = None, error
    check(f"[D6 input] {label} -> False, no exception" + (f" (raised {type(raised).__name__})" if raised else ""),
          raised is None and result is False)
class _StrSub(str):
    pass
check("[D6 input] str subclass still works", is_explicit_memory_delete_request(_StrSub("Forget my phone number")) is True)
check("[D6 input] normal string still works", is_explicit_memory_delete_request("Forget my phone number") is True)

# Performance guards (generous bound)
for label, text in (("'a'*100000", "a" * 100000), ("'delete '*2000", "delete " * 2000)):
    started = time.time()
    result = is_explicit_memory_delete_request(text)
    elapsed = time.time() - started
    print(f"timing {label}: {elapsed:.3f}s")
    check(f"perf {label} < 5s", elapsed < 5)
    check(f"perf {label} returns False", result is False)

# P-A (D1): every false positive reproduced in the independent audit is now an assertion
for message in [
    "How do I clear memory in Python?", "remove the memory leak",
    "delete memory from the cache", "How do I delete a file from memory?",
    "Don't save it as a PDF", "Why do you stop remembering things?",
    "Forget all the tests I wrote",
]:
    check(f"[D1 regression] {message!r} is not a deletion request",
          is_explicit_memory_delete_request(message) is False)

# D6: repeated keywords - performance regression guards (generous bound) + benchmark output
GUARD_SECONDS = 2.0
SIZES = (1000, 2000, 4000, 20000, 100000)
for label, unit in (("delete ", "delete "), ("forget my ", "forget my "), ("stop remembering ", "stop remembering "),
                    ("please ", "please "), ("can you ", "can you "), ("delete my saved ", "delete my saved "),
                    ("memory ", "memory ")):
    timings = []
    for n in SIZES:
        text = unit * n
        started = time.perf_counter()
        result = is_explicit_memory_delete_request(text)
        elapsed = time.perf_counter() - started
        timings.append((n, elapsed))
        check(f"[D6 perf] {label!r} * {n} -> False in < {GUARD_SECONDS}s (took {elapsed:.3f}s)",
              result is False and elapsed < GUARD_SECONDS)
    print("BENCH | " + f"{label!r}: " + ", ".join(f"{n}: {t:.4f}s" for n, t in timings))

# many politeness prefixes in front of a real command must stay fast and still match
text = "please " * 20000 + "forget my phone number"
started = time.perf_counter()
result = is_explicit_memory_delete_request(text)
elapsed = time.perf_counter() - started
check(f"[D6 perf] 20000 politeness prefixes + real command -> True in < {GUARD_SECONDS}s (took {elapsed:.3f}s)",
      result is True and elapsed < GUARD_SECONDS)
check("[D6] repeated keyword alone never triggers a match",
      all(is_explicit_memory_delete_request(w * 50) is False for w in
          ("delete ", "forget ", "remove ", "erase ", "clear ", "wipe ", "memory ", "memories ", "forget my ", "my ")))
text = "x" * 100000 + " forget my phone number"
check("[D6] very long unrelated text before a command is not a command (anchored)",
      is_explicit_memory_delete_request(text) is False)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
