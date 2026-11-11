"""D7 regression: storage.delete_memory() validates the memory id before any SQL.

Contract (documented in docs/remediation/D7_FIX_REPORT.md):
  returns True  -> the row existed in this conversation and was deleted
  returns False -> nothing deleted (nonexistent id, other conversation's id, invalid id)
  genuine database failures still propagate (not disguised as an invalid id)
Accepted ids: genuine ints (not bool) within bigint range, and ASCII integer strings
("2", " 2 ", "+2", "-2" - these already worked via the PostgreSQL cast).
Real storage layer on the scratch database; embeddings mocked; no Gemini.
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


def state(*convs):
    """Memories (incl. embedding text) and links of the given conversations."""
    with get_connection() as conn:
        out = []
        for conv in convs:
            out.append(conn.execute(
                "SELECT id, memory, embedding::text, source_message_id FROM conversation_memories "
                "WHERE conversation_id=%s ORDER BY id", (conv,)).fetchall())
            out.append(conn.execute(
                "SELECT memory_id, source_message_id, link_kind FROM memory_sources "
                "WHERE conversation_id=%s ORDER BY memory_id, source_message_id", (conv,)).fetchall())
    return out


class Fixture:
    def __init__(self):
        self.conv = create_conversation("p1-d7")
        self.other = create_conversation("p1-d7-other")
        CREATED.extend([self.conv, self.other])
        self.a = self._seed(self.conv, "User keeps goats")
        self.b = self._seed(self.conv, "User grows tomatoes")
        self.foreign = self._seed(self.other, "Foreign memory")

    def _seed(self, conv, text):
        source = save_message(conv, "user", text)
        assert quiet(storage.save_memory, conv, text, source)
        with get_connection() as conn:
            return conn.execute("SELECT id FROM conversation_memories WHERE conversation_id=%s AND memory=%s",
                                (conv, text)).fetchone()[0]


def attempt(fx, memory_id):
    """Call delete_memory; return (result_or_exception, number of get_connection calls)."""
    with mock.patch.object(storage, "get_connection", wraps=storage.get_connection) as spy:
        try:
            result = quiet(storage.delete_memory, fx.conv, memory_id)
        except BaseException as error:  # noqa: BLE001
            result = error
    return result, spy.call_count


def run():
    # --- invalid ids: False, no exception, no SQL at all, nothing deleted ------
    invalid = [
        ("True", True), ("False", False),
        ("float 2.7", 2.7), ("float -2.7", -2.7), ("float 2.0", 2.0), ("float 0.0", 0.0), ("float inf", float("inf")),
        ("float nan", float("nan")),
        ("string 'abc'", "abc"), ("string ''", ""), ("string ' '", " "), ("string '2.0'", "2.0"),
        ("string '1e1'", "1e1"), ("string '0x2'", "0x2"), ("string '2 3'", "2 3"), ("string '2abc'", "2abc"),
        ("string '--2'", "--2"), ("string '+-2'", "+-2"), ("string 'true'", "true"), ("string '2;DROP'", "2;DROP"),
        ("fullwidth digit string", "２"), ("arabic-indic digit string", "٢"),
        ("None", None), ("list [id]", [None]), ("empty list", []), ("dict", {"id": 1}), ("tuple", (1,)),
        ("set", {1}), ("bytes", b"2"), ("object", object()),
        ("int above bigint", 2 ** 70), ("int below bigint", -(2 ** 70)),
    ]
    for label, value in invalid:
        fx = Fixture()
        before = state(fx.conv, fx.other)
        if label == "list [id]":
            value = [fx.a]
        elif label == "tuple":
            value = (fx.a,)
        elif label == "set":
            value = {fx.a}
        elif label == "dict":
            value = {"id": fx.a}
        elif label == "bytes":
            value = str(fx.a).encode()
        result, calls = attempt(fx, value)
        check(f"[invalid] {label} -> False, no exception, no SQL executed, nothing deleted",
              result is False and calls == 0 and state(fx.conv, fx.other) == before)

    # the id of an existing row passed as an unsafe type must never delete that row
    fx = Fixture()
    before = state(fx.conv, fx.other)
    for value in (float(fx.a), bool(fx.a), [fx.a], {"id": fx.a}, f"{fx.a}.0", f"{fx.a}x"):
        attempt(fx, value)
    check("[invalid] existing row id disguised as float/bool/list/dict/'N.0'/'Nx' deletes nothing",
          state(fx.conv, fx.other) == before)

    # --- valid ints ---------------------------------------------------------------
    fx = Fixture()
    other_before = state(fx.other)
    sibling = [r for r in state(fx.conv)[0] if r[0] == fx.b]
    result, calls = attempt(fx, fx.a)
    mem, links = state(fx.conv)
    check("[valid] real int id of own memory -> True, row and its links gone, sibling intact",
          result is True and calls >= 1 and all(r[0] != fx.a for r in mem) and mem == sibling
          and all(l[0] != fx.a for l in links))
    check("[valid] other conversation untouched", state(fx.other) == other_before)
    check("[valid] second delete of the same id -> False", attempt(fx, fx.a)[0] is False)

    # --- numeric strings (existing compatibility, now converted before SQL) ------
    for label, make in (("'N'", lambda i: str(i)), ("' N '", lambda i: f" {i} "), ("'+N'", lambda i: f"+{i}"),
                        ("'\\tN\\n'", lambda i: f"\t{i}\n"), ("'00N'", lambda i: f"00{i}")):
        fx = Fixture()
        result, _ = attempt(fx, make(fx.a))
        mem = state(fx.conv)[0]
        check(f"[numeric string] {label} -> True, deletes exactly that memory",
              result is True and [r[0] for r in mem] == [fx.b])

    # --- zero / negative / nonexistent / huge-but-valid ints -----------------------
    for label, value in (("zero", 0), ("negative -1", -1), ("negative -5 as string '-5'", "-5"),
                         ("nonexistent 2_000_000_000", 2_000_000_000), ("bigint max", 2 ** 63 - 1),
                         ("bigint min", -(2 ** 63))):
        fx = Fixture()
        before = state(fx.conv, fx.other)
        result, _ = attempt(fx, value)
        check(f"[no row] {label} -> False, no exception, nothing deleted",
              result is False and state(fx.conv, fx.other) == before)

    # --- ownership: other conversation's id (int or numeric string) ----------------
    for label, value in (("int", None), ("numeric string", None)):
        fx = Fixture()
        before = state(fx.conv, fx.other)
        value = fx.foreign if label == "int" else str(fx.foreign)
        result, calls = attempt(fx, value)
        check(f"[ownership] other conversation's id as {label} -> False, row intact, ownership check ran",
              result is False and calls >= 1 and state(fx.conv, fx.other) == before)

    # --- real database failures are not disguised as 'invalid id' -------------------
    fx = Fixture()
    with mock.patch.object(storage, "get_connection", side_effect=RuntimeError("db down")):
        try:
            quiet(storage.delete_memory, fx.conv, fx.a)
            propagated = False
        except RuntimeError:
            propagated = True
    check("[db failure] a genuine connection error still propagates for a valid id", propagated)
    check("[db failure] row still present after failed attempt", fx.a in [r[0] for r in state(fx.conv)[0]])

    # --- diagnostics do not echo the invalid value -----------------------------------
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        storage.delete_memory("conv", "SECRET-ID-ABC")
    check("[log] invalid id refusal logs the type only, not the value",
          "str" in buf.getvalue() and "SECRET-ID-ABC" not in buf.getvalue())


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
