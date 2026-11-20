"""Development replay safety/metric tests. No database or provider I/O."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import v2_reliability_check as check
from services.evidence_trace import answer_evidence_trace, trace_candidates, trace_event, diagnose_expected_evidence


class ReliabilityRuntimeTests(unittest.TestCase):
    def test_source_review_checks_match_fixed_case_set(self):
        plan = json.loads(check.PLAN.read_text())
        self.assertEqual(set(check.CHECKS), {c['id'] for c in plan['cases']})
        self.assertEqual(len(plan['cases']), 13)
        self.assertEqual(plan['max_provider_calls'], 52)

    def test_subset_uses_original_questions_and_rejects_new_expectations(self):
        plan = json.loads(check.PLAN.read_text())
        chosen = check.select_cases(plan, ['conflict', 'partial'])
        self.assertEqual(chosen, [c for c in plan['cases'] if c['id'] in ('conflict', 'partial')])
        for bad in ([], ['new-question'], ['conflict', 'conflict']):
            with self.assertRaises(ValueError):
                check.select_cases(plan, bad)

    def test_long_section_requires_all_six_additional_features(self):
        labels = [f['label'] for f in check.CHECKS['long_section']['facts']]
        for label in ('adaptive learning', 'doubt forum', 'progress analytics', 'gamification', 'multilingual', 'offline/mobile'):
            self.assertIn(label, labels)
        answer = 'Video lessons, notes, test series, Q&A, adaptive learning, forum, analytics, gamification.'
        facts = check.check_facts(answer, check.CHECKS['long_section']['facts'])
        self.assertEqual([x['label'] for x in facts if not x['observed']], ['multilingual', 'offline/mobile'])

    def test_artifacts_are_private_exclusive_create(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'run' / 'result.json'
            check.private_json(path, {'value': 'private'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError):
                check.private_json(path, {'value': 'changed'})
            self.assertEqual(json.loads(path.read_text()), {'value': 'private'})

    def test_default_trace_has_no_private_source_or_secret(self):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '1'}):
            with answer_evidence_trace('private query', ['owned-doc']) as trace:
                trace_candidates('vector_candidates', [(1, 'owned-doc', 2, 'private source content')])
                trace_event('generation', raw={'prompt': 'private prompt', 'api_key': 'configured-secret'})
        serialized = json.dumps(trace.snapshot())
        for private in ('private query', 'private source content', 'private prompt', 'configured-secret'):
            self.assertNotIn(private, serialized)
        self.assertIn('sha256', serialized)

    def test_trace_opt_in_required(self):
        with patch.dict(os.environ, {'RAG_DEVELOPMENT_TRACE': '0'}):
            with self.assertRaises(RuntimeError):
                with answer_evidence_trace('query'):
                    pass

    def test_guard_refuses_rag_db_before_connect(self):
        import psycopg
        with patch.object(psycopg, 'connect') as original:
            with check.guarded_scratch_connections():
                with self.assertRaises(ValueError):
                    psycopg.connect('postgresql://localhost/rag_db')
            original.assert_not_called()

    def test_guard_verifies_actual_database_before_returning_connection(self):
        import psycopg
        fake = MagicMock()
        fake.execute.return_value.fetchone.return_value = ('rag_test_scratch',)
        with patch.object(psycopg, 'connect', return_value=fake):
            with check.guarded_scratch_connections():
                got = psycopg.connect('postgresql://localhost/rag_test_scratch')
        self.assertIs(got, fake)
        fake.execute.assert_called_once_with('SELECT current_database()')
        fake.commit.assert_called_once()

    def test_guard_closes_identity_mismatch_without_commit(self):
        import psycopg
        fake = MagicMock()
        fake.execute.return_value.fetchone.return_value = ('unexpected',)
        with patch.object(psycopg, 'connect', return_value=fake):
            with check.guarded_scratch_connections():
                with self.assertRaises(ValueError):
                    psycopg.connect('postgresql://localhost/rag_test_scratch')
        fake.close.assert_called_once()
        fake.commit.assert_not_called()

    def test_ambiguous_question_is_diagnosed_without_inventing_evidence(self):
        result = diagnose_expected_evidence({'events': []}, [], question_ambiguous=True)
        self.assertEqual(result, ['QUESTION_AMBIGUOUS'])

    def test_missing_source_and_generation_failure_are_separate(self):
        self.assertEqual(diagnose_expected_evidence({'events': []}, [], source_information_absent=True), ['SOURCE_INFORMATION_ABSENT'])
        self.assertEqual(check.check_facts('unknown', check.EXAMS), [{'label': x, 'observed': False} for x in ('JEE', 'GATE', 'NEET')])

    def test_explicit_unavailable_pdf_never_falls_back_to_unscoped_search(self):
        from services import rag_service as rag
        with patch.dict(os.environ, {'RAG_V2': '1'}), patch('services.v2_evidence_recovery.explicit_document_scope', return_value=[]), patch.object(rag, 'hybrid_search_detailed') as search, patch.object(rag, 'generate_answer') as provider:
            result = rag._answer_from_route('What is in private-other-owner.pdf?',
                'What is in private-other-owner.pdf?', 'DOCUMENT', [], '')
        search.assert_not_called()
        provider.assert_not_called()
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(result['retrieved'], [])
        self.assertEqual(result['citations'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
