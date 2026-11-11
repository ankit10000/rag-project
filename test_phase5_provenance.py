"""
Phase 5 provenance tests. Run through run_tests.py (scratch database only);
testsafe refuses any database that is not a rag_*test* scratch DB.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import os
import sys
import uuid
from unittest import mock

import psycopg

import services.automatic_memory_service as automatic
import services.memory_cleanup_service as cleanup
import services.memory_provenance_service as prov
import services.memory_service as memsvc
import services.memory_storage_service as storage
from services.conversation_service import create_conversation, save_message
from services.database import get_connection


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def check(label, value):
    assert value, label
    print("PASS |", label)


def raises(label, exc, fn, *a, **k):
    try:
        quiet(fn, *a, **k)
    except exc:
        print("PASS |", label)
        return
    raise AssertionError(label)


def q(sql, params=()):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def mem_by_text(cid, text):
    rows = q("SELECT id FROM conversation_memories WHERE conversation_id=%s AND memory=%s",
             (cid, text))
    return rows[0][0] if rows else None


def links(mid):
    return q("SELECT source_message_id, link_kind FROM memory_sources "
             "WHERE memory_id=%s ORDER BY source_message_id", (mid,))


def count_mem(cid):
    return q("SELECT count(*) FROM conversation_memories WHERE conversation_id=%s", (cid,))[0][0]


def main():
    c1 = create_conversation("p5-main")
    c2 = create_conversation("p5-other")
    c1, c2 = str(c1), str(c2)
    try:
        u1 = save_message(c1, "user", "I use Postgres for my project.")
        a1 = save_message(c1, "assistant", "Nice, Postgres is great.")
        u2 = save_message(c1, "user", "Also I deploy it on Windows.")
        a2 = save_message(c1, "assistant", "Windows deployment noted.")
        u3 = save_message(c1, "user", "My favourite colour is teal.")
        a3 = save_message(c1, "assistant", "Teal is lovely.")
        x1 = save_message(c2, "user", "Other conversation message.")

        # 1. multi-source creation
        quiet(storage.save_memory, c1, "User runs a Postgres project on Windows.",
              source_message_ids=[u1, u2])
        m1 = mem_by_text(c1, "User runs a Postgres project on Windows.")
        check("multi-source memory linked to both user messages",
              links(m1) == [(u1, "origin"), (u2, "origin")])
        check("legacy column holds primary source",
              q("SELECT source_message_id FROM conversation_memories WHERE id=%s", (m1,))[0][0] == u1)

        # 2. invalid sources: nothing written
        before = count_mem(c1)
        raises("assistant source rejected", ValueError, storage.save_memory, c1,
               "Bad assistant sourced fact about zebras.", source_message_ids=[a1])
        raises("other-conversation source rejected", ValueError, storage.save_memory, c1,
               "Bad cross conversation fact about whales.", source_message_ids=[x1])
        raises("unknown source rejected", ValueError, storage.save_memory, c1,
               "Bad unknown fact about owls.", source_message_ids=[10**9])
        raises("one bad id rejects whole save", ValueError, storage.save_memory, c1,
               "Mixed validity fact about camels.", source_message_ids=[u3, a3])
        check("no memory or link written by rejected saves", count_mem(c1) == before
              and q("SELECT count(*) FROM memory_sources WHERE conversation_id=%s", (c1,))[0][0] == 2)

        # 3. database enforces user-only and blocks message deletion
        with get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO memory_sources (conversation_id, memory_id, source_message_id, source_role)"
                    " VALUES (%s,%s,%s,'assistant')", (c1, m1, a1))
                conn.commit()
                ok = False
            except psycopg.Error:
                ok = True
        check("database rejects assistant link", ok)
        with get_connection() as conn:
            try:
                conn.execute("DELETE FROM messages WHERE id=%s", (u1,))
                conn.commit()
                ok = False
            except psycopg.Error:
                ok = True
        check("direct delete of a linked message is refused", ok)

        # 4. update appends, keeps old links
        quiet(storage.update_memory, c1, m1, "User runs a Postgres project on Windows 11.",
              source_message_ids=[u3])
        check("update appends link and keeps earlier ones",
              links(m1) == [(u1, "origin"), (u2, "origin"), (u3, "update")])

        # 5. semantic duplicate -> confirmation, no new memory
        n = count_mem(c1)
        u4 = save_message(c1, "user", "Yes, Postgres project on Windows 11.")
        saved = quiet(storage.save_memory, c1, "User runs a Postgres project on Windows 11.",
                      source_message_ids=[u4])
        check("semantic duplicate not saved, linked as confirmation",
              saved is False and count_mem(c1) == n and (u4, "confirmation") in links(m1))

        # 6. DUPLICATE decision: valid id confirms, invalid id does not link
        u5 = save_message(c1, "user", "Again: Postgres on Windows.")
        u6 = save_message(c1, "user", "One more restatement.")
        with mock.patch.object(automatic, "decide_memory_action",
                               return_value={"action": "DUPLICATE", "memory_id": m1}):
            r = quiet(automatic.process_memory, c1, "dup text", source_message_id=u5)
        check("DUPLICATE with valid id links confirmation",
              r == "SKIPPED" and (u5, "confirmation") in links(m1))
        with mock.patch.object(automatic, "decide_memory_action",
                               return_value={"action": "DUPLICATE", "memory_id": 987654}):
            quiet(automatic.process_memory, c1, "dup text", source_message_id=u6)
        check("DUPLICATE with invalid id links nothing",
              q("SELECT count(*) FROM memory_sources WHERE source_message_id=%s", (u6,))[0][0] == 0)

        # 7. parser: list / singular / junk ids filtered to user ids of the batch
        parsed = memsvc._parse_json_memories(
            '[{"memory":"A fact","source_message_ids":[%d,%d,999,"x"],"source_message_id":%d}]'
            % (u1, u2, u1), {u1, u2, u3})
        check("parser keeps only valid ids, de-duplicated",
              parsed[0]["source_message_ids"] == [u1, u2] and parsed[0]["source_message_id"] == u1)
        legacy_shape = memsvc._parse_json_memories('[{"memory":"B","source_message_id":%d}]' % u3, {u3})
        check("parser still accepts legacy single id", legacy_shape[0]["source_message_ids"] == [u3])

        # 8. extraction end to end (LLM mocked)
        u7 = save_message(c1, "user", "I own a red bicycle.")
        a7 = save_message(c1, "assistant", "Cool bicycle.")
        u8 = save_message(c1, "user", "The bicycle is made of carbon.")
        msgs = [
            {"id": u7, "role": "user", "content": "I own a red bicycle."},
            {"id": a7, "role": "assistant", "content": "Cool bicycle."},
            {"id": u8, "role": "user", "content": "The bicycle is made of carbon."},
        ]
        fake = '[{"memory":"User owns a red carbon bicycle.","source_message_ids":[%d,%d,%d]}]' % (u7, a7, u8)
        # Both LLM touch points are mocked: extraction output and the
        # NEW/UPDATE/DUPLICATE decision (the conversation already has memories).
        with mock.patch.object(memsvc, "generate_answer", return_value=fake), \
             mock.patch.object(automatic, "decide_memory_action", return_value={"action": "NEW"}):
            quiet(memsvc.extract_and_save_memories, c1, msgs)
        mb = mem_by_text(c1, "User owns a red carbon bicycle.")
        check("extraction stores all contributing user ids, drops assistant id",
              mb is not None and [s for s, _ in links(mb)] == [u7, u8])

        # 9. second memory + deletion via links only
        quiet(storage.save_memory, c1, "User's favourite colour is teal.", source_message_ids=[u3])
        mt = mem_by_text(c1, "User's favourite colour is teal.")
        # u3 is also a source of m1 (shared). Delete mb only.
        details = storage.get_memory_details(c1, [mb])
        check("details expose every source", details[mb]["source_message_ids"] == [u7, u8])
        with mock.patch.object(cleanup, "find_echo_message_ids", return_value=[]), \
             mock.patch.object(cleanup, "rewrite_summary_without", return_value="unchanged"):
            quiet(storage.delete_memory, c1, mb)
            quiet(cleanup.apply_deletion_cleanup, c1, list(details.values()))
        ex = {r[0] for r in q("SELECT id FROM messages WHERE conversation_id=%s AND context_excluded", (c1,))}
        check("cleanup excluded exactly sources + paired assistant reply",
              ex == {u7, a7, u8})
        check("deleting a memory removes its links only",
              links(mb) == [] and mem_by_text(c1, "User's favourite colour is teal.") == mt
              and links(mt) == [(u3, "origin")])
        check("unrelated messages with similar text not excluded",
              u1 not in ex and u3 not in ex)

        # 10. message deletion via provenance function
        res = quiet(prov.delete_message_with_provenance, c1, u3)
        check("message delete reports orphan and still-supported, deletes no memory",
              res["deleted"] and res["orphaned"] == [mt] and res["still_supported"] == [m1]
              and mem_by_text(c1, "User's favourite colour is teal.") == mt)
        check("lookup helpers", [s["message_id"] for s in prov.get_memory_sources(c1, m1)]
              == [u1, u2, u4, u5]
              and [m["memory_id"] for m in prov.get_memories_for_message(c1, u1)] == [m1])
        check("cross-conversation message delete is a no-op",
              quiet(prov.delete_message_with_provenance, c2, u1)["deleted"] is False)

        # 11. conversation delete cascades; other conversation untouched
        quiet(storage.save_memory, c2, "Other conversation fact about trains.", source_message_ids=[x1])
        mo = mem_by_text(c2, "Other conversation fact about trains.")
        with get_connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id=%s", (c1,))
        check("conversation delete leaves no memories/links/messages behind",
              count_mem(c1) == 0
              and q("SELECT count(*) FROM memory_sources WHERE conversation_id=%s", (c1,))[0][0] == 0
              and q("SELECT count(*) FROM messages WHERE conversation_id=%s", (c1,))[0][0] == 0)
        check("other conversation untouched", links(mo) == [(x1, "origin")])
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ANY(%s::uuid[])", ([c1, c2],))
    print("\nALL PHASE 5 TESTS PASSED")


if __name__ == "__main__":
    main()
