import os, sys, json, time, pathlib, hashlib, contextlib, io
sys.path.insert(0, '/Volumes/Storage/rag-project')
from scripts.v2_scratch import app_url
os.environ.update(DATABASE_URL=app_url(), RAG_V2='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2', GEMINI_FALLBACK_MODELS='')
import psycopg
from psycopg.conninfo import conninfo_to_dict
original_connect=psycopg.connect
def guarded(info='', **kw):
    if conninfo_to_dict(info).get('dbname') != 'rag_test_scratch': raise RuntimeError('unsafe database')
    c=original_connect(info, **kw)
    if c.execute('select current_database()').fetchone()[0] != 'rag_test_scratch':
        c.close(); raise RuntimeError('database identity mismatch')
    c.commit()
    return c
psycopg.connect=guarded
from google.genai.models import Models
original_generate=Models.generate_content
calls=[]
def counted(self, *a, **kw):
    if len(calls)>=24: raise ValueError('development provider cap reached')
    record={'model':kw.get('model'),'prompt_sha256':hashlib.sha256(str(kw.get('contents')).encode()).hexdigest()}
    calls.append(record)
    r=original_generate(self,*a,**kw)
    record['response_sha256']=hashlib.sha256((r.text or '').encode()).hexdigest()
    return r
Models.generate_content=counted
from services.tenant_context import tenant_scope
from services.request_budget import request_budget
from services.rag_service import ask_question
ROOT=pathlib.Path('/Volumes/Storage/rag-project/v2_evidence/backend-executive-20261119')
CASES=[
 {'id':'product','question':'According to Executive Summary.pdf, what is the proposed product and which three entrance examinations does it target?','expected':'AI education portal; JEE, GATE, NEET; page 1'},
 {'id':'estimates','question':'According to Executive Summary.pdf, what overall development duration, team size and rough budget does the executive summary estimate? Give all three estimates.','expected':'2–3 years; about 10–15 people; $1M–$5M over 2 years; page 1'},
 {'id':'accessibility','question':'According to Executive Summary.pdf, what multilingual support and offline/mobile access are proposed?','expected':'Hindi/other regional languages; downloading videos and notes for offline study; mobile app; page 2'},
 {'id':'phases','question':'List all four implementation phases and their month ranges from the roadmap in Executive Summary.pdf.','expected':'Planning & Prototype 0–6; MVP Development 6–15; Pilot & Feedback 15–21; Launch & Scale 21–30; page 15'},
 {'id':'risks','question':'According to Executive Summary.pdf, how should quality risks and data/copyright risks be mitigated? Cover both.','expected':'human review/conservative generation/early feedback; legal review/open data/rephrasing; page 16'},
 {'id':'unsupported','question':'What is the signed customer contract number for the proposed education portal in Executive Summary.pdf?','expected':'abstain; no invented contract number'},
]
identity=sys.argv[1]
path=ROOT/(identity+'.json')
if path.exists(): raise RuntimeError('will not overwrite experiment')
plan=ROOT/(identity+'-plan.json')
plan.write_text(json.dumps({'identity':identity,'cases':CASES,'cap':24,'scope':'development only; actual tenant-scoped uploaded source; no held-out evaluation'},indent=2))
report={'identity':identity,'results':[],'calls':calls}
for case in CASES:
    start=time.monotonic(); log=io.StringIO(); before=len(calls)
    try:
        with tenant_scope('25973a8a-09db-4a15-a686-304a5c986eec'), request_budget(seconds=90,suppress_output=True), contextlib.redirect_stdout(log):
            answer=ask_question(case['question'])
        entry={**case,'result':answer}
    except Exception as e:
        entry={**case,'error':type(e).__name__+': '+str(e)}
    entry.update(seconds=round(time.monotonic()-start,2),provider_calls=len(calls)-before)
    report['results'].append(entry)
    path.write_text(json.dumps(report,indent=2,default=str))
    (ROOT/(identity+'-'+case['id']+'.log')).write_text(log.getvalue())
    print(json.dumps(entry,default=str),flush=True)
print('TOTAL_PROVIDER_CALLS',len(calls),flush=True)
