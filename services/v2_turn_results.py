"""Atomic, tenant-owned committed turns; history never guesses citations."""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID
import hashlib
from psycopg.types.json import Jsonb
from services.database import get_connection
from backend.errors import ApiError

_turn=ContextVar('v2_turn_id',default=None)

@contextmanager
def turn_identity(turn_id):
    token=_turn.set(str(turn_id))
    try:yield
    finally:_turn.reset(token)

def save_committed_turn(conversation_id,question,result):
    turn=_turn.get()
    if turn is None:return False
    metadata={key:result[key] for key in ('answer','status','citations','issues','retrieval_status','calculation') if key in result}
    metadata['kind']='answer'
    with get_connection() as c:
        c.execute('INSERT INTO v2_turn_receipts(conversation_id,turn_id,question_sha256) VALUES(%s,%s,%s)',
                  (conversation_id,turn,hashlib.sha256(question.encode()).hexdigest()))
        c.execute('INSERT INTO messages(conversation_id,role,content,turn_id) VALUES(%s,%s,%s,%s)',(conversation_id,'user',question,turn))
        c.execute('INSERT INTO messages(conversation_id,role,content,turn_id,answer_metadata) VALUES(%s,%s,%s,%s,%s)',(conversation_id,'assistant',result['answer'],turn,Jsonb(metadata)))
    return True

def safe_result(c,metadata,conversation_id,turn_id=None):
    """Validate persisted identities against live owned original chunks, not text."""
    citations=[]
    for item in metadata.get('citations') or []:
        try:did=str(UUID(str(item.get('document_id') or item['document'])))
        except (ValueError,KeyError,TypeError):continue
        row=c.execute("SELECT d.filename FROM documents d JOIN document_chunks ch ON ch.document_id=d.id AND ch.owner_id=d.owner_id WHERE d.id=%s AND d.status='ready' AND ch.id=%s AND ch.page_number=%s",(did,item.get('chunk_id'),item.get('page'))).fetchone()
        if row:citations.append({**item,'document_id':did,'document':row[0]})
    result={**metadata,'conversation_id':str(conversation_id),'turn_id':str(turn_id) if turn_id else None,'answer_status':metadata.get('status'),'citations':citations}
    proof=metadata.get('calculation')
    if isinstance(proof,dict):
        live={(item['ref'],item['document_id'],item['page'],item['chunk_id']) for item in citations}
        operands={(proof.get('source_ref'),proof.get('source_document'),proof.get('source_page'),proof.get('source_chunk_id'))}
        person=proof.get('person_evidence')
        if isinstance(person,dict):
            operands.add((person.get('ref'),person.get('document'),person.get('page'),person.get('chunk_id')))
        if not operands.issubset(live):
            result.pop('calculation')
    return result

def committed_result(conversation_id,turn_id,question=None):
    with get_connection() as c:
        rows=c.execute('SELECT role,content,answer_metadata,context_excluded FROM messages WHERE conversation_id=%s AND turn_id=%s ORDER BY id',(conversation_id,turn_id)).fetchall()
        receipt=c.execute('SELECT question_sha256 FROM v2_turn_receipts WHERE conversation_id=%s AND turn_id=%s',(conversation_id,turn_id)).fetchone()
        if receipt and question is not None and receipt[0]!=hashlib.sha256(question.encode()).hexdigest():
            raise ApiError(409,'turn_conflict','turn identity already used')
        if not rows:
            if receipt:raise ApiError(410,'turn_deleted','turn is no longer available')
            return None
        if len(rows)!=2:raise ApiError(410,'turn_deleted','turn is no longer available')
        if any(r[3] for r in rows):raise ApiError(410,'turn_deleted','turn is no longer available')
        user=next((r for r in rows if r[0]=='user'),None)
        if question is not None and (not user or user[1]!=question):raise ApiError(409,'turn_conflict','turn identity already used')
        assistant=next((r for r in rows if r[0]=='assistant'),None)
        if assistant and assistant[2]:return safe_result(c,assistant[2],conversation_id,turn_id)
        return None

def history(conversation_id):
    with get_connection() as c:
        rows=c.execute('SELECT id,role,content,turn_id,answer_metadata FROM messages WHERE conversation_id=%s AND NOT context_excluded ORDER BY id DESC LIMIT 200',(conversation_id,)).fetchall()
        return [dict(id=r[0],role=r[1],content=r[2],turn_id=str(r[3]) if r[3] else None,
                     **({'answer_metadata':safe_result(c,r[4],conversation_id,r[3])} if r[4] else {})) for r in reversed(rows)]
