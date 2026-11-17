"""Deterministic provenance boundary and privacy regression tests."""
import testsafe
testsafe.require_scratch_db()

import unittest
from unittest.mock import MagicMock, patch

from services import conversation_service as conversation
from services import memory_cleanup_service as cleanup
from services import memory_provenance_service as provenance
from services import memory_storage_service as storage

CID = '00000000-0000-0000-0000-000000000001'


class ProvenanceBoundaries(unittest.TestCase):
    def test_invalid_read_ids_never_reach_sql(self):
        for value in [True, False, 1.8, 1.0, {}, [], -1, 0, '1.2']:
            with self.subTest(value=value), patch.object(provenance, 'get_connection') as connect:
                self.assertEqual(provenance.get_memory_sources(CID, value), [])
                self.assertEqual(provenance.get_memories_for_message(CID, value), [])
                connect.assert_not_called()

    def test_exclusion_does_not_coerce_bool_or_float(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = [(2,)]
        with patch.object(conversation, 'get_connection', return_value=conn):
            self.assertEqual(conversation.mark_messages_excluded(CID, [True, 1.2, 1.0, '2', 2]), 1)
        self.assertEqual(conn.execute.call_args.args[1][1], [2])

    def test_echo_selection_never_coerces_malformed_ids(self):
        with patch.object(cleanup, 'get_live_messages', return_value=[{'id': 1, 'role': 'user', 'content': 'fact'}, {'id': 2, 'role': 'assistant', 'content': 'fact'}]), patch.object(cleanup, 'generate_answer', return_value='[true, 1.4, 2.0, "1", 2]'):
            self.assertEqual(cleanup.find_echo_message_ids(CID, ['fact']), [2])

    def test_validation_locks_only_live_user_sources(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [(9, 'user')]
        storage._validate_source_messages(cursor, CID, [9])
        sql = cursor.execute.call_args.args[0]
        self.assertIn('NOT context_excluded', sql)
        self.assertIn('FOR SHARE', sql)
        cursor.fetchall.return_value = []
        with self.assertRaises(ValueError):
            storage._validate_source_messages(cursor, CID, [9])

    def test_link_explicitly_records_user_role(self):
        cursor = MagicMock()
        storage._link_memory_source(cursor, CID, 1, 9)
        sql = cursor.execute.call_args.args[0]
        self.assertIn('source_role', sql)
        self.assertIn("'user'", sql)

    def test_history_optional_ids_preserves_default_shape(self):
        for include_ids in [False, True]:
            conn = MagicMock()
            conn.__enter__.return_value = conn
            first, second = MagicMock(), MagicMock()
            first.fetchone.return_value = (0,)
            second.fetchall.return_value = [(9, 'user', 'hello')]
            conn.execute.side_effect = [first, second]
            with patch.object(conversation, 'get_connection', return_value=conn):
                result = conversation.get_conversation_history(CID, include_ids=include_ids)
            expected = {'role': 'user', 'content': 'hello'}
            if include_ids:
                expected['id'] = 9
            self.assertEqual(result, [expected])

    def test_duplicate_query_only_uses_supported_ids(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(5, 'user')]
        cursor.fetchone.side_effect = [None, (9,)]
        embedding = MagicMock()
        embedding.tolist.return_value = [1.0, 0.0]
        with patch.object(storage, 'get_connection', return_value=conn), patch.object(storage, 'generate_embeddings', return_value=[embedding]), patch('services.legacy_provenance_quarantine.eligible_memory_ids', return_value={2, 7}):
            self.assertTrue(storage.save_memory(CID, 'fact', source_message_ids=[5]))
        nearest = next(call for call in cursor.execute.call_args_list if 'ORDER BY embedding' in call.args[0])
        self.assertIn('id = ANY(%s::bigint[])', nearest.args[0])
        self.assertEqual(nearest.args[1][2], [2, 7])

    def test_missing_or_foreign_cleanup_sources_force_fence(self):
        for owned in [set(), {8}]:
            with self.subTest(owned=owned), patch.object(cleanup, '_owned_source_ids', return_value=owned), patch.object(cleanup, 'get_paired_assistant_ids', return_value=[]), patch.object(cleanup, 'mark_messages_excluded', return_value=0) as exclude, patch.object(cleanup, 'find_echo_message_ids', return_value=[]), patch.object(cleanup, 'rewrite_summary_without', return_value='NO_SUMMARY'), patch.object(cleanup, 'clear_summary_and_advance_checkpoints') as fence:
                result = cleanup.apply_deletion_cleanup(CID, [{'memory': 'fact', 'source_message_ids': [8, 9]}])
                self.assertEqual(result['status'], 'INCOMPLETE')
                self.assertTrue(result['checkpoints_fenced'])
                fence.assert_called_once_with(CID)
                self.assertEqual(exclude.call_args_list[0].args[1], sorted(owned))

    def test_source_ownership_lookup_is_conversation_scoped(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = [(8,)]
        with patch.object(cleanup, 'get_connection', return_value=conn):
            self.assertEqual(cleanup._owned_source_ids(CID, [8, 9]), {8})
        self.assertIn('conversation_id = %s', conn.execute.call_args.args[0])
        self.assertEqual(str(conn.execute.call_args.args[1][0]), CID)

    def test_checkpoint_updates_cannot_lower_fence(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(conversation, 'get_connection', return_value=conn):
            conversation.update_memory_extraction_checkpoint(CID, 5)
            conversation.update_conversation_memory(CID, 'stale', 5)
        extraction, summary = conn.execute.call_args_list
        self.assertIn('GREATEST', extraction.args[0])
        self.assertIn('COALESCE(summary_up_to_message_id, 0) < %s', summary.args[0])
        self.assertEqual(summary.args[1][-1], 5)

    def test_provenance_reads_reconcile_scalar_without_duplicate_links(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = [(8, 'assistant', 'legacy', 'old')]
        with patch.object(provenance, 'get_connection', return_value=conn):
            result = provenance.get_memory_sources(CID, 4)
        self.assertEqual(result[0]['role'], 'assistant')
        sql = conn.execute.call_args.args[0]
        self.assertIn('UNION ALL', sql)
        self.assertIn('NOT EXISTS', sql)
        self.assertIn('m.conversation_id = cm.conversation_id', sql)
        conn.execute.return_value.fetchall.return_value = [(4, 'fact', 'legacy')]
        with patch.object(provenance, 'get_connection', return_value=conn):
            self.assertEqual(provenance.get_memories_for_message(CID, 8)[0]['memory_id'], 4)
        self.assertIn('NOT EXISTS', conn.execute.call_args.args[0])

    def test_source_support_requires_live_history(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (False,)
        self.assertFalse(provenance._has_valid_user_source(conn, CID, 3))
        self.assertEqual(conn.execute.call_args.args[0].count('NOT source_message.context_excluded'), 2)


if __name__ == '__main__':
    unittest.main()
