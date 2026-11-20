"""Queue/worker regression plus explicitly opted-in real PostgreSQL/process checks."""
import os
os.environ.setdefault('DATABASE_URL','postgresql://nobody@127.0.0.1:1/rag_test_scratch')
import json
import numpy as np
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import MagicMock,patch
from services import v2_jobs as jobs
from services.v2_coordination import resource_lock
from services.tenant_context import tenant_scope

OWNER='f4879912-7324-4ae4-ac1d-3303294c2f45'
JOB={'id':str(uuid.uuid4()),'document_id':str(uuid.uuid4()),'document_version':'1','lease_token':str(uuid.uuid4())}

class WorkerTests(unittest.TestCase):
    def test_invalid_lease_and_heartbeat_refuse_before_connection(self):
        with patch.object(jobs,'get_connection') as connection:
            for lease in (0,4,601):
                with self.assertRaises(ValueError):jobs.claim('worker',lease)
                with self.assertRaises(ValueError):jobs.heartbeat(JOB,0,lease)
            with self.assertRaises(ValueError):jobs.heartbeat(JOB,101)
            connection.assert_not_called()

    def test_foreign_or_empty_chunk_publication_refused(self):
        with patch.object(jobs,'get_connection') as connection:
            with self.assertRaises(ValueError):jobs.publish(JOB,[],[],[])
            with self.assertRaises(ValueError):jobs.publish(JOB,[],[{'document_name':'foreign'}],[[]])
            connection.assert_not_called()

    def test_direct_publication_refuses_wrong_embedding_dimensions(self):
        with patch.object(jobs,'get_connection') as connection:
            with self.assertRaises(ValueError):
                jobs.publish(JOB,[],[{'document_name':JOB['document_id']}],np.zeros((1,12)))
            connection.assert_not_called()

    def test_expired_token_cannot_publish(self):
        c=MagicMock();c.execute.side_effect=[MagicMock(fetchone=lambda:(1,'queued')),MagicMock(fetchone=lambda:None)]
        with patch.object(jobs,'get_connection') as get,patch('services.ingestion_service.write_document_chunks') as write:
            get.return_value.__enter__.return_value=c
            self.assertFalse(jobs.publish(JOB,[],[{'document_name':JOB['document_id']}],np.zeros((1,384))))
            write.assert_not_called()

    def test_deleted_or_new_document_version_cannot_publish(self):
        for row in ((1,'deleted'),(2,'queued'),None):
            c=MagicMock();c.execute.side_effect=[MagicMock(fetchone=lambda:row),MagicMock(fetchone=lambda:(1,))]
            with patch.object(jobs,'get_connection') as get,patch('services.ingestion_service.write_document_chunks') as write:
                get.return_value.__enter__.return_value=c
                self.assertFalse(jobs.publish(JOB,[],[{'document_name':JOB['document_id']}],np.zeros((1,384))))
                write.assert_not_called()

    def test_lock_requires_tenant(self):
        with self.assertRaises(PermissionError):
            with resource_lock('x'):pass

    def test_lock_releases_on_handler_failure_and_has_no_open_transaction(self):
        c=MagicMock();c.execute.return_value.fetchone.return_value=(True,)
        with tenant_scope(OWNER),patch('services.v2_coordination.get_connection',return_value=c):
            with self.assertRaises(RuntimeError):
                with resource_lock('resource'):raise RuntimeError('handler')
        c.commit.assert_called_once();self.assertTrue(c.autocommit);c.close.assert_called_once()
        self.assertIn('pg_advisory_unlock',c.execute.call_args.args[0])

    def test_lock_closes_even_if_unlock_fails(self):
        c=MagicMock();c.execute.side_effect=[MagicMock(fetchone=lambda:(True,)),RuntimeError('disconnect')]
        with tenant_scope(OWNER),patch('services.v2_coordination.get_connection',return_value=c):
            with self.assertRaises(RuntimeError):
                with resource_lock('resource'):pass
        c.close.assert_called_once()

    def test_idle_worker_does_not_load_models(self):
        from services.v2_worker import process_one
        with patch('services.v2_worker.jobs.claim',return_value=None),patch('services.v2_worker.get_connection') as conn:
            self.assertFalse(process_one(OWNER,'worker'));conn.assert_not_called()

    def test_worker_publication_and_failure_paths(self):
        from services.v2_worker import process_one
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/OWNER;folder.mkdir();file=folder/'fixture.pdf';file.write_bytes(b'fixture')
            c=MagicMock();c.execute.return_value.fetchone.return_value=(str(file),1,'queued')
            for accepted in (True,False):
                with patch.dict(os.environ,{'RAG_V2_UPLOAD_DIR':temp}),patch('services.v2_worker.get_connection') as conn,patch.object(jobs,'claim',return_value=JOB),patch.object(jobs,'publish',return_value=accepted) as publish,patch.object(jobs,'fail') as fail:
                    conn.return_value.__enter__.return_value=c
                    extract=lambda *a,**kw:[{'page_number':1,'text':'This fixture contains enough words for a single searchable chunk with original page provenance.'}]
                    embed=lambda texts:np.zeros((len(texts),384))
                    self.assertTrue(process_one(OWNER,'worker',extract=extract,embed=embed));publish.assert_called_once();fail.assert_not_called()

    def test_worker_does_not_read_another_owners_file(self):
        from services.v2_worker import process_one
        c=MagicMock();c.execute.return_value.fetchone.return_value=('/tmp/other/secret.pdf',1,'queued')
        with patch('services.v2_worker.get_connection') as conn,patch.object(jobs,'claim',return_value=JOB),patch.object(jobs,'publish') as publish,patch.object(jobs,'fail') as fail:
            conn.return_value.__enter__.return_value=c
            self.assertTrue(process_one(OWNER,'worker',extract=MagicMock(),embed=MagicMock()))
            publish.assert_not_called();fail.assert_called_once_with(JOB,'processing_failed')


@unittest.skipUnless(os.getenv('RAG_V2_DB_TESTS')=='1','explicit isolated PostgreSQL fixture required')
class QueueProcessTests(unittest.TestCase):
    def setUp(self):
        from services.database import get_connection
        from services.tenant_context import auth_system_context
        self.owner=str(uuid.uuid4());self.doc=str(uuid.uuid4());self.job=None
        self.original_connection=get_connection
        def checked():
            c=self.original_connection()
            if c.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
                c.close();raise RuntimeError('refusing non-scratch database')
            return c
        self.queue_patch=patch.object(jobs,'get_connection',side_effect=checked);self.queue_patch.start();self.addCleanup(self.queue_patch.stop)
        with auth_system_context(),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute("INSERT INTO users(id,email,password_hash) VALUES(%s,%s,'not-an-auth-fixture')",(self.owner,self.owner+'@worker.test'))
        with tenant_scope(self.owner),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute("INSERT INTO documents(id,filename,storage_path) VALUES(%s,'fixture.pdf','unread')",(self.doc,))
            self.job=jobs.enqueue(c,self.doc,1,self.doc+':1')

    def tearDown(self):
        from services.database import get_connection
        from services.tenant_context import auth_system_context
        with tenant_scope(self.owner),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute('DELETE FROM job_events WHERE owner_id=%s',(self.owner,));c.execute('DELETE FROM jobs WHERE owner_id=%s',(self.owner,));c.execute('DELETE FROM document_chunks WHERE owner_id=%s',(self.owner,));c.execute('DELETE FROM documents WHERE owner_id=%s',(self.owner,))
        with auth_system_context(),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute('DELETE FROM users WHERE id=%s',(self.owner,))

    def test_two_independent_processes_claim_once_and_expired_claim_recovers(self):
        from services.database import get_connection
        code="""import json,sys
from services.tenant_context import tenant_scope
from services import v2_jobs as jobs
original=jobs.get_connection
def checked():
 c=original()
 if c.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':raise RuntimeError('not scratch')
 return c
jobs.get_connection=checked
with tenant_scope(sys.argv[1]):print(json.dumps(jobs.claim(sys.argv[2],5)))
"""
        children=[subprocess.Popen([sys.executable,'-B','-c',code,self.owner,'worker-'+str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for i in range(2)]
        values=[]
        for child in children:
            out,err=child.communicate(timeout=20);self.assertEqual(child.returncode,0,err);values.append(json.loads(out))
        self.assertEqual(sum(v is not None for v in values),1)
        old=next(v for v in values if v)
        with tenant_scope(self.owner),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(old['id'],))
        with tenant_scope(self.owner):
            fresh=jobs.claim('replacement',5);self.assertIsNotNone(fresh);self.assertNotEqual(old['lease_token'],fresh['lease_token'])
            self.assertFalse(jobs.heartbeat(old));self.assertTrue(jobs.heartbeat(fresh,40,5))
            with get_connection() as c:
                self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch');self.assertTrue(jobs.cancel(c,fresh['id']))
            self.assertFalse(jobs.heartbeat(fresh));self.assertIsNone(jobs.claim('last',5))


    def test_old_job_cancellation_cannot_cancel_replacement_version(self):
        from services.database import get_connection
        with tenant_scope(self.owner),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute("UPDATE documents SET version=2,status='queued' WHERE id=%s",(self.doc,))
            self.assertTrue(jobs.cancel(c,self.job))
            self.assertEqual(c.execute('SELECT version,status FROM documents WHERE id=%s',(self.doc,)).fetchone(),(2,'queued'))

    def test_crashed_worker_is_recovered_and_final_crash_marks_document_failed(self):
        from services.database import get_connection
        code="""import os,sys
from services.tenant_context import tenant_scope
from services.database import get_connection
from services.v2_jobs import claim
with tenant_scope(sys.argv[1]):
 with get_connection() as c:assert c.execute('SELECT current_database()').fetchone()[0]=='rag_test_scratch'
 assert claim('crashing-process',5) is not None
 os._exit(17)
"""
        child=subprocess.run([sys.executable,'-B','-c',code,self.owner],capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,17,child.stderr)
        with tenant_scope(self.owner),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            self.assertEqual(c.execute('SELECT attempts,status FROM jobs WHERE id=%s',(self.job,)).fetchone(),(1,'running'))
            c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(self.job,))
        with tenant_scope(self.owner):
            recovered=jobs.claim('surviving-process',5);self.assertIsNotNone(recovered)
            with get_connection() as c:
                self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
                c.execute("UPDATE jobs SET attempts=max_attempts,lease_until=now()-interval '1 second' WHERE id=%s",(self.job,))
            self.assertIsNone(jobs.claim('terminal-reaper',5))
            with get_connection() as c:
                self.assertEqual(c.execute('SELECT status,error_code FROM jobs WHERE id=%s',(self.job,)).fetchone(),('failed','attempts_exhausted'))
                self.assertEqual(c.execute('SELECT status FROM documents WHERE id=%s',(self.doc,)).fetchone()[0],'failed')
                self.assertEqual(c.execute("SELECT count(*) FROM job_events WHERE job_id=%s AND event='attempts_exhausted'",(self.job,)).fetchone()[0],1)

    def test_cancelled_claim_cannot_publish_or_duplicate_chunks(self):
        from services.database import get_connection
        import numpy as np
        with tenant_scope(self.owner):
            claimed=jobs.claim('publishing-process',120)
            chunks=[{'document_name':self.doc,'page_number':1,'chunk_id':1,'content':'This independently owned fixture verifies atomic chunk publication and retry idempotency.'}]
            vectors=np.zeros((1,384))
            self.assertTrue(jobs.publish(claimed,[{'page_number':1,'text':chunks[0]['content']}],chunks,vectors))
            self.assertFalse(jobs.publish(claimed,[{'page_number':1}],chunks,vectors))
            with get_connection() as c:
                self.assertEqual(c.execute('SELECT count(*) FROM document_chunks WHERE document_id=%s',(self.doc,)).fetchone()[0],1)
                from services import retrieval_config as cfg
                self.assertEqual(c.execute('SELECT embedding_model,embedding_dim FROM documents WHERE id=%s',(self.doc,)).fetchone(),(cfg.EMBEDDING_MODEL,cfg.EMBEDDING_DIM))
                self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
                c.execute("UPDATE documents SET status='queued',version=2 WHERE id=%s",(self.doc,))
                fresh_id=jobs.enqueue(c,self.doc,2,self.doc+':2')
            fresh=jobs.claim('cancelled-process',120)
            with get_connection() as c:
                self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch');self.assertTrue(jobs.cancel(c,fresh_id))
            self.assertFalse(jobs.publish(fresh,[{'page_number':1}],chunks,vectors))
            with get_connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM document_chunks WHERE document_id=%s',(self.doc,)).fetchone()[0],1)

    def test_scheduler_discovers_new_active_owner_without_restart(self):
        from scripts.run_v2_worker import active_owner_batch
        self.assertIn(self.owner,active_owner_batch(None,100))
        # Keyset batches honor cursor and bound work; account scope does not query tenant rows.
        after=active_owner_batch(self.owner,100)
        self.assertTrue(all(uuid.UUID(value)>uuid.UUID(self.owner) for value in after))

    def test_independent_process_resource_locks_order_work(self):
        from services.database import get_connection
        cid=str(uuid.uuid4())
        with tenant_scope(self.owner),get_connection() as c:
            self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
            c.execute("INSERT INTO conversations(id,title) VALUES(%s,'0')",(cid,))
        code="""import sys,time
from services.tenant_context import tenant_scope
from services.database import get_connection
from services.v2_coordination import resource_lock
with tenant_scope(sys.argv[1]),resource_lock(sys.argv[2]):
 with get_connection() as c:
  assert c.execute('SELECT current_database()').fetchone()[0]=='rag_test_scratch'
  n=int(c.execute('SELECT title FROM conversations WHERE id=%s',(sys.argv[2],)).fetchone()[0])
 time.sleep(.15)
 with get_connection() as c:
  assert c.execute('SELECT current_database()').fetchone()[0]=='rag_test_scratch'
  c.execute('UPDATE conversations SET title=%s WHERE id=%s',(str(n+1),sys.argv[2]))
"""
        children=[subprocess.Popen([sys.executable,'-B','-c',code,self.owner,cid],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        try:
            for child in children:
                out,err=child.communicate(timeout=20);self.assertEqual(child.returncode,0,err)
            with tenant_scope(self.owner),get_connection() as c:
                self.assertEqual(c.execute('SELECT title FROM conversations WHERE id=%s',(cid,)).fetchone()[0],'2')
        finally:
            with tenant_scope(self.owner),get_connection() as c:
                self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
                c.execute('DELETE FROM conversations WHERE id=%s',(cid,))

if __name__=='__main__':unittest.main()
