"""Offline cooperative middleware/provider deadline tests; no running worker abandoned."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import asyncio
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app import RequestBudgetMiddleware
from backend.errors import install
from services.request_budget import request_budget, RequestDeadlineExceeded, remaining_seconds
from services import llm_service as llm
from services.gemini_retry_service import generate_with_retry

class DeadlineTests(unittest.TestCase):
    def test_slow_request_body_is_bounded_before_worker(self):
        async def exercise():
            sent=[]
            async def receive(): await asyncio.sleep(1)
            async def send(message): sent.append(message)
            async def application(scope,receive,send): await receive()
            with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'1','LOCAL_V1_REQUEST_TIMEOUT_SECONDS':'.01'}):
                await RequestBudgetMiddleware(application)({'type':'http'},receive,send)
            self.assertEqual(sent[0]['status'],504)
        asyncio.run(exercise())
    def test_worker_context_and_late_response_fenced(self):
        app=FastAPI();install(app);app.add_middleware(RequestBudgetMiddleware)
        completed=[]
        @app.get('/slow')
        def slow():
            self.assertIsNotNone(remaining_seconds())
            time.sleep(.025);completed.append(True)
            return {'secret':'late-success'}
        with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'1','LOCAL_V1_REQUEST_TIMEOUT_SECONDS':'.01'}),TestClient(app) as client:
            response=client.get('/slow')
        self.assertEqual(completed,[True]);self.assertEqual(response.status_code,504)
        self.assertNotIn('late-success',response.text)
        self.assertIsNone(remaining_seconds())
    def test_provider_timeout_clamped_per_attempt(self):
        fake=MagicMock();fake.models.generate_content.return_value=SimpleNamespace(text='answer',usage_metadata=None)
        with patch.object(llm,'get_client',return_value=fake),request_budget(.5):
            self.assertEqual(llm._generate_with_model('fake-model','secret'),'answer')
        timeout=fake.models.generate_content.call_args.kwargs['config'].http_options.timeout
        self.assertGreater(timeout,0);self.assertLessEqual(timeout,500)
    def test_return_after_deadline_not_used(self):
        def slow(**kwargs):time.sleep(.015);return SimpleNamespace(text='late',usage_metadata=None)
        fake=MagicMock();fake.models.generate_content.side_effect=slow
        with patch.object(llm,'get_client',return_value=fake),self.assertRaises(RequestDeadlineExceeded):
            with request_budget(.005):llm._generate_with_model('fake','secret')
    def test_retry_wait_cannot_exceed_budget(self):
        class Temporary(Exception):code=503
        generate=MagicMock(side_effect=Temporary('secret'))
        with request_budget(.01),patch('services.gemini_retry_service.time.sleep') as sleep:
            with self.assertRaises(RequestDeadlineExceeded):generate_with_retry(generate)
        self.assertEqual(generate.call_count,1);sleep.assert_not_called()
    def test_quota_wait_cannot_exceed_budget(self):
        from google.genai import errors
        error=errors.ClientError(429,{'error':{'message':'quota'}})
        with request_budget(.01),patch.object(llm,'_model_order',return_value=['fake']),patch.object(llm,'_generate_with_model',side_effect=error),patch.object(llm.time,'sleep') as sleep:
            with self.assertRaises(RequestDeadlineExceeded):llm.generate_answer('secret')
        sleep.assert_not_called()

if __name__=='__main__':unittest.main()
