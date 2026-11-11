"""Isolated PostgreSQL regressions for deterministic memory attribution."""
import contextlib
import io
import uuid
from unittest import mock

import numpy as np
from pgvector import Vector

import services.automatic_memory_service as automatic
import services.memory_cleanup_service as cleanup
import services.memory_storage_service as storage
from services.conversation_service import (
    create_conversation,
    save_message,
    get_conversation_history,
)
from services.database import get_connection


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def check(label, value):
    assert value, label
    print("PASS |", label)


def main():
    conversation_id = create_conversation("isolated-memory-sources-regression")
    other_conversation_id = create_conversation("isolated-memory-sources-other")
    try:
        a = save_message(conversation_id, "user", "Fact A")
        ar = save_message(conversation_id, "assistant", "Reply A")
        b = save_message(conversation_id, "user", "Fact B")
        br = save_message(conversation_id, "assistant", "Reply B")
        c = save_message(conversation_id, "user", "Fact C")
        cr = save_message(conversation_id, "assistant", "Reply C")
        foreign = save_message(other_conversation_id, "user", "foreign")

        with mock.patch.object(storage, "generate_embeddings", return_value=[np.zeros(384)]):
            check("create accepts owned source", storage.save_memory(conversation_id, "Memory A", a))
            memory_id = automatic.get_all_conversation_memories(conversation_id)[0][0]

            decisions = [
                {"action": "UPDATE", "memory_id": memory_id, "updated_memory": "Memory B"},
                {"action": "UPDATE", "memory_id": memory_id, "updated_memory": "Memory C"},
            ]
            with mock.patch.object(automatic, "decide_memory_action", side_effect=decisions):
                check("A to B update attributed", automatic.process_memory(conversation_id, "Memory B", b) == "UPDATED")
                check("B to C update attributed", automatic.process_memory(conversation_id, "Memory C", c) == "UPDATED")

            # Repeating a source is idempotent.
            check("duplicate source link is idempotent", storage.update_memory(conversation_id, memory_id, "Memory C", c))

            # Legacy row: its compatibility column remains sufficient even
            # if it has not yet been copied into the normalized relation.
            legacy_text = "Legacy-only attributed memory"
            check("legacy fixture created", storage.save_memory(conversation_id, legacy_text, b))
            legacy_id = max(
                memory_id
                for memory_id, text in automatic.get_all_conversation_memories(conversation_id)
                if text == legacy_text
            )
            # Simulate a pre-migration row with only the legacy FK populated.
            with get_connection() as conn:
                conn.execute("DELETE FROM memory_sources WHERE memory_id=%s", (legacy_id,))

            with mock.patch.object(storage, "generate_embeddings", return_value=[np.zeros(384)]):
                try:
                    storage.save_memory(conversation_id, "must reject", foreign)
                    raise AssertionError("cross-conversation source accepted")
                except ValueError:
                    check("cross-conversation source rejected", True)
                try:
                    storage.save_memory(conversation_id, "must reject assistant", ar)
                    raise AssertionError("assistant source accepted")
                except ValueError:
                    check("assistant source rejected", True)

            details = storage.get_memory_details(conversation_id, [memory_id, legacy_id])
            check("all A/B/C sources retained", details[memory_id]["source_message_ids"] == [a, b, c])
            check("legacy source fallback returned", details[legacy_id]["source_message_ids"] == [b])
            with get_connection() as conn:
                n = conn.execute(
                    "SELECT count(*) FROM memory_sources WHERE memory_id=%s",
                    (memory_id,),
                ).fetchone()[0]
            check("duplicate links not stored", n == 3)

            # Deleting the updated memory must exclude every user source
            # and its paired assistant turn. Echo scanning is made fatal.
            deleted = details[memory_id]
            check("memory deletion succeeds", storage.delete_memory(conversation_id, memory_id))
            with mock.patch.object(cleanup, "find_echo_message_ids", side_effect=AssertionError("echo scan invoked")):
                result = quiet(cleanup.apply_deletion_cleanup, conversation_id, [deleted], [])
            hidden = {a, ar, b, br, c, cr}
            visible = {
                message["content"]
                for message in get_conversation_history(conversation_id, limit=100)
            }
            check("sources and paired replies excluded", result["messages_excluded"] == 6 and not ({"Fact A", "Reply A", "Fact B", "Reply B", "Fact C", "Reply C"} & visible))
            check("echo scan failure cannot block deterministic cleanup", result["echo_messages_excluded"] == 0)

            # DB-level composite FK also rejects ownership mismatch.
            try:
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO memory_sources (conversation_id,memory_id,source_message_id) VALUES (%s,%s,%s)",
                        (conversation_id, legacy_id, foreign),
                    )
                raise AssertionError("database accepted cross-conversation link")
            except Exception as exc:
                if isinstance(exc, AssertionError):
                    raise
                check("database rejects cross-conversation link", True)

        print("\nALL MEMORY SOURCE REGRESSIONS PASSED")
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(conversation_id),))
            conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(other_conversation_id),))


def _links(conversation_id, memory_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_message_id FROM memory_sources "
            "WHERE conversation_id=%s AND memory_id=%s ORDER BY source_message_id",
            (conversation_id, memory_id),
        ).fetchall()
    return [r[0] for r in rows]


def _legacy_column(memory_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT source_message_id FROM conversation_memories WHERE id=%s",
            (memory_id,),
        ).fetchone()[0]


def _excluded(conversation_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM messages WHERE conversation_id=%s AND context_excluded",
            (conversation_id,),
        ).fetchall()
    return {r[0] for r in rows}


def _delete_via_app_flow(conversation_id, memory_ids, echo=None):
    """Run delete_matching_memories + apply_deletion_cleanup like main.py,
    with the LLM classifier mocked so the test is deterministic."""
    verdict = {"status": "DELETE", "memory_ids": list(memory_ids)}
    echo_patch = (
        mock.patch.object(cleanup, "find_echo_message_ids", **echo)
        if echo is not None
        else mock.patch.object(cleanup, "find_echo_message_ids", return_value=[])
    )
    with mock.patch.object(automatic, "decide_memories_to_delete", return_value=verdict):
        result = quiet(automatic.delete_matching_memories, conversation_id, "forget it")
    with echo_patch:
        cleaned = quiet(
            cleanup.apply_deletion_cleanup,
            conversation_id,
            result["deleted_memories"],
            [],
        )
    return result, cleaned


def phase1_required_cases():
    """Phase 1 checklist, one isolated fixture per concern."""
    cid = create_conversation("phase1-fixture")
    other = create_conversation("phase1-other")
    created = [cid, other]
    zeros = mock.patch.object(storage, "generate_embeddings", return_value=[np.zeros(384)])

    try:
        a = save_message(cid, "user", "Fact A")
        ar = save_message(cid, "assistant", "Reply A")
        b = save_message(cid, "user", "Fact B")
        br = save_message(cid, "assistant", "Reply B")
        c = save_message(cid, "user", "Fact C")
        cr = save_message(cid, "assistant", "Reply C")
        u = save_message(cid, "user", "Unrelated U")
        ur = save_message(cid, "assistant", "Unrelated reply")
        foreign = save_message(other, "user", "foreign message")

        with zeros:
            # 1. create from A
            check("[1] memory created from message A", storage.save_memory(cid, "Memory A", a))
            mid = automatic.get_all_conversation_memories(cid)[0][0]
            check("[1] A linked", _links(cid, mid) == [a])

            # 2. update from B -> A and B linked
            with mock.patch.object(automatic, "decide_memory_action",
                                   return_value={"action": "UPDATE", "memory_id": mid, "updated_memory": "Memory B"}):
                check("[2] update from B", automatic.process_memory(cid, "x", b) == "UPDATED")
            check("[2] A and B linked", _links(cid, mid) == [a, b])
            check("[2] legacy column follows latest source", _legacy_column(mid) == b)

            # 3. update from C -> A, B and C linked
            with mock.patch.object(automatic, "decide_memory_action",
                                   return_value={"action": "UPDATE", "memory_id": mid, "updated_memory": "Memory C"}):
                check("[3] update from C", automatic.process_memory(cid, "x", c) == "UPDATED")
            check("[3] A, B and C linked", _links(cid, mid) == [a, b, c])

            # 6. idempotent links
            check("[6] repeat update with same source", storage.update_memory(cid, mid, "Memory C", c))
            check("[6] repeat update with older source", storage.update_memory(cid, mid, "Memory C", a))
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    storage._link_memory_source(cursor, cid, mid, b)
                    storage._link_memory_source(cursor, cid, mid, b)
                conn.commit()
            check("[6] still exactly one link per source", _links(cid, mid) == [a, b, c])

            # 7. cross-conversation rejection (app level, DB level, wrong-owner memory)
            for label, call in (
                ("save_memory", lambda: storage.save_memory(cid, "bad", foreign)),
                ("update_memory", lambda: storage.update_memory(cid, mid, "bad", foreign)),
            ):
                try:
                    call()
                    check(f"[7] {label} rejects foreign source", False)
                except ValueError:
                    check(f"[7] {label} rejects foreign source", True)
            check("[7] update through the wrong conversation changes nothing",
                  storage.update_memory(other, mid, "hijack") is False
                  and _links(cid, mid) == [a, b, c])
            try:
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO memory_sources (conversation_id, memory_id, source_message_id) "
                        "VALUES (%s,%s,%s)", (cid, mid, foreign))
                check("[7] database rejects foreign link", False)
            except Exception as exc:
                check("[7] database rejects foreign link", not isinstance(exc, AssertionError))

            # 4. delete through the real app flow -> everything hidden
            details = storage.get_memory_details(cid, [mid])[mid]
            check("[4] details list every source", details["source_message_ids"] == [a, b, c])
            result, cleaned = _delete_via_app_flow(cid, [mid])
            check("[4] memory deleted", result["deleted_count"] == 1 and not automatic.get_all_conversation_memories(cid))
            check("[4] all user sources and paired replies excluded",
                  _excluded(cid) == {a, ar, b, br, c, cr})
            check("[4] unrelated messages stay visible", u not in _excluded(cid) and ur not in _excluded(cid))
            check("[4] memory_sources rows cascaded away", _links(cid, mid) == [])

        # 5. echo-scan failure must not affect deterministic exclusion
        c5 = create_conversation("phase1-echo-failure"); created.append(c5)
        m1 = save_message(c5, "user", "Echo fact 1"); r1 = save_message(c5, "assistant", "Echo reply 1")
        m2 = save_message(c5, "user", "Echo fact 2"); r2 = save_message(c5, "assistant", "Echo reply 2")
        keep = save_message(c5, "user", "Keep me")
        with zeros:
            storage.save_memory(c5, "Echo memory", m1)
            mid5 = automatic.get_all_conversation_memories(c5)[0][0]
            with mock.patch.object(automatic, "decide_memory_action",
                                   return_value={"action": "UPDATE", "memory_id": mid5, "updated_memory": "Echo memory 2"}):
                automatic.process_memory(c5, "x", m2)
        result, cleaned = _delete_via_app_flow(c5, [mid5], echo={"side_effect": RuntimeError("503 echo scan down")})
        check("[5] echo scan raised, cleanup still completed", result["deleted_count"] == 1)
        check("[5] deterministic exclusion unaffected", _excluded(c5) == {m1, r1, m2, r2})
        check("[5] echo contribution is zero on failure", cleaned["echo_messages_excluded"] == 0)

        c5b = create_conversation("phase1-echo-extra"); created.append(c5b)
        s = save_message(c5b, "user", "Source"); sr = save_message(c5b, "assistant", "Source reply")
        extra = save_message(c5b, "assistant", "Mentions the forgotten fact")
        with zeros:
            storage.save_memory(c5b, "Echo extra memory", s)
        mid5b = automatic.get_all_conversation_memories(c5b)[0][0]
        _, cleaned = _delete_via_app_flow(c5b, [mid5b], echo={"return_value": [extra, foreign]})
        check("[5] echo scan success only adds extras (conversation-scoped)",
              _excluded(c5b) == {s, sr, extra} and foreign not in _excluded(other))

        # 8. legacy memories (no memory_sources rows) still delete correctly
        c8 = create_conversation("phase1-legacy"); created.append(c8)
        lu = save_message(c8, "user", "Legacy fact"); lr = save_message(c8, "assistant", "Legacy reply")
        keep8 = save_message(c8, "user", "Legacy unrelated")
        nu = save_message(c8, "user", "No-source fact")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO conversation_memories (conversation_id, memory, embedding, source_message_id) "
                "VALUES (%s, 'Legacy memory', %s, %s)", (c8, Vector([0.0] * 384), lu))
            conn.execute(
                "INSERT INTO conversation_memories (conversation_id, memory, embedding, source_message_id) "
                "VALUES (%s, 'Legacy memory without any source', %s, NULL)", (c8, Vector([0.0] * 384)))
        ids8 = {text: mid for mid, text in automatic.get_all_conversation_memories(c8)}
        legacy_id, nosrc_id = ids8["Legacy memory"], ids8["Legacy memory without any source"]
        check("[8] legacy row has no memory_sources link", _links(c8, legacy_id) == [])
        check("[8] details fall back to legacy column",
              storage.get_memory_details(c8, [legacy_id])[legacy_id]["source_message_ids"] == [lu])
        result, cleaned = _delete_via_app_flow(c8, [legacy_id, nosrc_id])
        check("[8] both legacy memories deleted", result["deleted_count"] == 2)
        check("[8] legacy source and its paired reply excluded", _excluded(c8) == {lu, lr})
        check("[8] unrelated messages untouched", keep8 not in _excluded(c8) and nu not in _excluded(c8))

        print("\nALL PHASE 1 CASES PASSED")
    finally:
        with get_connection() as conn:
            for conversation in created:
                conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(conversation),))


if __name__ == "__main__":
    main()
    phase1_required_cases()
