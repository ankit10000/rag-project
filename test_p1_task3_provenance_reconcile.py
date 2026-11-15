"""Phase 1 Task 3 legacy/modern provenance reconciliation regressions."""
import testsafe
testsafe.require_scratch_db()

import atexit
import contextlib
import io
import uuid
from unittest import mock

import services.memory_provenance_service as provenance
import services.memory_storage_service as storage
from services.conversation_service import create_conversation, save_message
from services.database import get_connection


CREATED = []


def tracked_conversation(title):
    cid = create_conversation(title)
    CREATED.append(cid)
    return cid


def cleanup_created():
    if CREATED:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id = ANY(%s::uuid[])",
                ([uuid.UUID(cid) for cid in CREATED],),
            )


atexit.register(cleanup_created)


class FakeEmbedding:
    def tolist(self):
        return [1.0] + [0.0] * 383


def check(label, condition):
    print(f"{'PASS' if condition else 'FAIL'} | {label}")
    assert condition, label


def make_memory(cid, text, source_ids):
    with mock.patch.object(storage, "generate_embeddings", return_value=[FakeEmbedding()]):
        check(f"new memory fixture saved: {text}", storage.save_memory(cid, text, source_message_ids=source_ids))
    with get_connection() as conn:
        return conn.execute(
            "SELECT id FROM conversation_memories WHERE conversation_id=%s AND memory=%s",
            (uuid.UUID(cid), text),
        ).fetchone()[0]


def state(cid, memory_id):
    with get_connection() as conn:
        memory = conn.execute(
            "SELECT source_message_id FROM conversation_memories "
            "WHERE conversation_id=%s AND id=%s",
            (uuid.UUID(cid), memory_id),
        ).fetchone()
        links = conn.execute(
            "SELECT source_message_id, source_role, link_kind FROM memory_sources "
            "WHERE conversation_id=%s AND memory_id=%s ORDER BY source_message_id",
            (uuid.UUID(cid), memory_id),
        ).fetchall()
        messages = conn.execute(
            "SELECT id, role FROM messages WHERE conversation_id=%s ORDER BY id",
            (uuid.UUID(cid),),
        ).fetchall()
    return (memory[0] if memory else None, links, messages, memory is not None)


def run_representation_cases():
    # Legacy scalar only.
    cid = tracked_conversation("p1-task3-legacy-only")
    source = save_message(cid, "user", "legacy scalar source")
    mid = make_memory(cid, "legacy scalar only memory", [source])
    with get_connection() as conn:
        conn.execute("DELETE FROM memory_sources WHERE conversation_id=%s AND memory_id=%s", (uuid.UUID(cid), mid))
    result = provenance.delete_message_with_provenance(cid, source)
    check("legacy scalar-only source returns its memory as orphaned", result == {
        "deleted": True, "orphaned": [mid], "still_supported": []
    })
    scalar, links, messages, exists = state(cid, mid)
    check("legacy scalar is detached and memory is retained", exists and scalar is None and links == [])
    check("legacy scalar source message was deleted", source not in {row[0] for row in messages})

    # Join-table only.
    cid = tracked_conversation("p1-task3-join-only")
    source = save_message(cid, "user", "join-only source")
    mid = make_memory(cid, "join-only memory", [source])
    with get_connection() as conn:
        conn.execute(
            "UPDATE conversation_memories SET source_message_id=NULL WHERE conversation_id=%s AND id=%s",
            (uuid.UUID(cid), mid),
        )
    result = provenance.delete_message_with_provenance(cid, source)
    check("join-only source remains supported by the existing behavior", result == {
        "deleted": True, "orphaned": [mid], "still_supported": []
    })
    scalar, links, _, exists = state(cid, mid)
    check("join-only link is detached but the memory remains", exists and scalar is None and links == [])

    # The same source in both representations is counted once.
    cid = tracked_conversation("p1-task3-duplicate-representation")
    source = save_message(cid, "user", "duplicate representation source")
    mid = make_memory(cid, "duplicated source memory", [source])
    result = provenance.delete_message_with_provenance(cid, source)
    occurrences = result["orphaned"].count(mid) + result["still_supported"].count(mid)
    check("same source in both stores produces one affected-memory result", occurrences == 1)
    check("duplicate representations do not falsely support the memory", result["orphaned"] == [mid])

    # A different valid user source preserves a shared memory.
    cid = tracked_conversation("p1-task3-shared-source")
    first = save_message(cid, "user", "first shared source")
    second = save_message(cid, "user", "surviving shared source")
    mid = make_memory(cid, "shared memory with two sources", [first, second])
    result = provenance.delete_message_with_provenance(cid, first)
    check("another source reports the memory as still supported", result == {
        "deleted": True, "orphaned": [], "still_supported": [mid]
    })
    scalar, links, messages, exists = state(cid, mid)
    check("surviving source and memory remain intact", exists and scalar is None and links == [(second, "user", "origin")])
    check("deleted source is gone but the other message remains", first not in {r[0] for r in messages} and second in {r[0] for r in messages})


def run_missing_and_foreign_cases():
    cid = tracked_conversation("p1-task3-missing")
    source = save_message(cid, "user", "present source")
    mid = make_memory(cid, "memory for missing-message check", [source])
    before = state(cid, mid)
    missing_id = max(row[0] for row in before[2]) + 1000
    result = provenance.delete_message_with_provenance(cid, missing_id)
    check("missing message is a no-op with the existing return shape", result == {
        "deleted": False, "orphaned": [], "still_supported": []
    })
    check("missing-message request leaves memory, links, and messages unchanged", state(cid, mid) == before)

    other = tracked_conversation("p1-task3-foreign")
    foreign_source = save_message(other, "user", "foreign source")
    foreign_mid = make_memory(other, "foreign conversation memory", [foreign_source])
    foreign_before = state(other, foreign_mid)
    result = provenance.delete_message_with_provenance(cid, foreign_source)
    check("foreign-conversation message is a safe no-op", result == {
        "deleted": False, "orphaned": [], "still_supported": []
    })
    check("foreign message and provenance remain untouched", state(other, foreign_mid) == foreign_before)


class FaultInjectingConnection:
    """Delegate to a real scratch connection but fail at one SQL operation."""
    def __init__(self, connection, needle):
        self.connection = connection
        self.needle = needle.lower()

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(exc_type, exc_value, traceback)

    def execute(self, query, params=None):
        normalized = " ".join(query.lower().split())
        if self.needle in normalized:
            raise RuntimeError(f"injected scratch failure at {self.needle}")
        return self.connection.execute(query, params)


def run_atomicity_cases():
    cid = tracked_conversation("p1-task3-rollback")
    target = save_message(cid, "user", "source to delete transactionally")
    other_source = save_message(cid, "user", "second surviving source")
    mid = make_memory(cid, "transaction rollback memory", [target, other_source])
    before = state(cid, mid)
    original_factory = provenance.get_connection

    for needle in ("update conversation_memories", "delete from messages"):
        with mock.patch.object(
            provenance,
            "get_connection",
            side_effect=lambda needle=needle: FaultInjectingConnection(original_factory(), needle),
        ):
            error = None
            try:
                provenance.delete_message_with_provenance(cid, target)
            except RuntimeError as caught:
                error = caught
        check(f"failure injected at {needle}", error is not None)
        check(f"failure at {needle} rolls back scalar, links, and message", state(cid, mid) == before)


class MockQueryResult:
    def __init__(self, rows=None, value=None):
        self.rows = rows or []
        self.value = value

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.value


class MockReadConnection:
    def __init__(self, rows=None, value=None):
        self.rows = rows or []
        self.value = value
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.queries.append(query)
        return MockQueryResult(rows=self.rows, value=self.value)


def run_assistant_role_cases():
    # The normal writer still enforces user-only source IDs.
    cid = tracked_conversation("p1-task3-assistant-write")
    assistant = save_message(cid, "assistant", "assistant cannot be a source")
    before_count = None
    with get_connection() as conn:
        before_count = conn.execute(
            "SELECT count(*) FROM conversation_memories WHERE conversation_id=%s",
            (uuid.UUID(cid),),
        ).fetchone()[0]
    with mock.patch.object(storage, "generate_embeddings", return_value=[FakeEmbedding()]):
        error = None
        try:
            storage.save_memory(cid, "must reject assistant provenance", source_message_id=assistant)
        except ValueError as caught:
            error = caught
    with get_connection() as conn:
        after_count = conn.execute(
            "SELECT count(*) FROM conversation_memories WHERE conversation_id=%s",
            (uuid.UUID(cid),),
        ).fetchone()[0]
    check("new assistant-source memory write is rejected", error is not None and before_count == after_count)

    # Simulate reading a pre-existing legacy row. Read APIs must preserve the
    # stored role and legacy link kind, rather than relabel it as user evidence.
    fake = MockReadConnection(rows=[(77, "assistant", "legacy", "old assistant content")])
    with mock.patch.object(provenance, "get_connection", return_value=fake):
        links = provenance.get_memory_sources("00000000-0000-0000-0000-000000000001", 10)
    check("historical assistant link retains actual source_role and legacy kind", links == [{
        "message_id": 77,
        "role": "assistant",
        "link_kind": "legacy",
        "content": "old assistant content",
    }])

    # A remaining assistant-only link is not valid user-origin support.
    fake = MockReadConnection(value=(False,))
    with mock.patch.object(provenance, "get_connection", return_value=fake):
        supported = provenance._has_valid_user_source(
            fake,
            uuid.UUID("00000000-0000-0000-0000-000000000001"),
            10,
        )
    check("assistant-only historical evidence does not count as valid support", supported is False)
    combined_query = " ".join(fake.queries[0].lower().split())
    check("valid modern support requires source_role and actual user role",
          "ms.source_role = 'user'" in combined_query and "source_message.role = 'user'" in combined_query)
    check("remaining support joins and filters sources within the memory conversation",
          "source_message.conversation_id = ms.conversation_id" in combined_query
          and "source_message.conversation_id = cm.conversation_id" in combined_query
          and "where ms.conversation_id = %s" in combined_query
          and "where cm.conversation_id = %s" in combined_query)


def run():
    run_representation_cases()
    run_missing_and_foreign_cases()
    run_atomicity_cases()
    run_assistant_role_cases()


try:
    run()
finally:
    cleanup_created()

print("\nALL PHASE 1 TASK 3 CHECKS PASSED")
