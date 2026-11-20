"""Opt-in retained synthetic-resume browser regression; fresh 12-call budget.

No ordinary application imports this harness. Never targets rag_db.
"""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def build_app():
    from scripts.v2_browser_harness import build_app as bounded_app
    app=bounded_app()  # guarded scratch connections and exclusive SDK slots
    # Fresh identities share one finite family budget, including failed runs.
    from google.genai.models import Models
    prior=Models.generate_content
    def remaining_budget(self,*args,**kwargs):
        directory=Path(os.environ['RAG_V2_BROWSER_EVIDENCE'])
        claimed=False
        for slot in range(1,int(os.environ['RAG_BROWSER_REMAINING_CALLS'])+1):
            try:
                fd=os.open(directory/f'remaining-{slot:02d}.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                os.close(fd);claimed=True;break
            except FileExistsError:continue
        if not claimed:raise RuntimeError('aggregate browser closure provider budget exhausted')
        return prior(self,*args,**kwargs)
    Models.generate_content=remaining_budget
    import main,time,uuid
    from services.evidence_trace import answer_evidence_trace
    from services.tenant_context import current_owner
    original=main.ask_question
    def traced(*args,**kwargs):
        if current_owner()!='97de44e7-f332-494b-95e1-86a432350198':
            raise PermissionError('this development generation harness is synthetic-owner only')
        question=kwargs.get('query',args[0] if args else '')
        with answer_evidence_trace(question,include_raw=True) as trace:
            try:return original(*args,**kwargs)
            finally:trace.write(Path(os.environ['RAG_V2_BROWSER_EVIDENCE'])/('trace-'+uuid.uuid4().hex+'.json'))
    main.ask_question=traced
    original_summary=main.update_long_term_memory
    def delayed(*args,**kwargs):
        # Reproduce a slow post-commit stage without altering provider deadlines.
        time.sleep(5)
        return original_summary(*args,**kwargs)
    main.update_long_term_memory=delayed
    return app

if __name__=='__main__':
    from scripts.v2_scratch import app_url,connect
    with connect(app_url()):pass
    identity=sys.argv[1] if len(sys.argv)>1 else 'live-03'
    import re
    if not re.fullmatch(r'live-\d{2}',identity):raise ValueError('fresh live-NN identity required')
    partial_only=len(sys.argv)>2 and sys.argv[2]=='partial'
    family=ROOT/('v2_evidence/browser-final-20261120' if partial_only else 'v2_evidence/browser-confirmation-20261120')
    cap=3 if partial_only else 6
    family.mkdir(mode=0o700,exist_ok=True)
    previous=len(list(family.glob('live-*/call-*.claim')))
    remaining=cap-previous
    if remaining<=0:raise RuntimeError('aggregate family budget exhausted')
    output=family/identity
    output.mkdir(mode=0o700,exist_ok=False)
    import json
    (output/'predeclared.json').write_text(json.dumps({'identity':family.name+'-'+identity,'max_sdk_calls':remaining,'aggregate_family_budget':cap,'purpose':'partial reporting-head correction' if partial_only else 'education filename identity confirmation','previous_calls':previous,'questions':['What is the qualifications of Morgan Vale?','In Browser_Check_Morgan_Vale.pdf, what is listed under EDUCATION? Please give the degree, institute and study dates.','According to Morgan Vale’s resume, how did the Atlas project change report preparation time? Also, what telephone number is listed for Morgan?'],'source_document':'567ee27b-074a-4d09-9af5-5dd796b8667e','expected_education':'Bachelor of Engineering in Computer Engineering; Sample Institute of Technology; 2016–2020; page2','expected_partial':'40→12minutes; no phone invented; partial; original page citations','controlled_postcommit_delay_seconds':5,'scope':'development only, no held-out evaluation'},indent=2))
    os.environ.update(RAG_BROWSER_REMAINING_CALLS=str(remaining),DATABASE_URL=app_url(),RAG_V2='1',RAG_V2_COMPAT='0',RAG_V2_BROWSER_EVIDENCE=str(output),RAG_DEVELOPMENT_TRACE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2',LOCAL_V1_PROFILE='0',GEMINI_FALLBACK_MODELS='')
    import uvicorn
    uvicorn.run('scripts.v2_browser_closure:build_app',factory=True,host='127.0.0.1',port=8000,workers=2,access_log=False)
