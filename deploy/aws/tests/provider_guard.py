"""Test-only real-provider call cap. Never mounted in the ordinary production API.

Only prompt/response hashes and usage counts enter receipts. The fixed directory
is reused across process restarts, so a failed experiment cannot reset its cap.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def _write(path,value):
    fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:
        json.dump(value,output,indent=2);output.write('\n')


def install_guard(models_class,policy_path:Path,receipts:Path):
    policy=json.loads(policy_path.read_text())
    if (policy.get('version')!='aws-demo-development-acceptance/1'
        or type(policy.get('maximum_sdk_calls')) is not int
        or not 1<=policy['maximum_sdk_calls']<=18
        or policy.get('allowed_models')!=['gemini-3.5-flash-lite']
        or not re.fullmatch(r'aws-demo-\d{8}-live-\d{2}',policy.get('run_id',''))):
        raise ValueError('invalid predeclared provider policy')
    receipts.mkdir(parents=True,exist_ok=True,mode=0o700)
    if receipts.stat().st_mode & 0o077:
        raise ValueError('provider receipts must be private')
    identity={'run_id':policy['run_id'],'policy_sha256':hashlib.sha256(policy_path.read_bytes()).hexdigest(),
              'maximum_sdk_calls':policy['maximum_sdk_calls']}
    marker=receipts/'fixed-policy.json'
    try:_write(marker,identity)
    except FileExistsError:
        if json.loads(marker.read_text())!=identity:
            raise ValueError('existing experiment identity or policy changed') from None
    original=models_class.generate_content
    if getattr(original,'_rag_aws_guard',False):
        raise RuntimeError('provider guard already installed')

    def bounded(self,*args,**kwargs):
        if os.getenv('RAG_AWS_PROVIDER_DISABLED')=='1':
            raise RuntimeError('live provider calls are disabled for remaining verification')
        model=kwargs.get('model')
        if args or model not in policy['allowed_models']:
            raise RuntimeError('provider model or call form not allowed by experiment policy')
        started=time.monotonic()
        record={'run_id':policy['run_id'],'requested_model':model,
                'started_utc':datetime.now(timezone.utc).isoformat(),
                'prompt_sha256':_hash(kwargs.get('contents'))}
        for index in range(1,policy['maximum_sdk_calls']+1):
            stem=f'call-{index:03d}'
            try:_write(receipts/(stem+'.claim'),record);break
            except FileExistsError:continue
        else:raise RuntimeError('development experiment SDK call budget exhausted')
        try:
            response=original(self,*args,**kwargs)
            record.update(status='SUCCESS',returned_model=getattr(response,'model_version',None),
                          response_sha256=_hash(getattr(response,'text',None)))
            usage=getattr(response,'usage_metadata',None)
            record['tokens']={name:getattr(usage,name,None) for name in
                ('prompt_token_count','candidates_token_count','total_token_count')}
            return response
        except BaseException as error:
            record.update(status='FAILED',error_type=type(error).__name__)
            code=getattr(error,'code',None)
            if isinstance(code,int):record['error_code']=code
            raise
        finally:
            record['elapsed_seconds']=round(time.monotonic()-started,3)
            _write(receipts/(stem+'.json'),record)
    bounded._rag_aws_guard=True
    models_class.generate_content=bounded
    return identity


def build_app():
    if os.getenv('RAG_DATABASE_NAME') not in {'rag_v2_demo','rag_aws_scratch'}:
        raise RuntimeError('test API requires the dedicated demonstration/scratch database')
    from google.genai.models import Models
    identity=install_guard(Models,Path(os.environ['RAG_AWS_ACCEPTANCE_POLICY']),
                  Path(os.environ['RAG_AWS_PROVIDER_RECEIPTS']))
    from backend.v2.app import create_app
    app=create_app()
    @app.middleware('http')
    async def experiment_identity(request,call_next):
        response=await call_next(request)
        response.headers['X-RAG-Browser-Run-ID']=identity['run_id']
        return response
    return app
