"""Synthetic provider faults for the authorized live-provider completion sprint.

No provider, database, credentials or frozen evaluation inputs are used.
"""
import os
os.environ.setdefault('DATABASE_URL','postgresql://nobody@127.0.0.1:1/rag_test_scratch')
import testsafe
testsafe.require_scratch_db()
import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import httpx
from google.genai import errors
from services import llm_service as llm
from services.request_budget import request_budget, RequestDeadlineExceeded


class LiveProviderPolicyTests(unittest.TestCase):
    def setUp(self):
        self.client=MagicMock()
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(llm,'get_client',return_value=self.client))
        self.stack.enter_context(patch.object(llm,'_model_order',return_value=['primary','fallback']))
        self.stack.enter_context(patch.dict(llm._quota_cooldown_until,{},clear=True))
        self.sleep=self.stack.enter_context(patch('services.gemini_retry_service.time.sleep'))

    @staticmethod
    def success():return SimpleNamespace(text='synthetic answer',usage_metadata=None)

    def test_existing_abstained_contract_not_refused_label(self):
        from scripts.live_gemini_verification import is_grounded_abstention
        self.assertTrue(is_grounded_abstention({"status":"abstained","citations":[]}))
        self.assertFalse(is_grounded_abstention({"status":"answered","citations":[]}))
        self.assertFalse(is_grounded_abstention({"status":"abstained","citations":[{"ref":"S1"}]}))

    def test_invalid_credential_does_not_fallback_or_retry(self):
        for code in (400,401,403):
            with self.subTest(code=code):
                self.client.models.generate_content.reset_mock()
                self.client.models.generate_content.side_effect=errors.ClientError(code,{'error':{'message':'synthetic invalid key'}})
                with self.assertRaises(errors.APIError):llm.generate_answer('synthetic')
                self.assertEqual(self.client.models.generate_content.call_count,1)
        self.sleep.assert_not_called()

    def test_quota_switches_model_without_same_model_wait(self):
        self.client.models.generate_content.side_effect=[errors.ClientError(429,{'error':{'message':'synthetic quota'}}),self.success()]
        self.assertEqual(llm.generate_answer('synthetic'),'synthetic answer')
        self.assertEqual([c.kwargs['model'] for c in self.client.models.generate_content.call_args_list],['primary','fallback'])
        self.sleep.assert_not_called()

    def test_transient_retries_once_then_falls_back(self):
        error=errors.ServerError(503,{'error':{'message':'synthetic unavailable'}})
        self.client.models.generate_content.side_effect=[error,error,self.success()]
        self.assertEqual(llm.generate_answer('synthetic'),'synthetic answer')
        self.assertEqual([c.kwargs['model'] for c in self.client.models.generate_content.call_args_list],['primary','primary','fallback'])
        self.sleep.assert_called_once_with(1)

    def test_timeout_advances_without_duplicate_same_model_attempt(self):
        self.client.models.generate_content.side_effect=[httpx.ReadTimeout('synthetic timeout'),self.success()]
        self.assertEqual(llm.generate_answer('synthetic'),'synthetic answer')
        self.assertEqual([c.kwargs['model'] for c in self.client.models.generate_content.call_args_list],['primary','fallback'])
        self.sleep.assert_not_called()

    def test_transient_retry_cannot_overrun_total_budget(self):
        self.client.models.generate_content.side_effect=errors.ServerError(503,{'error':{'message':'synthetic unavailable'}})
        with request_budget(.01),self.assertRaises(RequestDeadlineExceeded):llm.generate_answer('synthetic')
        self.assertEqual(self.client.models.generate_content.call_count,1)
        self.sleep.assert_not_called()


if __name__=='__main__':unittest.main()
