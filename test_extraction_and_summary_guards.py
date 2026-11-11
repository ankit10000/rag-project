"""Mocked tests: (1b) extraction never uses assistant text,
(1a) summary rewrite uses the original request + semantic verification."""
import contextlib, io
from unittest import mock

import services.memory_service as ms
import services.memory_cleanup_service as mcs
from services.conversation_service import (
    create_conversation, update_conversation_memory, get_conversation_summary,
)
from services.database import get_connection


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), "|", name)
    assert cond, name


# ---------------- 1b: extraction input is user-only ----------------------
BATCH = [
    {"id": 10, "role": "user", "content": "I use Python and PostgreSQL."},
    {"id": 11, "role": "assistant", "content": "LEAK: you use React frontend and Node backend."},
    {"id": 12, "role": "user", "content": "I prefer simple Hinglish."},
    {"id": 13, "role": "assistant", "content": "LEAK2: Aap pgvector bhi use karte hain."},
]

seen = {}
def fake_extractor(prompt):
    seen["prompt"] = prompt
    return ('[{"memory": "User uses Python and PostgreSQL.", "source_message_id": 10},'
            ' {"memory": "User uses React.", "source_message_id": 11},'
            ' {"memory": "User prefers simple Hinglish.", "source_message_id": 12}]')

with mock.patch.object(ms, "generate_answer", side_effect=fake_extractor):
    out = quiet(ms.extract_memories, BATCH)

p = seen["prompt"]
check("extractor prompt contains user messages", "I use Python and PostgreSQL." in p and "I prefer simple Hinglish." in p)
check("extractor prompt contains NO assistant text", "LEAK" not in p and "assistant:" not in p and "React frontend" not in p)
check("source id of an assistant message is rejected (-> None)",
      {m["memory"]: m["source_message_id"] for m in out} ==
      {"User uses Python and PostgreSQL.": 10, "User uses React.": None, "User prefers simple Hinglish.": 12})

with mock.patch.object(ms, "generate_answer", side_effect=AssertionError("must not be called")):
    only_assistant = [{"id": 1, "role": "assistant", "content": "hello"}]
    check("batch with no user messages -> [] and no LLM call", quiet(ms.extract_memories, only_assistant) == [])

# fallback attribution = last USER message, never the assistant message
captured = []
def fake_process(**kw):
    captured.append(kw["source_message_id"])
    return "SAVED"

with mock.patch.object(ms, "generate_answer", return_value='[{"memory": "User likes tea."}]'), \
     mock.patch.object(ms, "process_memory", side_effect=fake_process):
    quiet(ms.extract_and_save_memories, "c", BATCH, source_message_id=13)
check("fallback source = last user message (12), not assistant (13)", captured == [12])

# ---------------- 1a: summary rewrite -----------------------------------
NO = '{"still_contains": false, "evidence": ""}'
YES = '{"still_contains": true, "evidence": "Python"}'
ORIG = ("The user's RAG project uses Python and PostgreSQL. "
        "The user prefers explanations in simple Hinglish. "
        "The user enjoys cricket on weekends.")
CLEAN = ("The user prefers explanations in simple Hinglish. "
         "The user enjoys cricket on weekends.")
DEL = ["User is using Python and PostgreSQL with pgvector."]
REQ = "Forget my technology preferences."


def llm(rewrite, verify=NO, prompts=None):
    def fn(prompt):
        if prompts is not None:
            prompts.append(prompt)
        if "SUMMARY TO CHECK" in prompt:
            if isinstance(verify, Exception):
                raise verify
            return verify
        return rewrite
    return fn


def fresh(text=ORIG):
    s = create_conversation("T-guards")
    update_conversation_memory(s, text, 7)
    return s


def checkpoint(s):
    with get_connection() as c:
        return c.execute("select summary_up_to_message_id from conversations where id=%s", (s,)).fetchone()[0]


s = fresh(); prompts = []
with mock.patch.object(mcs, "generate_answer", side_effect=llm(CLEAN, prompts=prompts)):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("rewrite prompt includes the ORIGINAL REQUEST and deleted memory",
      REQ in prompts[0] and DEL[0] in prompts[0])
check("verification prompt includes the request too", REQ in prompts[1])
check("clean rewrite + verification NO -> REWRITTEN", r == "REWRITTEN" and get_conversation_summary(s) == CLEAN)

s = fresh()
LEAKY = ORIG.replace("The user's RAG project uses Python and PostgreSQL. ", "Building a RAG app with Python and PostgreSQL (with pgvector). ")
with mock.patch.object(mcs, "generate_answer", side_effect=llm(LEAKY, verify=YES)):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("semantic leak (not verbatim) caught -> RESET", r == "RESET" and get_conversation_summary(s) == "" and checkpoint(s) == 0)

s = fresh()
with mock.patch.object(mcs, "generate_answer", side_effect=llm(CLEAN, verify="maybe?")):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("unparseable verification -> RESET (uncertain is unsafe)", r == "RESET" and get_conversation_summary(s) == "")

s = fresh()
with mock.patch.object(mcs, "generate_answer", side_effect=llm(CLEAN, verify=RuntimeError("503"))):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("verification call failure -> RESET", r == "RESET" and get_conversation_summary(s) == "")

s = fresh()
with mock.patch.object(mcs, "generate_answer", side_effect=llm(CLEAN, verify='{"still_contains": "no"}')):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("non-boolean verification value -> RESET", r == "RESET")

s = fresh()
with mock.patch.object(mcs, "generate_answer", side_effect=llm(ORIG, verify=YES)):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("model 'changed nothing' is still verified -> RESET", r == "RESET")

s = fresh(CLEAN)
with mock.patch.object(mcs, "generate_answer", side_effect=llm(CLEAN, verify=NO)):
    r = quiet(mcs.rewrite_summary_without, s, DEL, REQ)
check("nothing to remove + verified clean -> UNCHANGED", r == "UNCHANGED" and get_conversation_summary(s) == CLEAN)

# apply_deletion_cleanup forwards the request
s = fresh(); prompts = []
with mock.patch.object(mcs, "generate_answer", side_effect=llm(CLEAN, prompts=prompts)):
    quiet(mcs.apply_deletion_cleanup, s, [{"id": 1, "memory": DEL[0], "source_message_id": None}], [], REQ)
check("apply_deletion_cleanup passes user_request to the rewrite", any(REQ in x for x in prompts))

print("\nALL PASSED")
