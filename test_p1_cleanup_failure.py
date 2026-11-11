"""Phase 1 (P1-07): apply_deletion_cleanup end-to-end under LLM failure.

Real scratch database, LLM (services.memory_cleanup_service.generate_answer)
mocked. Invariant under test: after any failure branch, the stored summary is
either empty or free of the deleted fact; the original leaky summary never
survives, and deterministic message exclusion is never undone.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import sys
import uuid
from unittest import mock

import services.memory_cleanup_service as mcs
from services.conversation_service import (
    create_conversation,
    save_message,
    get_conversation_history,
    get_conversation_summary,
    update_conversation_memory,
)
from services.database import get_connection

FAILURES = []
FINDINGS = []
CREATED = []

NO = '{"still_contains": false, "evidence": ""}'
YES = '{"still_contains": true, "evidence": "Python"}'
LEAKY = "The user uses Python for a RAG app. The user enjoys cricket on weekends."
GOOD = "The user enjoys cricket on weekends."
FACT = "User uses Python."
FORGOTTEN_WORD = "python"


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def finding(label, detail):
    FINDINGS.append(label)
    print(f"FINDING | {label} | {detail}")


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def llm(rewrite=GOOD, verify=NO, echo="[]"):
    """Prompt-dispatching fake. A value that is an Exception instance is raised."""
    def fn(prompt):
        if "SUMMARY TO CHECK" in prompt:
            value = verify
        elif "editing a conversation summary" in prompt:
            value = rewrite
        elif "RECENT MESSAGES" in prompt:
            value = echo
        else:
            raise AssertionError("unexpected prompt")
        if isinstance(value, Exception):
            raise value
        return value
    return fn


class Fx:
    def __init__(self):
        self.conv = create_conversation("p1-cleanup-failure")
        self.other = create_conversation("p1-cleanup-failure-other")
        CREATED.extend([self.conv, self.other])
        self.u1 = save_message(self.conv, "user", "I use Python for my RAG app")
        self.r1 = save_message(self.conv, "assistant", "Python is a good choice for RAG")
        self.u2 = save_message(self.conv, "user", "I enjoy cricket on weekends")
        self.r2 = save_message(self.conv, "assistant", "Cricket is fun")
        update_conversation_memory(self.conv, LEAKY, self.r2)
        self.ou = save_message(self.other, "user", "Other user message about Python")
        self.orr = save_message(self.other, "assistant", "Other reply")
        update_conversation_memory(self.other, "Other summary about Python.", self.orr)
        self.deleted = [{"id": 1, "memory": FACT, "source_message_id": self.u1,
                         "source_message_ids": [self.u1]}]

    def checkpoint(self, conv=None):
        with get_connection() as conn:
            return conn.execute("SELECT summary_up_to_message_id FROM conversations WHERE id=%s",
                                (uuid.UUID(conv or self.conv),)).fetchone()[0]

    def excluded(self, conv=None):
        with get_connection() as conn:
            return {r[0] for r in conn.execute(
                "SELECT id FROM messages WHERE conversation_id=%s AND context_excluded",
                (uuid.UUID(conv or self.conv),)).fetchall()}

    def other_fingerprint(self):
        return (get_conversation_summary(self.other), self.checkpoint(self.other), self.excluded(self.other),
                [m["content"] for m in get_conversation_history(self.other, limit=50)])

    def visible(self):
        return " ".join(m["content"] for m in get_conversation_history(self.conv, limit=50)).lower()


def cleanup(fx, fake, patch_echo=None):
    with contextlib.ExitStack() as stack:
        gen = stack.enter_context(mock.patch.object(mcs, "generate_answer", side_effect=fake))
        if patch_echo is not None:
            stack.enter_context(mock.patch.object(mcs, "find_echo_message_ids", **patch_echo))
        result = quiet(mcs.apply_deletion_cleanup, fx.conv, fx.deleted, [], "Forget my Python usage")
    return result, gen


def invariant(tag, fx):
    summary = get_conversation_summary(fx.conv)
    check(f"[{tag}] invariant: summary empty or free of the forgotten fact (not the leaky original)",
          summary == "" or (FORGOTTEN_WORD not in summary.lower() and summary != LEAKY))


def run():
    # a. rewrite call raises
    fx = Fx()
    iso = fx.other_fingerprint()
    result, gen = cleanup(fx, llm(rewrite=RuntimeError("503 unavailable")))
    check("[a] summary_status RESET", result["summary_status"] == "RESET")
    check("[a] stored summary is empty", get_conversation_summary(fx.conv) == "")
    check("[a] checkpoint reset to 0", fx.checkpoint() == 0)
    check("[a] messages_excluded > 0 (deterministic exclusion survives LLM failure)", result["messages_excluded"] > 0)
    check("[a] source message and paired reply excluded", {fx.u1, fx.r1} <= fx.excluded())
    check("[a] forgotten text absent from history", FORGOTTEN_WORD not in fx.visible())
    check("[a] unrelated messages still visible", "cricket" in fx.visible())
    check("[a] LLM mock was exercised", gen.call_count > 0)
    check("[g/a] other conversation untouched", fx.other_fingerprint() == iso)
    invariant("a", fx)

    # b. verifier says YES
    fx = Fx()
    iso = fx.other_fingerprint()
    result, gen = cleanup(fx, llm(rewrite=GOOD, verify=YES))
    check("[b] verifier YES -> RESET", result["summary_status"] == "RESET")
    check("[b] summary empty, checkpoint 0", get_conversation_summary(fx.conv) == "" and fx.checkpoint() == 0)
    check("[b] source message and paired reply excluded", {fx.u1, fx.r1} <= fx.excluded())
    check("[b] LLM mock exercised (rewrite + verify)", gen.call_count >= 2)
    check("[g/b] other conversation untouched", fx.other_fingerprint() == iso)
    invariant("b", fx)

    # c. verifier raises
    fx = Fx()
    iso = fx.other_fingerprint()
    result, gen = cleanup(fx, llm(rewrite=GOOD, verify=RuntimeError("verifier down")))
    check("[c] verifier raises -> RESET", result["summary_status"] == "RESET")
    check("[c] summary empty, checkpoint 0", get_conversation_summary(fx.conv) == "" and fx.checkpoint() == 0)
    check("[c] source messages still excluded", {fx.u1, fx.r1} <= fx.excluded())
    check("[g/c] other conversation untouched", fx.other_fingerprint() == iso)
    invariant("c", fx)

    # d. echo scan raises (patched)
    fx = Fx()
    iso = fx.other_fingerprint()
    raised = None
    try:
        result, gen = cleanup(fx, llm(rewrite=GOOD, verify=NO),
                              patch_echo=dict(side_effect=RuntimeError("echo scan exploded")))
    except Exception as error:
        raised = error
        result = {}
    check("[d] echo scan failure does not raise", raised is None)
    check("[d] summary_status still produced", result.get("summary_status") in {"REWRITTEN", "UNCHANGED", "RESET", "EMPTIED", "NO_SUMMARY"})
    check("[d] echo_messages_excluded == 0", result.get("echo_messages_excluded") == 0)
    check("[d] source message and paired reply still excluded", {fx.u1, fx.r1} <= fx.excluded())
    check("[d] summary cleaned by the (mocked, successful) rewrite", get_conversation_summary(fx.conv) == GOOD
          and result.get("summary_status") == "REWRITTEN")
    check("[g/d] other conversation untouched", fx.other_fingerprint() == iso)
    invariant("d", fx)

    # d2. echo scan LLM itself raises (real find_echo_message_ids swallows it)
    fx = Fx()
    result, gen = cleanup(fx, llm(rewrite=GOOD, verify=NO, echo=RuntimeError("echo llm down")))
    check("[d2] echo LLM failure swallowed, cleanup completes", result["summary_status"] == "REWRITTEN"
          and result["echo_messages_excluded"] == 0 and {fx.u1, fx.r1} <= fx.excluded())
    invariant("d2", fx)

    # e. rewrite returns empty string (not the sentinel)
    fx = Fx()
    iso = fx.other_fingerprint()
    result, gen = cleanup(fx, llm(rewrite=""))
    after = get_conversation_summary(fx.conv)
    print(f"INFO | [e] empty rewrite -> status={result['summary_status']!r} stored summary={after!r} checkpoint={fx.checkpoint()}")
    check("[e] empty-string rewrite -> RESET (pinned)", result["summary_status"] == "RESET")
    check("[e] summary empty and checkpoint 0", after == "" and fx.checkpoint() == 0)
    if FORGOTTEN_WORD in after.lower() or after == LEAKY:
        finding("empty rewrite leaves leaky summary", f"stored summary after '' rewrite: {after!r}")
    check("[g/e] other conversation untouched", fx.other_fingerprint() == iso)
    invariant("e", fx)

    # additional failure branches covered by the same invariant
    for tag, fake in (
        ("f1 rewrite still leaks verbatim", llm(rewrite="The user uses Python. The user enjoys cricket on weekends today.")),
        ("f2 rewrite too short", llm(rewrite="Ok.")),
        ("f3 verifier returns prose", llm(rewrite=GOOD, verify="I think it is fine")),
        ("f4 verifier non-boolean", llm(rewrite=GOOD, verify='{"still_contains": "no"}')),
        ("f5 rewrite returns whitespace", llm(rewrite="   \n ")),
    ):
        fx = Fx()
        result, gen = cleanup(fx, fake)
        check(f"[{tag}] RESET", result["summary_status"] == "RESET")
        check(f"[{tag}] summary empty, checkpoint 0", get_conversation_summary(fx.conv) == "" and fx.checkpoint() == 0)
        check(f"[{tag}] deterministic exclusion kept", result["messages_excluded"] > 0 and {fx.u1, fx.r1} <= fx.excluded())
        invariant(tag, fx)


try:
    run()
finally:
    with get_connection() as conn:
        for cid in CREATED:
            conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(cid),))

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
