"""
Classifier-only accuracy test for decide_memories_to_delete(), run
against the primary model and EVERY fallback model.

No database access and no deletion: only the LLM classifier runs.
A model is pinned by setting llm.MODEL_NAME and clearing the
fallback list, so the answer really comes from that model.

Usage: python test_memory_delete_fallback_models.py [runs_per_case]
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import sys

import services.llm_service as llm
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
    ("Forget my technology preferences", "DELETE", {1, 3}),
    ("Forget my Hinglish preference", "DELETE", {2}),
    ("Forget my cricket hobby", "DELETE", {5}),
    ("Forget everything", "UNCERTAIN", set()),
    ("Forget my favorite color", "NO_MATCH", set()),
]

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 2

MODELS = [llm.MODEL_NAME] + [
    m for m in llm.FALLBACK_MODELS if m != llm.MODEL_NAME
]

total_failures = 0

for model in MODELS:
    llm.MODEL_NAME = model
    llm.FALLBACK_MODELS = []          # pin: no switching to another model
    llm._quota_cooldown_until.clear()

    print(f"\n=== {model} ===")
    failures = 0

    for request, status, ids in CASES:
        for run in range(1, RUNS + 1):
            buffer = io.StringIO()

            try:
                with contextlib.redirect_stdout(buffer):
                    result = decide_memories_to_delete(request, MEMORIES)
                error = None
            except Exception as exc:        # e.g. quota exhausted
                result, error = None, exc

            parse_failed = "parsing failed" in buffer.getvalue()

            ok = (
                error is None
                and not parse_failed        # JSON must be valid
                and result["status"] == status
                and set(result["memory_ids"]) == ids
            )
            failures += not ok

            shown = (
                f"ERROR {str(error)[:60]}" if error
                else f"{result['status']} {sorted(result['memory_ids'])}"
                + (" [INVALID JSON]" if parse_failed else "")
            )
            print(
                f"{'PASS' if ok else 'FAIL'} | {request!r} run{run} -> "
                f"{shown} (expected {status} {sorted(ids)})"
            )

    print(f"{model}: {failures} failure(s)")
    total_failures += failures

print(f"\nTOTAL: {total_failures} failure(s) across {len(MODELS)} model(s)")
sys.exit(1 if total_failures else 0)
