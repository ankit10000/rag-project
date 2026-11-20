"""Tenant-scoped durable leases. Every publication checks its exact lease token.

Workers explicitly select an owner's queue; no connection may bypass tenant RLS.
Independent worker processes can service the same owner safely.
"""
import uuid
from services.database import get_connection


def enqueue(conn, document_id, version, key):
    # Serialize per-owner admission: bounded outstanding jobs even across servers.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_setting('app.user_id') || ':queue',0))")
    old=conn.execute('SELECT id FROM jobs WHERE idempotency_key=%s',(key,)).fetchone()
    if old:return str(old[0])
    if conn.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=20:
        raise ValueError('job quota exceeded')
    jid=uuid.uuid4()
    conn.execute('INSERT INTO jobs(id,document_id,document_version,idempotency_key) VALUES(%s,%s,%s,%s)',(jid,document_id,version,key))
    conn.execute("INSERT INTO job_events(job_id,event) VALUES(%s,'queued')",(jid,))
    return str(jid)


def claim(worker_id, lease_seconds=120):
    if not worker_id or len(worker_id)>120 or not 5<=lease_seconds<=600:raise ValueError('invalid worker lease')
    with get_connection() as c:
        # Reap exhausted crashed attempts in the same document->job lock order
        # as publication/deletion. A crash must not leave a queued document forever.
        exhausted=c.execute("SELECT id,document_id FROM jobs WHERE status='running' AND lease_until<now() AND attempts>=max_attempts ORDER BY document_id,id LIMIT 20").fetchall()
        for jid,did in exhausted:
            c.execute('SELECT id FROM documents WHERE id=%s FOR UPDATE',(did,))
            final=c.execute("UPDATE jobs SET status='failed',error_code='attempts_exhausted',lease_until=NULL,updated_at=now() WHERE id=%s AND status='running' AND lease_until<now() AND attempts>=max_attempts RETURNING document_version",(jid,)).fetchone()
            if final:
                c.execute("UPDATE documents SET status='failed' WHERE id=%s AND version=%s AND status NOT IN ('deleted','cancelled')",(did,final[0]))
                c.execute("INSERT INTO job_events(job_id,event) VALUES(%s,'attempts_exhausted')",(jid,))
        row=c.execute('''WITH candidate AS (
          SELECT j.id FROM jobs j JOIN documents d ON d.id=j.document_id
          WHERE d.status NOT IN ('deleted','cancelled') AND d.version=j.document_version
            AND j.attempts<j.max_attempts AND ((j.status='queued' AND j.available_at<=now()) OR (j.status='running' AND j.lease_until<now()))
          ORDER BY j.available_at,j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1)
          UPDATE jobs j SET status='running',attempts=attempts+1,worker_id=%s,lease_token=%s,
          lease_until=now()+(%s * interval '1 second'),heartbeat_at=now(),updated_at=now()
          FROM candidate WHERE j.id=candidate.id
          RETURNING j.id,j.document_id,j.document_version,j.lease_token''',(worker_id,uuid.uuid4(),lease_seconds)).fetchone()
        if not row:return None
        c.execute("INSERT INTO job_events(job_id,event) VALUES(%s,'claimed')",(row[0],))
        return dict(zip(('id','document_id','document_version','lease_token'),map(str,row)))


def heartbeat(job, progress=0, lease_seconds=120):
    if type(progress) is not int or not 0<=progress<=100 or not 5<=lease_seconds<=600:
        raise ValueError('invalid heartbeat')
    with get_connection() as c:
        return c.execute("UPDATE jobs SET heartbeat_at=now(),lease_until=now()+(%s * interval '1 second'),progress=%s WHERE id=%s AND lease_token=%s AND status='running' AND lease_until>now() RETURNING id",(lease_seconds,progress,job['id'],job['lease_token'])).fetchone() is not None


def publish(job, pages, chunks, embeddings):
    from services.ingestion_service import write_document_chunks, validate_embeddings
    from services import retrieval_config as cfg
    from services.embedding_service import _verify_model_configuration
    from psycopg.types.json import Jsonb
    if not chunks or len(chunks)!=len(embeddings) or any(str(chunk['document_name'])!=str(job['document_id']) for chunk in chunks):
        raise ValueError('invalid publication')
    validate_embeddings(embeddings,len(chunks),cfg.EMBEDDING_DIM)
    # Binds persisted vectors to the configured/loaded model identity, and refuses
    # configuration drift after model initialization without loading a new model.
    _verify_model_configuration()
    with get_connection() as c:
        # All document transitions lock document then job: same ordering as delete.
        d=c.execute('SELECT version,status FROM documents WHERE id=%s FOR UPDATE',(job['document_id'],)).fetchone()
        j=c.execute("SELECT 1 FROM jobs WHERE id=%s AND lease_token=%s AND status='running' AND lease_until>now() FOR UPDATE",(job['id'],job['lease_token'])).fetchone()
        if not d or str(d[0])!=job['document_version'] or d[1] in ('deleted','cancelled') or not j:return False
        write_document_chunks(c.cursor(),job['document_id'],chunks,embeddings)
        c.execute("UPDATE documents SET status='ready',pages=%s,chunks=%s,page_metadata=%s,embedding_model=%s,embedding_dim=%s WHERE id=%s",(len(pages),len(chunks),Jsonb([{k:v for k,v in p.items() if k!='text'} for p in pages]),cfg.EMBEDDING_MODEL,cfg.EMBEDDING_DIM,job['document_id']))
        c.execute("UPDATE jobs SET status='succeeded',progress=100,lease_until=NULL,updated_at=now() WHERE id=%s",(job['id'],))
        c.execute("INSERT INTO job_events(job_id,event) VALUES(%s,'succeeded')",(job['id'],))
    return True


def fail(job, error_code='processing_failed'):
    # Deliberately never store exception text/document text/provider credentials.
    if error_code not in ('processing_failed','ocr_unavailable','ocr_failed','embedding_failed','invalid_document'):
        error_code='processing_failed'
    with get_connection() as c:
        d=c.execute('SELECT id FROM documents WHERE id=%s FOR UPDATE',(job['document_id'],)).fetchone()
        row=c.execute("UPDATE jobs SET status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,error_code=%s,lease_until=NULL,available_at=now()+(power(2,attempts)*interval '1 second'),updated_at=now() WHERE id=%s AND lease_token=%s AND status='running' AND lease_until>now() RETURNING status",(error_code,job['id'],job['lease_token'])).fetchone()
        if row:
            c.execute('UPDATE documents SET status=%s WHERE id=%s AND version=%s AND status<>\'deleted\'',('queued' if row[0]=='queued' else 'failed',job['document_id'],int(job['document_version'])))
            c.execute('INSERT INTO job_events(job_id,event) VALUES(%s,%s)',(job['id'],row[0]))
        return bool(row)


def cancel(conn, job_id):
    d=conn.execute('SELECT document_id,document_version FROM jobs WHERE id=%s',(job_id,)).fetchone()
    if not d:return False
    conn.execute('SELECT id FROM documents WHERE id=%s FOR UPDATE',(d[0],))
    row=conn.execute("UPDATE jobs SET status='cancelled',lease_token=NULL,lease_until=NULL,updated_at=now() WHERE id=%s AND status IN ('queued','running') RETURNING id",(job_id,)).fetchone()
    if row:
        conn.execute("UPDATE documents SET status='cancelled',version=version+1 WHERE id=%s AND version=%s AND status<>'deleted'",(d[0],d[1]))
        conn.execute("INSERT INTO job_events(job_id,event) VALUES(%s,'cancelled')",(job_id,))
    return bool(row)
