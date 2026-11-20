"""Real scanned-PDF/worker/PostgreSQL/API journey with OFFLINE model fixtures.

OCR, storage, chunking, pgvector/BM25/RRF, citation validation, message persistence,
provenance and deletion are real. Embeddings and provider/extraction judgments
are deterministic fixtures: this suite does NOT certify live Gemini quality.
"""
import os
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import test_v2_integration as fixtures

@unittest.skipUnless(os.getenv('RAG_V2_DB_TEST')=='1','explicit isolated scratch integration required')
class V2Journey(unittest.TestCase):
    setUpClass=classmethod(fixtures.V2Integration.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.V2Integration.tearDownClass.__func__)
    headers=fixtures.V2Integration.headers

    def test_real_scan_worker_retrieval_answer_memory_followup_delete(self):
        import numpy as np
        import main
        from services import retrieval_config as cfg
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services.v2_worker import process_one
        from services.memory_storage_service import save_memory
        import pymupdf
        # Construct an image-only synthetic PDF locally; never consume corpus PDFs.
        native=pymupdf.open();page=native.new_page()
        page.insert_text((50,80),'Lumen visitor permit policy',fontsize=18)
        page.insert_text((50,120),'A visitor permit costs 71 tokens and remains valid for 23 days.',fontsize=14)
        page.insert_text((50,155),'Visitors must keep their permit during every observatory visit.',fontsize=14)
        image=page.get_pixmap(dpi=180).tobytes('png')
        scan=pymupdf.open();scan.new_page().insert_image(page.rect,stream=image)
        scanned=scan.tobytes();scan.close();native.close()
        def embeddings(texts):return np.ones((len(texts),384),dtype=np.float32)
        response=self.client.post('/api/v2/documents',files={'file':('scanned.pdf',scanned,'application/pdf')},headers=self.headers())
        self.assertEqual(response.status_code,202,response.text);did=response.json()['id'];jid=response.json()['job_id']
        self.assertTrue(process_one(self.a.id,'qa-real-ocr-worker',embed=embeddings))
        document=self.client.get('/api/v2/documents/'+did,headers=self.headers()).json()
        self.assertEqual(document['status'],'ready',document)
        self.assertGreater(document['chunks'],0)
        self.assertEqual(document['page_metadata'][0]['method'],'pymupdf-tesseract-fast-4.1.0')
        self.assertEqual(self.client.get('/api/v2/jobs/'+jid,headers=self.headers()).json()['status'],'succeeded')
        self.assertEqual(self.client.get('/api/v2/documents/'+did+'/file',headers=self.headers('b')).status_code,404)
        cid=self.client.post('/api/v2/conversations',json={'title':'scanned journey'},headers=self.headers()).json()['conversation_id']
        def extract_fixture(conversation_id,messages):
            source=next(m for m in messages if m['role']=='user' and 'prefer tea' in m['content'])
            self.assertTrue(save_memory(conversation_id,'The user prefers tea.',source_message_id=source['id']))
        with ExitStack() as stack:
            stack.enter_context(patch('services.search_service.generate_embeddings',side_effect=embeddings))
            stack.enter_context(patch('services.memory_search_service.generate_embeddings',side_effect=embeddings))
            stack.enter_context(patch('services.memory_storage_service.generate_embeddings',side_effect=embeddings))
            stack.enter_context(patch('services.rag_service.rewrite_query',side_effect=lambda query,**kw:query))
            stack.enter_context(patch('services.rag_service.classify_question',return_value='DOCUMENT'))
            stack.enter_context(patch('services.rag_service.generate_answer',return_value='[DOCUMENT] A visitor permit costs 71 tokens [S1].'))
            stack.enter_context(patch.object(cfg,'RERANK_ENABLED',False))
            stack.enter_context(patch.object(main,'extract_and_save_memories',side_effect=extract_fixture))
            first=self.client.post('/api/v2/chat',json={'conversation_id':cid,'message':'I prefer tea. What does a visitor permit cost?'},headers=self.headers())
            self.assertEqual(first.status_code,200,first.text);answer=first.json()
            self.assertEqual(answer['answer_status'],'answered',answer)
            self.assertIn('71',answer['answer']);self.assertEqual(answer['citations'][0]['document_id'],did)
            self.assertEqual(answer['citations'][0]['page'],1)
            followup=self.client.post('/api/v2/chat',json={'conversation_id':cid,'message':'What is that permit cost again?'},headers=self.headers())
            self.assertEqual(followup.status_code,200,followup.text)
            self.assertEqual(followup.json()['memory_extraction'],'checkpoint_advanced',followup.text)
            memories=self.client.get('/api/v2/memories?conversation_id='+cid,headers=self.headers())
            self.assertEqual(memories.status_code,200,memories.text)
            memory=memories.json()[0]['memories'][0];mid=memory['memory_id']
            provenance=f'/api/v2/conversations/{cid}/memories/{mid}/sources'
            self.assertEqual(self.client.get(provenance,headers=self.headers()).json()[0]['role'],'user')
            self.assertEqual(self.client.get(provenance,headers=self.headers('b')).status_code,404)
            deleted=self.client.delete(f'/api/v2/conversations/{cid}/memories/{mid}',headers=self.headers())
            self.assertEqual(deleted.status_code,200,deleted.text)
            self.assertEqual(self.client.get('/api/v2/memories?conversation_id='+cid,headers=self.headers()).json()[0]['memories'],[])
        self.assertEqual(self.client.delete('/api/v2/documents/'+did,headers=self.headers()).status_code,200)
        self.assertEqual(self.client.delete('/api/v2/conversations/'+cid,headers=self.headers()).status_code,200)
        with tenant_scope(self.a.id),get_connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM document_chunks WHERE document_id=%s',(did,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM messages WHERE conversation_id=%s',(cid,)).fetchone()[0],0)

if __name__=='__main__':unittest.main(verbosity=2)
