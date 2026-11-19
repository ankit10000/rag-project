"""Offline contract checks; no provider, database or original-score changes."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from ai_review.development_v2.contract import assess_behavior

ROOT = Path(__file__).resolve().parent


class AbstentionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.sources = [dict(ref='S1', document_name='synthetic.txt', page_number=1, chunk_id=7)]
        self.citation = dict(ref='S1', document='synthetic.txt', page=1, chunk_id=7)

    def response(self, status, answer, cited=True):
        return dict(status=status, answer=answer,
                    citations=[self.citation] if cited else [],
                    validation=dict(valid=True, invalid_refs=[]) if cited else None)

    def check(self, kind, response):
        return assess_behavior(kind, response, self.sources)['behavior_contract_pass']

    def test_cited_document_omission_is_valid_abstention(self):
        response = self.response('abstained', 'The policy does not provide a contact number [S1].')
        self.assertTrue(self.check('missing_information', response))
        response['status'] = 'answered'
        self.assertFalse(self.check('missing_information', response))

    def test_genuine_uncited_abstention_remains_valid(self):
        self.assertTrue(self.check('missing_information', self.response(
            'abstained', 'The supplied documents do not state the contact number.', False)))

    def test_explicit_negative_is_answered_and_still_requires_citation(self):
        response = self.response('answered', 'The observatory does not provide fax service [S1].')
        self.assertTrue(self.check('explicit_negative_fact', response))
        response['status'] = 'abstained'
        self.assertFalse(self.check('explicit_negative_fact', response))
        response['status'] = 'answered'; response['citations'] = []
        self.assertFalse(self.check('explicit_negative_fact', response))

    def test_partial_factual_answer_is_neither_full_answer_nor_full_abstention(self):
        response = self.response('partial', 'The permit lasts 11 days [S1]. The text does not state a phone number.')
        self.assertTrue(self.check('partial_information', response))
        for status in ('answered', 'abstained'):
            response['status'] = status
            self.assertFalse(self.check('partial_information', response))

    def test_invalid_citations_never_become_allowed_by_abstention(self):
        response = self.response('abstained', 'The policy omits the contact details [S1].')
        for field, value in [('ref','S9'), ('page',99), ('page',True), ('document','unrelated.txt'), ('chunk_id',100)]:
            bad = copy.deepcopy(response); bad['citations'][0][field] = value
            with self.subTest(field=field): self.assertFalse(self.check('missing_information', bad))
        response['validation']['valid'] = False
        self.assertFalse(self.check('missing_information', response))
        response['citations'] = []
        self.assertFalse(self.check('missing_information', response))

    def test_declared_contract_is_not_a_semantic_judge_or_acceptance(self):
        with self.assertRaises(ValueError): assess_behavior('infer_from_does_not_provide', {}, [])
        result = assess_behavior('missing_information', self.response('abstained', 'Not stated.', False), self.sources)
        self.assertFalse(result['formal_acceptance'])
        self.assertEqual(result['scope'], 'DEVELOPMENT_ONLY')

    def test_original_artifacts_and_failure_are_immutable(self):
        policy = json.loads((ROOT/'ai_review/development_v2/policy.json').read_text())
        original = policy['predecessor']
        for name, key in [('policy.json','policy_sha256'), ('dataset.json','dataset_sha256'), ('results.jsonl','results_sha256')]:
            data = (ROOT/'ai_review/development'/name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), original[key])
        evidence = json.loads((ROOT/'ai_review/development/run_evidence.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/original['run_evidence_path']).read_bytes()).hexdigest(),
                         original['run_evidence_sha256'])
        self.assertEqual(evidence['status'], 'AI_TECHNICAL_EVALUATION_FAIL')
        self.assertEqual((evidence['passed_cases'], evidence['completed_cases']), (3,4))
        self.assertFalse(original['reinterpret_historical_verdict'])
        self.assertEqual(policy['execution_status'], 'NOT_EXECUTED')
        self.assertNotEqual(policy['policy_id'], original['policy_id'])


if __name__ == '__main__':
    unittest.main()
