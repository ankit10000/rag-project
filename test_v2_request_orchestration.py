"""Synthetic request-boundary regressions. No DB, model or network access."""
import os
import unittest
from unittest.mock import patch

from services import rag_service as rag
from services.evidence_trace import answer_evidence_trace
from services.request_budget import RequestDeadlineExceeded
from services.tenant_context import tenant_scope

OWNER = '00000000-0000-4000-8000-000000000001'
DOC = '00000000-0000-4000-8000-000000000002'
QUESTION = 'Using private.pdf, give the budget and team size.'
EMPTY = {'results': [], 'rerank_status': 'skipped'}
BUDGET = {'chunk': (5,DOC,1,'Budget: 15 credits.'), 'rrf_score': 0.9, 'rerank_score': 4}
TEAM = {'chunk': (7,DOC,2,'Team size: 8 people.'), 'rrf_score': 0.8, 'rerank_score': 3}


class RoutingBoundaries(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {'RAG_V2': '1', 'RAG_DEVELOPMENT_TRACE': '1'}))

    def test_unknown_explicit_scope_survives_rewrite_and_memory_label(self):
        with patch('services.v2_evidence_recovery.explicit_document_scope',
                   side_effect=lambda q: [] if 'private.pdf' in q else None), \
                patch.object(rag,'rewrite_query',return_value='give budget and team size'), \
                patch.object(rag,'classify_question',return_value='MEMORY'), \
                patch.object(rag,'generate_answer',return_value='[MEMORY] We budgeted 10 credits.'), \
                patch.object(rag,'hybrid_search_detailed',return_value=EMPTY) as search:
            out = rag.ask_question(QUESTION)
        self.assertEqual(out['status'], 'abstained')
        self.assertFalse(out['citations'])
        search.assert_not_called()

    def test_verified_scope_allows_facet_recovery_after_empty_first_pass(self):
        def search(query, **kwargs):
            self.assertEqual(kwargs['document_names'], [DOC])
            if query == QUESTION:
                return EMPTY
            return {'results': [BUDGET if 'budget' in query.lower() else TEAM], 'rerank_status': 'ok'}

        with tenant_scope(OWNER), patch('services.v2_evidence_recovery.explicit_document_scope',return_value=[DOC]), \
                patch('services.v2_source_labels.label_owned_sources',side_effect=lambda bundle:bundle), \
                patch.object(rag,'hybrid_search_detailed',side_effect=search) as lookup, \
                patch.object(rag,'generate_answer',return_value='[DOCUMENT] The budget is 15 credits [S1]. The team has 8 people [S2].'), \
                answer_evidence_trace(QUESTION) as trace:
            result = rag._answer_from_route(QUESTION,QUESTION,'DOCUMENT',[],'')
        self.assertEqual(result['status'],'answered')
        self.assertEqual({c['chunk_id'] for c in result['citations']},{5,7})
        self.assertEqual(lookup.call_count,3)
        self.assertIn('evidence_recovery',[e['stage'] for e in trace.events])

    def test_failed_ranking_cannot_be_evidence_abstention(self):
        with patch.object(rag,'hybrid_search_detailed',return_value={'results':[],'rerank_status':'failed:OSError'}):
            out=rag._answer_from_route('What is the fee?','fee','DOCUMENT',[],'')
        self.assertEqual(out['status'],'error')
        self.assertFalse(out['citations'])

    def test_expired_rewrite_does_not_classify_or_retrieve(self):
        with patch.object(rag,'rewrite_query',side_effect=RequestDeadlineExceeded()), \
                patch.object(rag,'classify_question',return_value='DOCUMENT') as classify, \
                patch.object(rag,'hybrid_search_detailed',return_value=EMPTY) as lookup:
            with self.assertRaises(RequestDeadlineExceeded):
                rag.ask_question('How do the schedules compare?')
        classify.assert_not_called()
        lookup.assert_not_called()

    def test_rewrite_cannot_substitute_last_turns_named_person(self):
        history=[{'role':'user','content':'Who is Noel?'},{'role':'assistant','content':'A previous claim.'}]
        with patch.object(rag,'rewrite_query',return_value='Who is Noel?') as rewrite, \
                patch.object(rag,'classify_question',return_value='DOCUMENT'), \
                patch.object(rag,'hybrid_search_detailed',return_value=EMPTY) as search:
            rag.ask_question('Who is Priya?',history)
        self.assertEqual(rewrite.call_args.kwargs['history'],history[:1])
        self.assertEqual(search.call_args.args[0],'Who is Priya?')

    def test_removed_source_invalidates_stored_derivation_on_read(self):
        from unittest.mock import Mock
        from services.v2_turn_results import safe_result
        db=Mock()
        date_ref={'ref':'S1','chunk_id':1,'document':DOC,'page':1}
        person_ref={'ref':'S2','chunk_id':2,'document':DOC,'page':2}
        proof=dict(source_ref='S1',source_document=DOC,source_page=1,source_chunk_id=1,
                   person_evidence=person_ref,total_months=12)
        saved=dict(answer='Approximately 12 months [S1].',status='answered',
                   citations=[date_ref,person_ref],calculation=proof)
        for date_row,identity_row in [(None,None),(('fixture.pdf',),None),(('fixture.pdf',),('fixture.pdf',))]:
            with self.subTest(date_row=date_row,identity_row=identity_row):
                db.execute.return_value.fetchone.side_effect=[date_row,identity_row]
                current=safe_result(db,saved,OWNER)
                self.assertEqual('calculation' in current,bool(date_row and identity_row))
                self.assertEqual(saved['calculation'],proof)
