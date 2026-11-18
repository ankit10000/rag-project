"""Offline local-release security and readiness contracts."""
import testsafe
testsafe.require_scratch_db()
import asyncio
import contextlib
import hashlib
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.app import create_app, BodySizeLimitMiddleware, lifespan
from backend import config

TOKEN='local-test-token-with-more-than-thirty-two-characters'
class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {'LOCAL_V1_PROFILE':'1'}))
        self.stack.enter_context(patch('backend.app.load_token_digest',return_value=(hashlib.sha256(TOKEN.encode()).digest(),'test')))
        self.stack.enter_context(patch('backend.app._remove_stale_upload_temps'))
        self.client=self.stack.enter_context(TestClient(create_app(),base_url='http://127.0.0.1',raise_server_exceptions=False))
    def test_auth_and_host(self):
        for token in ['', 'Bearer wrong', 'Basic '+TOKEN, 'Bearer '+'x'*513]:
            self.assertEqual(self.client.get('/api/v1/health/ready',headers={'Authorization':token}).status_code,401)
        self.assertEqual(self.client.get('/api/v1/health',headers={'Host':'attacker.example'}).status_code,400)
        self.assertEqual(self.client.get('/api/v1/health').status_code,200)
    def test_correct_token_fails_closed_without_initialized_digest(self):
        self.client.app.state.token_digest=None
        response=self.client.get('/api/v1/health/ready',headers={'Authorization':'Bearer '+TOKEN})
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error']['code'],'auth_unavailable')
    def test_normal_shutdown_clears_digest(self):
        self.assertIsNotNone(self.client.app.state.token_digest)
        self.stack.close()
        self.assertIsNone(self.client.app.state.token_digest)
    def test_fresh_token_file_rotation_and_private_permissions(self):
        from backend import security
        with tempfile.TemporaryDirectory(prefix='local-v1-token-',dir='/private/tmp') as directory:
            path=Path(directory)/'isolated-config'/'api_token'
            environment=dict(os.environ)
            environment.pop('RAG_API_TOKEN',None)
            environment['RAG_API_TOKEN_FILE']=str(path)
            with patch.dict(os.environ,environment,clear=True):
                first_digest,_=security.load_token_digest()
                first_token=path.read_text().strip()
                self.assertGreaterEqual(len(first_token),security.MIN_TOKEN_LENGTH)
                self.assertEqual(first_digest,hashlib.sha256(first_token.encode()).digest())
                self.assertEqual(security.rotate_token(),str(path))
                second_digest,_=security.load_token_digest()
                self.assertNotEqual(first_digest,second_digest)
                self.assertNotEqual(first_token,path.read_text().strip())
                if os.name=='posix':
                    self.assertEqual(path.stat().st_mode & 0o777,0o600)
                    self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
    def test_readiness_actual_query_and_redaction(self):
        conn=MagicMock();conn.__enter__.return_value=conn
        cursor=conn.cursor.return_value.__enter__.return_value;cursor.fetchone.return_value=(1,)
        with patch('services.database.get_connection',return_value=conn):
            response=self.client.get('/api/v1/health/ready',headers={'Authorization':'Bearer '+TOKEN})
        self.assertEqual(response.status_code,200);cursor.execute.assert_called_once_with('SELECT 1')
        with patch('services.database.get_connection',side_effect=RuntimeError('SECRET DB password path')):
            response=self.client.get('/api/v1/health/ready',headers={'Authorization':'Bearer '+TOKEN})
        self.assertEqual(response.status_code,503);self.assertNotIn('SECRET',response.text)
    def test_cors_delete_and_bad_origins(self):
        self.assertIn('DELETE',config.CORS_METHODS)
        from backend.app import _validated_cors_origins
        for origin in ['*','null','https://*.example','http://user:pass@localhost','http://localhost/path']:
            with patch.object(config,'CORS_ORIGINS',[origin]),self.assertRaises(RuntimeError): _validated_cors_origins()
    def test_body_actual_bytes_before_application(self):
        async def exercise(declared,parts,limit):
            called=[];sent=[]
            async def app(scope,receive,send):called.append(True)
            async def receive():return parts.pop(0)
            async def send(message):sent.append(message)
            middleware=BodySizeLimitMiddleware(app)
            with patch.object(middleware,'_limit',return_value=limit):
                await middleware({'type':'http','method':'POST','path':'/x','headers':[(b'content-length',declared)]},receive,send)
            self.assertFalse(called);return sent[0]['status']
        self.assertEqual(asyncio.run(exercise(b'1',[{'type':'http.request','body':b'12345'}],4)),413)
        self.assertEqual(asyncio.run(exercise(b'1',[{'type':'http.request','body':b'12'}],4)),400)
    def test_startup_failure_clears_token(self):
        async def run():
            app=create_app()
            with patch('backend.app._remove_stale_upload_temps',side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):
                    async with lifespan(app):pass
            self.assertIsNone(app.state.token_digest)
        asyncio.run(run())
    def test_launcher_remote_flag_cannot_override_release(self):
        import run_api
        with self.assertRaises(SystemExit),contextlib.redirect_stderr(__import__('io').StringIO()):
            run_api.main(['--host','0.0.0.0','--allow-non-loopback'])

if __name__=='__main__':unittest.main()
