"""Additional real scratch release controls; no production/provider access."""
import os
import unittest
import uuid
from unittest.mock import patch
import test_v2_integration as fixtures
from backend.errors import ApiError

@unittest.skipUnless(os.getenv('RAG_V2_DB_TEST')=='1','explicit isolated scratch integration required')
class V2Release(unittest.TestCase):
    setUpClass=classmethod(fixtures.V2Integration.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.V2Integration.tearDownClass.__func__)
    headers=fixtures.V2Integration.headers

    def test_cross_owner_provenance_fk_and_source_id_enumeration(self):
        import numpy as np
        import psycopg
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services.conversation_service import create_conversation,save_message
        from services.memory_storage_service import save_memory
        vector=np.ones((1,384),dtype=np.float32)
        with tenant_scope(self.a.id):
            ca=create_conversation('owner A source');ma=save_message(ca,'user','I prefer jasmine tea.')
            with patch('services.memory_storage_service.generate_embeddings',return_value=vector):self.assertTrue(save_memory(ca,'The user prefers jasmine tea.',source_message_id=ma))
            with get_connection() as c:memory=c.execute('SELECT id FROM conversation_memories WHERE conversation_id=%s',(ca,)).fetchone()[0]
        with tenant_scope(self.b.id):
            cb=create_conversation('owner B source');mb=save_message(cb,'user','I prefer coffee.')
            with self.assertRaises(psycopg.errors.ForeignKeyViolation),get_connection() as c:
                c.execute('INSERT INTO memory_sources(conversation_id,memory_id,source_message_id) VALUES(%s,%s,%s)',(ca,memory,mb))
        with tenant_scope(self.a.id):
            c=get_connection()
            try:
                with self.assertRaises(psycopg.errors.ForeignKeyViolation),c:
                    c.execute('INSERT INTO conversation_memories(conversation_id,memory,embedding,source_message_id) VALUES(%s,%s,%s,%s)',(ca,'forged foreign source',vector[0].tolist(),mb))
                self.assertTrue(c.closed,'a rejected deferred commit must close its connection')
            finally:
                # Also clean up if the close-on-failed-commit regression fails.
                c.close()
        for cid in (ca,cb):
            r=self.client.get(f'/api/v2/conversations/{cid}/memories/{memory}/sources',headers=self.headers('b'))
            self.assertEqual(r.status_code,404,r.text)
        legitimate=self.client.get(f'/api/v2/conversations/{ca}/memories/{memory}/sources',headers=self.headers())
        self.assertEqual(legitimate.status_code,200,legitimate.text)
        self.assertEqual(legitimate.json()[0]['message_id'],ma)
        self.assertNotIn('jasmine',legitimate.text)

    def test_admin_bootstrap_reset_disable_and_audit(self):
        from backend.v2 import auth
        from scripts.v2_scratch import connect
        email=uuid.uuid4().hex+'@admin-release.test';password='secure-admin-scratch-password'
        admin_id=None
        try:
            with connect() as c:existing=c.execute("SELECT count(*) FROM users WHERE role='admin'").fetchone()[0]
            if existing:
                # An existing operator is never replaced merely to exercise bootstrap.
                with self.assertRaises(ApiError) as denied:auth.bootstrap_admin(email,password)
                self.assertEqual(denied.exception.code,'admin_exists')
                admin_id=str(uuid.uuid4())
                with connect() as c:c.execute("INSERT INTO users(id,email,password_hash,role) VALUES(%s,%s,%s,'admin')",(admin_id,email,auth.hash_password(password)))
            else:
                auth.bootstrap_admin(email,password)
                with connect() as c:admin_id=str(c.execute('SELECT id FROM users WHERE email=%s',(email,)).fetchone()[0])
            admin,token,csrf=auth.login(email,password)
            h={'cookie':f'rag_session={token}; rag_csrf={csrf}','x-csrf-token':csrf,'origin':'http://testserver'}
            listed=self.client.get('/api/v2/admin/users',headers=h)
            self.assertEqual(listed.status_code,200,listed.text)
            self.assertNotIn('password_hash',listed.text)
            duplicate=self.client.post('/api/v2/auth/register',json={'email':self.emails[1],'password':'different-duplicate-pass'},headers={'origin':'http://testserver'})
            fresh=self.client.post('/api/v2/auth/register',json={'email':email,'password':'different-duplicate-pass'},headers={'origin':'http://testserver'})
            self.assertEqual(duplicate.json(),fresh.json())
            user,old_token,old_csrf=auth.login(self.emails[1],'scratch-password-71')
            response=self.client.post(f'/api/v2/admin/users/{self.b.id}/reset-password',json={'password':'new-reset-scratch-password'},headers=h)
            self.assertEqual(response.status_code,200,response.text)
            with self.assertRaises(ApiError):auth.authenticate(old_token)
            with self.assertRaises(ApiError):auth.login(self.emails[1],'scratch-password-71')
            user,new_token,_=auth.login(self.emails[1],'new-reset-scratch-password')
            self.assertEqual(self.client.patch(f'/api/v2/admin/users/{self.b.id}',json={'status':'disabled'},headers=h).status_code,200)
            with self.assertRaises(ApiError):auth.authenticate(new_token)
            with self.assertRaises(ApiError):auth.login(self.emails[1],'new-reset-scratch-password')
            self.assertEqual(self.client.patch(f'/api/v2/admin/users/{self.b.id}',json={'status':'active'},headers=h).status_code,200)
            auth.login(self.emails[1],'new-reset-scratch-password')
            self.assertEqual(self.client.post('/api/v2/auth/logout',headers=h).status_code,200)
            self.assertEqual(self.client.get('/api/v2/admin/users',headers=h).status_code,401)
            with connect() as c:
                actions={r[0] for r in c.execute('SELECT action FROM audit_events WHERE actor_user_id=%s',(admin_id,)).fetchall()}
            self.assertTrue({'session.login','session.logout','admin.password_reset','admin.account_update'}<=actions)
        finally:
            # Restore this class's fixture account/session for later isolated probes.
            with connect() as c:c.execute("UPDATE users SET password_hash=%s,status='active',role='user' WHERE id=%s",(auth.hash_password('scratch-password-71'),self.b.id))
            _,type(self).tb,type(self).cb=auth.login(self.emails[1],'scratch-password-71')
            if admin_id:
                with connect() as c:
                    c.execute('DELETE FROM user_sessions WHERE user_id=%s',(admin_id,));c.execute('DELETE FROM audit_events WHERE actor_user_id=%s OR target_user_id=%s',(admin_id,admin_id));c.execute('DELETE FROM users WHERE id=%s',(admin_id,))

    def test_replacement_cancels_inflight_generation_and_keeps_atomic_file_contract(self):
        import numpy as np
        import pymupdf
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services import v2_jobs
        from services.v2_worker import process_one
        def pdf(text):
            doc=pymupdf.open();doc.new_page().insert_text((40,60),text)
            data=doc.tobytes();doc.close();return data
        def embed(texts):return np.ones((len(texts),384),dtype=np.float32)
        original=pdf('Original astronomy policy states that a visitor permit costs forty one tokens and lasts seven days.')
        second=pdf('Intermediate astronomy policy states that a visitor permit costs fifty one tokens and lasts eight days.')
        final=pdf('Final astronomy policy states that a visitor permit costs sixty one tokens and lasts nine days.')
        created=self.client.post('/api/v2/documents',files={'file':('original.pdf',original,'application/pdf')},headers=self.headers())
        self.assertEqual(created.status_code,202,created.text);did=created.json()['id']
        self.assertTrue(process_one(self.a.id,'qa-replacement-worker',embed=embed))
        response=self.client.put('/api/v2/documents/'+did,files={'file':('intermediate.pdf',second,'application/pdf')},headers=self.headers())
        self.assertEqual(response.status_code,202,response.text);intermediate_job=response.json()['job_id']
        with tenant_scope(self.a.id):
            stale=v2_jobs.claim('qa-interrupted-generation')
            self.assertEqual(stale['id'],intermediate_job)
            with get_connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM document_chunks WHERE document_id=%s',(did,)).fetchone()[0],0)
        foreign=self.client.put('/api/v2/documents/'+did,files={'file':('foreign.pdf',final,'application/pdf')},headers=self.headers('b'))
        self.assertEqual(foreign.status_code,404,foreign.text)
        response=self.client.put('/api/v2/documents/'+did,files={'file':('final.pdf',final,'application/pdf')},headers=self.headers())
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(self.client.get('/api/v2/jobs/'+intermediate_job,headers=self.headers()).json()['status'],'cancelled')
        with tenant_scope(self.a.id):
            self.assertFalse(v2_jobs.publish(stale,[{'page_number':1,'text':'stale'}],
                [dict(document_name=did,page_number=1,chunk_id=1,content='stale')],embed(['stale'])))
        self.assertTrue(process_one(self.a.id,'qa-replacement-worker',embed=embed))
        detail=self.client.get('/api/v2/documents/'+did,headers=self.headers()).json()
        self.assertEqual(detail['status'],'ready',detail);self.assertEqual(detail['filename'],'final.pdf')
        self.assertEqual(self.client.get('/api/v2/documents/'+did+'/file',headers=self.headers()).content,final)
        rejected=self.client.put('/api/v2/documents/'+did,files={'file':('broken.pdf',b'not a PDF','application/pdf')},headers=self.headers())
        self.assertEqual(rejected.status_code,422,rejected.text)
        self.assertEqual(self.client.get('/api/v2/documents/'+did+'/file',headers=self.headers()).content,final)
        with tenant_scope(self.a.id),get_connection() as c:
            chunks=c.execute('SELECT content FROM document_chunks WHERE document_id=%s',(did,)).fetchall()
            self.assertEqual(len(chunks),1);self.assertIn('Final astronomy',chunks[0][0])
            self.assertNotIn('Intermediate',chunks[0][0]);self.assertNotIn('Original',chunks[0][0])

    def test_superuser_startup_refused_and_legacy_compatibility_is_explicit(self):
        from fastapi.testclient import TestClient
        from backend.v2.app import create_app
        from services import database
        from scripts.v2_scratch import DEFAULT,connect
        from services.tenant_context import tenant_scope
        with patch.object(database,'DATABASE_URL',DEFAULT):
            with self.assertRaisesRegex(RuntimeError,'non-superuser'):
                with TestClient(create_app()):pass
        legacy=str(uuid.uuid4())
        with connect() as c:c.execute("INSERT INTO conversations(id,title,owner_id) VALUES(%s,'unassigned legacy fixture',NULL)",(legacy,))
        try:
            with tenant_scope(self.a.id),database.get_connection() as c:self.assertIsNone(c.execute('SELECT id FROM conversations WHERE id=%s',(legacy,)).fetchone())
            with patch.dict(os.environ,{'RAG_V2':'0','RAG_V2_COMPAT':'1'}),database.get_connection() as c:
                self.assertIsNotNone(c.execute('SELECT id FROM conversations WHERE id=%s',(legacy,)).fetchone())
                self.assertEqual(c.execute('SELECT count(*) FROM conversations WHERE owner_id IS NOT NULL').fetchone()[0],0)
                c.execute('UPDATE conversations SET title=%s WHERE id=%s',('explicit compatibility edit',legacy))
            with patch.dict(os.environ,{'RAG_V2':'1','RAG_V2_COMPAT':'1'}):
                with self.assertRaises(RuntimeError):database.get_connection()
        finally:
            with connect() as c:c.execute('DELETE FROM conversations WHERE id=%s',(legacy,))

    def test_unknown_or_mismatched_index_model_refuses_each_retriever(self):
        import numpy as np
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services.ingestion_service import write_document_chunks
        from services.v2_index import require_index_identity
        from services.search_service import semantic_search
        from services.bm25_service import bm25_search
        from services.fts_service import fts_search
        from services import retrieval_config as cfg
        did=str(uuid.uuid4());vector=np.ones((1,384),dtype=np.float32)
        with tenant_scope(self.a.id),get_connection() as c:
            c.execute("INSERT INTO documents(id,filename,storage_path,status) VALUES(%s,'identity.pdf','unused','ready')",(did,))
            write_document_chunks(c.cursor(),did,[dict(document_name=did,page_number=1,chunk_id=1,content='A model identity fixture document contains astronomy permit tokens.')],vector)
        with tenant_scope(self.b.id):require_index_identity(self.b.id)
        for model,dim in ((None,None),('same-dimensional-other-model',384),(cfg.EMBEDDING_MODEL,128)):
            with tenant_scope(self.a.id),get_connection() as c:c.execute('UPDATE documents SET embedding_model=%s,embedding_dim=%s WHERE id=%s',(model,dim,did))
            with tenant_scope(self.a.id),patch('services.search_service.generate_embeddings',return_value=vector):
                for retriever in (semantic_search,bm25_search,fts_search):
                    with self.assertRaises(ApiError) as refused:retriever('astronomy')
                    self.assertEqual(refused.exception.code,'index_model_mismatch')
        with tenant_scope(self.a.id),get_connection() as c:c.execute('UPDATE documents SET embedding_model=%s,embedding_dim=%s WHERE id=%s',(cfg.EMBEDDING_MODEL,cfg.EMBEDDING_DIM,did))
        with tenant_scope(self.a.id),patch('services.search_service.generate_embeddings',return_value=vector):
            for retriever in (semantic_search,bm25_search,fts_search):self.assertTrue(retriever('astronomy'))

if __name__=='__main__':unittest.main(verbosity=2)
