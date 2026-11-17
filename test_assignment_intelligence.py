"""Deterministic memory decision regressions: all I/O is mocked."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql:///rag_test_scratch')
import testsafe
testsafe.require_scratch_db()
import unittest
from unittest.mock import patch
from services import automatic_memory_service as auto
from services import memory_decision_service as decision
from services.memory_consolidation_service import new_details_preserved


class IntelligenceTests(unittest.TestCase):
    def process(self, decision_value, *, confirmed=True, updated=True, candidates=None, text='User likes tea', **kwargs):
        if candidates is None:
            candidates = [(1, 'User enjoys tea')]
        with patch.object(auto, 'decide_memory_action', return_value=decision_value), \
             patch.object(auto, 'confirm_memory', return_value=confirmed) as confirm, \
             patch.object(auto, 'update_memory', return_value=updated) as update, \
             patch.object(auto, 'save_memory', return_value=True) as save:
            result = auto.process_memory('c', text, source_message_ids=[7], candidate_memories=candidates, **kwargs)
            return result, confirm, update, save

    def test_candidate_recall_older_than_twenty(self):
        rows = [(i, f'User project {i}') for i in range(1, 32)]
        with patch.object(auto, 'get_all_conversation_memories', return_value=rows) as all_rows, \
             patch.object(auto, 'get_recent_memories', side_effect=AssertionError('bounded recall')), \
             patch.object(auto, 'confirm_memory', return_value=True) as confirm, \
             patch.object(auto, 'decide_memory_action', side_effect=AssertionError('exact duplicate')):
            self.assertEqual(auto.process_memory('c', 'user project 1.', source_message_ids=[7]), 'SKIPPED')
        all_rows.assert_called_once_with('c', exclude_memory_ids=None, eligible_only=True)
        self.assertEqual(confirm.call_args.kwargs['memory_id'], 1)

    def test_confirmation_failure_is_unresolved(self):
        result, *_ = self.process({'action': 'DUPLICATE', 'memory_id': 1}, confirmed=False)
        self.assertEqual(result, 'UNCERTAIN')
        result, *_ = self.process({}, confirmed=False, candidates=[(1, 'User likes tea')])
        self.assertEqual(result, 'UNCERTAIN')

    def test_invalid_duplicate_cannot_checkpoint(self):
        for value in (None, [], {'action': 'DUPLICATE', 'memory_id': 999}):
            with self.subTest(value=value):
                result, *_ = self.process(value)
                self.assertEqual(result, 'UNCERTAIN')

    def test_update_failure_is_unresolved(self):
        result, *_ = self.process({'action': 'UPDATE', 'memory_id': 1, 'updated_memory': 'User now likes tea'}, updated=False)
        self.assertEqual(result, 'UNCERTAIN')

    def test_excluded_supplied_candidates_not_reconfirmed(self):
        result, confirm, _, save = self.process({}, candidates=[(1, 'User likes tea')], exclude_memory_ids=[1])
        self.assertEqual(result, 'SAVED')
        confirm.assert_not_called()
        save.assert_called_once()

    def test_status_and_negation_preserved(self):
        self.assertFalse(new_details_preserved('User no longer uses Python', 'User uses Python'))
        self.assertFalse(new_details_preserved('Project completed in 2026', 'Project in 2026'))
        self.assertTrue(new_details_preserved('Project completed in 2026', 'User project completed in 2026.'))

    def test_positive_statement_not_duplicate_of_negative(self):
        for new, old in [('User uses Python', 'User no longer uses Python'),
                         ('Project in 2026', 'Project completed in 2026')]:
            with self.subTest(new=new):
                self.assertFalse(new_details_preserved(new, old))
                result, confirm, update, save = self.process(
                    {'action': 'DUPLICATE', 'memory_id': 1}, text=new, candidates=[(1, old)])
                self.assertEqual(result, 'SAVED')
                confirm.assert_not_called()
                save.assert_called_once()

    def test_intentional_polarity_update_still_applied(self):
        result, _, update, save = self.process(
            {'action': 'UPDATE', 'memory_id': 1, 'updated_memory': 'User now uses Python'},
            text='User now uses Python', candidates=[(1, 'User no longer uses Python')])
        self.assertEqual(result, 'UPDATED')
        update.assert_called_once()
        save.assert_not_called()

    def test_storage_semantic_dedup_preserves_positive_correction(self):
        from services import memory_storage_service as storage
        from unittest.mock import MagicMock
        import numpy as np
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(1, 'User no longer uses Python', 0.01), (2,)]
        with patch.object(storage, 'get_connection', return_value=conn), \
             patch('services.legacy_provenance_quarantine.eligible_memory_ids', return_value={1}), \
             patch.object(storage, 'generate_embeddings', return_value=[np.zeros(384)]), \
             patch.object(storage, '_validate_source_messages'), \
             patch.object(storage, '_link_memory_sources') as link:
            self.assertTrue(storage.save_memory('c', 'User uses Python', source_message_ids=[7]))
        self.assertEqual(link.call_args.args[2], 2)
        self.assertTrue(any('INSERT INTO conversation_memories' in c.args[0] for c in cursor.execute.call_args_list))

    def test_lost_status_stored_separately(self):
        result, _, update, save = self.process({'action': 'UPDATE', 'memory_id': 1, 'updated_memory': 'User uses Python'}, text='User no longer uses Python')
        self.assertEqual(result, 'SAVED')
        update.assert_not_called()
        save.assert_called_once()

    def test_bad_model_shapes_fail_closed(self):
        for value in ('null', '[]', '{"action": []}', '{"action": "MAYBE"}'):
            with self.subTest(value=value), patch.object(decision, 'generate_answer', return_value=value):
                self.assertEqual(decision.decide_memory_action('tea', [(1, 'coffee')])['action'], 'UNCERTAIN')


if __name__ == '__main__':
    unittest.main()
