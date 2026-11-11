"""Phase 1 (P1-08): process_memory branching and delete_matching_memories.

Real storage on the scratch database; embeddings patched with distinct
one-hot vectors; both LLM decision functions mocked.
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
    """Distinct one-hot 384-vector per distinct text (same text -> same vector)."""

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


CREATED = []


class Fixture:
    def __init__(self):
        self.conv = create_conversation("p1-process-memory")
        self.other = create_conversation("p1-process-memory-other")
        CREATED.extend([self.conv, self.other])
        self.m1 = save_message(self.conv, "user", "Message one")
        self.a1 = save_message(self.conv, "assistant", "Assistant reply")
        self.m2 = save_message(self.conv, "user", "Message two")
        self.m3 = save_message(self.conv, "user", "Message three")
        self.m4 = save_message(self.conv, "user", "Message four")
        self.f1 = save_message(self.other, "user", "Foreign message")

    def seed(self, texts, conv=None, source=None):
        conv = conv or self.conv
        source = source or (self.m1 if conv == self.conv else self.f1)
        ids = []
        for text in texts:
            ok = quiet(storage.save_memory, conv, text, source)
            assert ok, f"seed failed for {text!r}"
            ids.append(max(i for i, t in automatic.get_all_conversation_memories(conv) if t == text))
        return ids


def rows(conv):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, memory, embedding::text, source_message_id "
            "FROM conversation_memories WHERE conversation_id=%s ORDER BY id",
            (conv,),
        ).fetchall()


def links(conv, memory_id=None):
    with get_connection() as conn:
        if memory_id is None:
            return conn.execute(
                "SELECT memory_id, source_message_id, link_kind FROM memory_sources "
                "WHERE conversation_id=%s ORDER BY memory_id, source_message_id", (conv,)
            ).fetchall()
        return conn.execute(
            "SELECT source_message_id, link_kind FROM memory_sources "
            "WHERE conversation_id=%s AND memory_id=%s ORDER BY source_message_id",
            (conv, memory_id),
        ).fetchall()


def state(fx):
    return (rows(fx.conv), links(fx.conv), rows(fx.other), links(fx.other))


def pm(fx, new_memory, source, **kw):
    return quiet(automatic.process_memory, fx.conv, new_memory, source, **kw)


def decide_mock(**decision):
    return mock.patch.object(automatic, "decide_memory_action", return_value=decision)


def spy(name):
    return mock.patch.object(automatic, name, wraps=getattr(automatic, name))


def run():
    emb = OneHot()
    with mock.patch.object(storage, "generate_embeddings", side_effect=emb):
        part_a()
        part_b()


def part_a():
    # ---- No-candidate paths: decide must not be called ----
    fx = Fixture()
    with decide_mock(action="NEW") as d:
        r = pm(fx, "User likes tea", fx.m1)
    check("[1] empty conversation -> SAVED", r == "SAVED")
    check("[1] decide not called", d.call_count == 0)
    got = rows(fx.conv)
    check("[1] one row with new text", len(got) == 1 and got[0][1] == "User likes tea")
    check("[1] source linked as origin", links(fx.conv, got[0][0]) == [(fx.m1, "origin")])

    fx = Fixture()
    with decide_mock(action="NEW") as d:
        r = pm(fx, "User likes tea", fx.m1, allow_new=False)
    check("[2] allow_new=False -> SKIPPED", r == "SKIPPED" and rows(fx.conv) == [] and d.call_count == 0)

    fx = Fixture()
    with decide_mock(action="NEW") as d:
        r = pm(fx, "User likes tea", fx.m1, delete_only=True)
    check("[3] delete_only with no candidates -> UNCERTAIN", r == "UNCERTAIN" and rows(fx.conv) == [] and d.call_count == 0)

    fx = Fixture()
    (mid,) = fx.seed(["User likes tea"])
    before = rows(fx.conv)
    with decide_mock(action="NEW") as d:
        r = pm(fx, "User likes tea", fx.m2, candidate_memories=[])
    check("[4] identical text with empty candidates -> SKIPPED (semantic duplicate)", r == "SKIPPED" and d.call_count == 0)
    check("[4] row count and rows unchanged", rows(fx.conv) == before)
    check("[4] confirmation link added to existing row",
          (fx.m2, "confirmation") in links(fx.conv, mid))

    fx = Fixture()
    with decide_mock(action="NEW") as d:
        r = pm(fx, "   ", fx.m1)
    check("[5] whitespace-only memory -> SKIPPED, no row", r == "SKIPPED" and rows(fx.conv) == [] and d.call_count == 0)

    # ---- Candidate sourcing / normalisation ----
    fx = Fixture()
    ids = fx.seed([f"Fact number {i}" for i in range(22)])
    with decide_mock(action="UNCERTAIN") as d:
        r = pm(fx, "something", fx.m2)
    passed = d.call_args.kwargs["existing_memories"]
    check("[6] limit 20 candidates", len(passed) == 20)
    check("[6] newest first (id DESC)", [i for i, _ in passed] == ids[::-1][:20])
    check("[6] UNCERTAIN passthrough", r == "UNCERTAIN")

    fx = Fixture()
    with decide_mock(action="UNCERTAIN") as d:
        pm(fx, "x", fx.m1, candidate_memories=[("5", "x"), (None, "y"), ("abc", "z"), (7, "w")])
    check("[7] supplied candidates normalised to ints, invalid dropped",
          d.call_args.kwargs["existing_memories"] == [(5, "x"), (7, "w")])

    fx = Fixture()
    with decide_mock(action="NEW") as d:
        r = pm(fx, "User likes tea", fx.m1, candidate_memories=[(None, "y")])
    check("[8] all-unparsable candidates behave as no candidates", r == "SAVED" and d.call_count == 0)

    # ---- NEW ----
    fx = Fixture()
    fx.seed(["Seed A", "Seed B"])
    fx.seed(["Foreign seed"], conv=fx.other)
    before = rows(fx.conv)
    other_before = rows(fx.other)
    with decide_mock(action="NEW"):
        r = pm(fx, "Brand new fact", fx.m2)
    after = rows(fx.conv)
    check("[9] NEW -> SAVED", r == "SAVED")
    check("[9] seeded rows byte-identical, one new row", after[:2] == before and len(after) == 3 and after[2][1] == "Brand new fact")
    check("[9] other conversation untouched", rows(fx.other) == other_before)

    fx = Fixture()
    fx.seed(["Seed A"])
    before = state(fx)
    with decide_mock(action="NEW"):
        r = pm(fx, "Brand new fact", fx.m2, allow_new=False)
    check("[10] NEW with allow_new=False -> SKIPPED, nothing changed", r == "SKIPPED" and state(fx) == before)

    fx = Fixture()
    fx.seed(["Seed A"])
    with decide_mock(action="NEW"), mock.patch.object(automatic, "save_memory", return_value=False):
        r = pm(fx, "Brand new fact", fx.m2)
    check("[11] NEW but save refuses -> SKIPPED", r == "SKIPPED")

    # ---- DUPLICATE ----
    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B"])
    before = rows(fx.conv)
    with decide_mock(action="DUPLICATE", memory_id=ids[0]):
        r = pm(fx, "Seed A", fx.m2)
    check("[12] DUPLICATE valid id -> SKIPPED", r == "SKIPPED")
    check("[12] text/embedding/rows unchanged", rows(fx.conv) == before)
    check("[12] confirmation link created", (fx.m2, "confirmation") in links(fx.conv, ids[0]))

    fx = Fixture()
    ids = fx.seed(["Seed A"])
    (oid,) = fx.seed(["Foreign seed"], conv=fx.other)
    before = state(fx)
    for label, mid in (("None id", None), ("foreign id", oid), ("nonexistent id", 2_000_000_000)):
        with decide_mock(action="DUPLICATE", memory_id=mid), spy("confirm_memory") as conf:
            r = pm(fx, "Seed A", fx.m2)
        check(f"[13] DUPLICATE {label} -> SKIPPED", r == "SKIPPED")
        check(f"[13] DUPLICATE {label} -> confirm_memory not called, nothing linked",
              conf.call_count == 0 and state(fx) == before)

    # ---- UPDATE ----
    fx = Fixture()
    ids = fx.seed(["User lives in Delhi", "User likes Python"])
    before = rows(fx.conv)
    with decide_mock(action="UPDATE", memory_id=ids[0], updated_memory="  User lives in Mumbai  "):
        r = pm(fx, "I moved to Mumbai", fx.m2)
    after = rows(fx.conv)
    check("[14] UPDATE -> UPDATED", r == "UPDATED")
    check("[14] row text stripped", after[0][1] == "User lives in Mumbai")
    check("[14] embedding changed", after[0][2] != before[0][2])
    check("[14] other row unchanged, count unchanged", after[1:] == before[1:] and len(after) == len(before))
    check("[14] origin retained and update link added",
          links(fx.conv, ids[0]) == [(fx.m1, "origin"), (fx.m2, "update")])

    fx = Fixture()
    ids = fx.seed(["User lives in Delhi"])
    with decide_mock(action="UPDATE", memory_id=str(ids[0]), updated_memory="User lives in Pune"):
        r = pm(fx, "x", fx.m2)
    check("[15] string memory_id coerced -> UPDATED", r == "UPDATED" and rows(fx.conv)[0][1] == "User lives in Pune")

    fx = Fixture()
    ids = fx.seed(["User lives in Delhi"])
    (oid,) = fx.seed(["User lives in Delhi (other)"], conv=fx.other)
    before = state(fx)
    for label, mid in (("None id", None), ("foreign id", oid), ("not among candidates", 2_000_000_000)):
        with decide_mock(action="UPDATE", memory_id=mid, updated_memory="Hijack"), spy("update_memory") as upd:
            r = pm(fx, "x", fx.m2)
        check(f"[16] UPDATE {label} -> UNCERTAIN", r == "UNCERTAIN")
        check(f"[16] UPDATE {label} -> update_memory not called, all rows unchanged",
              upd.call_count == 0 and state(fx) == before)

    for label, text in (("None", None), ("empty", ""), ("whitespace", "   ")):
        with decide_mock(action="UPDATE", memory_id=ids[0], updated_memory=text), spy("update_memory") as upd:
            r = pm(fx, "x", fx.m2)
        check(f"[17] UPDATE with {label} updated_memory -> UNCERTAIN, no write",
              r == "UNCERTAIN" and upd.call_count == 0 and state(fx) == before)

    with decide_mock(action="UPDATE", memory_id=ids[0], updated_memory="New text"), \
            mock.patch.object(automatic, "update_memory", return_value=False):
        r = pm(fx, "x", fx.m2)
    check("[18] storage refuses update -> SKIPPED", r == "SKIPPED")

    fx = Fixture()
    ids = fx.seed(["User lives in Delhi"])
    with decide_mock(action="UPDATE", memory_id=ids[0], updated_memory=123):
        r = pm(fx, "x", fx.m2)
    check("[19] non-str updated_memory 123 stored as '123' (pin)", r == "UPDATED" and rows(fx.conv)[0][1] == "123")

    fx = Fixture()
    ids = fx.seed(["User lives in Delhi"])
    with decide_mock(action="UPDATE", memory_id=ids[0], updated_memory="User lives in Mumbai"):
        pm(fx, "I moved to Mumbai", fx.m2)
    check("[20] one residence row, Mumbai", [r[1] for r in rows(fx.conv)] == ["User lives in Mumbai"])
    snap = state(fx)
    with decide_mock(action="UNCERTAIN"):
        r = pm(fx, "Maybe somewhere else", fx.m3)
    check("[20] later UNCERTAIN leaves it unchanged", r == "UNCERTAIN" and state(fx) == snap)

    fx = Fixture()
    ids = fx.seed(["Project A uses Python"])
    before = rows(fx.conv)
    with decide_mock(action="NEW"):
        r = pm(fx, "Project B uses Go", fx.m2)
    after = rows(fx.conv)
    check("[20b] different project -> NEW, two rows, project A unchanged",
          r == "SAVED" and len(after) == 2 and after[0] == before[0] and after[1][1] == "Project B uses Go")

    fx = Fixture()
    ids = fx.seed(["User lives in Delhi"])
    (oid,) = fx.seed(["Other conv fact"], conv=fx.other)
    before = state(fx)
    for label, src in (("assistant message", fx.a1), ("foreign-conversation message", fx.f1)):
        raised = None
        with decide_mock(action="UPDATE", memory_id=ids[0], updated_memory="User lives in Mumbai"):
            try:
                pm(fx, "x", src)
            except ValueError as error:
                raised = error
        check(f"[21] UPDATE with {label} source raises ValueError", raised is not None)
        check(f"[21] UPDATE with {label} source: rows and links unchanged (rolled back)", state(fx) == before)

    # ---- DELETE ban ----
    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    before = state(fx)
    with decide_mock(action="DELETE", memory_id=ids[0]), spy("delete_memory") as dele:
        r = pm(fx, "forget A", fx.m2)
    check("[22] DELETE valid id, default flags -> SKIPPED", r == "SKIPPED")
    check("[22] delete_memory not called, rows unchanged", dele.call_count == 0 and state(fx) == before)
    with decide_mock(action="DELETE", memory_id=2_000_000_000), spy("delete_memory") as dele:
        r = pm(fx, "forget A", fx.m2)
    check("[23] DELETE invalid id, default flags -> SKIPPED (ban precedes id check)",
          r == "SKIPPED" and dele.call_count == 0 and state(fx) == before)

    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    other_before = state(fx)[2:]
    b_row = [r for r in rows(fx.conv) if r[0] == ids[1]]
    with decide_mock(action="DELETE", memory_id=ids[0]):
        r = pm(fx, "forget A", fx.m2, allow_delete=True)
    check("[24] allow_delete + valid id -> DELETED", r == "DELETED")
    check("[24] target gone, sibling intact, other conversation intact",
          [x[0] for x in rows(fx.conv)] == [ids[1]] and rows(fx.conv) == b_row and state(fx)[2:] == other_before)

    fx = Fixture()
    ids = fx.seed(["Seed A"])
    (oid,) = fx.seed(["Other fact"], conv=fx.other)
    before = state(fx)
    for label, mid in (("None", None), ("foreign", oid), ("nonexistent", 2_000_000_000)):
        with decide_mock(action="DELETE", memory_id=mid):
            r = pm(fx, "forget", fx.m2, allow_delete=True)
        check(f"[25] allow_delete with {label} id -> UNCERTAIN, nothing deleted", r == "UNCERTAIN" and state(fx) == before)

    with decide_mock(action="DELETE", memory_id=ids[0]), mock.patch.object(automatic, "delete_memory", return_value=False):
        r = pm(fx, "forget", fx.m2, allow_delete=True)
    check("[26] storage refuses delete -> SKIPPED", r == "SKIPPED")

    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B"])
    with decide_mock(action="DELETE", memory_id=ids[0]):
        r = pm(fx, "forget A", fx.m2, delete_only=True)
    check("[27] delete_only + DELETE valid -> DELETED", r == "DELETED" and [x[0] for x in rows(fx.conv)] == [ids[1]])

    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B"])
    before = state(fx)
    for action in ("NEW", "DUPLICATE", "UPDATE", "UNCERTAIN"):
        with decide_mock(action=action, memory_id=ids[0], updated_memory="Changed"), \
                spy("save_memory") as sv, spy("update_memory") as upd, spy("confirm_memory") as conf:
            r = pm(fx, "x", fx.m2, delete_only=True)
        check(f"[27] delete_only + {action} -> UNCERTAIN", r == "UNCERTAIN")
        check(f"[27] delete_only + {action}: no save/update/confirm, rows unchanged",
              sv.call_count == upd.call_count == conf.call_count == 0 and state(fx) == before)

    # ---- Unknown / odd decisions ----
    fx = Fixture()
    ids = fx.seed(["Seed A"])
    before = state(fx)
    for label, decision in (("MERGE", {"action": "MERGE"}), ("missing action", {}),
                            ("None action", {"action": None}), ("UNCERTAIN", {"action": "UNCERTAIN"})):
        with mock.patch.object(automatic, "decide_memory_action", return_value=decision):
            r = pm(fx, "x", fx.m2)
        check(f"[28] {label} -> UNCERTAIN", r == "UNCERTAIN" and state(fx) == before)
    with decide_mock(action=" update ", memory_id=ids[0], updated_memory="Seed A2"):
        r = pm(fx, "x", fx.m2)
    check("[28] ' update ' normalised -> UPDATED", r == "UPDATED")

    # ---- Failure ----
    fx = Fixture()
    fx.seed(["Seed A"])
    before = state(fx)
    raised = None
    with mock.patch.object(automatic, "decide_memory_action", side_effect=RuntimeError("boom")):
        try:
            pm(fx, "x", fx.m2)
        except RuntimeError as error:
            raised = error
    check("[29] decide raising RuntimeError propagates", raised is not None)
    check("[29] rows unchanged after decide failure", state(fx) == before)


def dm(fx, classifier_result=None, side_effect=None, request="forget it"):
    kwargs = {"side_effect": side_effect} if side_effect is not None else {"return_value": classifier_result}
    with mock.patch.object(automatic, "decide_memories_to_delete", **kwargs) as c:
        result = quiet(automatic.delete_matching_memories, fx.conv, request)
    return result, c


def part_b():
    # 1. no memories
    fx = Fixture()
    result, c = dm(fx, {"status": "DELETE", "memory_ids": [1]})
    check("[b1] no memories -> SKIPPED, zero deleted, classifier not called",
          result == {"status": "SKIPPED", "deleted_ids": [], "deleted_count": 0,
                     "skipped_ids": [], "failed_ids": []} and c.call_count == 0)
    check("[b1] no deleted_memories key (pin)", "deleted_memories" not in result)

    # 2. classifier args
    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B", "Seed C"])
    fx.seed(["Foreign seed"], conv=fx.other)
    result, c = dm(fx, {"status": "NO_MATCH", "memory_ids": []}, request="forget my cats")
    kw = c.call_args.kwargs
    check("[b2] classifier gets all own memories ascending as (int, text)",
          kw["existing_memories"] == [(ids[0], "Seed A"), (ids[1], "Seed B"), (ids[2], "Seed C")])
    check("[b2] user_request passed through", kw["user_request"] == "forget my cats")

    # 3. UNCERTAIN even with ids
    before = state(fx)
    result, _ = dm(fx, {"status": "UNCERTAIN", "memory_ids": [ids[0]]})
    check("[b3] UNCERTAIN -> nothing deleted", result["status"] == "UNCERTAIN" and result["deleted_count"] == 0)
    check("[b3] skipped_ids is every id", set(result["skipped_ids"]) == set(ids))
    check("[b3] rows intact", state(fx) == before)

    # 4. NO_MATCH, empty, foreign
    result, _ = dm(fx, {"status": "NO_MATCH", "memory_ids": []})
    check("[b4] NO_MATCH", result["status"] == "NO_MATCH" and state(fx) == before)
    result, _ = dm(fx, {"status": "DELETE", "memory_ids": []})
    check("[b4] DELETE with empty ids -> NO_MATCH", result["status"] == "NO_MATCH" and state(fx) == before)
    (oid,) = [r[0] for r in rows(fx.other)]
    with spy("delete_memory") as dele:
        result, _ = dm(fx, {"status": "DELETE", "memory_ids": [oid, 2_000_000_000]})
    check("[b4] DELETE with only foreign/nonexistent ids -> NO_MATCH", result["status"] == "NO_MATCH")
    check("[b4] other row intact, delete_memory not called", state(fx) == before and dele.call_count == 0)

    # 5. mixed own + foreign
    other_before = rows(fx.other)
    result, _ = dm(fx, {"status": "DELETE", "memory_ids": [ids[0], oid]})
    check("[b5] mixed own + foreign -> DELETED, only own removed",
          result["status"] == "DELETED" and result["deleted_ids"] == [ids[0]])
    check("[b5] other conversation row intact", rows(fx.other) == other_before)
    check("[b5] deleted_memories only own details",
          [d["id"] for d in result["deleted_memories"]] == [ids[0]])

    # 6. success multi-id
    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B", "Seed C", "Seed D"])
    fx.seed(["Foreign seed"], conv=fx.other)
    other_before = rows(fx.other)
    keep = [r for r in rows(fx.conv) if r[0] in (ids[1], ids[3])]
    result, _ = dm(fx, {"status": "DELETE", "memory_ids": [ids[2], ids[0]]})
    check("[b6] DELETED, deleted_ids follows selected order", result["status"] == "DELETED" and result["deleted_ids"] == [ids[2], ids[0]])
    check("[b6] counts and lists", result["deleted_count"] == 2 and result["failed_ids"] == [] and set(result["skipped_ids"]) == {ids[1], ids[3]})
    dmem = {d["id"]: d for d in result["deleted_memories"]}
    check("[b6] deleted_memories capture id/text/source ids before deletion",
          set(dmem) == {ids[0], ids[2]} and dmem[ids[0]]["memory"] == "Seed A" and fx.m1 in dmem[ids[0]]["source_message_ids"])
    check("[b6] unselected and other-conversation rows untouched", rows(fx.conv) == keep and rows(fx.other) == other_before)

    # 7. partial failure
    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B", "Seed C"])
    real = storage.delete_memory

    def flaky(conversation_id, memory_id):
        if memory_id == ids[0]:
            return False
        if memory_id == ids[1]:
            raise RuntimeError("db down")
        return real(conversation_id=conversation_id, memory_id=memory_id)

    with mock.patch.object(automatic, "delete_memory", side_effect=flaky):
        result, _ = dm(fx, {"status": "DELETE", "memory_ids": ids})
    check("[b7] partial failure -> DELETED with failed ids listed, no raise",
          result["status"] == "DELETED" and result["deleted_ids"] == [ids[2]] and result["failed_ids"] == [ids[0], ids[1]])
    check("[b7] failed rows still present", sorted(r[0] for r in rows(fx.conv)) == [ids[0], ids[1]])

    # 8. all fail
    with mock.patch.object(automatic, "delete_memory", return_value=False):
        result, _ = dm(fx, {"status": "DELETE", "memory_ids": [ids[0], ids[1]]})
    check("[b8] all fail -> FAILED", result["status"] == "FAILED" and result["deleted_count"] == 0
          and result["deleted_memories"] == [] and result["failed_ids"] == [ids[0], ids[1]])

    # 9. {} classifier
    before = state(fx)
    result, _ = dm(fx, {})
    check("[b9] empty classifier result -> UNCERTAIN, nothing deleted", result["status"] == "UNCERTAIN" and state(fx) == before)

    # 10. classifier raises
    raised = None
    try:
        dm(fx, side_effect=RuntimeError("quota"))
    except RuntimeError as error:
        raised = error
    check("[b10] classifier RuntimeError propagates (pin)", raised is not None)

    # 11. get_memory_details contract
    with mock.patch.object(automatic, "get_memory_details", wraps=storage.get_memory_details) as gmd:
        dm(fx, {"status": "DELETE", "memory_ids": [ids[0]]})
    check("[b11] get_memory_details called with conversation and selected ids",
          gmd.call_args.args == (fx.conv, [ids[0]]))

    # Probes
    fx = Fixture()
    ids = fx.seed(["Seed A", "Seed B"])
    result, _ = dm(fx, {"status": "MAYBE", "memory_ids": [ids[0]]})
    deleted = ids[0] not in [r[0] for r in rows(fx.conv)]
    print(f"observed unknown-status result: {result['status']}")
    if deleted:
        finding("delete_matching_memories unknown status deletes",
                "classifier status 'MAYBE' with a valid id deleted the memory (status not validated; real classifier normalises, so latent only)")
    fx = Fixture()
    ids = fx.seed(["Seed A"])
    result, _ = dm(fx, {"status": "DELETE", "memory_ids": [str(ids[0])]})
    print(f"observed string-id result: {result['status']} deleted_ids={result['deleted_ids']}")
    check("[probe] string ids from classifier filtered -> NO_MATCH (observed pin)",
          result["status"] == "NO_MATCH" and len(rows(fx.conv)) == 1)


try:
    run()
finally:
    with get_connection() as conn:
        for cid in CREATED:
            conn.execute("DELETE FROM conversations WHERE id = %s", (uuid.UUID(cid),))

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed, {len(FINDINGS)} finding(s)")
sys.exit(1 if FAILURES else 0)
