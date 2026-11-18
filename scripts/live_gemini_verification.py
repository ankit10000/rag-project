"""Opt-in bounded live-provider smoke on a new verified disposable database.

No secrets, prompt text, raw answers or database URLs are emitted. The owner must
explicitly authorize live Gemini use before running this development utility.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def is_grounded_abstention(body):
    """Use the existing public answer status contract, without policy changes."""
    return body.get("status") == "abstained" and not body.get("citations")


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-live', action='store_true', required=True)
    parser.add_argument('--results-file', type=Path, required=True)
    args = parser.parse_args()
    if args.results_file.exists():
        raise ValueError('results path must not already exist')
    os.environ.update(LOCAL_V1_PROFILE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    from scripts.local_v1_scratch import create_database, initialize, scratch_url, connect
    name = 'rag_local_v1_test_live_' + uuid.uuid4().hex[:12]
    create_database(name)
    initialize(name)
    os.environ['DATABASE_URL'] = scratch_url(name)
    from services import llm_service as llm
    from google import genai
    from google.genai import types
    from services.request_budget import request_budget
    records = []
    checks = {}
    maximum = 28
    sdk = llm.get_client()
    generate = sdk.models.generate_content

    def measured(*a, **kw):
        if len(records) >= maximum:
            raise RuntimeError('bounded live call limit reached')
        started = time.monotonic()
        record = {'requested_model':kw.get('model')}
        records.append(record)
        try:
            response = generate(*a, **kw)
            record.update(status='success', returned_model=getattr(response, 'model_version', None))
            return response
        except Exception as error:
            record.update(status='failed', error_type=type(error).__name__, code=getattr(error, 'code', None))
            raise
        finally:
            record['seconds'] = round(time.monotonic()-started, 3)

    started = time.monotonic()
    report = {'database':name, 'configured_primary':llm.MODEL_NAME,
              'configured_fallbacks':llm.FALLBACK_MODELS, 'call_limit':maximum,
              'source_head':__import__('subprocess').check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()}
    try:
        with patch.object(sdk.models, 'generate_content', side_effect=measured):
            with request_budget(25):
                checks['minimal_response'] = llm.generate_answer('Reply exactly READY. Synthetic connectivity check.').strip() == 'READY'
            # Fake credential is isolated; never replaces the real global client.
            bad = genai.Client(api_key='deliberately-invalid-synthetic-key', http_options=types.HttpOptions(timeout=10000))
            before = time.monotonic()
            try:
                bad.models.generate_content(model=llm.MODEL_NAME, contents='Reply READY.')
                checks['invalid_credential_rejected'] = False
                records.append(dict(requested_model=llm.MODEL_NAME, credential='synthetic-invalid',status='unexpected_success',seconds=round(time.monotonic()-before,3)))
            except Exception as error:
                code=getattr(error,'code',None)
                checks['invalid_credential_rejected'] = code in (400,401,403)
                records.append(dict(requested_model=llm.MODEL_NAME, credential='synthetic-invalid',status='rejected',code=code,error_type=type(error).__name__,seconds=round(time.monotonic()-before,3)))
            finally:
                bad.close()
            import pymupdf
            from fastapi.testclient import TestClient
            from backend.app import create_app
            token='synthetic-local-live-verification-bearer-token'
            with tempfile.TemporaryDirectory(prefix='live-gemini-',dir='/private/tmp') as folder, contextlib.ExitStack() as stack:
                stack.enter_context(patch('backend.config.UPLOAD_DIR',folder))
                stack.enter_context(patch('backend.app.load_token_digest',return_value=(hashlib.sha256(token.encode()).digest(),'synthetic')))
                client=stack.enter_context(TestClient(create_app(),base_url='http://127.0.0.1',raise_server_exceptions=False))
                client.headers['Authorization']='Bearer '+token
                prefix='/api/v1'
                with pymupdf.open() as pdf:
                    page=pdf.new_page()
                    page.insert_textbox(pymupdf.Rect(36,36,559,806),
                        'SYNTHETIC NEBULA PERMIT HANDBOOK. The Nebula permit application fee is 65 dollars. '
                        'The Nebula permit is valid for 30 days. Applicants submit a local application. '
                        'The handbook does not state a contact telephone number.',fontsize=11)
                    content=pdf.tobytes()
                upload=client.post(prefix+'/documents',files={'file':('synthetic_nebula.pdf',content,'application/pdf')})
                checks['pdf_ingestion']=upload.status_code==201 and upload.json().get('chunks',0)>0
                created=client.post(prefix+'/conversations',json={'title':'Synthetic live verification'})
                checks['create_conversation']=created.status_code==201
                cid=created.json()['conversation_id']
                def chat(label,message):
                    response=client.post(prefix+'/chat',json={'conversation_id':cid,'message':message})
                    body=response.json()
                    report[label]={'http_status':response.status_code,'answer_status':body.get('status'),
                        'citation_count':len(body.get('citations') or []),'memory_extraction':body.get('memory_extraction')}
                    return body
                first=chat('document_question','I prefer concise explanations. According to the Nebula handbook, what is the permit application fee?')
                checks['grounded_document_answer']=first.get('status')=='answered' and '65' in first.get('answer','')
                checks['citation_reference']=any(c.get('document')=='synthetic_nebula.pdf' and c.get('page')==1 for c in first.get('citations',[]))
                second=chat('followup','According to that same handbook, how long is that permit valid?')
                checks['followup']=second.get('status')=='answered' and '30' in second.get('answer','') and bool(second.get('citations'))
                memories=client.get(prefix+f'/conversations/{cid}/memories').json().get('memories',[])
                checks['memory_stored']=any('concise' in m.get('memory','').lower() for m in memories)
                memory=chat('memory_followup','What preference did I tell you about how I like explanations?')
                checks['memory_followup']='concise' in memory.get('answer','').lower()
                abstain=chat('unsupported_question','According to the Nebula handbook, what is the exact street address of the permit office?')
                checks['unsupported_abstention']=is_grounded_abstention(abstain)
                report['message_count_before_deletion']=len(client.get(prefix+f'/conversations/{cid}').json().get('messages',[]))
                checks['no_duplicate_turn_writes']=report['message_count_before_deletion']==8
                deletion=client.delete(prefix+f'/conversations/{cid}')
                checks['conversation_deletion']=deletion.status_code==200 and client.get(prefix+f'/conversations/{cid}').status_code==404
                with connect(name) as db:
                    checks['no_orphan_messages']=db.execute('SELECT count(*) FROM messages WHERE conversation_id=%s',(uuid.UUID(cid),)).fetchone()[0]==0
                    checks['no_orphan_memories']=db.execute('SELECT count(*) FROM conversation_memories WHERE conversation_id=%s',(uuid.UUID(cid),)).fetchone()[0]==0
    except Exception as error:
        report['error']={'type':type(error).__name__,'code':getattr(error,'code',None)}
    finally:
        report.update(checks=checks,calls=records,total_calls=len(records),seconds=round(time.monotonic()-started,3),
                      verdict='LIVE_GEMINI_PASS' if checks and all(checks.values()) and 'error' not in report else 'LIVE_GEMINI_FAIL')
        with args.results_file.open('x') as target:
            json.dump(report,target,indent=2);target.write('\n')
    return report


if __name__=='__main__':
    # Suppress framework/model diagnostics; print only redacted structured evidence.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        outcome=run()
    print(json.dumps(outcome,indent=2))
    raise SystemExit(0 if outcome['verdict']=='LIVE_GEMINI_PASS' else 1)
