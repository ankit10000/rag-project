"""Real PostgreSQL/API isolation, never rag_db; opt in explicitly."""
import os
import unittest
import uuid
import tempfile
from unittest.mock import patch

@unittest.skipUnless(os.getenv('RAG_V2_DB_TEST')=='1','explicit isolated scratch integration required')
class V2Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts import v2_scratch
        from services import database
        cls.env=patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'0','LOCAL_V1_PROFILE':'0','RAG_V2_ORIGINS':'http://testserver','TESTSAFE_BLOCK_NETWORK':'1'})
        cls.env.start();cls.url=patch.object(database,'DATABASE_URL',v2_scratch.app_url());cls.url.start()
        # Verify actual database on EVERY connection before application writes.
        import psycopg
        original=psycopg.connect
        def guarded(*args,**kwargs):
            c=original(*args,**kwargs)
            if c.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
                c.close();raise AssertionError('not scratch')
            c.commit();return c
        cls.guard=patch.object(psycopg,'connect',side_effect=guarded);cls.guard.start()
        from backend.v2 import auth
        cls.marker=uuid.uuid4().hex
        cls.emails=[cls.marker+x+'@example.test' for x in ('a','b')]
        for email in cls.emails:auth.register(email,'scratch-password-71')
        cls.a,cls.ta,cls.ca=auth.login(cls.emails[0],'scratch-password-71')
        cls.b,cls.tb,cls.cb=auth.login(cls.emails[1],'scratch-password-71')
        cls.temp=tempfile.TemporaryDirectory(prefix='rag-v2-api-');cls.uploadenv=patch.dict(os.environ,{'RAG_V2_UPLOAD_DIR':cls.temp.name});cls.uploadenv.start()
        from fastapi.testclient import TestClient
        from backend.v2.app import create_app
        cls.client=TestClient(create_app(),raise_server_exceptions=True)
        cls.client.__enter__()
    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None)
        from scripts.v2_scratch import connect
        with connect() as c:
            ids=[cls.a.id,cls.b.id]
            c.execute('DELETE FROM job_events WHERE owner_id=ANY(%s::uuid[])',(ids,));c.execute('DELETE FROM jobs WHERE owner_id=ANY(%s::uuid[])',(ids,))
            c.execute('DELETE FROM document_chunks WHERE owner_id=ANY(%s::uuid[])',(ids,));c.execute('DELETE FROM documents WHERE owner_id=ANY(%s::uuid[])',(ids,))
            c.execute('DELETE FROM conversations WHERE owner_id=ANY(%s::uuid[])',(ids,))
            c.execute('DELETE FROM user_sessions WHERE user_id=ANY(%s::uuid[])',(ids,));c.execute('DELETE FROM audit_events WHERE actor_user_id=ANY(%s::uuid[]) OR target_user_id=ANY(%s::uuid[])',(ids,ids));c.execute('DELETE FROM users WHERE id=ANY(%s::uuid[])',(ids,))
        cls.uploadenv.stop();cls.temp.cleanup();cls.guard.stop();cls.url.stop();cls.env.stop()
    def headers(self,who='a'):
        token,csrf=(self.ta,self.ca) if who=='a' else (self.tb,self.cb)
        return {'cookie':f'rag_session={token}; rag_csrf={csrf}','x-csrf-token':csrf,'origin':'http://testserver'}
    def test_01_auth_and_safe_errors(self):
        self.assertEqual(self.client.get('/api/v2/auth/me').status_code,401)
        r=self.client.get('/api/v2/auth/me',headers=self.headers());self.assertEqual(r.status_code,200);self.assertEqual(r.json()['id'],self.a.id)
        for email in (self.emails[0],'not-present@example.test'):
            r=self.client.post('/api/v2/auth/login',json={'email':email,'password':'wrong'},headers={'origin':'http://testserver'})
            self.assertEqual(r.status_code,401);self.assertEqual(r.json()['error']['message'],'invalid email or password')
        self.assertEqual(self.client.get('/api/v2/admin/users',headers=self.headers()).status_code,403)
        self.assertEqual(self.client.post('/api/v2/conversations',json={'title':'x'},headers={'cookie':f'rag_session={self.ta}'}).status_code,403)
        self.assertEqual(self.client.post('/api/v2/conversations',json={'title':'x'},headers={**self.headers(),'origin':'https://evil.test'}).status_code,403)
    def test_02_conversation_memory_provenance_isolation(self):
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        r=self.client.post('/api/v2/conversations',json={'title':'Private A'},headers=self.headers());self.assertEqual(r.status_code,201,r.text);cid=r.json()['conversation_id']
        for path in (f'/conversations/{cid}',f'/conversations/{cid}/memories/1/sources'):
            self.assertEqual(self.client.get('/api/v2'+path,headers=self.headers('b')).status_code,404)
        self.assertEqual(self.client.delete('/api/v2/conversations/'+cid,headers=self.headers('b')).status_code,404)
        self.assertEqual(self.client.post('/api/v2/chat',json={'conversation_id':cid,'message':'secret'},headers=self.headers('b')).status_code,404)
        with tenant_scope(self.b.id),get_connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM conversations WHERE id=%s',(cid,)).fetchone()[0],0)
            with self.assertRaises(Exception):c.execute("INSERT INTO messages(conversation_id,role,content) VALUES(%s,'user','intrusion')",(cid,))
        from services.conversation_service import save_message
        with tenant_scope(self.a.id):mid=save_message(cid,'user','I prefer tea.')
        self.assertEqual(self.client.delete(f'/api/v2/conversations/{cid}/messages/{mid}',headers=self.headers('b')).status_code,404)
        self.assertEqual(self.client.delete('/api/v2/conversations/'+cid,headers=self.headers()).status_code,200)
    def test_03_upload_job_download_isolation_and_delete_fence(self):
        import pymupdf
        from services.tenant_context import tenant_scope
        from services import v2_jobs
        p=pymupdf.open();p.new_page().insert_text((40,50),'Private astronomy permits cost seventy one tokens and last twenty three days.');data=p.tobytes();p.close()
        r=self.client.post('/api/v2/documents',files={'file':('private.pdf',data,'application/pdf')},headers=self.headers());self.assertEqual(r.status_code,202,r.text)
        did,jid=r.json()['id'],r.json()['job_id']
        for path in (f'/documents/{did}',f'/documents/{did}/file',f'/jobs/{jid}'):
            self.assertEqual(self.client.get('/api/v2'+path,headers=self.headers('b')).status_code,404)
        self.assertEqual(self.client.get('/api/v2/documents/'+did+'/file',headers=self.headers()).content,data)
        with tenant_scope(self.a.id):job=v2_jobs.claim('api-fixture-worker')
        self.assertEqual(job['id'],jid)
        self.assertEqual(self.client.delete('/api/v2/documents/'+did,headers=self.headers('b')).status_code,404)
        self.assertEqual(self.client.delete('/api/v2/documents/'+did,headers=self.headers()).status_code,200)
        import numpy as np
        with tenant_scope(self.a.id):self.assertFalse(v2_jobs.publish(job,[{'page_number':1,'text':'stale'}],[dict(document_name=did,page_number=1,chunk_id=1,content='stale')],np.ones((1,384))))
        self.assertEqual(self.client.get('/api/v2/documents/'+did+'/file',headers=self.headers()).status_code,404)
    def test_04_vector_bm25_fts_owner_scopes(self):
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services.ingestion_service import write_document_chunks
        from services.search_service import semantic_search
        from services.bm25_service import bm25_search,clear_bm25_cache
        from services.fts_service import fts_search
        import numpy as np
        vector=np.ones((1,384),dtype=np.float32)
        docs=[]
        for user,text in ((self.a,'alpha astronomy unique permit tokens'),(self.b,'beta astronomy private permit tokens')):
            did=uuid.uuid4();docs.append(str(did))
            with tenant_scope(user.id),get_connection() as c:
                c.execute("INSERT INTO documents(id,filename,storage_path,status,embedding_model,embedding_dim) VALUES(%s,'search.pdf','unused','ready',%s,384)",(did,'all-MiniLM-L6-v2'))
                write_document_chunks(c.cursor(),str(did),[dict(document_name=str(did),page_number=1,chunk_id=1,content=text)],vector)
        clear_bm25_cache()
        for user,did,foreign in ((self.a,docs[0],docs[1]),(self.b,docs[1],docs[0]),(self.a,docs[0],docs[1])):
            with tenant_scope(user.id),patch('services.search_service.generate_embeddings',return_value=vector):
                for result in (semantic_search('astronomy',similarity_threshold=0),bm25_search('astronomy'),fts_search('astronomy')):
                    self.assertTrue(result);self.assertEqual({r[1] for r in result},{did})
                self.assertEqual(bm25_search('astronomy',document_names=[foreign]),[])
    def test_05_sessions_disable_expire_logout(self):
        from backend.v2 import auth
        from scripts.v2_scratch import connect
        user,token,csrf=auth.login(self.emails[1],'scratch-password-71')
        auth.logout(token)
        with self.assertRaises(ApiError):auth.authenticate(token)
        user,token,csrf=auth.login(self.emails[1],'scratch-password-71')
        with connect() as c:c.execute("UPDATE user_sessions SET expires_at=now()-interval '1 second' WHERE token_hash=%s",(auth.secret_hash(token),))
        with self.assertRaises(ApiError):auth.authenticate(token)
        user,token,csrf=auth.login(self.emails[1],'scratch-password-71')
        with connect() as c:c.execute("UPDATE users SET status='disabled' WHERE id=%s",(user.id,))
        with self.assertRaises(ApiError):auth.authenticate(token)
        with connect() as c:c.execute("UPDATE users SET status='active' WHERE id=%s",(user.id,))

from backend.errors import ApiError
if __name__=='__main__':unittest.main(verbosity=2)
