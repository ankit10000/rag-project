"""One bounded synthetic v2 functional journey, never a held-out evaluation.

Predeclared hard checks: two independent real OCR/embedding workers publish one
image-only page for each of two new owners; A's grounded answer contains 37/19,
all document citations belong to A on page1, B receives safe404 on A resources;
a real second turn extracts a peppermint-tea user preference with user-message
provenance; a later memory follow-up recalls it; deletion cannot be republished
by the old completed lease. Maximum12 actual Gemini SDK calls, no model downloads.
Only the explicitly identified localhost rag_test_scratch may be connected to.

Run once: .venv/bin/python -B scripts/v2_live_smoke.py
Outputs exclusively created v2_evidence/live_smoke.json (real PASS or FAIL).
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
MAX_CALLS=12
CRITERIA={
 'scope':'synthetic functional integration only; not formal evaluation acceptance',
 'two_independent_workers':'both separate PIDs use real pinned local OCR and actual cached embeddings',
 'image_only_pdf':'no native PDF text; original page1 is preserved in indexed chunks/citations',
 'document_facts':{'permit_cost':37,'validity_days':19},
 'negative_fact':'the gallery does not operate a fax service',
 'grounding':'answered; facts37 and19; nonempty valid citation belonging only to A document/page1; rerank_status ok',
 'isolation':'B receives404 for A document/file/job/conversation/memory provenance and cannot list A resources',
 'memory':'peppermint-tea preference extracted from actual user message, user_source link, followed by real memory recall',
 'deletion':'document chunks disappear and completed stale lease cannot republish; conversation cascades memory/source removal',
 'maximum_actual_gemini_sdk_calls':MAX_CALLS,
 'failure_policy':'preserve raw actual outcome; do not change criteria, retry identity or claim formal acceptance',
}
SOURCE_A=('Orion Gallery visitor policy. A visitor permit costs 37 credits. '
          'Every visitor permit is valid for 19 days. The gallery does not operate a fax service.')
SOURCE_B=('Zephyr Archive private member policy. A private member pass costs 88 credits. '
          'The Zephyr pass is valid for 8 days. Zephyr operates a members-only reading room.')


def configure():
    from scripts.v2_scratch import app_url
    os.environ.update(DATABASE_URL=app_url(),RAG_V2='1',RAG_V2_COMPAT='0',HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1',LOCAL_V1_PROFILE='0',LOCAL_V1_REQUEST_TIMEOUT_SECONDS='300',
                      GEMINI_FALLBACK_MODELS='',RAG_OCR_TESSDATA='/private/tmp/rag-v2-tessdata',
                      TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2')
    # Verify identity on EVERY real connection before any caller can write.
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    original=psycopg.connect
    def guarded(conninfo='',**kwargs):
        info=conninfo_to_dict(conninfo,**{k:v for k,v in kwargs.items() if k in ('dbname','host','port','user','password')})
        if info.get('dbname')!='rag_test_scratch' or info.get('host') not in ('127.0.0.1','localhost','::1'):
            raise PermissionError('only explicit localhost scratch connections permitted')
        conn=original(conninfo,**kwargs)
        try:
            if conn.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
                raise PermissionError('scratch database identity mismatch')
            conn.commit()
        except BaseException:
            conn.close();raise
        return conn
    psycopg.connect=guarded


def image_pdf(text):
    import pymupdf
    native=pymupdf.open();page=native.new_page(width=600,height=500)
    page.insert_textbox(pymupdf.Rect(35,45,565,460),text,fontsize=20,lineheight=1.5)
    png=page.get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png')
    result=pymupdf.open();page=result.new_page(width=600,height=500)
    page.insert_image(page.rect,stream=png)
    assert not page.get_text().strip(),'fixture must contain no native text'
    data=result.tobytes();native.close();result.close();return data


def internal_worker(owner,identity):
    configure()
    from services.v2_worker import process_one
    return 0 if process_one(owner,identity) else 2


def main(output_name="live_smoke.json"):
    import re
    if not re.fullmatch(r"live_smoke(?:_[a-z0-9]+)?\.json",output_name):raise ValueError("invalid evidence basename")
    output=ROOT/"v2_evidence"/output_name
    output.parent.mkdir(exist_ok=True)
    run_id='v2-orion-live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    report={'run_id':run_id,'started_at':datetime.now(timezone.utc).isoformat(),
            'predeclared_criteria':CRITERIA,'synthetic_sources':{'A':SOURCE_A,'B':SOURCE_B},
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'status':'RUNNING','checks':[],'provider_calls':[],'answers':[],'human_certification':False}
    # Exclusive claim precedes provider calls; an interrupted identity is not rerun.
    with output.open('x') as f:json.dump(report,f,indent=2)
    started=time.monotonic()
    lock=threading.Lock()
    def check(name,value,detail=None):
        entry={'name':name,'pass':bool(value)}
        if detail is not None:entry['detail']=detail
        report['checks'].append(entry)
    try:
        configure()
        from fastapi.testclient import TestClient
        from backend.v2.app import create_app
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services import llm_service
        from google import genai
        from google.genai import types
        # Client construction has no network call; turn off SDK transport retries.
        real_client=genai.Client(api_key=os.environ['GEMINI_API_KEY'],http_options=types.HttpOptions(
            timeout=120000,retry_options=types.HttpRetryOptions(attempts=1)))
        original=real_client.models.generate_content
        class CountedModels:
            def generate_content(self,*args,**kwargs):
                with lock:
                    if len(report['provider_calls'])>=MAX_CALLS:raise RuntimeError('synthetic provider call budget exhausted')
                    contents=kwargs.get('contents',args[0] if args else '')
                    exact=contents if isinstance(contents,str) else json.dumps(contents,sort_keys=True,default=str)
                    item={'requested_model':kwargs.get('model'),'prompt_sha256':hashlib.sha256(exact.encode()).hexdigest(),
                          'started_at':datetime.now(timezone.utc).isoformat()}
                    report['provider_calls'].append(item)
                tick=time.monotonic()
                try:
                    response=original(*args,**kwargs)
                    item.update(outcome='success',returned_model=getattr(response,'model_version',None),
                                response_sha256=hashlib.sha256((response.text or '').encode()).hexdigest())
                    return response
                except BaseException as error:
                    item.update(outcome='failure',error_type=type(error).__name__);raise
                finally:item['seconds']=round(time.monotonic()-tick,4)
        class CountedClient:models=CountedModels()
        llm_service.client=CountedClient()
        with TestClient(create_app()) as a,TestClient(create_app()) as b:
            clients=(a,b);owners=[];docs=[]
            password=secrets.token_urlsafe(24)
            for label,client in zip(('a','b'),clients):
                email=f'{run_id}-{label}@example.test'
                reg=client.post('/api/v2/auth/register',json={'email':email,'password':password,'display_name':'Synthetic '+label.upper()})
                assert reg.status_code==201,('registration',reg.status_code)
                login=client.post('/api/v2/auth/login',json={'email':email,'password':password})
                assert login.status_code==200,('login',login.status_code)
                owner=login.json()['id'];owners.append(owner)
                client.headers['X-CSRF-Token']=client.cookies['rag_csrf']
                source=SOURCE_A if label=='a' else SOURCE_B
                upload=client.post('/api/v2/documents',files={'file':(f'{run_id}-{label}.pdf',image_pdf(source),'application/pdf')})
                assert upload.status_code==202,('upload',upload.status_code)
                docs.append(upload.json())
            report['resource_ids']={'owner_ids':owners,'document_ids':[d['document_id'] for d in docs],
                                    'job_ids':[d['job_id'] for d in docs]}
            workers=[]
            for index,owner in enumerate(owners):
                process=subprocess.Popen([sys.executable,'-B',str(Path(__file__)),'--internal-worker',owner,
                                          '--identity',run_id+'-'+str(index)],cwd=ROOT,env=os.environ.copy(),
                                         stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                workers.append(process)
            worker_results=[]
            for process in workers:
                try:stdout,stderr=process.communicate(timeout=240)
                except subprocess.TimeoutExpired:
                    process.kill();stdout,stderr=process.communicate()
                worker_results.append({'pid':process.pid,'exit_code':process.returncode,
                                       'stdout_sha256':hashlib.sha256(stdout).hexdigest(),
                                       'stderr_sha256':hashlib.sha256(stderr).hexdigest()})
            report['worker_processes']=worker_results
            check('two_independent_real_workers',len({x['pid'] for x in worker_results})==2 and all(x['exit_code']==0 for x in worker_results))
            details=[]
            for client,doc in zip(clients,docs):
                detail=client.get('/api/v2/documents/'+doc['document_id']).json();details.append(detail)
                check('ready_'+doc['document_id'],detail.get('status')=='ready' and detail.get('pages')==1 and detail.get('chunks',0)>0,
                      {'status':detail.get('status'),'pages':detail.get('pages'),'chunks':detail.get('chunks')})
                check('real_ocr_'+doc['document_id'],bool(detail.get('page_metadata')) and detail['page_metadata'][0].get('method')=='pymupdf-tesseract-fast-4.1.0')
            report['document_metadata']=details
            if not all(d.get('status')=='ready' for d in details):raise RuntimeError('actual OCR/embedding worker did not publish')
            check('cross_owner_document_404',b.get('/api/v2/documents/'+docs[0]['document_id']).status_code==404)
            check('cross_owner_pdf_404',b.get('/api/v2/documents/'+docs[0]['document_id']+'/file').status_code==404)
            check('cross_owner_job_404',b.get('/api/v2/jobs/'+docs[0]['job_id']).status_code==404)
            check('cross_owner_delete_404',b.delete('/api/v2/documents/'+docs[0]['document_id']).status_code==404)
            check('tenant_document_listing',all(d['id']!=docs[0]['document_id'] for d in b.get('/api/v2/documents').json()))
            created=a.post('/api/v2/conversations',json={'title':run_id})
            assert created.status_code==201,('conversation',created.status_code)
            cid=created.json()['conversation_id'];report['resource_ids']['conversation_id']=cid
            check('cross_owner_conversation_404',b.get('/api/v2/conversations/'+cid).status_code==404)
            questions=[
                'I prefer peppermint tea. According to the Orion Gallery policy, how many credits does a visitor permit cost and for how many days is it valid?',
                'For my Orion Gallery visit, remind me how many days the visitor permit lasts. My preferred drink is peppermint tea.',
                'What drink do I prefer?'
            ]
            for index,query in enumerate(questions):
                captured=io.StringIO()
                with redirect_stdout(captured),redirect_stderr(captured):
                    response=a.post('/api/v2/chat',json={'conversation_id':cid,'message':query})
                result=response.json();report['answers'].append({'query':query,'http_status':response.status_code,'response':result})
                check('chat_http_'+str(index+1),response.status_code==200,{'http_status':response.status_code})
                if response.status_code!=200:break
                answer=result.get('answer','').casefold();citations=result.get('citations',[])
                if index==0:
                    check('grounded_document_numbers',all(str(n) in answer for n in (37,19)) and result.get('status')=='answered')
                    check('owner_page_citations',bool(citations) and all(c.get('document_id')==docs[0]['document_id'] and c.get('page')==1 for c in citations))
                    check('actual_reranker_used',result.get('retrieval_status')=='ok')
                    check('no_other_owner_fact', 'zephyr' not in answer and '88' not in answer)
                if index==1:
                    check('actual_followup_document_answer','19' in answer)
                    check('actual_extraction_checkpoint',result.get('memory_extraction')=='checkpoint_advanced',result.get('memory_extraction'))
                if index==2:
                    check('actual_memory_followup','peppermint' in answer and result.get('status')=='answered')
            memories=a.get('/api/v2/memories',params={'conversation_id':cid})
            assert memories.status_code==200
            memory_rows=[m for block in memories.json() for m in block.get('memories',[])]
            report['memories']=memory_rows
            check('real_user_preference_memory',any('peppermint' in m['memory'].casefold() and m.get('source_message_ids') for m in memory_rows))
            check('cross_owner_memories_404',b.get('/api/v2/memories',params={'conversation_id':cid}).status_code==404)
            if memory_rows:
                mid=memory_rows[0]['memory_id']
                check('cross_owner_source_provenance_404',b.get(f'/api/v2/conversations/{cid}/memories/{mid}/sources').status_code==404)
            with tenant_scope(owners[0]),get_connection() as conn:
                links=conn.execute("SELECT s.source_message_id,m.role,s.link_kind FROM memory_sources s JOIN messages m ON m.id=s.source_message_id WHERE s.conversation_id=%s",(cid,)).fetchall()
                stale=conn.execute('SELECT id,document_id,document_version,lease_token FROM jobs WHERE id=%s',(docs[0]['job_id'],)).fetchone()
                old_chunks=conn.execute('SELECT document_name,page_number,chunk_id,content,embedding FROM document_chunks WHERE document_id=%s ORDER BY chunk_id',(docs[0]['document_id'],)).fetchall()
            check('user_supported_memory_provenance',bool(links) and all(r[1]=='user' and r[2]=='user_source' for r in links))
            deletion=a.delete('/api/v2/documents/'+docs[0]['document_id'])
            check('document_delete',deletion.status_code==200)
            from services import v2_jobs
            stale_job=dict(zip(('id','document_id','document_version','lease_token'),map(str,stale)))
            chunks=[dict(document_name=str(r[0]),page_number=r[1],chunk_id=r[2],content=r[3]) for r in old_chunks]
            with tenant_scope(owners[0]):
                result=v2_jobs.publish(stale_job,[{'page_number':1,'method':'stale-test'}],chunks,[r[4] for r in old_chunks])
                check('completed_stale_lease_cannot_resurrect',result is False)
                with get_connection() as conn:remaining=conn.execute('SELECT count(*) FROM document_chunks WHERE document_id=%s',(docs[0]['document_id'],)).fetchone()[0]
            check('deleted_chunks_absent',remaining==0)
            check('conversation_delete',a.delete('/api/v2/conversations/'+cid).status_code==200)
            with tenant_scope(owners[0]),get_connection() as conn:
                counts=[conn.execute(f'SELECT count(*) FROM {table} WHERE conversation_id=%s',(cid,)).fetchone()[0] for table in ('messages','conversation_memories','memory_sources')]
            check('conversation_memory_source_cascade',counts==[0,0,0],counts)
            check('logout_invalidates_session',a.post('/api/v2/auth/logout').status_code==200 and a.get('/api/v2/auth/me').status_code==401)
        real_client.close()
        report['status']='PASS' if report['checks'] and all(c['pass'] for c in report['checks']) else 'FAIL'
    except BaseException as error:
        report['status']='FAIL';report['error_type']=type(error).__name__
        # Exception messages may contain credentials/SQL, so record type only.
    finally:
        report['sdk_call_count']=len(report['provider_calls'])
        report['elapsed_seconds']=round(time.monotonic()-started,4)
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        report['limits']=['synthetic functional smoke, not benchmark/formal acceptance','no browser automation in this script',
                          'no protected inputs or human certification','no cleanup of unrelated scratch rows']
        temp=output.with_suffix('.tmp')
        with temp.open('x') as f:json.dump(report,f,indent=2,default=str)
        os.replace(temp,output);output.chmod(0o444)
    print(json.dumps({'status':report['status'],'sdk_calls':report['sdk_call_count'],
                      'checks_passed':sum(c['pass'] for c in report['checks']),'checks_total':len(report['checks']),
                      'error_type':report.get('error_type'),'evidence':str(output)}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--internal-worker');parser.add_argument('--identity')
    parser.add_argument('--output',default='live_smoke.json')
    args=parser.parse_args()
    if args.internal_worker:raise SystemExit(internal_worker(args.internal_worker,args.identity))
    raise SystemExit(main(args.output))
