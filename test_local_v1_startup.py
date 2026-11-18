"""Actual localhost process startup/readiness/shutdown; no provider/model calls."""
import testsafe
testsafe.require_scratch_db()
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import psycopg


class StartupTests(unittest.TestCase):
    def test_real_localhost_process_and_shutdown(self):
        with psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=5) as conn:
            self.assertEqual(conn.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        token=secrets.token_urlsafe(32)
        with tempfile.TemporaryDirectory(prefix='local-v1-startup-') as folder:
            env=dict(os.environ,LOCAL_V1_PROFILE='1',RAG_API_TOKEN=token,
                     LOCAL_V1_STARTUP_UPLOAD_DIR=folder,LOCAL_V1_STARTUP_PORT=str(port),
                     TESTSAFE_BLOCK_NETWORK='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            code="""import os,sys
import testsafe
testsafe.require_scratch_db()
import backend.config as cfg
cfg.UPLOAD_DIR=os.environ['LOCAL_V1_STARTUP_UPLOAD_DIR']
import run_api
sys.exit(run_api.main(['--port',os.environ['LOCAL_V1_STARTUP_PORT']]))
"""
            process=subprocess.Popen([sys.executable,'-B','-c',code],cwd=Path(__file__).resolve().parent,
                                     env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                base=f'http://127.0.0.1:{port}/api/v1'
                limit=time.monotonic()+15
                while True:
                    try:
                        with urlopen(base+'/health',timeout=1) as response:
                            self.assertEqual(json.load(response),{'status':'ok'})
                        break
                    except (OSError,URLError):
                        if process.poll() is not None or time.monotonic()>limit:
                            self.fail('localhost application did not become live')
                        time.sleep(0.05)
                with self.assertRaises(HTTPError) as denied:
                    urlopen(base+'/conversations',timeout=2)
                self.assertEqual(denied.exception.code,401)
                denied.exception.close()
                status_request=Request(base+'/health/status',headers={'Authorization':'Bearer '+token})
                with urlopen(status_request,timeout=5) as response:
                    self.assertEqual(json.load(response)['app_version'],'1.0.0')
                request=Request(base+'/health/ready',headers={'Authorization':'Bearer '+token})
                with urlopen(request,timeout=5) as response:
                    self.assertEqual(response.status,200)
                    body=response.read().decode()
                    self.assertNotIn(token,body)
                    self.assertFalse(os.environ['DATABASE_URL'] in body,'connection details leaked')
            finally:
                process.terminate()
                try:output,_=process.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill();output,_=process.communicate();self.fail('localhost process did not stop cleanly')
            self.assertIn(process.returncode,(0,-signal.SIGTERM),'localhost process did not stop normally')
            self.assertIn('Application shutdown complete',output)
            self.assertNotIn(token,output)
            self.assertFalse(os.environ['DATABASE_URL'] in output,'connection details leaked')
            self.assertEqual(list(Path(folder).iterdir()),[])


if __name__=='__main__':unittest.main()
