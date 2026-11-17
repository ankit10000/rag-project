"""Phase 1 Task 2 deletion safety regressions on the guarded scratch DB."""
import testsafe
testsafe.require_scratch_db()

import atexit
import contextlib
import io
import uuid
from unittest import mock

import services.memory_cleanup_service as cleanup_service
import services.memory_service as memory_service
import services.memory_storage_service as storage
from services.conversation_service import (
    create_conversation as _create_conversation,
    get_conversation_history,
    get_messages_for_memory_extraction,
    get_messages_to_summarize,
    get_paired_assistant_ids,
    get_conversation_summary,
    save_message,
    update_conversation_memory,
)
from services.database import get_connection


CREATED = []
NO = '{"still_contains": false, "evidence": ""}'
YES = '{"still_contains": true, "evidence": "forgotten"}'


def create_conversation(title):
    conversation_id = _create_conversation(title)
    CREATED.append(conversation_id)
    return conversation_id


def cleanup_created_conversations():
    if CREATED:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id = ANY(%s::uuid[])",
                ([uuid.UUID(value) for value in CREATED],),
            )


atexit.register(cleanup_created_conversations)


class FakeEmbedding:
    def tolist(self):
        return [1.0] + [0.0] * 383


def quiet(fn, *args, **kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        value = fn(*args, **kwargs)
    return value, output.getvalue()


def check(label, condition):
    print(f"{'PASS' if condition else 'FAIL'} | {label}")
    assert condition, label


def db_messages(conversation_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, role, content, context_excluded FROM messages "
            "WHERE conversation_id=%s ORDER BY id",
            (uuid.UUID(conversation_id),),
        ).fetchall()


def checkpoints(conversation_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT summary_up_to_message_id, memory_extraction_up_to_message_id "
            "FROM conversations WHERE id=%s",
            (uuid.UUID(conversation_id),),
        ).fetchone()


def other_fingerprint(conversation_id):
    return (
        get_conversation_summary(conversation_id),
        checkpoints(conversation_id),
        db_messages(conversation_id),
    )


def make_deleted_memory(conversation_id, text, source_ids, *, make_source_unknown=False):
    with mock.patch.object(storage, "generate_embeddings", return_value=[FakeEmbedding()]):
        saved = storage.save_memory(
            conversation_id,
            text,
            source_message_ids=source_ids,
        )
    assert saved

    with get_connection() as conn:
        memory_id = conn.execute(
            "SELECT id FROM conversation_memories "
            "WHERE conversation_id=%s AND memory=%s ORDER BY id DESC LIMIT 1",
            (uuid.UUID(conversation_id), text),
        ).fetchone()[0]

        if make_source_unknown:
            # Model a legacy row after Task 1 made source-less new writes invalid.
            conn.execute("DELETE FROM memory_sources WHERE memory_id=%s", (memory_id,))
            conn.execute(
                "UPDATE conversation_memories SET source_message_id=NULL WHERE id=%s",
                (memory_id,),
            )

    details = storage.get_memory_details(conversation_id, [memory_id])[memory_id]
    check(f"scratch memory created for cleanup fixture: {text}", storage.delete_memory(conversation_id, memory_id))
    return details


def model(rewrite, verify=NO, echo="[]"):
    def answer(prompt):
        if "RECENT MESSAGES" in prompt:
            value = echo
        elif "editing a conversation summary" in prompt:
            value = rewrite
        elif "SUMMARY TO CHECK" in prompt:
            value = verify
        else:
            raise AssertionError("unexpected cleanup prompt")
        if isinstance(value, Exception):
            raise value
        return value
    return answer


def add_deletion_turn(conversation_id):
    request_id = save_message(conversation_id, "user", "Forget the selected memory")
    answer_id = save_message(
        conversation_id,
        "assistant",
        "Memory deleted; processing historical cleanup.",
    )
    return request_id, answer_id


def run_pairing_cases():
    conversation_id = create_conversation("p1-task2-pairing")
    other = create_conversation("p1-task2-pairing-other")

    adjacent_user = save_message(conversation_id, "user", "adjacent user")
    save_message(other, "user", "unrelated other conversation row")
    adjacent_assistant = save_message(conversation_id, "assistant", "adjacent assistant")
    check(
        "adjacent user and assistant pair despite unrelated conversation rows",
        get_paired_assistant_ids(conversation_id, [adjacent_user]) == [adjacent_assistant],
    )

    first_user = save_message(conversation_id, "user", "first consecutive user")
    second_user = save_message(conversation_id, "user", "second consecutive user")
    first_assistant = save_message(conversation_id, "assistant", "first assistant")
    second_assistant = save_message(conversation_id, "assistant", "second assistant")
    check(
        "consecutive users pair only the immediately preceding user",
        get_paired_assistant_ids(conversation_id, [first_user, second_user]) == [first_assistant],
    )
    check(
        "consecutive assistant messages pair only the first assistant",
        get_paired_assistant_ids(conversation_id, [second_user]) == [first_assistant],
    )

    excluded_assistant_user = save_message(conversation_id, "user", "excluded assistant origin")
    excluded_assistant = save_message(conversation_id, "assistant", "already excluded assistant")
    with get_connection() as conn:
        conn.execute("UPDATE messages SET context_excluded=true WHERE id=%s", (excluded_assistant,))
    check(
        "an excluded immediate assistant still occupies the next row and pairs",
        get_paired_assistant_ids(conversation_id, [excluded_assistant_user]) == [excluded_assistant],
    )

    intervened_user = save_message(conversation_id, "user", "origin before intervening user")
    excluded_user = save_message(conversation_id, "user", "excluded intervening user")
    later_assistant = save_message(conversation_id, "assistant", "not guessed as reply")
    with get_connection() as conn:
        conn.execute("UPDATE messages SET context_excluded=true WHERE id=%s", (excluded_user,))
    check(
        "an excluded intervening user prevents guessing a later assistant",
        get_paired_assistant_ids(conversation_id, [intervened_user]) == [],
    )
    check("test has a later assistant after the intervening user", later_assistant > excluded_user)


def run_unknown_provenance_case(name, rewrite, verify, echo, *, old_origin=False):
    conversation_id = create_conversation(f"p1-task2-unknown-{name}")
    other = create_conversation(f"p1-task2-unknown-other-{name}")
    old_text = "UNATTRIBUTED_OLD_SOURCE_MARKER from the start of history"

    if old_origin:
        origin_id = save_message(conversation_id, "user", old_text)
        for index in range(44):
            save_message(conversation_id, "user", f"old filler message {index}")
    else:
        origin_id = save_message(conversation_id, "user", old_text)
        save_message(conversation_id, "assistant", "response to the possible source")

    update_conversation_memory(
        conversation_id,
        "The account has a private detail. The user likes cricket and concise reports.",
        0,
    )
    details = make_deleted_memory(
        conversation_id,
        "A legacy memory with unknown origin.",
        [origin_id],
        make_source_unknown=True,
    )
    check("legacy source-less memory has no recoverable IDs", details["source_message_ids"] == [])

    save_message(other, "user", "unrelated conversation message")
    update_conversation_memory(other, "Other conversation summary.", 0)
    other_before = other_fingerprint(other)

    request_id, answer_id = add_deletion_turn(conversation_id)
    pre_cleanup_rows = db_messages(conversation_id)
    high_water = pre_cleanup_rows[-1][0]
    observed_scan = []
    original_get_live = cleanup_service.get_live_messages

    def record_scan(*args, **kwargs):
        rows = original_get_live(*args, **kwargs)
        observed_scan.extend(row["id"] for row in rows)
        return rows

    with mock.patch.object(cleanup_service, "generate_answer", side_effect=model(rewrite, verify, echo)), \
            mock.patch.object(cleanup_service, "get_live_messages", side_effect=record_scan):
        result, output = quiet(
            cleanup_service.apply_deletion_cleanup,
            conversation_id,
            [details],
            [request_id, answer_id],
            "Forget the selected memory",
        )

    check(f"{name}: result explicitly marks cleanup incomplete", result["status"] == "INCOMPLETE")
    check(f"{name}: provenance is explicitly unknown", result["provenance_status"] == "UNKNOWN")
    check(f"{name}: final summary is explicitly cleared", result["summary_status"] == "CLEARED_UNKNOWN_PROVENANCE")
    check(f"{name}: user-visible incomplete outcome is printed", "Memory deleted, historical cleanup incomplete" in output)
    check(f"{name}: both checkpoints equal current high-water", checkpoints(conversation_id) == (high_water, high_water))
    check(f"{name}: current summary is empty", get_conversation_summary(conversation_id) == "")
    check(f"{name}: rewrite branch recorded", result["rewrite_status"] in {"RESET", "REWRITTEN"})
    check(f"{name}: echo scan was performed", bool(observed_scan))
    if old_origin:
        check(f"{name}: possible origin lies outside the 40-message scan", origin_id not in observed_scan)

    after_rows = db_messages(conversation_id)
    before_ids = {row[0] for row in pre_cleanup_rows}
    check(f"{name}: every original message row remains", before_ids <= {row[0] for row in after_rows})
    check(
        f"{name}: no unrelated history was broadly excluded",
        {row[0] for row in after_rows if row[3]} == {request_id, answer_id},
    )
    check(f"{name}: possible old source remains stored and unexcluded",
          any(row[0] == origin_id and row[2] == old_text and not row[3] for row in after_rows))
    check(f"{name}: other conversation unchanged", other_fingerprint(other) == other_before)

    check(
        f"{name}: no old messages enter summary input",
        get_messages_to_summarize(conversation_id, keep_recent=1)[1] == [],
    )
    check(
        f"{name}: no old messages enter extraction input",
        get_messages_for_memory_extraction(conversation_id, limit=100) == [],
    )
    check(
        f"{name}: no old messages enter recent history",
        get_conversation_history(conversation_id, limit=100) == [],
    )

    future_user = save_message(conversation_id, "user", "POST_CLEANUP_FUTURE_FACT")
    future_assistant = save_message(conversation_id, "assistant", "POST_CLEANUP_FUTURE_REPLY")

    extraction_batch = get_messages_for_memory_extraction(conversation_id, limit=100)
    check(
        f"{name}: extraction selects only post-cleanup messages",
        [row["id"] for row in extraction_batch] == [future_user, future_assistant],
    )
    extraction_prompts = []
    with mock.patch.object(memory_service, "generate_answer", side_effect=lambda prompt: extraction_prompts.append(prompt) or "[]"):
        check("new extraction batch is a valid empty result", memory_service.extract_memories(extraction_batch) == [])
    check(
        f"{name}: extraction prompt excludes pre-cleanup source",
        old_text not in extraction_prompts[0] and "POST_CLEANUP_FUTURE_FACT" in extraction_prompts[0],
    )

    summary_prompts = []
    with mock.patch.object(memory_service, "generate_answer", side_effect=lambda prompt: summary_prompts.append(prompt) or "Post-cleanup future summary."):
        memory_service.update_long_term_memory(conversation_id, keep_recent=1, min_messages=1)
    check(
        f"{name}: summary rebuild uses only verified live memories without a model",
        summary_prompts == [] and get_conversation_summary(conversation_id) == "",
    )


def run_known_provenance_case(name, *, source_count, verification_failure):
    conversation_id = create_conversation(f"p1-task2-known-{name}")
    other = create_conversation(f"p1-task2-known-other-{name}")
    source_ids = []
    assistant_ids = []
    for index in range(source_count):
        source_ids.append(save_message(conversation_id, "user", f"I use SecretToken fact {index}"))
        assistant_ids.append(save_message(conversation_id, "assistant", f"SecretToken noted {index}"))
    for index in range(8):
        save_message(conversation_id, "user", f"unrelated old context {index}")

    update_conversation_memory(
        conversation_id,
        "The project uses SecretToken. The user also enjoys cricket and concise reports.",
        0,
    )
    deleted = make_deleted_memory(
        conversation_id,
        "The user uses SecretToken.",
        source_ids,
    )
    save_message(other, "user", "independent other conversation")
    update_conversation_memory(other, "Other summary.", 0)
    other_before = other_fingerprint(other)
    request_id, answer_id = add_deletion_turn(conversation_id)
    high_water = db_messages(conversation_id)[-1][0]

    rewrite = "The user enjoys cricket and concise reports, and likes weekend walks."
    verify = YES if verification_failure else NO
    fake = model(
        RuntimeError("rewrite service failed") if not verification_failure else rewrite,
        verify=verify,
        echo=RuntimeError("echo scan failed"),
    )
    with mock.patch.object(cleanup_service, "generate_answer", side_effect=fake):
        result, output = quiet(
            cleanup_service.apply_deletion_cleanup,
            conversation_id,
            [deleted],
            [request_id, answer_id],
            "Forget SecretToken",
        )

    label = f"known-{name}"
    check(f"{label}: known provenance cleanup is complete", result["status"] == "COMPLETE")
    check(f"{label}: user-facing completion is explicit", "Historical memory cleanup completed" in output)
    check(f"{label}: rewrite or verification failure is safely reported", result["rewrite_status"] == "RESET")
    check(f"{label}: summary cleared", get_conversation_summary(conversation_id) == "")
    check(f"{label}: both checkpoints fenced at current history", checkpoints(conversation_id) == (high_water, high_water))
    excluded_ids = {row[0] for row in db_messages(conversation_id) if row[3]}
    check(
        f"{label}: all sources and only immediate assistant replies excluded",
        set(source_ids + assistant_ids + [request_id, answer_id]) <= excluded_ids,
    )
    check(f"{label}: no pre-cleanup summary inputs", get_messages_to_summarize(conversation_id, 1)[1] == [])
    check(f"{label}: no pre-cleanup extraction inputs", get_messages_for_memory_extraction(conversation_id, 100) == [])
    check(f"{label}: other conversation unchanged", other_fingerprint(other) == other_before)


def run():
    run_pairing_cases()

    run_unknown_provenance_case(
        "old-source-rewrite-failure",
        rewrite=RuntimeError("rewrite failed"),
        verify=NO,
        echo=RuntimeError("echo scan failed"),
        old_origin=True,
    )
    run_unknown_provenance_case(
        "verification-failure",
        rewrite="The user likes cricket and concise reports, and enjoys weekend walks.",
        verify=YES,
        echo="[]",
    )
    run_unknown_provenance_case(
        "verified-rewrite-still-cleared",
        rewrite="The user likes cricket and concise reports, and enjoys weekend walks.",
        verify=NO,
        echo="[]",
    )

    run_known_provenance_case("multi-source-rewrite-failure", source_count=2, verification_failure=False)
    run_known_provenance_case("single-source-verification-failure", source_count=1, verification_failure=True)


try:
    run()
finally:
    cleanup_created_conversations()

print("\nALL PHASE 1 TASK 2 CHECKS PASSED")
