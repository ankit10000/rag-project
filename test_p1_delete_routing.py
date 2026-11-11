"""Phase 1 (P1-04): main.main() routing of explicit memory-delete requests.

Every collaborator that main uses is patched on the `main` module, so no
database, embedding or LLM call is made. The real detector is used (unless a
scenario patches it) so detector + router are exercised together.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import builtins
import contextlib
import io
import sys
from unittest import mock

import main

FAILURES = []
FINDINGS = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def finding(label, detail):
    FINDINGS.append(label)
    print(f"FINDING | {label} | {detail}")


PATCHED = [
    "create_conversation", "conversation_exists", "save_message",
    "delete_matching_memories", "apply_deletion_cleanup", "ask_question",
    "get_conversation_history", "get_conversation_summary", "search_memories",
    "get_messages_for_memory_extraction", "extract_and_save_memories",
    "update_memory_extraction_checkpoint", "update_long_term_memory",
    "process_memory",
]
for _name in PATCHED:
    assert hasattr(main, _name), f"main has no attribute {_name}"

QUERY = "Forget my cricket habit"
UNCERTAIN_TEXT = ("I'm not sure which memories you want me to forget. "
                  "Could you specify the topic or information?")
SKIPPED_TEXT = "There are no stored memories in this conversation, so nothing was deleted."
NO_MATCH_TEXT = ("I couldn't find any memories that clearly match "
                 "your deletion request. No memories were deleted.")
FAILED_TEXT = "No memories were deleted. The deletion operation could not be completed."


def run_main(inputs, **overrides):
    """Run main.main() with scripted input. overrides: name -> kwargs for the MagicMock
    (e.g. return_value=..., side_effect=...) or a ready-made mock object.
    Returns (stdout, mocks, escaped_exception)."""
    script = list(inputs)
    state = {"i": 0}
    counter = {"n": 100}

    def fake_input(prompt=""):
        if state["i"] >= len(script):
            raise AssertionError("scripted input exhausted (test bug)")
        value = script[state["i"]]
        state["i"] += 1
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_save(*args, **kwargs):
        counter["n"] += 1
        return counter["n"]

    defaults = {
        "create_conversation": dict(return_value="conv-test"),
        "conversation_exists": dict(return_value=True),
        "save_message": dict(side_effect=fake_save),
        "delete_matching_memories": dict(return_value={"status": "UNCERTAIN"}),
        "apply_deletion_cleanup": dict(return_value={"messages_excluded": 2, "summary_status": "UNCHANGED"}),
        "ask_question": dict(return_value={"answer": "RAG ANSWER", "sources": []}),
        "get_conversation_history": dict(return_value=[]),
        "get_conversation_summary": dict(return_value=""),
        "search_memories": dict(return_value=[]),
        "get_messages_for_memory_extraction": dict(return_value=[]),
        "extract_and_save_memories": dict(),
        "update_memory_extraction_checkpoint": dict(),
        "update_long_term_memory": dict(),
        "process_memory": dict(),
    }
    mocks = {}
    out = io.StringIO()
    escaped = None
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(builtins, "input", side_effect=fake_input))
        for name in PATCHED:
            spec = overrides.pop(name, defaults[name])
            m = spec if isinstance(spec, mock.Mock) else mock.MagicMock(**spec)
            mocks[name] = m
            stack.enter_context(mock.patch.object(main, name, m))
        if "detector" in overrides:
            stack.enter_context(mock.patch.object(main, "is_explicit_memory_delete_request", overrides.pop("detector")))
        assert not overrides, f"unknown overrides {list(overrides)}"
        with contextlib.redirect_stdout(out):
            try:
                main.main()
            except Exception as error:
                escaped = error
    mocks["_inputs_used"] = state["i"]
    mocks["_inputs_total"] = len(script)
    return out.getvalue(), mocks, escaped


NON_DELETE_FLOW = ["ask_question", "get_conversation_history", "get_conversation_summary", "search_memories",
                   "get_messages_for_memory_extraction", "extract_and_save_memories",
                   "update_memory_extraction_checkpoint", "update_long_term_memory", "process_memory"]


def last(mock_obj):
    """Last call of a mock; an empty call (never raises) when it was not called, so a
    wrong routing decision fails an assertion instead of crashing the script."""
    return mock_obj.call_args if mock_obj.call_args is not None else mock.call()


def none_called(mocks, names):
    return all(mocks[n].call_count == 0 for n in names)


# ------------------------------ Session handling ------------------------------
out, m, err = run_main(["", "", "   ", "exit"])
check("[R1] blank lines ignored, Goodbye printed", err is None and "Goodbye!" in out)
check("[R1] create_conversation called once, nothing else", m["create_conversation"].call_count == 1
      and m["save_message"].call_count == 0 and none_called(m, NON_DELETE_FLOW + ["delete_matching_memories"]))

for text in ("EXIT", "  exit  ", "Exit"):
    out, m, err = run_main(["", text])
    check(f"[R2] {text!r} exits", err is None and "Goodbye!" in out and m["_inputs_used"] == 2)

out, m, err = run_main(["abc", "What is RAG?", "exit"])
check("[R3] ordinary question 'What is RAG?' takes the RAG path, deletion flow never entered",
      err is None and m["ask_question"].call_count == 1 and m["delete_matching_memories"].call_count == 0
      and m["apply_deletion_cleanup"].call_count == 0)
check("[R3] resume: create_conversation not called", err is None and m["create_conversation"].call_count == 0)
check("[R3] resume: conversation id used in later calls",
      last(m["conversation_exists"]).args == ("abc",) and last(m["get_conversation_history"]).args[:1] == ("abc",))
out, m, err = run_main(["abc"], conversation_exists=dict(return_value=False))
check("[R3] not found -> message and return", err is None and "Conversation not found!" in out and m["_inputs_used"] == 1)
out, m, err = run_main(["abc"], conversation_exists=dict(side_effect=ValueError("bad uuid")))
check("[R3] invalid id -> message and return", err is None and "Invalid Conversation ID!" in out and m["_inputs_used"] == 1)


# ------------------------------ Delete branch by status ------------------------------
def delete_case(tag, result, expected_answer, cleanup_expected, extra_check=None, query=QUERY):
    out, m, err = run_main(["", query, "exit"], delete_matching_memories=dict(return_value=result))
    check(f"[{tag}] no exception escapes", err is None)
    check(f"[{tag}] delete_matching_memories called once with keyword args",
          m["delete_matching_memories"].call_args_list == [mock.call(conversation_id="conv-test", user_request=query)])
    check(f"[{tag}] normal RAG flow and extraction not run", none_called(m, NON_DELETE_FLOW))
    check(f"[{tag}] user then assistant message saved in order",
          m["save_message"].call_args_list == [mock.call("conv-test", "user", query),
                                               mock.call("conv-test", "assistant", expected_answer)])
    check(f"[{tag}] detection notice and answer printed",
          "Explicit memory deletion request detected." in out and expected_answer in out)
    check(f"[{tag}] cleanup {'called once' if cleanup_expected else 'not called'}",
          m["apply_deletion_cleanup"].call_count == (1 if cleanup_expected else 0))
    if cleanup_expected:
        check(f"[{tag}] answer printed before cleanup line", out.index(expected_answer) < out.index("Deletion cleanup"))
    if extra_check:
        extra_check(out, m)
    return out, m


delete_case("D1", {"status": "UNCERTAIN"}, UNCERTAIN_TEXT, False)
delete_case("D2", {"status": "SKIPPED"}, SKIPPED_TEXT, False)
delete_case("D3", {"status": "NO_MATCH"}, NO_MATCH_TEXT, False)

mem_list = [{"id": 1, "memory": "a"}, {"id": 2, "memory": "b"}]


def d4_extra(out, m):
    check("[D4] cleanup args", m["apply_deletion_cleanup"].call_args == mock.call(
        conversation_id="conv-test", deleted_memories=mem_list, extra_message_ids=[101, 102], user_request=QUERY))
    check("[D4] cleanup summary line printed", "Deletion cleanup: 2 message(s) excluded; summary: UNCHANGED." in out)


delete_case("D4", {"status": "DELETED", "deleted_count": 2, "failed_ids": [], "deleted_memories": mem_list},
            "Deleted 2 matching memory/memories.", True, d4_extra)
delete_case("D5", {"status": "DELETED", "deleted_count": 1, "failed_ids": [9, 10], "deleted_memories": mem_list[:1]},
            "Deleted 1 matching memory/memories. 2 deletion(s) could not be completed.", True)
delete_case("D6", {"status": "FAILED", "deleted_count": 0, "failed_ids": [3]}, FAILED_TEXT, False)
delete_case("D7", {}, UNCERTAIN_TEXT, False)
delete_case("D8", {"status": "DELETED", "deleted_count": 0}, FAILED_TEXT, False)
delete_case("D9a", {"status": "UNCERTAIN", "deleted_count": 2, "deleted_memories": mem_list}, UNCERTAIN_TEXT, True)
delete_case("D9b", {"status": "FAILED", "deleted_count": 1, "deleted_memories": mem_list[:1]},
            "Deleted 1 matching memory/memories.", True)
print("NOTE | D9: cleanup follows deleted_count > 0, not status (inconsistent results pinned as-is)")


def d10_extra(out, m):
    check("[D10] missing deleted_memories key -> cleanup receives []",
          last(m["apply_deletion_cleanup"]).kwargs.get("deleted_memories") == [])


delete_case("D10", {"status": "DELETED", "deleted_count": 1}, "Deleted 1 matching memory/memories.", True, d10_extra)

# ------------------------------ Cleanup and error resilience ------------------------------
out, m, err = run_main(["", QUERY, "What is RAG?", "exit"],
                       delete_matching_memories=dict(return_value={"status": "DELETED", "deleted_count": 1, "deleted_memories": []}),
                       apply_deletion_cleanup=dict(side_effect=RuntimeError("boom")))
check("[E1] cleanup failure does not escape", err is None)
check("[E1] warning printed with cause", "Warning: deletion cleanup failed" in out and "boom" in out)
check("[E1] both messages saved before cleanup", m["save_message"].call_args_list[:2] ==
      [mock.call("conv-test", "user", QUERY), mock.call("conv-test", "assistant", "Deleted 1 matching memory/memories.")])
check("[E1] loop continues: next question reaches ask_question", m["ask_question"].call_count == 1 and "RAG ANSWER" in out)

out, m, err = run_main(["", QUERY, "exit"],
                       delete_matching_memories=dict(return_value={"status": "DELETED", "deleted_count": 1, "deleted_memories": []}),
                       apply_deletion_cleanup=dict(return_value={}))
check("[E2] cleanup result missing keys -> swallowed with warning (pin)",
      err is None and "Warning: deletion cleanup failed" in out)

out, m, err = run_main(["", QUERY, "exit"], delete_matching_memories=dict(side_effect=RuntimeError("classifier down")))
check("[E3] delete_matching_memories raising -> Error printed", err is None and "Error: classifier down" in out)
check("[E3] nothing saved, no cleanup, loop reached exit",
      m["save_message"].call_count == 0 and m["apply_deletion_cleanup"].call_count == 0 and "Goodbye!" in out)

state = {"n": 0}


def save_second_fails(*a, **k):
    state["n"] += 1
    if state["n"] == 2:
        raise RuntimeError("db write failed")
    return 100 + state["n"]


out, m, err = run_main(["", QUERY, "exit"],
                       delete_matching_memories=dict(return_value={"status": "DELETED", "deleted_count": 1, "deleted_memories": []}),
                       save_message=dict(side_effect=save_second_fails))
check("[E4] assistant save failure -> Error printed", err is None and "Error: db write failed" in out)
check("[E4] user message was saved first, cleanup not called",
      m["save_message"].call_count == 2 and m["apply_deletion_cleanup"].call_count == 0)

out, m, err = run_main(["", "What is RAG?", "exit"], ask_question=dict(side_effect=RuntimeError("llm down")))
check("[E5] ask_question failure -> Error printed, loop continues",
      err is None and "Error: llm down" in out and "Goodbye!" in out)
check("[E5] nothing saved, extraction not run",
      m["save_message"].call_count == 0 and m["get_messages_for_memory_extraction"].call_count == 0)

# ------------------------------ Normal routing ------------------------------
out, m, err = run_main(["", "What is RAG?", "exit"])
check("[N1] delete flow not used",
      m["delete_matching_memories"].call_count == 0 and m["apply_deletion_cleanup"].call_count == 0)
check("[N1] history/summary/memory search called with expected args",
      m["get_conversation_history"].call_args == mock.call("conv-test", limit=16)
      and m["get_conversation_summary"].call_args == mock.call("conv-test")
      and m["search_memories"].call_args == mock.call(conversation_id="conv-test", query="What is RAG?", top_k=5))
check("[N1] ask_question called once", m["ask_question"].call_count == 1
      and last(m["ask_question"]).kwargs.get("query") == "What is RAG?"
      and last(m["ask_question"]).kwargs.get("history") == [])
check("[N1] user then assistant saved", m["save_message"].call_args_list ==
      [mock.call("conv-test", "user", "What is RAG?"), mock.call("conv-test", "assistant", "RAG ANSWER")])
check("[N1] extraction lookup and summary update called",
      m["get_messages_for_memory_extraction"].call_args == mock.call("conv-test", limit=4)
      and m["update_long_term_memory"].call_args == mock.call("conv-test", keep_recent=6))

for label, summary, found, expected in (
        ("summary + memories", "S", [{"memory": "M1"}, {"memory": "M2"}], "S\nM1\nM2"),
        ("memories only", "", [{"memory": "M1"}, {"memory": "M2"}], "M1\nM2"),
        ("neither", "", [], "")):
    out, m, err = run_main(["", "What is RAG?", "exit"], get_conversation_summary=dict(return_value=summary),
                           search_memories=dict(return_value=found))
    check(f"[N2] memory_summary composition: {label}", last(m["ask_question"]).kwargs.get("memory_summary") == expected)

out, m, err = run_main(["", "What is RAG?", "exit"],
                       get_messages_for_memory_extraction=dict(return_value=[{"id": 1}, {"id": 2}, {"id": 3}]))
check("[N3] 3 messages -> extraction skipped", m["extract_and_save_memories"].call_count == 0
      and "Memory extraction skipped. 3 new messages; 4 required." in out)
batch = [{"id": i} for i in (11, 12, 13, 14)]
out, m, err = run_main(["", "What is RAG?", "exit"], get_messages_for_memory_extraction=dict(return_value=batch))
check("[N3] 4 messages -> extraction with last id as source", m["extract_and_save_memories"].call_args ==
      mock.call(conversation_id="conv-test", messages=batch, source_message_id=14))
check("[N3] checkpoint advanced to 14", m["update_memory_extraction_checkpoint"].call_args ==
      mock.call(conversation_id="conv-test", last_message_id=14))
out, m, err = run_main(["", "What is RAG?", "exit"], get_messages_for_memory_extraction=dict(return_value=batch),
                       extract_and_save_memories=dict(side_effect=RuntimeError("extract fail")))
check("[N3] extraction failure -> warning, checkpoint not advanced, summary update still runs",
      err is None and "Warning: memory extraction failed" in out
      and m["update_memory_extraction_checkpoint"].call_count == 0 and m["update_long_term_memory"].call_count == 1)

for text in ("Forget it, move on", "Don't forget to save the file", "I forgot my password",
             "Hey, forget my name", "How do I remove a column?"):
    out, m, err = run_main(["", text, "exit"])
    check(f"[N4] {text!r} takes the RAG path",
          m["delete_matching_memories"].call_count == 0 and m["ask_question"].call_count == 1
          and m["save_message"].call_count == 2)

# N5: process_memory never called anywhere; extraction never in delete branch
for tag, result in (("UNCERTAIN", {"status": "UNCERTAIN"}), ("DELETED", {"status": "DELETED", "deleted_count": 1}),
                    ("FAILED", {"status": "FAILED"}), ("NO_MATCH", {"status": "NO_MATCH"})):
    out, m, err = run_main(["", QUERY, "exit"], delete_matching_memories=dict(return_value=result))
    check(f"[N5] delete branch ({tag}): process_memory and extraction never called",
          m["process_memory"].call_count == 0 and m["extract_and_save_memories"].call_count == 0)
out, m, err = run_main(["", "What is RAG?", "exit"])
check("[N5] normal path: process_memory not called", m["process_memory"].call_count == 0)

out, m, err = run_main(["", "  FORGET MY cricket habit  ", "exit"])
check("[N6] query stripped, case preserved", m["delete_matching_memories"].call_args ==
      mock.call(conversation_id="conv-test", user_request="FORGET MY cricket habit"))

out, m, err = run_main(["", "hello", "exit"], detector=lambda q: True)
check("[N7] detector True for 'hello' -> delete branch", m["delete_matching_memories"].call_count == 1
      and m["ask_question"].call_count == 0)
out, m, err = run_main(["", "forget my name", "exit"], detector=lambda q: False)
check("[N7] detector False for 'forget my name' -> RAG branch", m["delete_matching_memories"].call_count == 0
      and m["ask_question"].call_count == 1)

out, m, err = run_main(["", QUERY, "What is RAG?", "exit"],
                       delete_matching_memories=dict(return_value={"status": "DELETED", "deleted_count": 1, "deleted_memories": []}))
check("[N8] four messages saved, mixed session", m["save_message"].call_count == 4)
check("[N8] cleanup extra_message_ids only the deletion pair",
      last(m["apply_deletion_cleanup"]).kwargs.get("extra_message_ids") == [101, 102])

# ------------------------------ D1: detector -> routing (real detector) ------------------------------
for text in ("How do I clear memory in Python?", "remove the memory leak", "Forget all the tests I wrote",
             "Please remove the memory leak in my code.", "Delete memory from the cache.",
             "Don't save it as a PDF.", "Why do you stop remembering things?",
             "Remove this memory variable from my React component.", "How can I clear browser memory?"):
    out, m, err = run_main(["", text, "exit"], delete_matching_memories=dict(return_value={"status": "NO_MATCH"}))
    check(f"[D1] {text!r} takes the RAG path, deletion flow never entered",
          err is None and m["delete_matching_memories"].call_count == 0
          and m["apply_deletion_cleanup"].call_count == 0 and m["ask_question"].call_count == 1)

for text in ("Forget what you remember about me.", "Delete my saved memories.", "Forget my previous job details.",
             "Remove the memory about my old project.", "Clear all memories you have stored about me.",
             "Please forget the personal details I shared earlier."):
    out, m, err = run_main(["", text, "exit"], delete_matching_memories=dict(return_value={"status": "UNCERTAIN"}))
    check(f"[D1] {text!r} reaches delete_matching_memories, RAG skipped",
          err is None and m["delete_matching_memories"].call_args_list == [mock.call(conversation_id="conv-test", user_request=text)]
          and m["ask_question"].call_count == 0)

out, m, err = run_main(["", EOFError()])
print(f"INFO | EOFError at prompt propagates out of main(): {type(err).__name__ if err else 'no'}")

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
