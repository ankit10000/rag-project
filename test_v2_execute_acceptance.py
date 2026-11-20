"""Current contract replay of immutable development traces; zero live calls.

These are offline recorded-response fixtures, not a new Gemini experiment.
The frozen extra ongoing-cost expectation remains a reported metric limitation.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import os
import unittest
from unittest.mock import Mock, patch

from scripts import v2_reliability_check as harness
from services import answer_service
from services.request_budget import request_budget


@lru_cache(maxsize=1)
def replay_recorded_cases():
    plan = json.loads(harness.PLAN.read_text())
    outcomes = []
    for case in plan['cases']:
        for identity in ('live-03', 'live-02', 'live-01'):
            path = harness.ARTIFACTS / identity / (case['id'] + '-trace.json')
            if path.exists():
                break
        snapshot = json.loads(path.read_text())
        requests = [event for event in snapshot['events'] if event['stage'] == 'generation_request']
        replies = [event['raw']['answer'] for event in snapshot['events'] if event['stage'] == 'answer_generated']
        initial = requests[0]
        sources = deepcopy(initial['raw']['sources'])
        bundle = {'sources': sources, 'context_text': initial['raw']['context_text'],
                  'total_chars': sum(len(source['content']) for source in sources),
                  'dropped': [], 'truncated': any(source.get('truncated') for source in sources)}
        source_before = deepcopy(sources)
        fixture = Mock(side_effect=replies)
        with patch.dict(os.environ, {'RAG_V2': '1'}), request_budget(seconds=60), \
             patch('psycopg.connect', side_effect=AssertionError('offline replay forbids database access')), \
             patch('socket.socket.connect', side_effect=AssertionError('offline replay forbids all network access')):
            result = answer_service.generate_grounded_answer(
                case['question'], bundle, initial['metadata']['question_type'], fixture,
                history=case.get('history', []))
        recorded_result = json.loads((path.parent / (case['id'] + '.json')).read_text())['result']
        # Citation rows are compared with the captured original owned sources.
        # Separate scratch-only integration verifies those sources still exist.
        rows = {s['chunk_id']: (s['chunk_id'], s['document_name'], s['page_number'], s['content']) for s in sources}
        metrics = harness.metrics_for(case, result, {'events': [initial]}, rows)
        outcomes.append({'id': case['id'], 'fixture_identity': identity,
                         'fixture_generation_calls': fixture.call_count, 'provider_calls': 0,
                         'source_ids_preserved': sources == source_before,
                         'recorded_status': recorded_result['status'], 'result': result,
                         'answer_unchanged': result['answer'] == recorded_result['answer'],
                         'status_unchanged': result['status'] == recorded_result['status'],
                         'metrics': metrics})
    return outcomes


class ExecuteAcceptanceTests(unittest.TestCase):
    def test_all_thirteen_recorded_bundles_match_current_contract(self):
        results = replay_recorded_cases()
        self.assertEqual(len(results), 13)
        for item in results:
            with self.subTest(case=item['id']):
                self.assertTrue(item['answer_unchanged'])
                self.assertTrue(item['status_unchanged'])
                self.assertTrue(item['source_ids_preserved'])
                self.assertEqual(item['provider_calls'], 0)
                self.assertLessEqual(item['fixture_generation_calls'], 1 + max(0, answer_service.cfg.ANSWER_MAX_RETRIES))
                self.assertTrue(item['metrics']['scope_and_budget_ok'])

    def test_three_metrics_remain_separate_and_strict_failure_is_retained(self):
        results = replay_recorded_cases()
        evidence = [r['metrics']['evidence_coverage'] for r in results if r['metrics']['evidence_coverage'] is not None]
        facts = [r['metrics']['answer_factual_completeness'] for r in results]
        citations = [r['metrics']['citation_abstention_correctness'] for r in results]
        self.assertEqual((sum(evidence), len(evidence)), (12, 12))
        self.assertEqual((sum(facts), len(facts)), (12, 13))
        self.assertEqual((sum(citations), len(citations)), (13, 13))
        negative = next(r for r in results if r['id'] == 'explicit_negative')
        self.assertEqual([x['label'] for x in negative['metrics']['answer_fact_checks'] if not x['observed']], ['ongoing usage cost'])
        self.assertEqual(negative['result']['status'], 'answered')

    def test_golden_hashes_and_historical_provider_cap_are_unchanged(self):
        self.assertEqual(hashlib.sha256(harness.PLAN.read_bytes()).hexdigest(), '185d0ab7ad600e65d77ddd672a86bdefd8d660eae417244df40fb8f88aa91a54')
        self.assertEqual(hashlib.sha256((harness.ARTIFACTS/'frozen_fact_checks.json').read_bytes()).hexdigest(), '46e4accef77df0901e7c8fc0c786d72d9eacc2b64f512201b6fafa183bdaebbb')
        calls = sum(json.loads((harness.ARTIFACTS/run/'result.json').read_text())['provider_calls'] for run in ('live-01', 'live-02', 'live-03'))
        self.assertEqual(calls, 52)


if __name__ == '__main__':
    unittest.main(verbosity=2)
