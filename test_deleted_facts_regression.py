"""
Focused live regression: a forgotten technology fact must stay forgotten.

Real Gemini + real DB, driven through main.main() with scripted input.
Note: the long-term SUMMARY is injected directly (a real one needs 16+
messages); everything else goes through the normal app flow.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import re
import sys
from unittest import mock

import main
from services.conversation_service import update_conversation_memory
from services.database import get_connection

TECH = ("python", "postgres", "pgvector", "react", "node.js", "nodejs")

TURNS = [
    "I use Python and PostgreSQL.",                          # 1 tech fact
    "I prefer explanations in simple Hinglish.",             # 2 style fact -> extraction (4 msgs)
    "I enjoy playing cricket on weekends.",                  # 3 hobby fact
    "Explain what an embedding is in one line.",             # 4 filler -> extraction (8 msgs)
]
DELETE_TURN = "Forget my technology preferences."
POST_TURNS = [
    "Which technologies do I use?",                          # recall (must NOT leak)
    "Tell me one short fun fact.",                           # filler
    "Tell me another short fun fact.",                       # filler -> extraction runs
]

buffer = io.StringIO()


def run(inputs):
    it = iter(inputs)

    def fake_input(*_):
        value = next(it)
        print(f"\n>>>>> USER: {value}")
        return value

    with mock.patch("builtins.input", side_effect=fake_input), \
         contextlib.redirect_stdout(buffer):
        main.main()


def db(query, *params):
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def has_tech(text):
    text = (text or "").lower()
    return [t for t in TECH if t in text]


failures = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "|", name, detail)
    if not cond:
        failures.append(name)


# ---- phase 1: build up memories ------------------------------------------
run([""] + TURNS + ["exit"])
conversation_id = str(db(
    "select id from conversations order by created_at desc limit 1")[0][0])


def memories():
    return [r[0] for r in db(
        "select memory from conversation_memories where conversation_id=%s "
        "order by id", conversation_id)]


before = memories()
check("1-2. tech memory extracted", any(has_tech(m) for m in before), str(before))
check("2. Hinglish memory exists", any("hinglish" in m.lower() for m in before))
check("2. cricket memory exists", any("cricket" in m.lower() for m in before))

update_conversation_memory(
    conversation_id,
    "The user uses Python and PostgreSQL (with pgvector) for a RAG project. "
    "The user prefers explanations in simple Hinglish. "
    "The user enjoys playing cricket on weekends.",
    0,
)

# ---- phase 2: delete, recall, more turns ---------------------------------
mark = len(buffer.getvalue())
run([conversation_id, DELETE_TURN] + POST_TURNS + ["exit"])
log = buffer.getvalue()[mark:]

after = memories()
summary = db("select summary from conversations where id=%s", conversation_id)[0][0]

check("3-4. tech memories deleted", not any(has_tech(m) for m in after), str(after))
check("8. Hinglish memory survives", any("hinglish" in m.lower() for m in after))
check("8. cricket memory survives", any("cricket" in m.lower() for m in after))
check("7. summary contains no tech terms", not has_tech(summary), repr(summary))

# answer to the post-deletion recall question
turn = log.split(">>>>> USER: Which technologies do I use?")[1].split(">>>>> USER:")[0]
answer = turn.split("Assistant:")[1] if "Assistant:" in turn else ""
check("5. recall answer does not state deleted tech",
      not has_tech(answer), repr(answer.strip()[:160]))

# extraction ran after the deletion and did not resurrect anything
check("6. extraction ran after deletion", "Running memory extraction" in log)
check("6. no tech memory re-created by extraction (DB)",
      not any(has_tech(m) for m in memories()))
check("7. summary still tech-free after extra turns",
      not has_tech(db("select summary from conversations where id=%s",
                      conversation_id)[0][0]))

print(f"\nconversation: {conversation_id}")
print("memories now:", memories())
print("summary now :", repr(db("select summary from conversations where id=%s",
                               conversation_id)[0][0]))
if "-v" in sys.argv:
    print("\n===== APP LOG =====")
    print(buffer.getvalue())

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
