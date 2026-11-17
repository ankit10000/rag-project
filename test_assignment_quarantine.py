"""Deterministic quarantine/read-path tests; no database or provider calls."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql:///rag_test_scratch')
import testsafe
testsafe.require_scratch_db()
import unittest
from unittest.mock import MagicMock, patch
from services import legacy_provenance_quarantine as quarantine
from services.memory_context_service import assemble_memory_context
from services.legacy_provenance_classifier import MemoryProvenanceFacts, ModernLinkFact

CID = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'


def supported(mid, cid=CID, quarantined=False):
    return MemoryProvenanceFacts(mid, cid, (
        ModernLinkFact(mid + 10, cid, 'origin', 'user', True, cid, 'user'),
    ), quarantined=quarantined)


class QuarantineReadTests(unittest.TestCase):
    def test_optional_table_absent_is_read_only(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (False,)
        self.assertEqual(quarantine.active_quarantine_ids(CID, [1], connection=conn), set())
        self.assertEqual(conn.execute.call_count, 1)
        self.assertIn('to_regclass', conn.execute.call_args.args[0])

    def test_active_marker_query_is_conversation_scoped(self):
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(**{'fetchone.return_value': (True,)}),
                                    MagicMock(**{'fetchall.return_value': [(3,)]})]
        self.assertEqual(quarantine.active_quarantine_ids(CID, [3], connection=conn), {3})
        sql, params = conn.execute.call_args.args
        self.assertIn("status = 'quarantined'", sql)
        self.assertIn('conversation_id = %s', sql)
        self.assertEqual(str(params[0]), CID)

    def test_status_read_failure_does_not_release(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            quarantine.active_quarantine_ids(CID, [1], connection=conn)

    def test_supported_quarantined_and_foreign_facts_never_enter_context(self):
        facts = {1: supported(1), 2: supported(2, quarantined=True),
                 3: supported(3, OTHER), 4: MemoryProvenanceFacts(4, CID)}
        result = assemble_memory_context(CID, 'facts',
            search_fn=lambda **kw: [{'id': i, 'memory': f'fact {i}'} for i in facts],
            provenance_fn=lambda *args: facts)
        self.assertEqual([r['id'] for r in result['memories']], [1])
        self.assertEqual(result['excluded']['quarantined_or_excluded'], [2])
        self.assertEqual(result['excluded']['unverified_provenance'], [3, 4])

    def test_filter_preserves_order_and_excludes_marked_memories(self):
        with patch.object(quarantine, 'eligible_memory_ids', return_value={1, 3}):
            self.assertEqual(quarantine.filter_supported_memories(CID,
                [(3, 'three'), (2, 'two'), (1, 'one')], [1]), [(3, 'three')])

    def test_search_filters_before_top_k(self):
        import numpy as np
        from services import memory_search_service as search
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            (1, 'quarantined', 0.01), (2, 'supported', 0.1), (3, 'supported older', 0.2)]
        with patch.object(search, 'get_connection') as connect, \
                patch.object(search, 'generate_embeddings', return_value=[np.array([0., 1.])]), \
                patch.object(quarantine, 'eligible_memory_ids', return_value={2, 3}):
            connect.return_value.__enter__.return_value = conn
            result = search.search_memories(CID, 'query', top_k=1)
        self.assertEqual([r['id'] for r in result], [2])

    def test_empty_search_does_not_call_embedding(self):
        from services import memory_search_service as search
        with patch.object(search, 'generate_embeddings') as embed:
            self.assertEqual(search.search_memories(CID, 'query', top_k=0), [])
            embed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
