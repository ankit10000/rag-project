"""Live-Gemini classifier test (read-only: no DB access)."""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib, io, sys
from services.memory_decision_service import decide_memories_to_delete

MEMORIES = [
    (1, "The user's RAG project uses Python and PostgreSQL"),
    (2, "The user prefers Hinglish explanations"),
    (3, "The user has experience with React and Node.js"),
    (4, "The user prefers concise answers"),
    (5, "The user has a cricket hobby"),
    (6, "The user's grandfather has a medical condition"),
]

CASES = [
    ("Forget my technology preferences.", "DELETE", {1, 3}),
    ("Forget my tech stack", "DELETE", {1, 3}),
    ("Forget my Hinglish preference", "DELETE", {2}),
    ("Forget everything.", "UNCERTAIN", set()),
    ("Forget my favorite color", "NO_MATCH", set()),
    ("Forget my cricket hobby", "DELETE", {5}),
]

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
failures = 0

for request, status, ids in CASES:
    for run in range(RUNS):
        with contextlib.redirect_stdout(io.StringIO()):
            r = decide_memories_to_delete(request, MEMORIES)
        ok = r["status"] == status and set(r["memory_ids"]) == ids
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} | {request!r} run{run+1} -> {r['status']} {sorted(r['memory_ids'])} (expected {status} {sorted(ids)})")

print(f"\n{failures} failure(s)")
