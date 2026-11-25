"""Provider-free deployment host regressions; no database connections."""
import os
import unittest
import threading
import sys
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from backend.v2.app import create_app


class DeploymentHostTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, host, configured=None):
        with patch.dict(os.environ):
            os.environ.pop('RAG_V2_ALLOWED_HOSTS',None)
            if configured is not None:
                os.environ['RAG_V2_ALLOWED_HOSTS']=configured
            app=create_app()
        with patch('backend.v2.app.get_connection',side_effect=AssertionError('no database')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
                return await client.get('/api/v2/health',headers={'host':host})

    async def test_default_rejects_container_and_attacker_hosts(self):
        for host in ('api','evil.test','localhost.evil.test'):
            self.assertEqual((await self.request(host)).status_code,400)
        self.assertEqual((await self.request('localhost')).status_code,200)

    async def test_explicit_private_host_does_not_enable_other_hosts(self):
        for host in ('api','api:8000','localhost'):
            self.assertEqual((await self.request(host,'localhost,api')).status_code,200)
        for host in ('api.evil.test','evil.test','api.attacker'):
            self.assertEqual((await self.request(host,'localhost,api')).status_code,400)

    async def test_wildcards_urls_ports_and_empty_configuration_fail_closed(self):
        for value in ('','*','*.example.com','http://api','api:8000','localhost,','api/path'):
            with self.subTest(value=value),patch.dict(os.environ,{'RAG_V2_ALLOWED_HOSTS':value}):
                with self.assertRaises(ValueError):
                    create_app()


class GenerationAdmissionTests(unittest.TestCase):
    def test_only_one_generation_runs_and_waiter_uses_the_existing_deadline(self):
        from backend.v2.app import _run_limited_turn
        from services.request_budget import request_budget,RequestDeadlineExceeded
        slots=threading.BoundedSemaphore(1)
        entered,release=threading.Event(),threading.Event()
        calls=[];failures=[]
        def turn(cid,message):
            calls.append(message);entered.set()
            if not release.wait(2):raise AssertionError('fixture did not release')
            return {'answer':message}
        def first():
            try:
                with request_budget(2):_run_limited_turn('fixture','first',slots)
            except BaseException as error:failures.append(error)
        with patch.dict(sys.modules,{'main':SimpleNamespace(run_turn=turn)}):
            worker=threading.Thread(target=first);worker.start()
            try:
                self.assertTrue(entered.wait(1))
                with self.assertRaises(RequestDeadlineExceeded),request_budget(.02):
                    _run_limited_turn('other','must-not-run',slots)
                self.assertEqual(calls,['first'])
            finally:
                release.set();worker.join(2)
            self.assertFalse(worker.is_alive());self.assertEqual(failures,[])
            self.assertTrue(slots.acquire(blocking=False),'completed generation must release admission')
            slots.release()

    def test_generation_limit_is_explicit_and_invalid_configuration_fails_closed(self):
        from backend.v2.app import _chat_generation_slots
        for value in ('-1','5','unknown',''):
            with patch.dict(os.environ,{'RAG_V2_CHAT_CONCURRENCY':value}):
                with self.assertRaises(ValueError):create_app()
        with patch.dict(os.environ,{'RAG_V2_CHAT_CONCURRENCY':'0'}):
            self.assertIsNone(_chat_generation_slots())
        with patch.dict(os.environ,{'RAG_V2_CHAT_CONCURRENCY':'1'}):
            slots=_chat_generation_slots()
            self.assertTrue(slots.acquire(blocking=False))
            self.assertFalse(slots.acquire(blocking=False))
            slots.release()

if __name__=='__main__':
    unittest.main()
