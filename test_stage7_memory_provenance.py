"""Batch 2 / Stage 7: deterministic memory provenance and deletion integrity.

Scratch database only (testsafe; run via run_tests.py). Fixtures are created
in fresh conversations and removed in `finally`. Embeddings are fake one-hot
vectors (no model load); the LLM is mocked only where extraction or the
delete classifier would call it. No real user data is read or written.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import sys
import uuid
from unittest import mock

import numpy as np
from pgvector import Vector

import main as app_main
import services.automatic_memory_service as automatic
import services.memory_cleanup_service as cleanup
import services.memory_provenance_service as prov
import services.memory_service as memsvc
import services.memory_storage_service as storage
from services.conversation_service import create_conversation, save_message
from services.database import get_connection
from services.legacy_provenance_classifier import MISSING_SOURCE, USER_SUPPORTED, INCONSISTENT_SOURCE, classify_memory
from services.memory_context_service import assemble_memory_context, load_provenance_facts

FAILURES, CREATED = [], []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def one_hot(texts):
    return [np.eye(384)[sum(map(ord, t)) % 384] for t in texts]


def q(sql, params=()):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def raises(fn, *args, **kwargs):
    try:
        quiet(fn, *args, **kwargs)
        return False
    except ValueError:
        return True


def conversation(title):
    cid = create_conversation(title)
    CREATED.append(cid)
    return cid


def links(mid):
    return q("SELECT source_message_id, link_kind FROM memory_sources WHERE memory_id=%s ORDER BY 1", (mid,))


def memory(cid, text, sources):
    quiet(storage.save_memory, cid, text, source_message_ids=sources)
    return q("SELECT id FROM conversation_memories WHERE conversation_id=%s AND memory=%s", (cid, text))[0][0]


def raw_memory(cid, text, scalar=None):
    """A legacy-shaped memory written directly (no memory_sources row)."""
    with get_connection() as conn:
        return conn.execute(
            "INSERT INTO conversation_memories (conversation_id, memory, embedding, source_message_id) "
            "VALUES (%s,%s,%s,%s) RETURNING id", (cid, text, Vector(np.ones(384).tolist()), scalar)).fetchone()[0]


def category(cid, mid):
    return classify_memory(load_provenance_facts(cid, [mid])[mid]).category


def in_context(cid, mid, text):
    found = [{"id": mid, "memory": text, "similarity": 0.9}]
    out = assemble_memory_context(cid, "anything", search_fn=lambda **_: found)
    return text in out["text"], mid in out["excluded"]["unverified_provenance"]


def test_creation(cid, other, u1, u2, a1, x1):
    m = memory(cid, "User drinks green tea.", [u1, u2, u1, float(u2)])
    check("create: multiple sources, duplicates collapsed, all 'origin'", links(m) == [(u1, "origin"), (u2, "origin")])
    before = q("SELECT count(*) FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0]
    for label, bad in (("assistant role", [a1]), ("other conversation", [x1]), ("unknown id", [10 ** 12]),
                       ("bool", [True]), ("fractional float", [2.5]), ("zero", [0]), ("none", [None]), ("empty", [])):
        check(f"create: {label} source rejected", raises(storage.save_memory, cid, f"Rejected fact {label}.",
                                                         source_message_ids=bad))
    check("create: rejected saves wrote nothing",
          q("SELECT count(*) FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0] == before)
    return m


def test_updates(cid, m, u1, u2, u3, a1, x1):
    text = lambda: q("SELECT memory FROM conversation_memories WHERE id=%s", (m,))[0][0]
    quiet(storage.update_memory, cid, m, "User drinks green tea daily.", source_message_ids=[u3])
    check("update: previous sources kept, new source added as 'update'",
          links(m) == [(u1, "origin"), (u2, "origin"), (u3, "update")])
    quiet(storage.update_memory, cid, m, "User drinks green tea daily.", source_message_ids=[u3, u1])
    check("update: repeating sources creates no duplicate relationship", len(links(m)) == 3)
    snapshot = (text(), links(m))
    check("update: no source -> ValueError (Stage 7)", raises(storage.update_memory, cid, m, "Changed without evidence."))
    check("update: assistant source -> ValueError", raises(storage.update_memory, cid, m, "Changed.", a1))
    check("update: other-conversation source -> ValueError", raises(storage.update_memory, cid, m, "Changed.", x1))
    check("update: refused updates changed neither content nor provenance", (text(), links(m)) == snapshot)
    with mock.patch.object(storage, "_link_memory_sources", side_effect=RuntimeError("link insert failed")):
        try:
            quiet(storage.update_memory, cid, m, "Half-written update.", source_message_ids=[u2])
        except RuntimeError:
            pass
    check("update: failure after the UPDATE rolls back content and provenance together", (text(), links(m)) == snapshot)


def test_message_deletion(cid, other, m, u1, u2, u3, a1, x1):
    shared = memory(cid, "User owns a teapot.", [u2])
    count = lambda: q("SELECT count(*) FROM messages WHERE conversation_id=%s", (cid,))[0][0]
    n = count()
    for label, bad in (("bool True", True), ("float with fraction", u1 + 0.7), ("integral float", float(u1)),
                       ("zero", 0), ("negative", -u1), ("non-numeric string", "abc"), ("None", None), ("list", [u1])):
        res = quiet(prov.delete_message_with_provenance, cid, bad)
        check(f"delete: invalid message id ({label}) refused, nothing deleted",
              res == {"deleted": False, "orphaned": [], "still_supported": []} and count() == n)
    check("delete: message of another conversation is a no-op",
          quiet(prov.delete_message_with_provenance, cid, x1)["deleted"] is False and q("SELECT 1 FROM messages WHERE id=%s", (x1,)))

    res = quiet(prov.delete_message_with_provenance, cid, str(u2))
    check("delete: one of several sources -> memory still supported; shared-source memory orphaned",
          res["deleted"] and res["still_supported"] == [m] and res["orphaned"] == [shared])
    check("delete: both memories kept (policy a); only the deleted source's links removed",
          links(m) == [(u1, "origin"), (u3, "update")] and links(shared) == []
          and q("SELECT count(*) FROM conversation_memories WHERE id = ANY(%s)", ([m, shared],))[0][0] == 2)
    check("delete: repeated deletion is an idempotent no-op",
          quiet(prov.delete_message_with_provenance, cid, u2) == {"deleted": False, "orphaned": [], "still_supported": []})
    pu = save_message(cid, "user", "I like jazz.")
    pa = save_message(cid, "assistant", "Jazz noted.")
    jazz = memory(cid, "User likes jazz.", [pu])
    res = quiet(prov.delete_message_with_provenance, cid, pu)
    check("delete: paired assistant reply of the deleted user message is neither deleted nor excluded",
          res["orphaned"] == [jazz] and q("SELECT context_excluded FROM messages WHERE id=%s", (pa,)) == [(False,)])
    return shared


def test_orphan_and_legacy(cid, other, shared, u1, a1, x1):
    check("orphan: classified MISSING_SOURCE", category(cid, shared) == MISSING_SOURCE)
    shown, excluded = in_context(cid, shared, "User owns a teapot.")
    check("orphan: never included in answer context", not shown and excluded)

    none = raw_memory(cid, "Legacy fact with no provenance.")
    check("legacy: no source rows -> MISSING_SOURCE, excluded from context",
          category(cid, none) == MISSING_SOURCE and in_context(cid, none, "Legacy fact with no provenance.") == (False, True))
    partial = memory(cid, "User prefers short answers.", [u1])
    with get_connection() as conn:
        conn.execute("UPDATE conversation_memories SET source_message_id=%s WHERE id=%s", (a1, partial))
    verdict = classify_memory(load_provenance_facts(cid, [partial])[partial])
    check("legacy: partial (valid user link + assistant scalar) -> USER_SUPPORTED with the issue recorded",
          verdict.category == USER_SUPPORTED and verdict.issues)
    stale = raw_memory(cid, "Legacy fact pointing elsewhere.", scalar=x1)
    check("legacy: stale foreign-conversation reference -> INCONSISTENT_SOURCE, excluded",
          category(cid, stale) == INCONSISTENT_SOURCE and in_context(cid, stale, "Legacy fact pointing elsewhere.") == (False, True))
    twin = save_message(cid, "user", "Legacy fact with no provenance.")
    quiet(prov.delete_message_with_provenance, cid, twin)
    check("legacy: no guessed backfill (identical-text message never linked), nothing deleted",
          links(none) == [] and q("SELECT count(*) FROM conversation_memories WHERE id=%s", (none,))[0][0] == 1)


def test_explicit_delete(cid, other):
    om = memory(other, "Other conversation fact.", [save_message(other, "user", "Other fact.")])
    mine = q("SELECT count(*) FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0]
    bad = {"status": "DELETE", "memory_ids": [True, str(om), om, 10 ** 12]}
    with mock.patch.object(automatic, "decide_memories_to_delete", return_value=bad):
        res = quiet(automatic.delete_matching_memories, cid, "forget it")
    check("explicit delete: invalid / foreign / unknown decision ids delete nothing",
          res["status"] == "NO_MATCH" and q("SELECT count(*) FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0] == mine
          and q("SELECT 1 FROM conversation_memories WHERE id=%s", (om,)))
    u = save_message(cid, "user", "I play chess.")
    reply = save_message(cid, "assistant", "Chess noted.")
    target = memory(cid, "User plays chess.", [u])
    with mock.patch.object(automatic, "decide_memories_to_delete", return_value={"status": "DELETE", "memory_ids": [target]}):
        res = quiet(automatic.delete_matching_memories, cid, "forget chess")
    with mock.patch.object(cleanup, "find_echo_message_ids", return_value=[]), \
            mock.patch.object(cleanup, "rewrite_summary_without", return_value="UNCHANGED"):
        out = quiet(cleanup.apply_deletion_cleanup, cid, res["deleted_memories"])
    excluded = {r[0] for r in q("SELECT id FROM messages WHERE conversation_id=%s AND context_excluded", (cid,))}
    check("explicit delete: provenance-driven cleanup excludes source + paired reply (existing contract)",
          res["deleted_ids"] == [target] and out["provenance_status"] == "KNOWN" and {u, reply} <= excluded)
    check("explicit delete: other conversation untouched", q("SELECT count(*) FROM memory_sources WHERE memory_id=%s", (om,))[0][0] == 1)


def checkpoint_case(extraction_json):
    cid = conversation("s7-checkpoint")
    u = save_message(cid, "user", "I like hiking.")
    a = save_message(cid, "assistant", "Hiking noted.")
    payload = extraction_json.replace("{U}", str(u)).replace("{A}", str(a))
    with mock.patch.object(app_main, "ask_question", return_value={"answer": "ok", "sources": [], "status": "answered"}), \
            mock.patch.object(app_main, "assemble_memory_context", return_value={"text": ""}), \
            mock.patch.object(app_main, "update_long_term_memory"), \
            mock.patch.object(memsvc, "generate_answer", return_value=payload):
        out = quiet(app_main.run_turn, cid, "Tell me something.")
    last = q("SELECT max(id) FROM messages WHERE conversation_id=%s", (cid,))[0][0]
    point = q("SELECT memory_extraction_up_to_message_id FROM conversations WHERE id=%s", (cid,))[0][0]
    return out["memory_extraction"], point, last, u, cid


def test_checkpoints():
    outcome, point, last, u, cid = checkpoint_case('[{"memory":"User likes hiking.","source_message_ids":[{A}]}]')
    check("checkpoint: assistant-sourced extraction rejected, checkpoint not advanced",
          outcome == "rejected_will_retry" and point == 0
          and q("SELECT count(*) FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0] == 0)
    outcome, point, last, u, cid = checkpoint_case('[{"memory":"User likes hiking.","source_message_ids":[{U}]}]')
    mid = q("SELECT id FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0]
    check("checkpoint: valid extraction advances to the last batch message and links the user source",
          outcome == "checkpoint_advanced" and point == last and links(mid) == [(u, "origin")])


def main():
    cid, other = conversation("s7-main"), conversation("s7-other")
    u1 = save_message(cid, "user", "I drink green tea.")
    a1 = save_message(cid, "assistant", "Green tea noted.")
    u2 = save_message(cid, "user", "Every morning, and I own a teapot.")
    u3 = save_message(cid, "user", "Daily, actually.")
    x1 = save_message(other, "user", "Message in another conversation.")
    m = test_creation(cid, other, u1, u2, a1, x1)
    test_updates(cid, m, u1, u2, u3, a1, x1)
    shared = test_message_deletion(cid, other, m, u1, u2, u3, a1, x1)
    test_orphan_and_legacy(cid, other, shared, u1, a1, x1)
    test_explicit_delete(cid, other)
    test_checkpoints()


try:
    with mock.patch.object(storage, "generate_embeddings", side_effect=one_hot):
        main()
finally:
    if CREATED:
        with get_connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ANY(%s::uuid[])", ([uuid.UUID(c) for c in CREATED],))
    left = q("SELECT count(*) FROM conversations WHERE id = ANY(%s::uuid[])", ([uuid.UUID(c) for c in CREATED],))[0][0]
    check("cleanup: no Stage 7 test conversations left", left == 0)

print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
