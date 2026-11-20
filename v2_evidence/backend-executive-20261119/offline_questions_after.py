import os,sys,json,pathlib,contextlib,io
sys.path.insert(0,'/Volumes/Storage/rag-project')
from scripts.v2_scratch import app_url
os.environ.update(DATABASE_URL=app_url(),RAG_V2='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2')
import psycopg
from psycopg.conninfo import conninfo_to_dict
original=psycopg.connect
def guarded(info='',**kw):
    if conninfo_to_dict(info).get('dbname')!='rag_test_scratch':raise RuntimeError('unsafe database')
    c=original(info,**kw)
    if c.execute('select current_database()').fetchone()[0]!='rag_test_scratch':c.close();raise RuntimeError('identity mismatch')
    c.commit();return c
psycopg.connect=guarded
from services.tenant_context import tenant_scope
from services.hybrid_search_service import hybrid_search_detailed
from services import retrieval_config as cfg
from services.context_assembly_service import assemble_context
questions=[
 'According to Executive Summary.pdf, what is the proposed product and which three entrance examinations does it target?',
 'According to Executive Summary.pdf, what overall development duration, team size and rough budget does the executive summary estimate? Give all three estimates.',
 'According to Executive Summary.pdf, what multilingual support and offline/mobile access are proposed?',
 'List all four implementation phases and their month ranges from the roadmap in Executive Summary.pdf.',
 'According to Executive Summary.pdf, how should quality risks and data/copyright risks be mitigated? Cover both.',
 'What is the signed customer contract number for the proposed education portal in Executive Summary.pdf?'
]
rows=[]
for q in questions:
    with tenant_scope('25973a8a-09db-4a15-a686-304a5c986eec'),contextlib.redirect_stdout(io.StringIO()):
        r=hybrid_search_detailed(q,top_k=cfg.FINAL_TOP_K)
    results=r['results']; threshold=results[0].get('rerank_score',-999)-cfg.RERANK_SCORE_MARGIN if results else -999
    kept=[x for x in results if x.get('rerank_score',999)>=threshold]
    with tenant_scope('25973a8a-09db-4a15-a686-304a5c986eec'):
        from services.v2_page_context import expand_page_context
        kept=expand_page_context(q,kept,cfg.CONTEXT_MAX_CHUNKS)
    row={'question':q,'status':r['rerank_status'],'candidates':results,'bundle':assemble_context(kept)}
    rows.append(row)
    print(json.dumps({'question':q,'chunks':[(x['chunk'][0],x['chunk'][2],round(x.get('rerank_score',0),2)) for x in results],'context':row['bundle']['context_text']}),flush=True)
pathlib.Path('v2_evidence/backend-executive-20261119/offline-after-context-fix.json').write_text(json.dumps(rows,indent=2,default=str))
