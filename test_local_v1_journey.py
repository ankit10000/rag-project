"""Gate 1: real local HTTP/PDF/Postgres/retrieval/memory lifecycle; providers mocked.

Requires explicitly configured rag_test_scratch and verifies current_database()
before every fixture/cleanup write. It never truncates or clears unrelated rows.
"""
import os
os.environ.setdefault("LOCAL_V1_PROFILE", "1")
import testsafe
testsafe.require_scratch_db()
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
import uuid
from unittest.mock import patch
import numpy as np
import pymupdf
from fastapi.testclient import TestClient
from backend.app import create_app
from services.database import get_connection

TOKEN='local-gate-one-test-token-more-than-thirty-two-characters'
PREFIX='/api/v1'


class LocalJourneyTests(unittest.TestCase):
    def checked_connection(self):
        conn=get_connection()
        if conn.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
            conn.close();raise RuntimeError('Gate 1 requires rag_test_scratch exactly')
        return conn

    def setUp(self):
        # Verify the actual server, not only the spelling in a connection URL.
        with self.checked_connection(): pass
        self.created=[];self.uid=uuid.uuid4().hex;self.keyword='NebulaPermit'+self.uid
        self.document=self.keyword+'.pdf';self.prompts=[]
        self.stack=contextlib.ExitStack();self.addCleanup(self.cleanup)
        self.folder=self.stack.enter_context(tempfile.TemporaryDirectory(dir='/private/tmp'))
        self.stack.enter_context(patch('backend.config.UPLOAD_DIR',self.folder))
        self.stack.enter_context(patch('backend.app.load_token_digest',return_value=(hashlib.sha256(TOKEN.encode()).digest(),'test')))
        def embeddings(texts):
            vectors=np.zeros((len(texts),384),dtype=np.float32);vectors[:,0]=1;return vectors
        for module in ('ingestion_service','search_service','memory_storage_service','memory_search_service'):
            self.stack.enter_context(patch('services.'+module+'.generate_embeddings',side_effect=embeddings))
        self.stack.enter_context(patch('services.rag_service.generate_answer',side_effect=self.provider))
        self.stack.enter_context(patch('services.rag_service.rewrite_query',side_effect=lambda query,**kw:query))
        self.stack.enter_context(patch('services.memory_service.generate_answer',side_effect=self.extractor))
        self.stack.enter_context(patch('services.memory_decision_service.generate_answer',side_effect=self.memory_decision))
        self.stack.enter_context(patch('services.memory_cleanup_service.generate_answer',side_effect=self.cleanup_provider))
        self.stack.enter_context(patch('services.hybrid_search_service.rerank_results',side_effect=self.rerank))
        self.client=self.stack.enter_context(TestClient(create_app(),base_url='http://127.0.0.1',raise_server_exceptions=False))
        self.client.headers['Authorization']='Bearer '+TOKEN

    def cleanup(self):
        self.stack.close()
        with self.checked_connection() as conn:
            for cid in self.created:
                conn.execute('DELETE FROM conversations WHERE id=%s',(uuid.UUID(cid),))
            conn.execute('DELETE FROM document_chunks WHERE document_name=%s',(self.document,))

    def provider(self,prompt):
        self.prompts.append(prompt)
        if 'Classify the user' in prompt:
            query=prompt.rsplit('Question:\n',1)[1].lower()
            return 'MEMORY' if 'remember' in query else 'DOCUMENT'
        query=prompt.rsplit('<user_question>\n',1)[1].split('</user_question>')[0]
        if 'remember' in query.lower():
            memory=prompt.split('CONVERSATION MEMORY (context only):\n',1)[1].split('<conversation_history>')[0]
            return '[MEMORY] You prefer concise explanations.' if 'concise explanations' in memory else '[MEMORY] I have no stored preference.'
        refs=re.findall(r'\[(S\d+)\] Document: '+re.escape(self.document)+r' \|',prompt)
        if not refs: raise AssertionError('real retrieval did not return the uploaded fixture')
        fact='duration is 30 days' if 'long' in query.lower() else 'fee is 65 dollars'
        return f'[DOCUMENT] The {self.keyword} {fact}. [{refs[0]}]'

    def extractor(self,prompt):
        lines=re.findall(r'\[id=(\d+)\] user: ([^\n]*)',prompt)
        for sid,text in lines:
            if 'I prefer concise explanations' in text:
                return json.dumps([{'memory':'User prefers concise explanations.','source_message_ids':[int(sid)]}])
        return '[]'

    def memory_decision(self,prompt):
        if 'AVAILABLE MEMORIES:' in prompt:
            ids=[int(i) for i in re.findall(r'ID: (\d+) \| Memory: User prefers concise explanations',prompt)]
            return json.dumps({'status':'DELETE' if ids else 'NO_MATCH','memory_ids':ids})
        return json.dumps({'action':'NEW','memory_id':None,'updated_memory':None})

    def cleanup_provider(self,prompt):
        if 'RECENT MESSAGES:' in prompt:
            return json.dumps([int(i) for i,text in re.findall(r'\[id=(\d+)\] [^:]+: ([^\n]*)',prompt) if 'concise explanations' in text])
        if 'SUMMARY TO CHECK' in prompt:return '{"still_contains":false,"evidence":""}'
        return 'EMPTY'

    def rerank(self,query,results,top_k):
        ranked=sorted(results,key=lambda r:r['chunk'][1]!=self.document)
        return [dict(r,rerank_score=10.0 if r['chunk'][1]==self.document else -100.0) for r in ranked[:top_k]]

    def create(self):
        response=self.client.post(PREFIX+'/conversations',json={'title':'Gate1 '+self.uid})
        self.assertEqual(response.status_code,201,response.text)
        cid=response.json()['conversation_id'];self.created.append(cid);return cid

    def chat(self,cid,message):
        with contextlib.redirect_stdout(io.StringIO()) as console:
            response=self.client.post(PREFIX+'/chat',json={'conversation_id':cid,'message':message})
        self.assertNotIn(self.document,console.getvalue())
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def pdf(self):
        with pymupdf.open() as doc:
            page=doc.new_page();page.insert_textbox(pymupdf.Rect(36,36,559,806),
                f'{self.keyword} local permit rules. The {self.keyword} fee is 65 dollars. '
                f'The {self.keyword} duration is 30 days. Permits are issued locally for registered applicants.',fontsize=10)
            return doc.tobytes()

    def test_gate_one_pdf_chat_memory_followup_forget_and_deletions(self):
        with contextlib.redirect_stdout(io.StringIO()):
            upload=self.client.post(PREFIX+'/documents',files={'file':(self.document,self.pdf(),'application/pdf')})
            self.assertEqual(upload.status_code,201,upload.text);self.assertGreater(upload.json()['chunks'],0)
            self.assertEqual(self.client.get(PREFIX+'/documents/'+self.document).status_code,200)
            duplicate=self.client.post(PREFIX+'/documents',files={'file':(self.document,self.pdf(),'application/pdf')})
            self.assertEqual(duplicate.status_code,409)
            old=(Path(self.folder)/self.document).read_bytes()
            broken=self.client.post(PREFIX+'/documents?replace=true',files={'file':(self.document,b'not a PDF','application/pdf')})
            self.assertEqual(broken.status_code,422);self.assertEqual((Path(self.folder)/self.document).read_bytes(),old)
            cid=self.create()
            first=self.chat(cid,f'I prefer concise explanations. What is the {self.keyword} fee?')
            self.assertEqual(first['status'],'answered');self.assertEqual(first['citations'][0]['document'],self.document)
            self.assertEqual(first['citations'][0]['page'],1)
            second=self.chat(cid,f'How long is the {self.keyword} permit valid?')
            self.assertIn('30 days',second['answer']);self.assertEqual(second['memory_extraction'],'checkpoint_advanced')
            memories=self.client.get(PREFIX+f'/conversations/{cid}/memories').json()['memories']
            self.assertEqual(len(memories),1);mid=memories[0]['memory_id']
            source=self.client.get(PREFIX+f'/conversations/{cid}/memories/{mid}/sources')
            self.assertEqual(source.status_code,200);self.assertEqual(source.json()[0]['role'],'user')
            reminder=self.chat(cid,'What do you remember about my preference?')
            self.assertIn('concise explanations',reminder['answer'])
            forgotten=self.chat(cid,'Forget my preference for concise explanations.')
            self.assertEqual(forgotten['kind'],'memory_deletion');self.assertEqual(forgotten['deleted_count'],1)
            after=self.chat(cid,'What do you remember about my preference?')
            self.assertNotIn('concise explanations',after['answer'])
            self.assertEqual(self.client.get(PREFIX+f'/conversations/{cid}/memories').json()['memories'],[])
            current=self.client.get(PREFIX+f'/conversations/{cid}').json()['messages']
            self.assertFalse(any('concise explanations' in m['content'] for m in current))
            other=self.create()
            self.chat(other,f'I prefer concise explanations. What is the {self.keyword} fee?')
            self.chat(other,f'How long is the {self.keyword} permit valid?')
            own=self.client.get(PREFIX+f'/conversations/{other}').json()['messages']
            foreign=self.client.delete(PREFIX+f'/conversations/{cid}/messages/{own[0]["id"]}')
            self.assertEqual(foreign.status_code,404)
            deletion=self.client.delete(PREFIX+f'/conversations/{other}/messages/{own[0]["id"]}')
            self.assertEqual(deletion.status_code,200,deletion.text)
            self.assertTrue(deletion.json()['orphaned_memory_ids'])
            self.assertEqual(self.client.get(PREFIX+f'/conversations/{other}/memories').json()['memories'],[])
            again=self.chat(other,'What do you remember about my preference?')
            self.assertNotIn('concise explanations',again['answer'])
            for conversation in (cid,other):
                self.assertEqual(self.client.delete(PREFIX+f'/conversations/{conversation}').status_code,200)
                self.assertEqual(self.client.get(PREFIX+f'/conversations/{conversation}').status_code,404)
                with self.checked_connection() as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM messages WHERE conversation_id=%s',(uuid.UUID(conversation),)).fetchone()[0],0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM conversation_memories WHERE conversation_id=%s',(uuid.UUID(conversation),)).fetchone()[0],0)

    def test_provider_failure_returns_safe_error_without_checkpoint_or_memory(self):
        secret='SECRET-provider-key-and-private-document-content'
        with contextlib.redirect_stdout(io.StringIO()):
            upload=self.client.post(PREFIX+'/documents',files={'file':(self.document,self.pdf(),'application/pdf')})
            self.assertEqual(upload.status_code,201,upload.text)
            cid=self.create()
            with patch('services.rag_service.generate_answer',side_effect=RuntimeError(secret)), \
                 patch('services.memory_service.generate_answer',side_effect=RuntimeError(secret)):
                first=self.chat(cid,f'What is the {self.keyword} fee?')
                second=self.chat(cid,f'How long is the {self.keyword} permit valid?')
        for response in (first,second):
            self.assertEqual(response['status'],'error')
            self.assertEqual(response['citations'],[])
            self.assertNotIn(secret,json.dumps(response))
            self.assertIn('try again',response['answer'].lower())
        self.assertEqual(second['memory_extraction'],'failed_will_retry')
        with self.checked_connection() as conn:
            checkpoint=conn.execute('SELECT COALESCE(memory_extraction_up_to_message_id,0) FROM conversations WHERE id=%s',(uuid.UUID(cid),)).fetchone()[0]
            self.assertEqual(checkpoint,0)
            self.assertEqual(conn.execute('SELECT count(*) FROM conversation_memories WHERE conversation_id=%s',(uuid.UUID(cid),)).fetchone()[0],0)
            rows=conn.execute('SELECT role,content FROM messages WHERE conversation_id=%s ORDER BY id',(uuid.UUID(cid),)).fetchall()
            self.assertEqual(len(rows),4)
            self.assertFalse(any(secret in text for _,text in rows))

    def test_direct_memory_delete_fences_history_and_cross_conversation(self):
        from services.conversation_service import save_message,update_conversation_memory
        from services.memory_storage_service import save_memory
        cid=self.create();other=self.create()
        sid=save_message(cid,'user','I prefer concise explanations.');save_message(cid,'assistant','Concise explanations noted.')
        self.assertTrue(save_memory(cid,'User prefers concise explanations.',source_message_ids=[sid]))
        update_conversation_memory(cid,'User prefers concise explanations.',sid)
        mid=self.client.get(PREFIX+f'/conversations/{cid}/memories').json()['memories'][0]['memory_id']
        self.assertEqual(self.client.delete(PREFIX+f'/conversations/{other}/memories/{mid}').status_code,404)
        self.assertEqual(self.client.delete(PREFIX+f'/conversations/{cid}/memories/{mid}').status_code,200)
        self.assertEqual(self.client.get(PREFIX+f'/conversations/{cid}').json()['messages'],[])
        with self.checked_connection() as conn:
            self.assertEqual(conn.execute('SELECT summary FROM conversations WHERE id=%s',(uuid.UUID(cid),)).fetchone()[0],'')


if __name__=='__main__':unittest.main()
