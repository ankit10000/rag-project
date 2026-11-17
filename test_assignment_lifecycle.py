"""Scratch-only integrated memory lifecycle with mocked embeddings/providers."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import io
import json
import unittest
from unittest.mock import patch
import numpy as np
from pgvector import Vector
from services.database import get_connection
from services.conversation_service import create_conversation, save_message, get_conversation_history, get_messages_for_memory_extraction
from services.conversation_service import clear_summary_and_advance_checkpoints, update_conversation_memory, update_memory_extraction_checkpoint
from services import memory_provenance_service as provenance
from services import memory_cleanup_service as cleanup
from services import memory_storage_service as storage
from services import legacy_provenance_quarantine as quarantine
from services import memory_service as memory_service
from services import automatic_memory_service as automatic
from services.memory_context_service import load_provenance_facts, assemble_memory_context
from services.memory_service import build_supported_memory_summary
from services.legacy_provenance_classifier import classify_memory, USER_SUPPORTED, MISSING_SOURCE
import main as app


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0], 'rag_test_scratch')
        self.cid = create_conversation('assignment lifecycle fixture')
        self.other = create_conversation('assignment isolated fixture')
        self.u1 = save_message(self.cid, 'user', 'I prefer tea.')
        self.a1 = save_message(self.cid, 'assistant', 'Tea noted.')
        self.u2 = save_message(self.cid, 'user', 'I prefer tea every morning.')
        self.mid = self.memory(self.cid, 'User prefers tea.', self.u1, [self.u1, self.u2])

    def tearDown(self):
        with get_connection() as conn:
            conn.execute('DELETE FROM conversations WHERE id = ANY(%s::uuid[])', ([self.cid, self.other],))

    def memory(self, cid, text, scalar=None, sources=()):
        with get_connection() as conn:
            mid = conn.execute('INSERT INTO conversation_memories(conversation_id,memory,embedding,source_message_id) VALUES(%s,%s,%s,%s) RETURNING id', (cid,text,Vector(np.eye(384)[0]),scalar)).fetchone()[0]
            for sid in sources:
                conn.execute("INSERT INTO memory_sources(conversation_id,memory_id,source_message_id,source_role,link_kind) VALUES(%s,%s,%s,'user','origin')", (cid,mid,sid))
        return mid

    def test_remaining_sources_and_cross_conversation_isolation(self):
        foreign = save_message(self.other, 'user', 'Unrelated')
        self.assertFalse(provenance.delete_message_with_provenance(self.cid, foreign)['deleted'])
        first = provenance.delete_message_with_provenance(self.cid, self.u1)
        self.assertEqual(first['still_supported'], [self.mid])
        self.assertEqual(classify_memory(load_provenance_facts(self.cid, [self.mid])[self.mid]).category, USER_SUPPORTED)
        second = provenance.delete_message_with_provenance(self.cid, self.u2)
        self.assertEqual(second['orphaned'], [self.mid])
        self.assertEqual(classify_memory(load_provenance_facts(self.cid, [self.mid])[self.mid]).category, MISSING_SOURCE)
        self.assertNotIn('tea', build_supported_memory_summary(self.cid))

    def test_deletion_rolls_back_all_provenance_on_failure(self):
        with patch.object(provenance, '_has_valid_user_source', side_effect=RuntimeError('injected after mutation')):
            with self.assertRaises(RuntimeError):
                provenance.delete_message_with_provenance(self.cid, self.u1)
        with get_connection() as conn:
            self.assertIsNotNone(conn.execute('SELECT id FROM messages WHERE id=%s', (self.u1,)).fetchone())
            self.assertEqual(conn.execute('SELECT source_message_id FROM conversation_memories WHERE id=%s', (self.mid,)).fetchone()[0], self.u1)
            self.assertEqual(conn.execute('SELECT count(*) FROM memory_sources WHERE memory_id=%s', (self.mid,)).fetchone()[0], 2)

    def test_quarantine_and_explicit_exclusions_block_all_context_paths(self):
        with patch.object(quarantine, 'active_quarantine_ids', return_value={self.mid}):
            self.assertEqual(build_supported_memory_summary(self.cid), '')
            blocked = quarantine.get_blocked_source_message_ids(self.cid)
            self.assertTrue({self.u1, self.a1, self.u2} <= blocked)
            context = assemble_memory_context(self.cid, 'tea', search_fn=lambda **kw: [{'id': self.mid, 'memory': 'User prefers tea.'}])
            self.assertEqual(context['text'], '')
        self.assertEqual(build_supported_memory_summary(self.cid, [self.mid]), '')

    def test_forgotten_fact_cannot_return_through_summary_history_or_extraction(self):
        details = storage.get_memory_details(self.cid, [self.mid])[self.mid]
        self.assertTrue(storage.delete_memory(self.cid, self.mid))
        with patch.object(cleanup, 'find_echo_message_ids', return_value=[]), patch.object(cleanup, 'rewrite_summary_without', return_value='UNCHANGED'):
            cleanup.apply_deletion_cleanup(self.cid, [details])
        self.assertEqual(build_supported_memory_summary(self.cid), '')
        self.assertFalse(any('tea' in m['content'].lower() for m in get_conversation_history(self.cid)))
        self.assertFalse(any('tea' in m['content'].lower() for m in get_messages_for_memory_extraction(self.cid)))

    def test_multiple_real_turns_keep_quarantined_facts_out_of_answer_context(self):
        with get_connection() as conn:
            conn.execute("UPDATE conversations SET summary = 'Stale unverified summary: user prefers tea.' WHERE id=%s", (self.cid,))
        with patch.object(quarantine, 'active_quarantine_ids', return_value={self.mid}), \
             patch.object(app, 'search_memories', return_value=[{'id': self.mid, 'memory': 'User prefers tea.'}]), \
             patch.object(app, 'ask_question', return_value={'answer': 'Tell me your preference.', 'sources': []}) as answer, \
             patch.object(app, 'extract_and_save_memories', return_value=[]), \
             contextlib.redirect_stdout(io.StringIO()):
            first = app.run_turn(self.cid, 'What do I prefer?')
            second = app.run_turn(self.cid, 'What about mornings?')
        self.assertEqual(first['kind'], 'answer')
        self.assertEqual(second['kind'], 'answer')
        self.assertEqual(answer.call_count, 2)
        for call in answer.call_args_list:
            self.assertNotIn('tea', call.kwargs['memory_summary'].lower())
            self.assertFalse(any('tea' in item['content'].lower() for item in call.kwargs['history']))

    def test_partial_batch_retry_is_idempotent_and_keeps_all_sources(self):
        first_source = save_message(self.cid, 'user', 'I build Orion.')
        second_source = save_message(self.cid, 'user', 'I know Rust.')
        batch = [
            {'id': first_source, 'role': 'user', 'content': 'I build Orion.'},
            {'id': second_source, 'role': 'user', 'content': 'I know Rust.'},
        ]
        payload = json.dumps([
            {'memory': 'User builds Orion.', 'source_message_ids': [first_source]},
            {'memory': 'User knows Rust.', 'source_message_ids': [second_source]},
        ])
        original_process = memory_service.process_memory
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs['new_memory'])
            if len(calls) == 2:
                raise RuntimeError('injected failure after first committed memory')
            return original_process(**kwargs)

        def embeddings(texts):
            return [np.eye(384)[1 if 'Orion' in text else 2] for text in texts]

        with patch.object(memory_service, 'generate_answer', return_value=payload), \
             patch.object(automatic, 'decide_memory_action', return_value={'action': 'NEW'}), \
             patch.object(storage, 'generate_embeddings', side_effect=embeddings), \
             contextlib.redirect_stdout(io.StringIO()):
            with patch.object(memory_service, 'process_memory', side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                    memory_service.extract_and_save_memories(self.cid, batch)
            with get_connection() as conn:
                self.assertEqual(conn.execute('SELECT memory_extraction_up_to_message_id FROM conversations WHERE id=%s', (self.cid,)).fetchone()[0], 0)
                rows = conn.execute('SELECT memory FROM conversation_memories WHERE conversation_id=%s ORDER BY id', (self.cid,)).fetchall()
                self.assertEqual([r[0] for r in rows], ['User prefers tea.', 'User builds Orion.'])
            # The first memory is already committed: retry must confirm it
            # idempotently and complete the second item rather than duplicate it.
            memory_service.extract_and_save_memories(self.cid, batch)
            memory_service.extract_and_save_memories(self.cid, batch)
        with get_connection() as conn:
            rows = conn.execute('SELECT cm.memory, ms.source_message_id FROM conversation_memories cm JOIN memory_sources ms ON ms.memory_id=cm.id WHERE cm.conversation_id=%s ORDER BY cm.id, ms.source_message_id', (self.cid,)).fetchall()
            self.assertEqual(rows, [
                ('User prefers tea.', self.u1), ('User prefers tea.', self.u2),
                ('User builds Orion.', first_source), ('User knows Rust.', second_source),
            ])

    def test_stale_checkpoint_and_summary_writes_cannot_undo_deletion_fence(self):
        clear_summary_and_advance_checkpoints(self.cid)
        update_memory_extraction_checkpoint(self.cid, self.u1)
        update_conversation_memory(self.cid, 'stale secret', self.u1)
        # Equal checkpoints must not restore a summary cleared by the fence.
        update_conversation_memory(self.cid, 'equal-checkpoint stale secret', self.u2)
        with get_connection() as conn:
            row = conn.execute('SELECT summary, summary_up_to_message_id, memory_extraction_up_to_message_id FROM conversations WHERE id=%s', (self.cid,)).fetchone()
        self.assertEqual(row, ('', self.u2, self.u2))

    def test_initial_summary_at_zero_is_allowed_but_not_after_fencing(self):
        update_conversation_memory(self.cid, 'Initial supported summary', 0)
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT summary FROM conversations WHERE id=%s', (self.cid,)).fetchone()[0], 'Initial supported summary')
        clear_summary_and_advance_checkpoints(self.cid)
        update_conversation_memory(self.cid, 'stale zero-checkpoint summary', 0)
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT summary FROM conversations WHERE id=%s', (self.cid,)).fetchone()[0], '')

    def test_missing_or_foreign_cleanup_sources_are_unknown_and_cannot_mutate_foreign_history(self):
        foreign_source = save_message(self.other, 'user', 'Private foreign fact')
        nonexistent_source = 9223372036854775807
        with patch.object(cleanup, 'find_echo_message_ids', return_value=[]), \
             patch.object(cleanup, 'rewrite_summary_without', return_value='UNCHANGED'), \
             contextlib.redirect_stdout(io.StringIO()):
            result = cleanup.apply_deletion_cleanup(self.cid, [{
                'id': 999, 'memory': 'unknown legacy fact',
                'source_message_ids': [foreign_source, nonexistent_source],
            }])
        self.assertEqual(result['provenance_status'], 'UNKNOWN')
        self.assertTrue(result['checkpoints_fenced'])
        with get_connection() as conn:
            self.assertFalse(conn.execute('SELECT context_excluded FROM messages WHERE id=%s', (foreign_source,)).fetchone()[0])
            self.assertEqual(conn.execute('SELECT summary_up_to_message_id, memory_extraction_up_to_message_id FROM conversations WHERE id=%s', (self.cid,)).fetchone(), (self.u2, self.u2))

    def test_scalar_only_provenance_reads_preserve_actual_roles_and_deduplicate(self):
        legacy = self.memory(self.cid, 'Historical assistant statement.', self.a1)
        sources = provenance.get_memory_sources(self.cid, legacy)
        self.assertEqual(sources, [{'message_id': self.a1, 'role': 'assistant', 'link_kind': 'legacy', 'content': 'Tea noted.'}])
        self.assertEqual(provenance.get_memories_for_message(self.cid, self.a1), [{'memory_id': legacy, 'memory': 'Historical assistant statement.', 'link_kind': 'legacy'}])
        # Existing modern + scalar representations are a single logical source.
        self.assertEqual([s['message_id'] for s in provenance.get_memory_sources(self.cid, self.mid)], [self.u1, self.u2])
        self.assertEqual(len([m for m in provenance.get_memories_for_message(self.cid, self.u1) if m['memory_id'] == self.mid]), 1)

    def test_assistant_only_cleanup_cannot_claim_known_user_provenance(self):
        with patch.object(cleanup, 'find_echo_message_ids', return_value=[]), \
             patch.object(cleanup, 'rewrite_summary_without', return_value='UNCHANGED'), \
             contextlib.redirect_stdout(io.StringIO()):
            result = cleanup.apply_deletion_cleanup(self.cid, [{
                'id': 999, 'memory': 'Historical assistant-only fact',
                'source_message_id': self.a1, 'source_message_ids': [self.a1],
            }])
        self.assertEqual(result['provenance_status'], 'UNKNOWN')
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertTrue(result['checkpoints_fenced'])
        self.assertEqual(get_conversation_history(self.cid), [])
        self.assertEqual(get_messages_for_memory_extraction(self.cid), [])
        with get_connection() as conn:
            self.assertEqual(conn.execute('SELECT summary_up_to_message_id, memory_extraction_up_to_message_id FROM conversations WHERE id=%s', (self.cid,)).fetchone(), (self.u2, self.u2))


if __name__ == '__main__':
    unittest.main()
