"""Task 1 regressions: strict memory provenance and identifier validation.

Run only through run_tests.py; this script writes fixtures to rag_test_scratch.
All embedding/extraction/decision functions are mocked and fixtures are removed
in a finally block.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import json
import uuid
from unittest import mock
from decimal import Decimal

import numpy as np

import add_memory
import main as app_main
import services.automatic_memory_service as automatic
import services.memory_service as memory_service
import services.memory_storage_service as storage
from services.conversation_service import create_conversation, save_message
from services.database import get_connection


CREATED = []
CHECKS = 0


def check(label, condition):
    global CHECKS
    CHECKS += 1
    assert condition, label
    print("PASS |", label)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class OneHot:
    def __init__(self):
        self.indices = {}

    def __call__(self, texts):
        values = []
        for text in texts:
            if text not in self.indices:
                self.indices[text] = len(self.indices) % 384
            vector = np.zeros(384)
            vector[self.indices[text]] = 1.0
            values.append(vector)
        return values


class Fixture:
    def __init__(self):
        self.conversation = create_conversation("p1-task1-strict-attribution")
        self.other = create_conversation("p1-task1-strict-attribution-other")
        CREATED.extend([self.conversation, self.other])
        self.u1 = save_message(self.conversation, "user", "I use Python for project A.")
        self.a1 = save_message(self.conversation, "assistant", "Python noted.")
        self.u2 = save_message(self.conversation, "user", "I prefer concise explanations.")
        self.a2 = save_message(self.conversation, "assistant", "Understood.")
        self.foreign = save_message(self.other, "user", "Foreign source message.")


def memory_count(conversation_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT count(*) FROM conversation_memories WHERE conversation_id=%s",
            (conversation_id,),
        ).fetchone()[0]


def links(conversation_id, memory_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT source_message_id FROM memory_sources "
            "WHERE conversation_id=%s AND memory_id=%s ORDER BY source_message_id",
            (conversation_id, memory_id),
        ).fetchall()


def extraction_json(memory_text, source_ids=None, singular_source_id=None):
    item = {"memory": memory_text}
    if source_ids is not None:
        item["source_message_ids"] = source_ids
    if singular_source_id is not None:
        item["source_message_id"] = singular_source_id
    return json.dumps([item])


def run_parser_and_attribution_cases(fx):
    batch = [
        {"id": fx.u1, "role": "user", "content": "I use Python for project A."},
        {"id": fx.a1, "role": "assistant", "content": "Python noted."},
        {"id": fx.u2, "role": "user", "content": "I prefer concise explanations."},
        {"id": fx.a2, "role": "assistant", "content": "Understood."},
    ]

    def extract(response):
        with mock.patch.object(memory_service, "generate_answer", return_value=response):
            return quiet(memory_service.extract_memories, batch)

    single = extract(extraction_json("Project A uses Python.", [fx.u1]))
    check("explicit source for first user message is retained", single[0]["source_message_ids"] == [fx.u1])
    multi = extract(extraction_json("Project A uses Python.", [fx.u1, fx.u2]))
    check("explicit multi-source attribution is retained", multi[0]["source_message_ids"] == [fx.u1, fx.u2])

    invalid_responses = [
        ("missing source IDs", '[{"memory":"fact"}]'),
        ("boolean source ID", '[{"memory":"fact","source_message_ids":[true]}]'),
        ("fractional source ID", extraction_json("fact", [fx.u1 + 0.5])),
        ("numeric-string source ID", extraction_json("fact", [str(fx.u1)])),
        ("malformed source ID", '[{"memory":"fact","source_message_ids":["not-an-id"]}]'),
        ("negative source ID", '[{"memory":"fact","source_message_ids":[-1]}]'),
        ("zero source ID", '[{"memory":"fact","source_message_ids":[0]}]'),
        ("mixed valid and assistant IDs", extraction_json("fact", [fx.u1, fx.a1])),
        ("foreign conversation source ID", extraction_json("fact", [fx.foreign])),
        ("integral-looking but invalid batch source", extraction_json("fact", [fx.u1 + 1000000])),
    ]
    for label, response in invalid_responses:
        raised = None
        try:
            extract(response)
        except memory_service.InvalidMemoryProvenanceError as error:
            raised = error
        check(f"{label} rejects the extraction", raised is not None)

    integral_float = extract(extraction_json("Project A uses Python.", [float(fx.u1)]))
    check("exact integral float source ID normalizes without truncation", integral_float[0]["source_message_ids"] == [fx.u1])

    raised = None
    with mock.patch.object(memory_service, "generate_answer", return_value="- User likes tea"):
        try:
            quiet(memory_service.extract_memories, batch)
        except memory_service.InvalidMemoryProvenanceError as error:
            raised = error
    check("bullet-format extraction without source IDs is rejected", raised is not None)

    check("valid empty JSON extraction remains a successful no-op", extract("[]") == [])
    check("explicit NONE response remains a successful no-op", extract("NONE") == [])
    for failed_response in ("unparseable response", ""):
        raised = None
        with mock.patch.object(memory_service, "generate_answer", return_value=failed_response):
            try:
                quiet(memory_service.extract_memories, batch)
            except memory_service.MemoryExtractionError as error:
                raised = error
        check(f"failed extraction response does not look like an empty success: {failed_response!r}", raised is not None)

    # No guessed last-user fallback, even when the deprecated argument is passed.
    process = mock.Mock(return_value="SAVED")
    with mock.patch.object(memory_service, "generate_answer", return_value='[{"memory":"fact"}]'), \
            mock.patch.object(memory_service, "process_memory", process):
        raised = None
        try:
            quiet(
                memory_service.extract_and_save_memories,
                fx.conversation,
                batch,
                source_message_id=fx.a2,
            )
        except memory_service.InvalidMemoryProvenanceError as error:
            raised = error
    check("missing source is not replaced by last user or legacy argument", raised is not None and process.call_count == 0)

    # A later invalid item rejects the whole parsed batch before any write.
    response = json.dumps([
        {"memory": "valid first fact", "source_message_ids": [fx.u1]},
        {"memory": "invalid second fact", "source_message_ids": [fx.a1]},
    ])
    with mock.patch.object(memory_service, "generate_answer", return_value=response), \
            mock.patch.object(memory_service, "process_memory", process):
        raised = None
        try:
            quiet(memory_service.extract_and_save_memories, fx.conversation, batch)
        except memory_service.InvalidMemoryProvenanceError as error:
            raised = error
    check("mixed batch is rejected before partial memory writes", raised is not None and process.call_count == 0)

    # Valid extraction hands exact single and multiple source IDs to processing.
    process.reset_mock(return_value=True, side_effect=True)
    process.return_value = "SAVED"
    response = extraction_json("fact from first message", [fx.u1])
    with mock.patch.object(memory_service, "generate_answer", return_value=response), \
            mock.patch.object(memory_service, "process_memory", process):
        saved = quiet(memory_service.extract_and_save_memories, fx.conversation, batch)
    check("valid single-source extraction is processed", saved == ["fact from first message"])
    check("valid extraction passes source IDs unchanged", process.call_args.kwargs["source_message_ids"] == [fx.u1])


def run_storage_and_creation_cases(fx):
    embedding = OneHot()

    # Storage rejects a missing source before embedding or opening a connection.
    embed_mock = mock.patch.object(storage, "generate_embeddings", side_effect=embedding)
    connection_mock = mock.patch.object(storage, "get_connection", side_effect=AssertionError("unexpected DB"))
    with embed_mock as embed, connection_mock as connection:
        error = None
        try:
            storage.save_memory(fx.conversation, "source-less memory")
        except ValueError as caught:
            error = caught
    check("save_memory rejects missing provenance before embedding/DB", error is not None and embed.call_count == connection.call_count == 0)

    check("source normalization accepts integer and exact integral float", storage.normalize_source_ids(None, [fx.u1, float(fx.u1)]) == [fx.u1])
    for value in (True, False, 1.5, Decimal("1.5"), "1", "bad", 0, -1, 2 ** 63, float("inf"), float(2 ** 53)):
        error = None
        try:
            storage.normalize_source_ids(None, [value])
        except ValueError as caught:
            error = caught
        check(f"invalid raw source ID rejected: {value!r}", error is not None)

    with mock.patch.object(storage, "generate_embeddings", side_effect=embedding):
        start = memory_count(fx.conversation)
        for label, source_ids in (
            ("assistant", [fx.a1]),
            ("foreign", [fx.foreign]),
            ("mixed valid/assistant", [fx.u1, fx.a1]),
        ):
            error = None
            try:
                storage.save_memory(
                    fx.conversation,
                    f"invalid source case {label}",
                    source_message_ids=source_ids,
                )
            except ValueError as caught:
                error = caught
            check(f"{label} provenance rejected by storage", error is not None)
        check("rejected source lists create no rows", memory_count(fx.conversation) == start)

        check("valid single-source memory saves", storage.save_memory(
            fx.conversation, "single-source fact", source_message_id=fx.u1
        ))
        check("valid multi-source memory saves", storage.save_memory(
            fx.conversation, "multi-source fact", source_message_ids=[fx.u1, fx.u2]
        ))
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, memory FROM conversation_memories WHERE conversation_id=%s "
                "AND memory IN ('single-source fact','multi-source fact') ORDER BY memory",
                (fx.conversation,),
            ).fetchall()
        ids = {text: mid for mid, text in rows}
        check("single-source link is present", links(fx.conversation, ids["single-source fact"]) == [(fx.u1,)])
        check("multi-source links are present", links(fx.conversation, ids["multi-source fact"]) == [(fx.u1,), (fx.u2,)])

    # Automatic processing must not create a source-less memory or normalize a
    # malformed decision ID into the valid candidate ID.
    with mock.patch.object(automatic, "save_memory") as save, \
            mock.patch.object(automatic, "decide_memory_action") as decide:
        status = quiet(automatic.process_memory, fx.conversation, "no provenance")
    check("process_memory rejects source-less creation before decision/write", status == "UNCERTAIN" and decide.call_count == save.call_count == 0)

    with mock.patch.object(storage, "generate_embeddings", side_effect=embedding):
        # Use a real valid candidate ID, while mutation methods are spies.
        mid = ids["single-source fact"]
        invalid = [(True, 1), (False, 1), (1.5, 1), (mid + 0.5, mid), ("bad", mid), (0, mid), (-mid, mid)]
        for value, target_id in invalid:
            with mock.patch.object(automatic, "decide_memory_action", return_value={
                "action": "UPDATE", "memory_id": value, "updated_memory": "wrong memory"
            }), mock.patch.object(automatic, "update_memory") as update:
                status = quiet(
                    automatic.process_memory,
                    fx.conversation,
                    "new fact",
                    source_message_id=fx.u2,
                    candidate_memories=[(target_id, "candidate")],
                )
            check(f"invalid UPDATE decision ID rejected: {value!r}", status == "UNCERTAIN" and update.call_count == 0)

            with mock.patch.object(automatic, "decide_memory_action", return_value={
                "action": "DELETE", "memory_id": value, "updated_memory": None
            }), mock.patch.object(automatic, "delete_memory") as delete:
                status = quiet(
                    automatic.process_memory,
                    fx.conversation,
                    "delete request",
                    candidate_memories=[(target_id, "candidate")],
                    allow_delete=True,
                )
            check(f"invalid DELETE decision ID rejected: {value!r}", status == "UNCERTAIN" and delete.call_count == 0)

        for value in (float(mid), str(mid)):
            with mock.patch.object(automatic, "decide_memory_action", return_value={
                "action": "UPDATE", "memory_id": value, "updated_memory": "valid target"
            }), mock.patch.object(automatic, "update_memory", return_value=True) as update:
                status = quiet(
                    automatic.process_memory,
                    fx.conversation,
                    "new fact",
                    source_message_id=fx.u2,
                    candidate_memories=[(mid, "single-source fact")],
                )
            check(f"exact integral/numeric-string decision ID compatibility retained: {value!r}",
                  status == "UPDATED" and update.call_args.kwargs["memory_id"] == mid)

            with mock.patch.object(automatic, "decide_memory_action", return_value={
                "action": "DELETE", "memory_id": value, "updated_memory": None
            }), mock.patch.object(automatic, "delete_memory", return_value=True) as delete:
                status = quiet(
                    automatic.process_memory,
                    fx.conversation,
                    "delete request",
                    candidate_memories=[(mid, "single-source fact")],
                    allow_delete=True,
                )
            check(f"exact integral/numeric-string DELETE decision ID is normalized: {value!r}",
                  status == "DELETED" and delete.call_args.kwargs["memory_id"] == mid)

    # add_memory.py is now import-safe and requires a source argument, then
    # routes through the same storage validation boundary.
    with mock.patch.object(storage, "save_memory") as save:
        for args in ([], ["--source-message-id", "0"], ["--source-message-id", "1.5"]):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                try:
                    add_memory.main(args)
                except SystemExit:
                    pass
                else:
                    raise AssertionError(f"add_memory accepted invalid args {args!r}")
        check("add_memory requires a valid explicit source argument", save.call_count == 0)

        with mock.patch.object(add_memory, "CONVERSATION_ID", fx.conversation):
            with contextlib.redirect_stdout(io.StringIO()):
                add_memory.main(["--source-message-id", str(fx.u1)])
        check("add_memory delegates with parsed source ID", save.call_args.kwargs == {
            "conversation_id": fx.conversation,
            "memory_text": add_memory.MEMORY_TEXT,
            "source_message_id": fx.u1,
        })


def run_checkpoint_case(fx):
    batch = [
        {"id": fx.u1, "role": "user", "content": "I use Python for project A."},
        {"id": fx.a1, "role": "assistant", "content": "Python noted."},
        {"id": fx.u2, "role": "user", "content": "I prefer concise explanations."},
        {"id": fx.a2, "role": "assistant", "content": "Understood."},
    ]

    answers = iter(["", "hello", "exit"])
    stdout = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("builtins.input", side_effect=lambda _: next(answers)))
        stack.enter_context(mock.patch.object(app_main, "create_conversation", return_value=fx.conversation))
        stack.enter_context(mock.patch.object(app_main, "get_conversation_history", return_value=[]))
        stack.enter_context(mock.patch.object(app_main, "get_conversation_summary", return_value=""))
        stack.enter_context(mock.patch.object(app_main, "search_memories", return_value=[]))
        stack.enter_context(mock.patch.object(app_main, "ask_question", return_value={"answer": "hello back", "sources": []}))
        stack.enter_context(mock.patch.object(app_main, "save_message", side_effect=[100, 101]))
        stack.enter_context(mock.patch.object(app_main, "get_messages_for_memory_extraction", return_value=batch))
        checkpoint = stack.enter_context(mock.patch.object(app_main, "update_memory_extraction_checkpoint"))
        stack.enter_context(mock.patch.object(app_main, "update_long_term_memory"))
        stack.enter_context(mock.patch.object(memory_service, "generate_answer", return_value='[{"memory":"fact with missing source"}]'))
        stack.enter_context(contextlib.redirect_stdout(stdout))
        app_main.main()

    check("invalid extraction outcome is explicit in main", "checkpoint not advanced" in stdout.getvalue())
    check("invalid extraction does not advance checkpoint", checkpoint.call_count == 0)


def main():
    fx = Fixture()
    with mock.patch.object(storage, "generate_embeddings", side_effect=OneHot()):
        run_parser_and_attribution_cases(fx)
        run_storage_and_creation_cases(fx)
        run_checkpoint_case(fx)
    print(f"\nALL {CHECKS} TASK 1 CHECKS PASSED")


try:
    main()
finally:
    if CREATED:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id = ANY(%s::uuid[])",
                ([uuid.UUID(value) for value in CREATED],),
            )
