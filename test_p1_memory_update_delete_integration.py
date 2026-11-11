"""Phase 1 (P1-08): row-level update_memory / delete_memory / get_memory_details.

Replaces the hard-coded-id manual test_memory_update.py coverage. Real scratch
database, embeddings patched with distinct one-hot vectors, no LLM.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import sys
import uuid
from unittest import mock

import numpy as np

import services.memory_storage_service as storage
from services.conversation_service import create_conversation, save_message
from services.database import get_connection

FAILURES = []
FINDINGS = []


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


class OneHot:
    def __init__(self):
        self.index = {}
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        out = []
        for text in texts:
            if text not in self.index:
                self.index[text] = len(self.index) % 384
            vec = np.zeros(384)
            vec[self.index[text]] = 1.0
            out.append(vec)
        return out


EMB = OneHot()
CREATED = []


class Fixture:
    def __init__(self):
        self.conv = create_conversation("p1-update-delete")
        self.other = create_conversation("p1-update-delete-other")
        CREATED.extend([self.conv, self.other])
        self.m1 = save_message(self.conv, "user", "Message one")
        self.a1 = save_message(self.conv, "assistant", "Assistant reply")
        self.m2 = save_message(self.conv, "user", "Message two")
        self.m3 = save_message(self.conv, "user", "Message three")
        self.f1 = save_message(self.other, "user", "Foreign message")

    def seed(self, texts, conv=None):
        conv = conv or self.conv
        source = self.m1 if conv == self.conv else self.f1
        ids = []
        for text in texts:
            assert quiet(storage.save_memory, conv, text, source), text
            with get_connection() as conn:
                ids.append(conn.execute(
                    "SELECT max(id) FROM conversation_memories WHERE conversation_id=%s AND memory=%s",
                    (conv, text)).fetchone()[0])
        return ids


def rows(conv):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, memory, embedding::text, source_message_id "
            "FROM conversation_memories WHERE conversation_id=%s ORDER BY id", (conv,)).fetchall()


def links(conv, memory_id=None):
    with get_connection() as conn:
        if memory_id is None:
            return conn.execute(
                "SELECT memory_id, source_message_id, link_kind FROM memory_sources "
                "WHERE conversation_id=%s ORDER BY memory_id, source_message_id", (conv,)).fetchall()
        return conn.execute(
            "SELECT source_message_id, link_kind FROM memory_sources "
            "WHERE conversation_id=%s AND memory_id=%s ORDER BY source_message_id",
            (conv, memory_id)).fetchall()


def state(fx):
    return (rows(fx.conv), links(fx.conv), rows(fx.other), links(fx.other))


def raises(exc_type, fn, *args, **kwargs):
    try:
        quiet(fn, *args, **kwargs)
    except exc_type as error:
        return error
    except Exception as error:  # different type
        print(f"  unexpected {type(error).__name__}: {error}")
        return None
    return None


def run():
    # ------------------------------ update_memory ------------------------------
    fx = Fixture()
    ids = fx.seed(["Fact A", "Fact B"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    before = rows(fx.conv)
    other_before = state(fx)[2:]
    ok = quiet(storage.update_memory, fx.conv, ids[0], "  Fact A updated  ", fx.m2)
    after = rows(fx.conv)
    check("[u1] update returns True", ok is True)
    check("[u1] same id, count unchanged, text stripped", [r[0] for r in after] == [r[0] for r in before] and after[0][1] == "Fact A updated")
    check("[u1] embedding changed", after[0][2] != before[0][2])
    check("[u1] source_message_id set to new source", after[0][3] == fx.m2)
    check("[u1] sibling row unchanged", after[1] == before[1])
    check("[u1] other conversation unchanged", state(fx)[2:] == other_before)
    check("[u1] update link added, origin retained", links(fx.conv, ids[0]) == [(fx.m1, "origin"), (fx.m2, "update")])

    fx = Fixture()
    ids = fx.seed(["Fact A"])
    link_before = links(fx.conv, ids[0])
    ok = quiet(storage.update_memory, fx.conv, ids[0], "Fact A v2")
    after = rows(fx.conv)
    check("[u2] no source: update True, text changed", ok is True and after[0][1] == "Fact A v2")
    check("[u2] no source: legacy source_message_id kept (COALESCE), no new link",
          after[0][3] == fx.m1 and links(fx.conv, ids[0]) == link_before)

    ok = quiet(storage.update_memory, fx.conv, ids[0], "Fact A v3", None, [fx.m2, fx.m3])
    check("[u3] source_message_ids links both", ok is True and links(fx.conv, ids[0]) ==
          [(fx.m1, "origin"), (fx.m2, "update"), (fx.m3, "update")])
    check("[u3] first of list becomes source_message_id", rows(fx.conv)[0][3] == fx.m2)

    # negatives
    fx = Fixture()
    ids = fx.seed(["Fact A"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    before = state(fx)
    calls = EMB.calls
    for label, text in (("empty", ""), ("whitespace", "   \n\t ")):
        ok = quiet(storage.update_memory, fx.conv, ids[0], text, fx.m2)
        check(f"[u4] {label} text -> False", ok is False)
    check("[u4] embeddings not generated for empty text", EMB.calls == calls)
    check("[u4] rows unchanged", state(fx) == before)
    ok = quiet(storage.update_memory, fx.conv, 2_000_000_000, "x", fx.m2)
    check("[u5] nonexistent id -> False, nothing changed", ok is False and state(fx) == before)
    ok = quiet(storage.update_memory, fx.conv, oid, "Hijacked", fx.m2)
    check("[u6] id of other conversation -> False (hijack blocked)", ok is False)
    check("[u6] other conversation row and links unchanged", state(fx) == before)

    # failures
    for label, src in (("assistant message", fx.a1), ("foreign-conversation message", fx.f1),
                       ("unknown message id", 2_000_000_000)):
        err = raises(ValueError, storage.update_memory, fx.conv, ids[0], "Changed", src)
        check(f"[u7] {label} source -> ValueError", err is not None)
        check(f"[u7] {label} source: nothing written", state(fx) == before)
    err = raises(ValueError, storage.update_memory, fx.conv, ids[0], "Changed", fx.m2, [fx.a1])
    check("[u7] one bad id in source_message_ids -> ValueError, nothing written", err is not None and state(fx) == before)

    with mock.patch.object(storage, "generate_embeddings", side_effect=RuntimeError("embed down")):
        err = raises(RuntimeError, storage.update_memory, fx.conv, ids[0], "Changed", fx.m2)
    check("[u8] generate_embeddings failure propagates, row unchanged", err is not None and state(fx) == before)

    # ambiguous pins
    ok = quiet(storage.update_memory, fx.conv, ids[0], "Fact A", fx.m2)
    check("[u9] no-op update (same text) -> True (pin)", ok is True)
    try:
        ok = quiet(storage.update_memory, fx.conv, str(ids[0]), "Fact A str-id", fx.m2)
        print(f"INFO | update_memory with numeric-string memory_id returned {ok}")
    except Exception as error:
        print(f"INFO | update_memory with numeric-string memory_id raised {type(error).__name__}")

    # ------------------------------ delete_memory ------------------------------
    fx = Fixture()
    ids = fx.seed(["Fact A", "Fact B"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    sibling = [r for r in rows(fx.conv) if r[0] == ids[1]]
    other_before = state(fx)[2:]
    ok = quiet(storage.delete_memory, fx.conv, ids[0])
    check("[d1] own row deleted -> True", ok is True and ids[0] not in [r[0] for r in rows(fx.conv)])
    check("[d1] sibling and other conversation intact", rows(fx.conv) == sibling and state(fx)[2:] == other_before)
    check("[d1] second delete of same id -> False", quiet(storage.delete_memory, fx.conv, ids[0]) is False)
    with get_connection() as conn:
        orphans = conn.execute("SELECT count(*) FROM memory_sources WHERE memory_id=%s", (ids[0],)).fetchone()[0]
    print(f"INFO | memory_sources rows left after delete: {orphans}")
    if orphans:
        finding("delete_memory leaves orphan memory_sources", f"{orphans} link row(s) remain for deleted memory {ids[0]}")

    before = state(fx)
    check("[d2] nonexistent id -> False", quiet(storage.delete_memory, fx.conv, 2_000_000_000) is False)
    check("[d3] other-conversation id -> False, row intact (ownership)",
          quiet(storage.delete_memory, fx.conv, oid) is False and state(fx) == before)
    # D7: invalid ids are refused before SQL (full matrix in test_p1_d7_storage_id_validation.py)
    try:
        res = quiet(storage.delete_memory, fx.conv, "abc")
    except Exception as error:  # noqa: BLE001
        res = error
    check("[d4] non-int id 'abc' -> False, no exception (no raw DB error)", res is False)
    check("[d4] state unchanged after non-int id attempt", state(fx) == before)

    # ------------------------------ get_memory_details ------------------------------
    fx = Fixture()
    ids = fx.seed(["Fact A", "Fact B"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    det = storage.get_memory_details(fx.conv, [ids[0], oid])
    check("[g1] own id returned, foreign id absent", set(det) == {ids[0]})
    check("[g1] details shape", det[ids[0]]["memory"] == "Fact A" and det[ids[0]]["source_message_ids"] == [fx.m1]
          and det[ids[0]]["source_message_id"] == fx.m1)
    check("[g2] empty id list -> {}", storage.get_memory_details(fx.conv, []) == {})
    with get_connection() as conn:
        conn.execute("DELETE FROM memory_sources WHERE memory_id=%s", (ids[1],))
    det = storage.get_memory_details(fx.conv, [ids[1]])
    check("[g3] legacy source_message_id fallback used when no link rows", det[ids[1]]["source_message_ids"] == [fx.m1])


try:
    with mock.patch.object(storage, "generate_embeddings", side_effect=EMB):
        run()
finally:
    with get_connection() as conn:
        for cid in CREATED:
            conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(cid),))

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
