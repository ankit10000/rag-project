"""Exact fusion rejection causes; no database, models or providers."""
import os
import unittest
from unittest.mock import patch

from services.evidence_trace import answer_evidence_trace
from services.rrf_service import reciprocal_rank_fusion


def row(cid, text):
    return (cid, 'owned-doc', 1, text, .5)


class FusionTraceTests(unittest.TestCase):
    def decisions(self, candidates, limit):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}):
            with answer_evidence_trace('query', ['owned-doc']) as trace:
                result = reciprocal_rank_fusion([candidates], top_k=limit)
        event = next(e for e in trace.events if e['stage'] == 'rrf_selection')
        return result, event['metadata'], trace

    def test_duplicate_before_pool_fills_is_not_a_pool_limit(self):
        result, decision, trace = self.decisions(
            [row(1, 'Same text'), row(2, 'same   TEXT'), row(3, 'complementary fact')], 5)
        self.assertEqual([r['chunk'][0] for r in result], [1, 3])
        self.assertEqual(decision['removals'], [{'chunk_id': 2, 'reason': 'duplicate_content'}])
        ranking = next(e for e in trace.events if e['stage'] == 'fusion_rankings')
        self.assertEqual(len(ranking['metadata']['candidates']), 3)

    def test_candidates_not_examined_after_full_pool_are_cap_losses(self):
        _, decision, _ = self.decisions([row(1, 'same'), row(2, 'same'), row(3, 'other')], 1)
        self.assertEqual(decision['removals'], [
            {'chunk_id': 2, 'reason': 'rrf_pool_limit'},
            {'chunk_id': 3, 'reason': 'rrf_pool_limit'}])

    def test_trace_never_changes_fusion_output_or_source_identity(self):
        candidates = [row(1, 'same'), row(2, 'SAME'), row(3, 'extra')]
        expected = reciprocal_rank_fusion([candidates], top_k=5)
        actual, _, _ = self.decisions(candidates, 5)
        self.assertEqual(actual, expected)
        self.assertIs(actual[0]['chunk'], candidates[0])

    def test_hybrid_points_to_authoritative_rrf_decisions(self):
        from services import hybrid_search_service as hybrid
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), \
                patch.object(hybrid, 'semantic_search', return_value=[row(1, 'same'), row(2, 'SAME')]), \
                patch.object(hybrid, 'keyword_search', return_value=[]):
            with answer_evidence_trace('query', ['owned-doc']) as trace:
                hybrid.hybrid_search_detailed('query', rerank=False)
        selection = next(e['metadata'] for e in trace.events if e['stage'] == 'fusion_selection')
        self.assertEqual(selection['decision_trace_stage'], 'rrf_selection')
        self.assertEqual(selection['removals'], [])
        self.assertEqual(next(e['metadata']['removals'] for e in trace.events if e['stage'] == 'rrf_selection'),
                         [{'chunk_id': 2, 'reason': 'duplicate_content'}])

    def test_interleave_does_not_report_rrf_rejections(self):
        from services import hybrid_search_service as hybrid
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), \
                patch.object(hybrid, 'semantic_search', return_value=[row(1, 'one'), row(2, 'two')]), \
                patch.object(hybrid, 'keyword_search', return_value=[]):
            with answer_evidence_trace('query', ['owned-doc']) as trace:
                hybrid.hybrid_search_detailed('query', rerank=False, fusion='interleave', rrf_top_k=1)
        selection = next(e['metadata'] for e in trace.events if e['stage'] == 'fusion_selection')
        self.assertEqual(selection['algorithm'], 'interleave')
        self.assertEqual(selection['removals'], [{'chunk_id': 2, 'reason': 'interleave_pool_limit'}])


if __name__ == '__main__':
    unittest.main(verbosity=2)
