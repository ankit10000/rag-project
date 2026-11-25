"""Development tracing and bounded source recovery; deterministic, no providers."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.evidence_trace import (answer_evidence_trace, trace_event,
                                     trace_candidates, diagnose_expected_evidence)
from services.tenant_context import tenant_scope
from services.v2_evidence_recovery import (explicit_document_scope,
                                           recover_complementary_evidence)

OWNER = '25973a8a-09db-4a15-a686-304a5c986eec'
DOC = 'e3160c67-ee6d-4983-9029-8273bd35525a'


def hit(cid, page, content, score=1, doc=DOC):
    return {'chunk': (cid, doc, page, content, .1), 'rrf_score': .02, 'rerank_score': score}


class TraceTests(unittest.TestCase):
    def test_trace_requires_explicit_development_opt_in(self):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '0'}):
            with self.assertRaises(RuntimeError), answer_evidence_trace('private question'):
                pass
        trace_event('inactive', raw={'answer': 'no output'})

    def test_default_trace_has_metadata_not_private_text_or_secrets(self):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), answer_evidence_trace('private question', [DOC]) as trace:
            trace_event('generated', {'api_key': 'verysecret'}, raw={'answer': 'private answer', 'password': 'anothersecret'})
            trace_candidates('vector_candidates', [hit(1, 3, 'private source')])
        text = json.dumps(trace.snapshot())
        for secret in ['private question', 'private answer', 'private source', 'verysecret', 'anothersecret']:
            self.assertNotIn(secret, text)
        candidate = trace.snapshot()['events'][1]['metadata']['candidates'][0]
        self.assertEqual(candidate['content_fingerprint']['chars'], len('private source'))

    def test_raw_trace_still_redacts_keys_and_writes_private_exclusive_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'raw' / 'trace.json'
            with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), answer_evidence_trace('selected question', [DOC], include_raw=True) as trace:
                trace_event('prompt', raw={'prompt': 'authorized source', 'gemini_api_key': 'nope'})
            trace.write(destination)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)
            content = destination.read_text()
            self.assertIn('authorized source', content)
            self.assertNotIn('nope', content)
            with self.assertRaises(FileExistsError):
                trace.write(destination)

    def test_nested_trace_restores_outer_and_snapshot_is_detached(self):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), answer_evidence_trace('outer') as outer:
            with answer_evidence_trace('inner') as inner:
                trace_event('inside')
            trace_event('outside')
        self.assertEqual([x['stage'] for x in inner.snapshot()['events']], ['inside'])
        snapshot = outer.snapshot(); snapshot['events'].clear()
        self.assertEqual([x['stage'] for x in outer.snapshot()['events']], ['outside'])

    def test_exact_filter_reason_and_stage_attribution(self):
        first, second = hit(1, 1, 'part 1'), hit(2, 2, 'part 2')
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), answer_evidence_trace('question') as trace:
            trace_candidates('vector_candidates', [first, second])
            trace_candidates('rerank_filter', [first, second], selected_ids=[1], removal_reason={2: 'score_below_best_minus_margin'})
            trace_candidates('after_adaptive_filter', [first])
            trace_candidates('final_context', [first])
        self.assertEqual(diagnose_expected_evidence(trace, [1, 2]), ['RERANK_FILTER_LOSS'])
        self.assertEqual(trace.snapshot()['events'][1]['metadata']['candidates'][1]['removal_reason'], 'score_below_best_minus_margin')
        self.assertEqual(diagnose_expected_evidence(trace, [3]), ['RETRIEVAL_MISS'])
        self.assertEqual(diagnose_expected_evidence(trace, [1], answer_missing_items=['field']), ['GENERATION_OMISSION'])
        self.assertEqual(diagnose_expected_evidence(trace, [1], validation_issues=['unsupported_number']), ['ANSWER_VALIDATION_ERROR'])
        self.assertEqual(diagnose_expected_evidence(trace, [], source_information_absent=True), ['SOURCE_INFORMATION_ABSENT'])
        self.assertEqual(diagnose_expected_evidence(trace, [], question_ambiguous=True), ['QUESTION_AMBIGUOUS'])

    def test_budget_loss_attribution(self):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}), answer_evidence_trace('question') as trace:
            trace_candidates('lexical_candidates', [hit(1, 1, 'one'), hit(2, 2, 'two')])
            trace_candidates('after_adaptive_filter', [hit(1, 1, 'one'), hit(2, 2, 'two')])
            trace_candidates('final_context', [hit(1, 1, 'one')])
        self.assertEqual(diagnose_expected_evidence(trace, [1, 2]), ['CONTEXT_BUDGET_LOSS'])


class RecoveryTests(unittest.TestCase):
    def recover(self, query, originals, search, *, scope=(DOC,), **kw):
        with tenant_scope(OWNER):
            return recover_complementary_evidence(query, query, originals, {'results': originals}, search,
                                                   document_names=scope, **kw)

    def test_explicit_scope_requires_owner_ready_document_and_real_filename(self):
        conn = MagicMock(); conn.execute.return_value.fetchall.return_value = [(DOC, 'Executive Summary.pdf', 'ready')]
        with tenant_scope(OWNER), patch('services.database.get_connection') as connect:
            connect.return_value.__enter__.return_value = conn
            self.assertEqual(explicit_document_scope('What is in Executive Summary.pdf?'), [DOC])
        sql, args = conn.execute.call_args.args
        self.assertIn("status<>'deleted'", sql); self.assertIn('owner_id=%s', sql)
        self.assertEqual(args[0], OWNER)
        with patch('services.database.get_connection') as connect:
            self.assertIsNone(explicit_document_scope('Executive Summary.pdf'))
            connect.assert_not_called()

    def test_unavailable_explicit_file_is_closed_scope(self):
        conn = MagicMock(); conn.execute.return_value.fetchall.return_value = []
        with tenant_scope(OWNER), patch('services.database.get_connection') as connect:
            connect.return_value.__enter__.return_value = conn
            self.assertEqual(explicit_document_scope('Question about Secret.pdf'), [])
        search = MagicMock()
        result = self.recover('Give budget and team in Secret.pdf', [hit(1, 1, 'unrelated source')], search, scope=[])
        self.assertEqual(result['results'], []); search.assert_not_called()

    def test_compound_fields_keep_complementary_low_score_facet_anchor(self):
        original = hit(1, 9, 'cloud budget $200K per year', score=8)
        database = hit(2, 13, 'PostgreSQL stores user accounts', score=-2)
        budget = hit(3, 9, 'Annual cloud budget is $200K', score=3)
        search = MagicMock(side_effect=[{'results':[database], 'rerank_status':'ok'}, {'results':[budget], 'rerank_status':'ok'}])
        result = self.recover('Which database stores accounts and what is the annual cloud budget?', [original], search)
        self.assertEqual([x['chunk'][0] for x in result['results']], [1, 2, 3])
        self.assertEqual(result['facet_queries'], 2)
        self.assertTrue(all(call.kwargs['document_names'] == [DOC] for call in search.call_args_list))

    def test_wrong_document_facet_never_admitted_even_if_search_contract_breaks(self):
        original = hit(1, 1, 'Budget and team details')
        intruder = hit(9, 1, 'Other tenant source', doc='other-document')
        search = MagicMock(return_value={'results':[intruder], 'rerank_status':'ok'})
        result = self.recover('Give budget and team size', [original], search)
        self.assertEqual(result['results'], [original])

    def test_no_owner_no_recovery_and_simple_question_no_extra_search(self):
        original = [hit(1, 1, 'Product details')]; search = MagicMock()
        result = recover_complementary_evidence('List all features', '', original, {}, search)
        self.assertEqual(result['results'], original)
        result = self.recover('What is the product?', original, search)
        self.assertEqual(result['results'], original); search.assert_not_called()

    def test_ambiguous_retained_documents_do_not_associate_missing_facts(self):
        originals = [hit(1, 1, 'Budget'), hit(2, 1, 'Team', doc='other-document')]
        with tenant_scope(OWNER), patch('services.v2_evidence_recovery.explicit_document_scope', return_value=None):
            search = MagicMock()
            result = recover_complementary_evidence('Give budget and team', '', originals, {}, search)
        self.assertEqual(result['results'], originals); search.assert_not_called()

    def test_adjacent_budget_section_recovered_across_page_boundary(self):
        original = hit(198, 16, 'Total budget ballpark $1.6M–$3M')
        adjacent = [(197, DOC, 15, 'Budget Range: Personnel $1.2M–$2M; Hardware $300K')]
        with patch('services.v2_evidence_recovery._adjacent_chunks', return_value=adjacent) as neighbours:
            result = self.recover('List the budget components and total ballpark', [original], MagicMock())
        self.assertEqual([x['chunk'][0] for x in result['results']], [198, 197])
        self.assertEqual(result['results'][1]['chunk'][2], 15)
        self.assertIsNone(result['results'][1]['rrf_score'])
        self.assertEqual(neighbours.call_args.args[1:], ([DOC], OWNER))

    def test_adjacent_sql_has_source_and_owner_identity_and_bounded_limit(self):
        from services.v2_evidence_recovery import _adjacent_chunks
        conn = MagicMock(); conn.execute.return_value.fetchall.return_value = []
        with patch('services.database.get_connection') as connect:
            connect.return_value.__enter__.return_value = conn
            _adjacent_chunks((1, DOC, 3, 'source'), [DOC], OWNER)
        self.assertEqual(conn.execute.call_count, 2)
        for call in conn.execute.call_args_list:
            sql, args = call.args
            self.assertIn('a.document_id=c.document_id', sql)
            self.assertIn('c.owner_id=%s AND d.owner_id=%s', sql)
            self.assertIn("d.status='ready'", sql)
            self.assertIn('LIMIT 1', sql)
            self.assertEqual(args, (1, OWNER, OWNER, [DOC]))

    def test_structural_count_conflict_recovers_second_continuation(self):
        first = hit(194, 15, 'Roughly 3 phases. Phase 1 planning. Phase 2 MVP.')
        continuation = {194: [(195, DOC, 15, 'Phase 3 Pilot and Feedback')],
                        195: [(194, DOC, 15, first['chunk'][3]), (196, DOC, 15, 'Phase 4 Launch and Scale')]}
        with patch('services.v2_evidence_recovery._adjacent_chunks', side_effect=lambda a,s,o: continuation.get(a[0], [])) as neighbors:
            result = self.recover('Does the roadmap stated phase count agree with its listed phases? Report any inconsistency.', [first], MagicMock())
        self.assertEqual([x['chunk'][0] for x in result['results']], [194, 195, 196])
        self.assertLessEqual(neighbors.call_count, 4)

    def test_actual_requested_section_beats_high_rank_overview(self):
        original = hit(131, 1, 'Core features include video lessons, notes, quizzes and Q&A.', 5.2)
        summary = hit(204, 17, 'Feature Prioritization (MVP vs Later): See Table 1 for feature list.', 4)
        details = hit(138, 2, 'Suggested Additional Features: Adaptive Learning Paths; Multilingual Support; Offline Access & Mobile App.', -1.8)
        search = MagicMock(return_value={'results': [summary], 'rerank_status':'ok'})
        with tenant_scope(OWNER), patch('services.v2_evidence_recovery._adjacent_chunks', return_value=[]):
            result = recover_complementary_evidence('List the core MVP features and all suggested additional features', '', [original],
                    {'results': [original, summary, details], 'rerank_status':'ok'}, search, document_names=[DOC])
        self.assertEqual([x['chunk'][0] for x in result['results']][:2], [131, 138])
        self.assertEqual(result['results'][1]['chunk'][2], 2)

    def test_failed_facet_rank_never_claimed_as_verified(self):
        original = hit(1, 1, 'Budget details')
        unranked = {'chunk': (2, DOC, 2, 'Team has 10 people', .2), 'rrf_score': .02}
        search = MagicMock(side_effect=[{'results': [original], 'rerank_status':'ok'},
                                        {'results': [unranked], 'rerank_status':'failed:RuntimeError'}])
        result = self.recover('Give budget and team size', [original], search)
        self.assertEqual(result['rerank_status'], 'failed:RuntimeError')

    def test_capital_prose_lost_by_margin_is_recovered_without_extra_search(self):
        original = hit(164, 8, 'On-premises GPU servers have hardware costs.', -7.49)
        table = hit(203, 17, 'Hosting Options: Upfront Cost Public Cloud None.', -7.57)
        prose = hit(166, 9, 'Cloud GPU rental: This approach avoids CapEx and you pay for what you use.', -9.95)
        search = MagicMock()
        with tenant_scope(OWNER):
            result = recover_complementary_evidence('Does public cloud require upfront capital expenditure?', '', [original, table],
                {'results': [original, table, prose], 'rerank_status':'ok'}, search, document_names=[DOC])
        self.assertIn(166, [x['chunk'][0] for x in result['results']])
        search.assert_not_called()

    def test_capital_synonym_probe_only_when_no_existing_prose_and_scoped(self):
        original = hit(203, 17, 'Hosting Options: Upfront Cost Public Cloud None.', -7.57)
        prose = hit(166, 9, 'Cloud GPU rental avoids CapEx; pay as you go.', .66)
        search = MagicMock(return_value={'results':[prose], 'rerank_status':'ok'})
        result = self.recover('Does public cloud require upfront capital expenditure?', [original], search)
        self.assertEqual(result['facet_queries'], 1)
        self.assertEqual(search.call_args.args[0], 'public cloud hosting CapEx upfront costs capital expenditure')
        self.assertEqual(search.call_args.kwargs['document_names'], [DOC])
        self.assertIn(166, [x['chunk'][0] for x in result['results']])

    def test_capital_term_recovery_does_not_turn_weak_table_into_evidence(self):
        original = hit(203, 17, 'Hosting Options: Upfront Cost Public Cloud None.', -7.57)
        search = MagicMock(return_value={'results':[original], 'rerank_status':'ok'})
        result = self.recover('Does public cloud require upfront capital expenditure?', [original], search)
        self.assertEqual(result['results'], [original])
        self.assertFalse(result['changed'])

    def test_capital_source_positive_relation_preserved_and_other_cloud_entity_rejected(self):
        from services.v2_evidence_recovery import _capital_prose_candidates
        positive = hit(1, 1, 'Public cloud requires upfront capital expenditure for reserved hardware.')
        negative = hit(2, 1, 'Public cloud avoids CapEx for this plan.')
        private = hit(3, 1, 'Private cloud requires upfront capital expenditure.')
        chosen = _capital_prose_candidates('public cloud', [positive, private, negative], [DOC])
        self.assertEqual([x['chunk'][0] for x in chosen], [1, 2])

    def test_char_budget_preserves_full_complementary_chunks_and_exact_dedup_only(self):
        from services.v2_evidence_recovery import _pack
        originals = [hit(1, 1, 'a' * 20), hit(2, 2, 'b' * 15), hit(3, 2, 'b' * 15 + ' complementary'), hit(4, 2, 'b' * 15)]
        selected, dropped = _pack(originals, 3, 50)
        self.assertEqual([x['chunk'][0] for x in selected], [1, 2])
        self.assertEqual(dropped, [{'chunk_id':3, 'reason':'character_budget'}])


class FusionAttributionTests(unittest.TestCase):
    def test_metadata_only_trace_hashes_unrecognized_nested_raw_fields(self):
        from services.evidence_trace import answer_evidence_trace, trace_event
        import json
        from unittest.mock import patch
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}):
            with answer_evidence_trace('private-question-sentinel') as trace:
                trace_event('question_category', raw={'search_query': 'private-rewrite-sentinel'})
                trace_event('answer_validation', raw={'coverage': {
                    'decomposition_clauses': ['private-clause-sentinel'],
                    'facets': [{'literal_titles': ['private-heading-sentinel']}],
                    'api_key': 'private-key-sentinel'}})
        serialized = json.dumps(trace.snapshot())
        for value in ('private-question-sentinel', 'private-rewrite-sentinel',
                      'private-clause-sentinel', 'private-heading-sentinel', 'private-key-sentinel'):
            self.assertNotIn(value, serialized)
        self.assertIn('sha256', serialized)

    def test_candidate_lost_before_reranking_is_retrieval_not_rerank_loss(self):
        from services.evidence_trace import diagnose_expected_evidence
        trace = {'events': [
            {'stage': 'vector_candidates', 'metadata': {'candidates': [{'chunk_id': 71}, {'chunk_id': 72}]}},
            {'stage': 'rrf_results', 'metadata': {'candidates': [{'chunk_id': 71}]}},
            {'stage': 'after_adaptive_filter', 'metadata': {'candidates': [{'chunk_id': 71}]}},
            {'stage': 'final_context', 'metadata': {'candidates': [{'chunk_id': 71}]}},
        ]}
        self.assertEqual(diagnose_expected_evidence(trace, [72]), ['RETRIEVAL_MISS'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
