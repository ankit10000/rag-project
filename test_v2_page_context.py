import os
import unittest
from unittest.mock import MagicMock, patch

from services.v2_page_context import expand_page_context, enumeration_request
from services.tenant_context import tenant_scope

OWNER = '25973a8a-09db-4a15-a686-304a5c986eec'
ANCHOR = {'chunk': (1, 'owned-doc', 15, 'Phase 1 Planning 0–6; Phase 2 MVP 6–15', .1),
          'rrf_score': .03, 'rerank_score': 2.3}
ROWS = [(1, 'owned-doc', 15, ANCHOR['chunk'][3], 0),
        (2, 'owned-doc', 15, 'Phase 3 Pilot 15–21', 1),
        (3, 'owned-doc', 15, 'Phase 4 Launch 21–30', 2)]


class PageContinuityTests(unittest.TestCase):
    def run_expansion(self, rows=ROWS, limit=8):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        with tenant_scope(OWNER), patch('services.database.get_connection') as connect:
            connect.return_value.__enter__.return_value = conn
            result = expand_page_context('List all four implementation phases and month ranges', [ANCHOR], limit)
        return result, conn

    def test_enumeration_intent_not_all_questions(self):
        self.assertTrue(enumeration_request('List the roadmap phases'))
        self.assertTrue(enumeration_request('What are all four implementation phases?'))
        self.assertFalse(enumeration_request('What is the budget?'))

    def test_recovers_split_list_without_inventing_rank_scores(self):
        result, conn = self.run_expansion()
        self.assertEqual([x['chunk'][0] for x in result], [1, 2, 3])
        self.assertIsNone(result[1]['rrf_score'])
        self.assertNotIn('rerank_score', result[1])
        self.assertEqual(ANCHOR['rerank_score'], 2.3)
        sql, args = conn.execute.call_args.args
        self.assertIn("d.status='ready'", sql)
        self.assertIn('a.document_id=c.document_id', sql)
        self.assertIn('a.page_number=c.page_number', sql)
        self.assertEqual(args, (1, OWNER, OWNER, 'owned-doc', 15, 9))

    def test_hard_budget_and_duplicate_dedup(self):
        result, _ = self.run_expansion([ROWS[0], ROWS[0], ROWS[1], ROWS[2]], 2)
        self.assertEqual([x['chunk'][0] for x in result], [1, 2])

    def test_no_owner_or_non_enumeration_never_reads_database(self):
        with patch('services.database.get_connection') as connect:
            self.assertEqual(expand_page_context('List all phases', [ANCHOR]), [ANCHOR])
            with tenant_scope(OWNER):
                self.assertEqual(expand_page_context('What is the budget?', [ANCHOR]), [ANCHOR])
            connect.assert_not_called()

    def test_absent_or_deleted_anchor_adds_no_evidence(self):
        result, _ = self.run_expansion([])
        self.assertEqual(result, [ANCHOR])

    def test_pipeline_uses_continuations_after_margin_filter(self):
        from services import rag_service as rag
        from services.context_assembly_service import assemble_context
        expanded = [ANCHOR] + [{'chunk': (*r[:4], None), 'rrf_score': None} for r in ROWS[1:]]
        outcome = dict(answer='test', status='answered', sources=[], citations=[], issues=[], attempts=1)
        with patch.dict(os.environ, {'RAG_V2': '1'}), patch.object(rag, 'hybrid_search_detailed', return_value={'results':[ANCHOR], 'rerank_status':'ok'}), patch('services.v2_page_context.expand_page_context', return_value=expanded) as expand, patch.object(rag, 'generate_grounded_answer', return_value=outcome) as generate:
            rag._answer_from_route('List all phases', 'roadmap phases', 'DOCUMENT', [], '')
        self.assertEqual(expand.call_args.args[1], [ANCHOR])
        text = generate.call_args.kwargs['bundle']['context_text']
        self.assertIn('Phase 3 Pilot', text)
        self.assertIn('Phase 4 Launch', text)
        self.assertEqual(assemble_context(expanded)['sources'][2]['page_number'], 15)

    def test_legacy_pipeline_does_not_expand(self):
        from services import rag_service as rag
        outcome = dict(answer='test', status='answered', sources=[], citations=[], issues=[], attempts=1)
        with patch.dict(os.environ, {'RAG_V2': '0'}), patch.object(rag, 'hybrid_search_detailed', return_value={'results':[ANCHOR], 'rerank_status':'ok'}), patch('services.v2_page_context.expand_page_context') as expand, patch.object(rag, 'generate_grounded_answer', return_value=outcome):
            rag._answer_from_route('List all phases', 'phases', 'DOCUMENT', [], '')
        expand.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
