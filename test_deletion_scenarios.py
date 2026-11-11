"""
Live deletion scenarios (real Gemini + real DB, no main.py loop).

Each scenario builds a fresh conversation:
  * 7 memories (each linked to its source user message)
  * 28 messages (assistant replies sometimes echo the fact)
  * an injected long-term summary containing every fact
and then runs the same sequence main.py runs for a deletion turn:
  delete_matching_memories -> save turn -> apply_deletion_cleanup.

Usage: python test_deletion_scenarios.py
"""
import contextlib
import io
import sys
from unittest import mock

import services.automatic_memory_service as ams
import services.memory_cleanup_service as mcs
import services.memory_service as ms
from services.conversation_service import (
    create_conversation, save_message, update_conversation_memory,
    get_conversation_summary,
)
from services.database import get_connection
from services.memory_storage_service import save_memory

# ------------------------------------------------------------------ fixture

FACTS = {   # key: (user message, assistant reply, memory text)
    "py": ("I use Python for my RAG project.",
           "Got it, Python for your RAG project.",
           "The user uses Python for their RAG project."),
    "pg": ("My project database is PostgreSQL.",
           "Noted, PostgreSQL is your database.",
           "The user uses PostgreSQL as the database for their project."),
    "react": ("I have experience with React and Node.js.",
              "Great, React and Node.js experience noted.",
              "The user has experience with React and Node.js."),
    "project": ("My project helps students check their exam results.",
                "Nice, a tool for exam results.",
                "The user's project helps students check exam results."),
    "hinglish": ("I prefer explanations in simple Hinglish.",
                 "Theek hai, main aasan Hinglish mein samjhaunga.",
                 "The user prefers explanations in simple Hinglish."),
    "cricket": ("I enjoy playing cricket on weekends.",
                "Cricket on weekends sounds fun.",
                "The user enjoys playing cricket on weekends."),
    "deadline": ("My project deadline is 15 December.",
                 "Noted, the deadline is 15 December.",
                 "The user's project deadline is 15 December."),
}

FILLERS = [
    ("What is a good breakfast?", "Poha, upma or eggs are popular choices."),
    ("How many players are in a cricket team?", "Eleven players per side."),
    ("Give me a tip for exam preparation.", "Revise in short sessions with breaks."),
    ("What is the capital of India?", "New Delhi."),
    ("How do I stay focused while studying?", "Remove distractions and use a timer."),
    ("Suggest a weekend activity.", "A walk in a park or a short trip."),
    ("What is photosynthesis?", "Plants turn light, water and CO2 into sugar."),
    ("How long is a marathon?", "About 42.2 kilometres."),
]

SUMMARY = (
    "The user uses Python and PostgreSQL for a project that helps students "
    "check exam results; the deadline is 15 December. The user has "
    "experience with React and Node.js. The user prefers explanations in "
    "simple Hinglish. The user enjoys playing cricket on weekends."
)

TECH_ALL = ("python", "postgres", "react", "node", "pgvector")


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def build_fixture():
    cid = create_conversation("T-scenario")
    ids = {}
    for key, (user, assistant, memory) in FACTS.items():
        user_id = save_message(cid, "user", user)
        save_message(cid, "assistant", assistant)
        quiet(save_memory, cid, memory, user_id)
        ids[key] = user_id
    for user, assistant in FILLERS:
        save_message(cid, "user", user)
        save_message(cid, "assistant", assistant)
    update_conversation_memory(cid, SUMMARY, 0)
    return cid, ids


def memory_keys(cid):
    texts = {m: k for k, (_, _, m) in FACTS.items()}
    with get_connection() as conn:
        rows = conn.execute(
            "select memory from conversation_memories where conversation_id=%s",
            (cid,)).fetchall()
    return {texts.get(r[0], f"?{r[0][:30]}") for r in rows}


def run_deletion(cid, request):
    """Mirror main.py's deletion turn."""
    result = quiet(ams.delete_matching_memories, cid, request)
    cleanup = None
    if result.get("deleted_count", 0) > 0:
        u = save_message(cid, "user", request)
        a = save_message(cid, "assistant", f"Deleted {result['deleted_count']} matching memory/memories.")
        cleanup = quiet(
            mcs.apply_deletion_cleanup, cid, result.get("deleted_memories", []),
            [u, a], request)
    return result, cleanup


def terms_in(text, terms):
    text = (text or "").lower()
    return [t for t in terms if t in text]


# ------------------------------------------------------------------ runner

rows = []
failures = 0


def record(name, request, expect_deleted, expect_kept, forbid, soft_keep_terms):
    global failures
    cid, _ = build_fixture()
    result, cleanup = run_deletion(cid, request)
    left = memory_keys(cid)
    deleted = set(FACTS) - left
    summary = get_conversation_summary(cid)

    ok_delete = deleted == set(expect_deleted)
    ok_kept = set(expect_kept) <= left
    leak = terms_in(summary, forbid)
    kept_in_summary = [t for t in soft_keep_terms if t in summary.lower()]
    status = cleanup["summary_status"] if cleanup else "NO_CLEANUP"
    ok = ok_delete and ok_kept and not leak
    failures += not ok

    print(f"\n[{'PASS' if ok else 'FAIL'}] {name}: {request!r}")
    print(f"   classifier : {result['status']}  deleted={sorted(deleted)} "
          f"(expected {sorted(expect_deleted)})")
    print(f"   kept ok    : {ok_kept}   leak in summary: {leak or 'none'}")
    print(f"   summary    : status={status}  unrelated kept in summary={kept_in_summary}")
    print(f"   text       : {summary[:200]!r}")
    rows.append((name, request, result["status"], sorted(deleted), status, leak, ok))
    return cid


ALL_UNRELATED = ["hinglish", "cricket", "project", "deadline"]
SOFT = ["cricket", "hinglish", "december", "exam"]

print("=" * 70, "\nSCENARIOS 1-4 (+ repeats of 2 to study summary_status)\n", "=" * 70, sep="")

record("S1", "Forget everything about my technologies.",
       {"py", "pg", "react"}, ALL_UNRELATED, TECH_ALL, SOFT)

for i in (1, 2, 3):
    record(f"S2.{i}", "Forget my technology preferences.",
           {"py", "pg", "react"}, ALL_UNRELATED, TECH_ALL, SOFT)

record("S3", "Forget Python and PostgreSQL.",
       {"py", "pg"}, {"react"} | set(ALL_UNRELATED), ("python", "postgres"), SOFT)

record("S4", "Forget that I use Python.",
       {"py"}, {"pg", "react"} | set(ALL_UNRELATED), ("python",),
       ["postgres", "cricket", "hinglish", "december"])

# ------------------------------------------------------------------ S5: verifier failure -> RESET -> rebuild

print("\n" + "=" * 70, "\nS5 verifier failure -> summary RESET -> rebuild\n", "=" * 70, sep="")

real_generate = mcs.generate_answer


def broken_verifier(mode):
    def fn(prompt):
        if "SUMMARY TO CHECK" in prompt:
            if mode == "malformed":
                return "Sorry, I think maybe? {not json"
            raise RuntimeError("503 simulated verifier outage")
        return real_generate(prompt)
    return fn


for mode in ("malformed", "api-failure"):
    cid, _ = build_fixture()
    req = "Forget my technology preferences."
    with mock.patch.object(mcs, "generate_answer", side_effect=broken_verifier(mode)):
        result, cleanup = run_deletion(cid, req)

    after_reset = get_conversation_summary(cid)
    with get_connection() as conn:
        ckpt = conn.execute("select summary_up_to_message_id from conversations where id=%s", (cid,)).fetchone()[0]

    ok_reset = cleanup and cleanup["summary_status"] == "RESET" and after_reset == "" and ckpt == 0

    quiet(ms.update_long_term_memory, cid, 6)      # normal per-turn summarization = rebuild
    rebuilt = get_conversation_summary(cid)
    leak = terms_in(rebuilt, TECH_ALL)
    kept = [t for t in ("cricket", "hinglish", "december", "exam") if t in rebuilt.lower()]
    ok = bool(ok_reset) and bool(rebuilt.strip()) and not leak
    failures += not ok

    print(f"\n[{'PASS' if ok else 'FAIL'}] S5 verifier={mode}")
    print(f"   cleanup status={cleanup['summary_status'] if cleanup else None}  "
          f"summary after reset={after_reset!r}  checkpoint={ckpt}")
    print(f"   rebuilt summary non-empty={bool(rebuilt.strip())}  tech leak={leak or 'none'}  "
          f"unrelated kept={kept}")
    print(f"   rebuilt text: {rebuilt[:260]!r}")
    rows.append((f"S5-{mode}", req, result["status"], [], cleanup["summary_status"] if cleanup else None, leak, ok))

# ------------------------------------------------------------------ U: UPDATE keeps the OLD source message

print("\n" + "=" * 70, "\nU update-memory attribution\n", "=" * 70, sep="")

cid = create_conversation("T-update-attr")
a_id = save_message(cid, "user", "I use Python for my RAG project.")
save_message(cid, "assistant", "Got it.")
quiet(save_memory, cid, "The user uses Python for their RAG project.", a_id)
mem_id = ams.get_all_conversation_memories(cid)[0][0]

b_id = save_message(cid, "user", "I also use Redis and Docker for the same project.")
save_message(cid, "assistant", "Noted, Redis and Docker too.")

update = {"action": "UPDATE", "memory_id": mem_id,
          "updated_memory": "The user uses Python, Redis and Docker for their RAG project."}
with mock.patch.object(ams, "decide_memory_action", return_value=update):
    status = quiet(ams.process_memory, cid, "User also uses Redis and Docker.",
                   source_message_id=b_id)

with get_connection() as conn:
    src_after = conn.execute("select source_message_id, memory from conversation_memories where id=%s", (mem_id,)).fetchone()
    links = [r[0] for r in conn.execute("select source_message_id from memory_sources where memory_id=%s order by 1", (mem_id,)).fetchall()]
print(f"process_memory UPDATE -> {status}; legacy source_message_id = {src_after[0]}; "
      f"memory_sources links = {links} (A={a_id}, B={b_id})")
u_ok = (links == [a_id, b_id])
print(f"   [{'PASS' if u_ok else 'FAIL'}] both contributing messages A and B are linked")

# delete that memory with the LLM echo scan DISABLED: B must still be excluded
with mock.patch.object(mcs, "find_echo_message_ids", return_value=[]):
    result, cleanup = run_deletion(cid, "Forget my technology preferences.")
with get_connection() as conn:
    excl = {r[0] for r in conn.execute("select id from messages where conversation_id=%s and context_excluded", (cid,)).fetchall()}
print(f"   deletion classifier={result['status']}  excluded message ids={sorted(excl)}")
b_excluded = b_id in excl and a_id in excl
u_ok = u_ok and b_excluded
print(f"   [{'PASS' if b_excluded else 'FAIL'}] A and B excluded deterministically (echo scan off)")

# can extraction resurrect it from message B?
live = [m for m in
        ({"id": r[0], "role": r[1], "content": r[2]} for r in get_connection().execute(
            "select id, role, content from messages where conversation_id=%s and not context_excluded order by id", (cid,)).fetchall())]
resurrected = quiet(ms.extract_and_save_memories, cid, live)
after_keys = [r[0] for r in get_connection().execute(
    "select memory from conversation_memories where conversation_id=%s", (cid,)).fetchall()]
print(f"   extraction over live messages re-created: {after_keys}")
u_ok = u_ok and not after_keys
print(f"   [{'PASS' if not after_keys else 'FAIL'}] nothing resurrected by extraction")
failures += not u_ok
rows.append(("U-update-attr", "Forget my technology preferences.", result["status"], [], "n/a", [], u_ok))

# ------------------------------------------------------------------ summary table

print("\n" + "=" * 70, "\nSUMMARY\n", "=" * 70, sep="")
for name, request, cls, deleted, status, leak, ok in rows:
    print(f"{'PASS' if ok else 'FAIL'} | {name:12} | {cls:9} | deleted={deleted} | summary={status} | leak={leak or '-'}")
print(f"\n{failures} scenario failure(s)")
sys.exit(1 if failures else 0)
