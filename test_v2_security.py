"""Bounded v2 security probes; real scratch DB opt-in, no provider calls."""
import os
import threading
import time
import unittest
from unittest.mock import patch
import test_v2_integration as fixtures

class V2BodyDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_drip_body_uses_one_total_deadline_before_route_validation(self):
        import asyncio
        from backend.v2.app import create_app
        app=create_app()
        chunks=[b'x']*5
        consumed=0
        messages=[]
        async def receive():
            nonlocal consumed
            if consumed>=len(chunks):
                return {'type':'http.disconnect'}
            await asyncio.sleep(.02)
            index=consumed;consumed+=1
            return {'type':'http.request','body':chunks[index],'more_body':consumed<len(chunks)}
        async def send(message):messages.append(message)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST',
               'scheme':'http','path':'/api/v2/auth/login','raw_path':b'/api/v2/auth/login',
               'query_string':b'','root_path':'','headers':[(b'host',b'localhost'),
                   (b'content-type',b'application/json'),(b'content-length',b'5')],
               'client':('127.0.0.1',12345),'server':('localhost',8766)}
        with patch.dict(os.environ,{'LOCAL_V1_REQUEST_TIMEOUT_SECONDS':'.03'}), \
             patch('backend.v2.app.get_connection',side_effect=AssertionError('no database allowed')), \
             patch('backend.v2.auth.login',side_effect=AssertionError('route must not authenticate')):
            await asyncio.wait_for(app(scope,receive,send),timeout=1)
        status=next(message['status'] for message in messages if message['type']=='http.response.start')
        self.assertIn(status,(408,504),'body deadline must expire before invalid JSON reaches route validation')
        self.assertLess(consumed,len(chunks),'per-chunk timeouts must not reset the total request budget')

class V2ServerErrorRedactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_unhandled_error_does_not_escape_to_asgi_server_logger(self):
        import httpx
        from backend.v2.app import create_app
        app=create_app()
        secret='PRIVATE-runtime-provider-key-and-document-content'
        @app.get('/api/v2/test-only-private-error')
        async def private_failure():
            raise RuntimeError(secret)
        transport=httpx.ASGITransport(app=app,raise_app_exceptions=True)
        escaped=None
        response=None
        with patch('backend.v2.app.get_connection',side_effect=AssertionError('no database allowed')):
            with self.assertLogs('rag.api',level='ERROR') as logs:
                try:
                    async with httpx.AsyncClient(transport=transport,base_url='http://localhost') as client:
                        response=await client.get('/api/v2/test-only-private-error')
                except Exception as error:
                    escaped=type(error).__name__
        self.assertIsNone(escaped,'an error escaping the application is logged with its private traceback by the ASGI server')
        self.assertEqual(response.status_code,500)
        self.assertEqual(response.json()['error']['code'],'internal_error')
        self.assertNotIn(secret,response.text)
        self.assertNotIn(secret,'\n'.join(logs.output))

class V2PrivateLogTests(unittest.TestCase):
    def test_deletion_classifier_and_failure_logs_hide_private_text_in_request_budget(self):
        import io
        from contextlib import redirect_stdout
        from services import automatic_memory_service as automatic
        from services.request_budget import request_budget
        secret='PRIVATE-provider-rationale-user-memory-and-key'
        for decision in ({'status':'UNCERTAIN','memory_ids':[],'reason':secret},
                         {'status':secret,'memory_ids':[]},
                         {'status':'DELETE','memory_ids':[7],'reason':secret}):
            with self.subTest(status=decision['status']):
                output=io.StringIO()
                with patch.object(automatic,'get_all_conversation_memories',return_value=[(7,'private user preference')]), \
                     patch.object(automatic,'decide_memories_to_delete',return_value=decision), \
                     patch.object(automatic,'get_memory_details',return_value={7:{'memory':'private user preference'}}), \
                     patch.object(automatic,'delete_memory',side_effect=RuntimeError(secret)), \
                     redirect_stdout(output),request_budget(30,suppress_output=True):
                    result=automatic.delete_matching_memories('fixture-conversation','forget my private preference')
                self.assertNotIn(secret,output.getvalue())
                self.assertNotIn('private user preference',output.getvalue())
                self.assertIn(result['status'],('UNCERTAIN','FAILED'))

@unittest.skipUnless(os.getenv('RAG_V2_DB_TEST')=='1','explicit isolated scratch integration required')
class V2Security(unittest.TestCase):
    setUpClass=classmethod(fixtures.V2Integration.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.V2Integration.tearDownClass.__func__)
    headers=fixtures.V2Integration.headers

    def test_host_body_and_owner_injection(self):
        self.assertEqual(self.client.get('/api/v2/health',headers={'host':'evil.test'}).status_code,400)
        self.assertEqual(self.client.post('/api/v2/auth/login',content=b'x'*(1024*1024+1),headers={'content-type':'application/json'}).status_code,413)
        self.assertEqual(self.client.post('/api/v2/conversations',json={'title':'owned','owner_id':self.b.id},headers=self.headers()).status_code,422)
        self.assertEqual(self.client.post('/api/v2/auth/register',json={'email':'unknown@example.test','password':'long enough test password'},headers={'origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/conversations',headers=self.headers()).status_code,404)

    def test_exception_response_and_logs_redact_provider_secret(self):
        import main
        from fastapi.testclient import TestClient
        cid=self.client.post('/api/v2/conversations',json={'title':'provider failure'},headers=self.headers()).json()['conversation_id']
        secret='PRIVATE-PROVIDER-KEY-and-private-document-text'
        with patch.object(main,'run_turn',side_effect=RuntimeError(secret)),TestClient(self.client.app,raise_server_exceptions=False) as client:
            with self.assertLogs('rag.api',level='ERROR') as log:
                response=client.post('/api/v2/chat',json={'conversation_id':cid,'message':'private query'},headers=self.headers())
        self.assertEqual(response.status_code,500)
        self.assertEqual(response.json()['error']['code'],'internal_error')
        self.assertNotIn(secret,response.text)
        self.assertNotIn(secret,'\n'.join(log.output))

    def test_timeout_database_failure_and_invalid_pdf_contracts(self):
        import main
        import psycopg
        from services.request_budget import RequestDeadlineExceeded
        cid=self.client.post('/api/v2/conversations',json={'title':'failure contracts'},headers=self.headers()).json()['conversation_id']
        for error,expected,code in ((RequestDeadlineExceeded(),504,'request_timeout'),(psycopg.OperationalError('private db credentials'),503,'database_unavailable')):
            with patch.object(main,'run_turn',side_effect=error):
                response=self.client.post('/api/v2/chat',json={'conversation_id':cid,'message':'query'},headers=self.headers())
            self.assertEqual(response.status_code,expected,response.text)
            self.assertEqual(response.json()['error']['code'],code)
            self.assertNotIn('credentials',response.text)
        for name,data in (('bad.pdf',b'not a PDF'),('bad.txt',b'not a PDF')):
            response=self.client.post('/api/v2/documents',files={'file':(name,data,'application/pdf')},headers=self.headers())
            self.assertEqual(response.status_code,422,response.text)
            self.assertNotIn('/tmp/',response.text)

    def test_chat_delete_serialization_and_no_resurrection(self):
        import main
        from services.conversation_service import save_message
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        cid=self.client.post('/api/v2/conversations',json={'title':'serialize'},headers=self.headers()).json()['conversation_id']
        entered,release,delete_done=threading.Event(),threading.Event(),threading.Event()
        outcomes={}
        def blocked_turn(conversation_id,message):
            save_message(conversation_id,'user',message);entered.set()
            if not release.wait(5):raise TimeoutError('test synchronization')
            save_message(conversation_id,'assistant','Fixture answer')
            return {'kind':'answer','answer':'Fixture answer','status':'answered','citations':[]}
        def chat():outcomes['chat']=self.client.post('/api/v2/chat',json={'conversation_id':cid,'message':'hello'},headers=self.headers())
        def delete():
            outcomes['delete']=self.client.delete('/api/v2/conversations/'+cid,headers=self.headers());delete_done.set()
        with patch.object(main,'run_turn',side_effect=blocked_turn):
            first=threading.Thread(target=chat);first.start();self.assertTrue(entered.wait(5))
            second=threading.Thread(target=delete);second.start()
            try:
                self.assertFalse(delete_done.wait(.15),'deletion bypassed conversation serialization')
            finally:release.set()
            first.join(8);second.join(8)
        self.assertFalse(first.is_alive());self.assertFalse(second.is_alive())
        self.assertEqual(outcomes['chat'].status_code,200,outcomes['chat'].text)
        self.assertEqual(outcomes['delete'].status_code,200,outcomes['delete'].text)
        self.assertEqual(self.client.post('/api/v2/chat',json={'conversation_id':cid,'message':'late'},headers=self.headers()).status_code,404)
        with tenant_scope(self.a.id),get_connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM messages WHERE conversation_id=%s',(cid,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM conversation_memories WHERE conversation_id=%s',(cid,)).fetchone()[0],0)

if __name__=='__main__':unittest.main(verbosity=2)
