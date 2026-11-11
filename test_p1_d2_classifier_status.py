"""D2 regression: delete_matching_memories deletes ONLY on an explicit, valid DELETE status.

Real storage layer on the scratch database; only the classifier response
(decide_memories_to_delete) is mocked. Every blocked case also proves that
delete_memory was never called and that the database is unchanged.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import sys
import uuid
from unittest import mock

import numpy as np

import services.automatic_memory_service as automatic
import services.memory_storage_service as storage
from services.conversation_service import create_conversation, save_message
from services.database import get_connection

FAILURES = []
CREATED = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class OneHot:
    def __init__(self):
        self.index = {}

    def __call__(self, texts):
        out = []
        for text in texts:
            self.index.setdefault(text, len(self.index) % 384)
            vec = np.zeros(384)
            vec[self.index[text]] = 1.0
            out.append(vec)
        return out


def snapshot(conv):
    """Full state of one conversation: memories (with embedding text) and links."""
    with get_connection() as conn:
        memories = conn.execute(
            "SELECT id, memory, embedding::text, source_message_id FROM conversation_memories "
            "WHERE conversation_id=%s ORDER BY id", (conv,)).fetchall()
        links = conn.execute(
            "SELECT memory_id, source_message_id, link_kind FROM memory_sources "
            "WHERE conversation_id=%s ORDER BY memory_id, source_message_id", (conv,)).fetchall()
    return memories, links


class Fixture:
    def __init__(self):
        self.conv = create_conversation("p1-d2")
        self.other = create_conversation("p1-d2-other")
        CREATED.extend([self.conv, self.other])
        self.m1 = save_message(self.conv, "user", "I keep goats")
        self.m2 = save_message(self.conv, "user", "I grow tomatoes")
        self.f1 = save_message(self.other, "user", "Foreign message")
        self.a = self._seed(self.conv, "User keeps goats", self.m1)
        self.b = self._seed(self.conv, "User grows tomatoes", self.m2)
        self.foreign = self._seed(self.other, "Foreign memory", self.f1)

    def _seed(self, conv, text, source):
        assert quiet(storage.save_memory, conv, text, source)
        return max(i for i, t in automatic.get_all_conversation_memories(conv) if t == text)


def classify(fx, response):
    """Run delete_matching_memories with a mocked classifier; return (result, delete_memory spy)."""
    with mock.patch.object(automatic, "decide_memories_to_delete", return_value=response), \
         mock.patch.object(automatic, "delete_memory", wraps=automatic.delete_memory) as dele:
        result = quiet(automatic.delete_matching_memories, fx.conv, "forget my goats")
    return result, dele


def expect_blocked(label, make_response, expected_status):
    """Fresh fixture; the response must delete nothing and leave both conversations byte-identical."""
    fx = Fixture()
    before = (snapshot(fx.conv), snapshot(fx.other))
    result, dele = classify(fx, make_response(fx))
    check(f"[blocked] {label} -> {expected_status}, delete_memory not called, DB unchanged",
          result["status"] == expected_status and result["deleted_count"] == 0
          and result["deleted_ids"] == [] and dele.call_count == 0
          and (snapshot(fx.conv), snapshot(fx.other)) == before)


def run():
    # --- statuses that must never delete ---------------------------------
    for status in ("UNCERTAIN", "NO_MATCH", "MAYBE", "delete", "Delete", " DELETE", "DELETE ", "DELETED",
                   "", "TRUE", "YES", "ALL"):
        expect_blocked(f"status {status!r} + valid id",
                       lambda fx, st=status: {"status": st, "memory_ids": [fx.a]},
                       "NO_MATCH" if status == "NO_MATCH" else "UNCERTAIN")

    # --- missing / None / wrongly typed status ---------------------------
    for label, status_part in (
        ("status key missing", {}),
        ("status None", {"status": None}),
        ("status int 1", {"status": 1}),
        ("status True", {"status": True}),
        ("status list ['DELETE']", {"status": ["DELETE"]}),
        ("status dict", {"status": {"v": "DELETE"}}),
        ("status bytes b'DELETE'", {"status": b"DELETE"}),
    ):
        expect_blocked(label, lambda fx, sp=status_part: {**sp, "memory_ids": [fx.a]}, "UNCERTAIN")

    # --- malformed classifier result itself ------------------------------
    for label, response in (("result None", None), ("result list", [1, 2]),
                            ("result string 'DELETE'", "DELETE"), ("result empty dict", {})):
        expect_blocked(label, lambda fx, r=response: r, "UNCERTAIN")

    # --- explicit DELETE but invalid / missing ids ------------------------
    for label, ids_of in (
        ("memory_ids key missing", None),
        ("memory_ids None", lambda fx: None),
        ("memory_ids empty list", lambda fx: []),
        ("memory_ids a string", lambda fx: str(fx.a)),
        ("memory_ids a bare int", lambda fx: fx.a),
        ("ids as strings", lambda fx: [str(fx.a)]),
        ("ids as floats", lambda fx: [float(fx.a)]),
        ("ids bool True", lambda fx: [True]),
        ("ids unhashable list", lambda fx: [[fx.a]]),
        ("ids None entry", lambda fx: [None]),
        ("ids nonexistent / negative", lambda fx: [2_000_000_000, -5]),
    ):
        def make(fx, f=ids_of):
            return {"status": "DELETE"} if f is None else {"status": "DELETE", "memory_ids": f(fx)}
        expect_blocked(f"DELETE with {label}", make, "NO_MATCH")

    # --- foreign id only: ownership / isolation preserved ----------------
    fx = Fixture()
    before = (snapshot(fx.conv), snapshot(fx.other))
    result, dele = classify(fx, {"status": "DELETE", "memory_ids": [fx.foreign]})
    check("[isolation] DELETE with only another conversation's id -> NO_MATCH, delete_memory not called, both DBs unchanged",
          result["status"] == "NO_MATCH" and dele.call_count == 0 and (snapshot(fx.conv), snapshot(fx.other)) == before)

    # --- valid explicit DELETE still works --------------------------------
    fx = Fixture()
    other_before = snapshot(fx.other)
    keep = [r for r in snapshot(fx.conv)[0] if r[0] == fx.b]
    result, dele = classify(fx, {"status": "DELETE", "memory_ids": [fx.a]})
    mem_after, links_after = snapshot(fx.conv)
    check("[delete] explicit DELETE + valid id -> DELETED with that id only",
          result["status"] == "DELETED" and result["deleted_ids"] == [fx.a] and result["deleted_count"] == 1)
    check("[delete] delete_memory called exactly once for the intended id",
          dele.call_count == 1 and dele.call_args.kwargs["memory_id"] == fx.a)
    check("[delete] target row and its links gone, sibling memory intact",
          [r for r in mem_after if r[0] == fx.a] == [] and mem_after == keep
          and all(l[0] != fx.a for l in links_after))
    check("[delete] other conversation untouched", snapshot(fx.other) == other_before)
    check("[delete] deleted_memories captured text and source before deletion",
          result["deleted_memories"][0]["memory"] == "User keeps goats"
          and fx.m1 in result["deleted_memories"][0]["source_message_ids"])

    # mixed own + foreign + invalid with explicit DELETE: only the own valid id goes
    fx = Fixture()
    other_before = snapshot(fx.other)
    result, dele = classify(fx, {"status": "DELETE", "memory_ids": [fx.a, fx.foreign, "x", None, True]})
    check("[delete] DELETE with own + foreign + junk ids deletes only the own valid id",
          result["deleted_ids"] == [fx.a] and dele.call_count == 1 and snapshot(fx.other) == other_before)

    # existing statuses keep their documented results
    fx = Fixture()
    result, _ = classify(fx, {"status": "UNCERTAIN", "memory_ids": [fx.a]})
    check("[pin] UNCERTAIN keeps status UNCERTAIN and lists every id as skipped",
          result["status"] == "UNCERTAIN" and set(result["skipped_ids"]) == {fx.a, fx.b})
    result, _ = classify(fx, {"status": "NO_MATCH", "memory_ids": []})
    check("[pin] NO_MATCH keeps status NO_MATCH", result["status"] == "NO_MATCH")


emb = OneHot()
try:
    with mock.patch.object(storage, "generate_embeddings", side_effect=emb):
        run()
finally:
    with get_connection() as conn:
        for cid in CREATED:
            conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(cid),))

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
