"""New-harness guards only; no live calls, DB access or protected execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ai_postfix_development_evaluation as E


class PostfixDevelopmentGuards(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)/'postfix'
        self.patch=patch.object(E,'OUT',self.out);self.patch.start();self.addCleanup(self.patch.stop)
        E.prepare()
        self.dataset=json.loads((self.out/'dataset.json').read_text())
        self.policy=json.loads((self.out/'policy.json').read_text())

    def test_four_distinct_semantic_cases_predeclared(self):
        self.assertEqual(len(E.validate_inputs(self.dataset,self.policy)),4)
        self.assertEqual({c['expected_kind'] for c in self.dataset['cases']},set(E.KINDS))

    def test_original_id_and_question_collisions_rejected(self):
        for field,value in [('id','A-direct-01'),('question',"Which colour lanyard do I have to wear while visiting someone at Kestrel Bay?")]:
            dataset=copy.deepcopy(self.dataset);dataset['cases'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):E.validate_inputs(dataset,self.policy)

    def test_duplicates_or_missing_semantic_kind_rejected(self):
        for field in ('id','expected_kind'):
            dataset=copy.deepcopy(self.dataset);dataset['cases'][0][field]=dataset['cases'][1][field]
            with self.subTest(field=field),self.assertRaises(ValueError):E.validate_inputs(dataset,self.policy)

    def test_dataset_or_contract_identity_mismatch_rejected(self):
        for field in ('dataset_sha256','behavior_contract_sha256','behavior_policy_sha256'):
            policy=dict(self.policy);policy[field]='0'*64
            with self.subTest(field=field),self.assertRaises(ValueError):E.validate_inputs(self.dataset,policy)

    def test_frozen_whole_case_score_is_not_new_partial_policy(self):
        source=dict(ref='S1',chunk_id=1,document_name='synthetic.txt',page_number=1)
        result=dict(answer='71 tokens; the address is not provided [S1].',status='partial',
            citations=[dict(ref='S1',chunk_id=1,document='synthetic.txt',page=1)],validation={'valid':True})
        score=dict(correct=False,fact_recall=1.,fabricated=0,ungrounded_numbers=[],forbidden_hits=[],citation_completeness=1.)
        case={'expected_kind':'partial_information'}
        self.assertTrue(E.evaluate_case(case,result,score,{'sources':[source]})['policy_pass'])
        result['status']='answered'
        self.assertFalse(E.evaluate_case(case,result,score,{'sources':[source]})['policy_pass'])

    def test_no_overwrite_and_no_resume(self):
        with self.assertRaises(ValueError):E.prepare()
        (self.out/'attempt.json').write_text('synthetic already attempted')
        with self.assertRaises(ValueError):E.run()

    def test_observed_partial_status_mismatch_is_not_relabelled_as_success(self):
        source=dict(ref='S1',chunk_id=1,document_name='synthetic_lumen_observatory.txt',page_number=1)
        response=dict(answer='A visitor permit costs 71 tokens [S1]. Regarding the mailing address, the policy does not provide a mailing address [S1].',
            status='answered',citations=[dict(ref='S1',chunk_id=1,document=source['document_name'],page=1)],validation={'valid':True})
        score=dict(correct=False,fact_recall=1.,fabricated=0,ungrounded_numbers=[],forbidden_hits=[],citation_completeness=1.)
        result=E.evaluate_case({'expected_kind':'partial_information'},response,score,{'sources':[source]})
        self.assertFalse(result['policy_pass'])
        self.assertEqual(result['issues'],['status_mismatch'])
        self.assertEqual(response['status'],'answered')


if __name__=='__main__':unittest.main()
