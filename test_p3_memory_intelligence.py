"""Phase 3 conversational memory intelligence — unit checks (pure modules + mocked flow).

WRITTEN BUT NOT EXECUTED: testing is disabled by user instruction until explicitly
authorized. No database, no model, no network: the DB-touching functions are mocked.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import sys
from unittest import mock

from services import automatic_memory_service as auto
from services.legacy_provenance_classifier import (
    LegacyScalarFact, MemoryProvenanceFacts, ModernLinkFact,
)
from services.memory_classification_service import (
    GOALS, OTHER, PREFERENCES, PROFILE, PROJECTS, RELATIONSHIPS, ROUTINES, SKILLS,
    classify_memory_text, is_temporary_statement,
)
from services.memory_consolidation_service import (
    DETAIL_CHANGE, EXACT_DUPLICATE, EXPLICIT_UPDATE, SAME_DETAILS, TEMPORARY_STATE,
    TIME_DEPENDENT, UNRESOLVED, DETAILS_DIFFER, analyze_relation, compare_memories,
    duplicate_key, find_exact_duplicate, material_details, new_details_preserved,
)
from services.memory_context_service import assemble_memory_context

FAILURES = []
CID = "11111111-1111-1111-1111-111111111111"


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


# ---------------------------------------------------------------- classification
cases = {
    "User prefers concise explanations.": PREFERENCES,
    "User wants to learn Rust next year.": GOALS,
    "User is building a RAG app with Python.": PROJECTS,
    "User has 5 years of experience with PostgreSQL.": SKILLS,
    "User works as a data engineer.": PROFILE,
    "User's manager is called Priya.": RELATIONSHIPS,
    "User goes for a run every morning.": ROUTINES,
    "The sky was cloudy.": OTHER,
}
for text, expected in cases.items():
    check(f"category {expected!r} for {text!r}", classify_memory_text(text) == expected)
check("category is deterministic", all(classify_memory_text(t) == classify_memory_text(t) for t in cases))
check("blank/non-text -> other", classify_memory_text("  ") == OTHER and classify_memory_text(None) == OTHER)
check("temporary statement detected", is_temporary_statement("I'm tired today") and not is_temporary_statement("I live in Pune"))

# ---------------------------------------------------------------- consolidation
check("duplicate_key ignores case/spacing/trailing punctuation only",
      duplicate_key("  I Live  in Jaipur. ") == duplicate_key("i live in jaipur"))
check("duplicate_key keeps internal punctuation differences",
      duplicate_key("Budget: 5,000") != duplicate_key("Budget 5000"))
check("material details: amounts, versions, dates, times, %",
      material_details("Budget $5,000 on 2026-01-05 at 10:30, Python 3.11, 20%")
      >= {"$5000", "2026-01-05", "10:30", "3.11", "20%"})
check("compare: exact duplicate", compare_memories("I use Python.", "i use python") == EXACT_DUPLICATE)
check("compare: same details", compare_memories("Budget is 5000.", "My budget: 5000") == SAME_DETAILS)
check("compare: details differ", compare_memories("Budget is 5000.", "Budget is 6000.") == DETAILS_DIFFER)
check("new details preserved", new_details_preserved("Uses Python 3.11", "User uses Python 3.11 daily"))
check("new details NOT preserved", not new_details_preserved("Uses Python 3.12", "User uses Python 3.11"))
check("exact duplicate finder returns lowest matching id",
      find_exact_duplicate("I use Python.", [(9, "i use python"), (4, "I use Python"), (5, "I use Go")]) == 4)
check("relation: temporary", analyze_relation("User works at X.", "User is working from home today.") == TEMPORARY_STATE)
check("relation: explicit update", analyze_relation("User works at X.", "User no longer works at X.") == EXPLICIT_UPDATE)
check("relation: time dependent", analyze_relation("In 2024 the user lived in Pune.", "In 2026 the user lives in Delhi.") == TIME_DEPENDENT)
check("relation: detail change", analyze_relation("Budget is 5000.", "Budget is 6000.") == DETAIL_CHANGE)
check("relation: unresolved", analyze_relation("User likes tea.", "User likes coffee.") == UNRESOLVED)


# ---------------------------------------------------------------- process_memory guards (mocked)
def run_process(decision, candidates, new_memory):
    with mock.patch.object(auto, "decide_memory_action", return_value=decision) as decide, \
            mock.patch.object(auto, "save_memory", return_value=True) as save, \
            mock.patch.object(auto, "update_memory", return_value=True) as update, \
            mock.patch.object(auto, "confirm_memory", return_value=True) as confirm, \
            contextlib.redirect_stdout(io.StringIO()):
        status = auto.process_memory(CID, new_memory, source_message_ids=[7],
                                     candidate_memories=candidates)
    return status, decide, save, update, confirm


st, decide, save, update, confirm = run_process({"action": "NEW"}, [(3, "I use Python")], "  i use python. ")
check("exact duplicate: no model call, confirmation linked, nothing saved",
      st == "SKIPPED" and decide.call_count == 0 and confirm.call_count == 1 and save.call_count == 0)

st, decide, save, update, confirm = run_process(
    {"action": "DUPLICATE", "memory_id": 3}, [(3, "Budget is 5000")], "Budget is 6000")
check("DUPLICATE with a new amount is kept as a separate memory",
      st == "SAVED" and save.call_count == 1 and confirm.call_count == 0)

st, decide, save, update, confirm = run_process(
    {"action": "DUPLICATE", "memory_id": 3}, [(3, "User likes tea")], "User really likes tea")
check("plain DUPLICATE still confirms and skips", st == "SKIPPED" and confirm.call_count == 1 and save.call_count == 0)

st, decide, save, update, confirm = run_process(
    {"action": "UPDATE", "memory_id": 3, "updated_memory": "User is at home"},
    [(3, "User works at the office")], "User is working from home today")
check("temporary state never overwrites a fact (stored separately)",
      st == "SAVED" and update.call_count == 0 and save.call_count == 1)

st, decide, save, update, confirm = run_process(
    {"action": "UPDATE", "memory_id": 3, "updated_memory": "User's budget changed"},
    [(3, "Budget is 5000")], "My budget is now 6000")
check("UPDATE that drops the new amount is not applied as a replacement",
      st == "SAVED" and update.call_count == 0 and save.call_count == 1)

st, decide, save, update, confirm = run_process(
    {"action": "UPDATE", "memory_id": 3, "updated_memory": "User's budget is 6000"},
    [(3, "Budget is 5000")], "My budget is now 6000")
check("clear UPDATE that keeps the details is applied with the new source",
      st == "UPDATED" and update.call_count == 1
      and update.call_args.kwargs["source_message_ids"] == [7])

# ---------------------------------------------------------------- context assembly (mocked)
def user_link(sid):
    return ModernLinkFact(sid, CID, "origin", "user", True, CID, "user")


def fake_provenance(conversation_id, ids):
    facts = {
        1: MemoryProvenanceFacts(1, CID, (user_link(10),)),
        2: MemoryProvenanceFacts(2, CID, (ModernLinkFact(11, CID, "legacy", "assistant", True, CID, "assistant"),)),
        3: MemoryProvenanceFacts(3, CID, (), LegacyScalarFact(12, True, CID, "user")),
        4: MemoryProvenanceFacts(4, CID, ()),
    }
    return {i: facts[i] for i in ids if i in facts}


def fake_search(conversation_id, query, top_k):
    return [
        {"id": 1, "memory": "User prefers concise explanations.", "similarity": 0.8},
        {"id": 2, "memory": "User uses React (assistant-said).", "similarity": 0.7},
        {"id": 3, "memory": "User is building a RAG app.", "similarity": 0.6},
        {"id": 4, "memory": "Source-less legacy fact.", "similarity": 0.5},
        {"id": 5, "memory": "Quarantined fact.", "similarity": 0.5},
    ]


ctx = assemble_memory_context(CID, "how should you explain?", search_fn=fake_search,
                              provenance_fn=fake_provenance, exclude_memory_ids=[5])
ids = [m["id"] for m in ctx["memories"]]
check("only user-supported memories are used (modern user link, legacy user scalar)", sorted(ids) == [1, 3])
check("assistant-only and source-less memories excluded", ctx["excluded"]["unverified_provenance"] == [2, 4])
check("future quarantine hook excludes ids", ctx["excluded"]["quarantined_or_excluded"] == [5])
check("context text has no internal IDs and is grouped by category",
      "Preferences:" in ctx["text"] and "Projects:" in ctx["text"] and "[" not in ctx["text"]
      and "assistant-said" not in ctx["text"])
check("internal metadata keeps provenance", ctx["memories"][0]["source_message_ids"] in ([10], [12]))
check("empty query -> empty context", assemble_memory_context(CID, " ", search_fn=fake_search,
                                                              provenance_fn=fake_provenance)["text"] == "")

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
