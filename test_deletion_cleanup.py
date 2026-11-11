"""Deletion cleanup tests (real DB, Gemini mocked)."""
import contextlib
import io
from unittest import mock

import services.memory_cleanup_service as mcs
import services.automatic_memory_service as ams
from services.conversation_service import (
    create_conversation, save_message, mark_messages_excluded,
    get_conversation_history, get_messages_to_summarize,
    get_messages_for_memory_extraction, get_conversation_summary,
    update_conversation_memory,
)
from services.memory_storage_service import save_memory


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


NO = '{"still_contains": false, "evidence": ""}'
YES = '{"still_contains": true, "evidence": "Python"}'


def llm(rewrite=None, verify=NO, echo="[]"):
    """Prompt-dispatching fake for generate_answer in memory_cleanup_service."""
    def fn(prompt):
        if "SUMMARY TO CHECK" in prompt:
            return verify
        if "editing a conversation summary" in prompt:
            return rewrite
        if "RECENT MESSAGES" in prompt:
            return echo
        raise AssertionError("unexpected prompt")
    return fn


def check(name, cond):
    print(("PASS" if cond else "FAIL"), "|", name)
    assert cond, name


# ---- 1. exclusion filters ------------------------------------------------
c = create_conversation("T-exclude")
ids = [save_message(c, "user" if i % 2 == 0 else "assistant", f"msg {i}")
       for i in range(20)]
check("save_message returns an id", all(isinstance(i, int) for i in ids))
check("mark_messages_excluded counts", mark_messages_excluded(c, [ids[0], ids[5]]) == 2)
hist = [m["content"] for m in get_conversation_history(c, limit=50)]
check("history hides excluded", "msg 0" not in hist and "msg 5" not in hist and len(hist) == 18)
ext = [m["id"] for m in get_messages_for_memory_extraction(c, limit=50)]
check("extraction hides excluded", ids[0] not in ext and ids[5] not in ext and len(ext) == 18)
_, summ = get_messages_to_summarize(c, keep_recent=6)
sid = [m["id"] for m in summ]
check("summarization hides excluded", ids[0] not in sid and ids[5] not in sid)

# isolation: excluding via another conversation must not touch this one
other = create_conversation("T-other")
check("exclusion is conversation-scoped", mark_messages_excluded(other, [ids[1]]) == 0)
check("other conversation's message untouched",
      "msg 1" in [m["content"] for m in get_conversation_history(c, limit=50)])

# checkpoint does not get stuck on excluded messages
e = create_conversation("T-ckpt")
eids = [save_message(e, "user", f"m{i}") for i in range(6)]
mark_messages_excluded(e, eids[2:4])
batch = get_messages_for_memory_extraction(e, limit=4)
check("batch of 4 skips excluded", [m["id"] for m in batch] == [eids[0], eids[1], eids[4], eids[5]])

# ---- 2. summary rewrite paths -------------------------------------------
def fresh_summary(text):
    s = create_conversation("T-sum")
    update_conversation_memory(s, text, 0)
    return s

ORIG = ("The user prefers explanations in simple Hinglish. "
        "The user is building a RAG app with Python and PostgreSQL. "
        "The user enjoys cricket on weekends.")
DEL = ["User prefers explanations in simple Hinglish."]

s = fresh_summary(ORIG)
good = ("The user is building a RAG app with Python and PostgreSQL. "
        "The user enjoys cricket on weekends.")
with mock.patch.object(mcs, "generate_answer", side_effect=llm(rewrite=good)):
    r = quiet(mcs.rewrite_summary_without, s, DEL)
check("valid rewrite -> REWRITTEN", r == "REWRITTEN" and get_conversation_summary(s) == good)
check("unrelated facts kept", "cricket" in get_conversation_summary(s) and "PostgreSQL" in get_conversation_summary(s))

s = fresh_summary(ORIG)
with mock.patch.object(mcs, "generate_answer", return_value="Short."):
    r = quiet(mcs.rewrite_summary_without, s, DEL)
check("destructive rewrite -> RESET", r == "RESET" and get_conversation_summary(s) == "")

s = fresh_summary(ORIG)
leaky = ORIG  # still contains deleted text
with mock.patch.object(mcs, "generate_answer", return_value=ORIG.replace("The user prefers explanations in simple Hinglish.", "User prefers explanations in simple Hinglish.")):
    r = quiet(mcs.rewrite_summary_without, s, DEL)
check("rewrite that still leaks -> RESET", r == "RESET" and get_conversation_summary(s) == "")

s = fresh_summary("The user prefers explanations in simple Hinglish.")
with mock.patch.object(mcs, "generate_answer", return_value="EMPTY"):
    r = quiet(mcs.rewrite_summary_without, s, DEL)
check("nothing left -> EMPTIED", r == "EMPTIED" and get_conversation_summary(s) == "")

s = fresh_summary(ORIG)
with mock.patch.object(mcs, "generate_answer", side_effect=RuntimeError("503")):
    r = quiet(mcs.rewrite_summary_without, s, DEL)
check("Gemini failure -> RESET (fact never left in place)", r == "RESET" and get_conversation_summary(s) == "")

s = fresh_summary("")
check("empty summary -> NO_SUMMARY", quiet(mcs.rewrite_summary_without, s, DEL) == "NO_SUMMARY")

s = fresh_summary("The user enjoys cricket on weekends.")
with mock.patch.object(mcs, "generate_answer", side_effect=llm(rewrite="The user enjoys cricket on weekends.")):
    r = quiet(mcs.rewrite_summary_without, s, DEL)
check("unrelated summary -> UNCHANGED", r == "UNCHANGED")

# ---- 3. delete_matching_memories reports text + source ids ---------------
d = create_conversation("T-del")
m1 = save_message(d, "user", "I prefer simple Hinglish.")
m1r = save_message(d, "assistant", "Sure, I will use simple Hinglish.")
quiet(save_memory, d, "The user prefers simple Hinglish.", m1)
mem_id = ams.get_all_conversation_memories(d)[0][0]
with mock.patch.object(ams, "decide_memories_to_delete",
                       return_value={"status": "DELETE", "memory_ids": [mem_id]}):
    res = quiet(ams.delete_matching_memories, d, "forget my hinglish preference")
check("deleted_memories has text + source id",
      res["deleted_memories"] == [{"id": mem_id, "memory": "The user prefers simple Hinglish.", "source_message_id": m1, "source_message_ids": [m1]}])

# candidate override was removed: partial candidate lists are impossible
try:
    ams.delete_matching_memories(d, "x", candidate_memories=[(mem_id, "y")])
    check("candidate_memories override rejected", False)
except TypeError:
    check("candidate_memories override rejected", True)

# ---- 4. apply_deletion_cleanup end-to-end (Gemini mocked) ----------------
update_conversation_memory(d, ORIG, 0)
turn_u = save_message(d, "user", "forget my hinglish preference")
turn_a = save_message(d, "assistant", "Deleted 1 matching memory/memories.")
with mock.patch.object(mcs, "generate_answer", side_effect=llm(rewrite=good)):
    out = quiet(mcs.apply_deletion_cleanup, d, res["deleted_memories"], [turn_u, turn_a])
check("cleanup excludes source + its reply + deletion-turn messages", out["messages_excluded"] == 4)
check("cleanup rewrote summary", out["summary_status"] == "REWRITTEN")
texts = [m["content"] for m in get_conversation_history(d, limit=50)]
check("history no longer contains forgotten message or its reply", "I prefer simple Hinglish." not in texts and "Sure, I will use simple Hinglish." not in texts)

# ---- 5. echo-message scan ----------------------------------------------
g = create_conversation("T-echo")
gu = save_message(g, "user", "I am building a RAG app.")
ga = save_message(g, "assistant", "Sure, I will explain in simple Hinglish.")
gx = save_message(g, "user", "Unrelated: I like cricket.")
other_msg = save_message(other, "user", "foreign message")

with mock.patch.object(mcs, "generate_answer",
                       return_value=f'[{ga}, {other_msg}, 999999, "abc"]'):
    echo = quiet(mcs.find_echo_message_ids, g, ["User prefers simple Hinglish."])
check("echo scan accepts only this conversation's ids", echo == [ga])

with mock.patch.object(mcs, "generate_answer", return_value="not json"):
    check("echo scan bad JSON -> []", quiet(mcs.find_echo_message_ids, g, ["x"]) == [])

with mock.patch.object(mcs, "generate_answer", side_effect=RuntimeError("503")):
    check("echo scan Gemini failure -> []", quiet(mcs.find_echo_message_ids, g, ["x"]) == [])

with mock.patch.object(mcs, "generate_answer", return_value="[]"):
    check("echo scan none -> []", quiet(mcs.find_echo_message_ids, g, ["x"]) == [])

print("\nALL PASSED")
