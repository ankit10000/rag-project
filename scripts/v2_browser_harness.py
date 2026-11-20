"""Opt-in synthetic live-browser harness, never an application startup path.

Starts two API processes and two local OCR/index workers on isolated scratch.
Shared exclusive SDK slots cap the entire fresh browser experiment at12 calls.
Only prompt/response hashes and model IDs are recorded; no credential material.
Stop with Ctrl-C after browser verification; child workers are terminated/reaped.
"""
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def build_app():
    import hashlib,json,time
    from datetime import datetime,timezone
    from scripts.v2_scratch import app_url
    os.environ['DATABASE_URL']=app_url()
    os.environ['RAG_V2']='1'
    os.environ['RAG_V2_COMPAT']='0'
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    # Verify actual identity before each connection can participate in a write.
    import psycopg
    original_connect=psycopg.connect
    def guarded(*args,**kwargs):
        c=original_connect(*args,**kwargs)
        if c.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
            c.close();raise RuntimeError('scratch identity mismatch')
        c.commit();return c
    psycopg.connect=guarded
    from google.genai.models import Models
    original=Models.generate_content
    output=Path(os.environ['RAG_V2_BROWSER_EVIDENCE'])
    def bounded(self,*args,**kwargs):
        slot=None
        for n in range(1,13):
            try:
                f=(output/f'call-{n:02d}.claim').open('x');f.write(str(os.getpid()));f.close();slot=n;break
            except FileExistsError:continue
        if slot is None:raise RuntimeError('synthetic browser provider budget exhausted')
        entry={'slot':slot,'pid':os.getpid(),'requested_model':kwargs.get('model'),
               'prompt_sha256':hashlib.sha256(str(kwargs.get('contents')).encode()).hexdigest(),
               'started_at':datetime.now(timezone.utc).isoformat()}
        start=time.monotonic()
        try:
            result=original(self,*args,**kwargs)
            entry.update(status='ok',returned_model=getattr(result,'model_version',None),
                         response_sha256=hashlib.sha256(str(getattr(result,'text','')).encode()).hexdigest())
            return result
        except BaseException as e:
            entry.update(status='error',error_type=type(e).__name__);raise
        finally:
            entry['seconds']=round(time.monotonic()-start,4)
            with (output/f'call-{slot:02d}.json').open('x') as f:json.dump(entry,f,indent=2)
    Models.generate_content=bounded
    from backend.v2.app import create_app
    app=create_app()
    @app.middleware('http')
    async def identity(request,call_next):
        response=await call_next(request)
        response.headers['X-RAG-Browser-Run-ID']=output.name
        return response
    return app


def main():
    import json,subprocess,uuid
    from datetime import datetime,timezone
    from scripts.v2_scratch import app_url,connect
    with connect():pass
    run='v2-browser-aster-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    output=ROOT/'v2_evidence'/run;output.mkdir(parents=True,exist_ok=False)
    report={'run_id':run,'scope':'synthetic browser functional integration, not formal evaluation',
            'maximum_sdk_calls':12,'source':'Aster Harbor visitor permit costs 83 credits and remains valid for 17 days.',
            'criteria':['real browser login and image-only PDF upload','two independent local worker processes','real OCR and cached embeddings/reranking','Gemini grounded83/17 with owned original-page citations','memory with user provenance and follow-up','cross-owner denial','deletion prevents stale resurrection'],
            'provider_identity':'actual returned model recorded per call','status':'RUNNING'}
    (output/'predeclared.json').write_text(json.dumps(report,indent=2))
    os.environ.update(DATABASE_URL=app_url(),RAG_V2='1',RAG_V2_COMPAT='0',
          RAG_V2_BROWSER_EVIDENCE=str(output),RAG_OCR_TESSDATA='/private/tmp/rag-v2-tessdata',
          HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',LOCAL_V1_PROFILE='0',
          LOCAL_V1_REQUEST_TIMEOUT_SECONDS='180',GEMINI_FALLBACK_MODELS='',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2')
    # Only synthetic test accounts use this process-local uploads root.
    os.environ['RAG_V2_UPLOAD_DIR']=str(Path('/private/tmp')/run)
    workers=[];logs=[]
    try:
        for n in range(2):
            log=(output/f'worker-{n+1}.log').open('x');logs.append(log)
            workers.append(subprocess.Popen([str(ROOT/'.venv/bin/python'),'-B',str(ROOT/'scripts/run_v2_worker.py')],cwd=ROOT,env=os.environ,stdout=log,stderr=log))
        (output/'processes.json').write_text(json.dumps({'ocr_worker_pids':[w.pid for w in workers]},indent=2))
        print('BROWSER_EVIDENCE_DIRECTORY',output,flush=True)
        import uvicorn
        uvicorn.run('scripts.v2_browser_harness:build_app',factory=True,host='127.0.0.1',port=8001,workers=2,access_log=False)
    finally:
        for w in workers:
            w.terminate()
        for w in workers:
            try:w.wait(timeout=20)
            except subprocess.TimeoutExpired:w.kill();w.wait()
        for log in logs:log.close()
if __name__=='__main__':main()
