"""Deterministic cap/receipt tests. The fake SDK performs no network activity."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from deploy.aws.tests.provider_guard import install_guard


class ProviderGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rag-aws-guard-')
        self.root=Path(self.temp.name);self.policy=self.root/'policy.json';self.receipts=self.root/'receipts'
        self.data={'version':'aws-demo-development-acceptance/1','run_id':'aws-demo-20261123-live-01',
                   'maximum_sdk_calls':2,'allowed_models':['gemini-3.5-flash-lite']}
        self.policy.write_text(json.dumps(self.data))
        self.calls=[]
        calls=self.calls
        class SDK:
            def generate_content(self,**kwargs):
                calls.append(kwargs)
                return SimpleNamespace(text='PRIVATE answer',model_version=kwargs['model'],
                    usage_metadata=SimpleNamespace(prompt_token_count=2,candidates_token_count=3,total_token_count=5))
        self.SDK=SDK
    def tearDown(self):self.temp.cleanup()
    def call(self):return self.SDK().generate_content(model='gemini-3.5-flash-lite',contents='PRIVATE prompt')
    def test_cap_claims_and_hash_receipts(self):
        install_guard(self.SDK,self.policy,self.receipts)
        self.call();self.call()
        with self.assertRaisesRegex(RuntimeError,'exhausted'):self.call()
        self.assertEqual(len(self.calls),2)
        self.assertEqual(len(list(self.receipts.glob('call-*.claim'))),2)
        records=[json.loads(file.read_text()) for file in self.receipts.glob('call-*.json')]
        self.assertEqual([record['status'] for record in records],['SUCCESS','SUCCESS'])
        self.assertNotIn('PRIVATE',''.join(file.read_text() for file in self.receipts.iterdir()))
        self.assertEqual(records[0]['tokens']['total_token_count'],5)
    def test_existing_slots_survive_reinstallation_in_another_process_class(self):
        install_guard(self.SDK,self.policy,self.receipts);self.call();self.call()
        class OtherSDK:
            def generate_content(self,**kwargs):raise AssertionError('cap bypass')
        install_guard(OtherSDK,self.policy,self.receipts)
        with self.assertRaisesRegex(RuntimeError,'exhausted'):
            OtherSDK().generate_content(model='gemini-3.5-flash-lite',contents='anything')
    def test_conversation_scope_leaves_other_traffic_and_its_data_alone(self):
        from contextvars import ContextVar
        selected=ContextVar('selected',default=False)
        install_guard(self.SDK,self.policy,self.receipts,active=selected.get)
        self.call()
        self.assertFalse(list(self.receipts.glob('call*')))
        token=selected.set(True)
        try:
            self.call();self.call()
            with self.assertRaisesRegex(RuntimeError,'exhausted'):self.call()
        finally:selected.reset(token)
        self.call()
        self.assertEqual(len(self.calls),4)
        self.assertEqual(len(list(self.receipts.glob('call-*.claim'))),2)
    def test_parallel_claims_never_exceed_cap(self):
        install_guard(self.SDK,self.policy,self.receipts)
        errors=[]
        def request():
            try:self.call()
            except RuntimeError:errors.append(True)
        threads=[threading.Thread(target=request) for _ in range(12)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(self.calls),2);self.assertEqual(len(errors),10)
    def test_exception_consumes_slot_and_redacts_failure(self):
        class BadSDK:
            def generate_content(self,**kwargs):raise ValueError('PRIVATE provider key')
        install_guard(BadSDK,self.policy,self.receipts)
        with self.assertRaises(ValueError):BadSDK().generate_content(model='gemini-3.5-flash-lite',contents='PRIVATE')
        record=json.loads((self.receipts/'call-001.json').read_text())
        self.assertEqual(record['status'],'FAILED');self.assertEqual(record['error_type'],'ValueError')
        self.assertNotIn('PRIVATE',json.dumps(record))
    def test_policy_changes_cannot_reset_budget(self):
        install_guard(self.SDK,self.policy,self.receipts)
        self.data['maximum_sdk_calls']=3;self.policy.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'changed'):install_guard(self.SDK,self.policy,self.receipts)
    def test_model_not_allowed_does_not_reach_sdk(self):
        install_guard(self.SDK,self.policy,self.receipts)
        with self.assertRaises(RuntimeError):self.SDK().generate_content(model='other',contents='private')
        self.assertEqual(len(self.calls),0)
    def test_spend_stop_prevents_sdk_and_does_not_consume_another_slot(self):
        install_guard(self.SDK,self.policy,self.receipts)
        with patch.dict('os.environ',{'RAG_AWS_PROVIDER_DISABLED':'1'}):
            with self.assertRaisesRegex(RuntimeError,'disabled'):self.call()
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.receipts.glob('call-*.claim')),[])
    def test_invalid_or_unbounded_policy_fails_closed(self):
        for value in (0,19,True):
            self.data['maximum_sdk_calls']=value;self.policy.write_text(json.dumps(self.data))
            with self.assertRaises(ValueError):install_guard(self.SDK,self.policy,self.receipts)


if __name__=='__main__':unittest.main()
