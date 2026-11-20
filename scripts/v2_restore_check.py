"""Backup and restore rehearsal restricted to the dedicated disposable v2 DB.

No existing database is overwritten. Only this invocation's UUID restore DB is
removed afterwards. No .env or application credentials are read.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from scripts import v2_scratch

def run():
    info=conninfo_to_dict(os.getenv('RAG_V2_SCRATCH_ADMIN_URL',v2_scratch.DEFAULT))
    name='rag_v2_restore_'+uuid.uuid4().hex
    env=dict(os.environ,PGPASSWORD=info['password'])
    args=['-h',info['host'],'-p',info.get('port','5432'),'-U',info['user']]
    tables=['users','user_sessions','documents','jobs','job_events','conversations','messages','conversation_memories','memory_sources','document_chunks']
    # Nonempty unique seed proves data, provenance and job recovery, not just DDL.
    seed=uuid.uuid4();cid=uuid.uuid4();did=uuid.uuid4();jid=uuid.uuid4()
    vector='['+','.join(['0.01']*384)+']'
    with v2_scratch.connect() as c:
        c.execute("INSERT INTO users(id,email,password_hash) VALUES(%s,%s,'restore-fixture-not-a-login')",(seed,str(seed)+'@restore.invalid'))
        c.execute("INSERT INTO conversations(id,title,owner_id) VALUES(%s,'restore fixture',%s)",(cid,seed))
        mid=c.execute("INSERT INTO messages(conversation_id,role,content,owner_id) VALUES(%s,'user','I prefer peppermint tea.',%s) RETURNING id",(cid,seed)).fetchone()[0]
        memory=c.execute("INSERT INTO conversation_memories(conversation_id,memory,embedding,source_message_id,owner_id) VALUES(%s,'Prefers peppermint tea.',%s::vector,%s,%s) RETURNING id",(cid,vector,mid,seed)).fetchone()[0]
        c.execute('INSERT INTO memory_sources(conversation_id,memory_id,source_message_id,owner_id) VALUES(%s,%s,%s,%s)',(cid,memory,mid,seed))
        c.execute("INSERT INTO documents(id,owner_id,filename,storage_path,status,embedding_model,embedding_dim) VALUES(%s,%s,'restore.pdf','synthetic-only','ready','all-MiniLM-L6-v2',384)",(did,seed))
        c.execute("INSERT INTO document_chunks(document_name,page_number,chunk_id,content,embedding,owner_id) VALUES(%s,1,1,'Synthetic restore chunk.',%s::vector,%s)",(str(did),vector,seed))
        c.execute("INSERT INTO jobs(id,owner_id,document_id,document_version,idempotency_key,status) VALUES(%s,%s,%s,1,%s,'succeeded')",(jid,seed,did,str(jid)))
        c.execute("INSERT INTO job_events(owner_id,job_id,event) VALUES(%s,%s,'restore-fixture')",(seed,jid))
    try:
      with tempfile.TemporaryDirectory(prefix='rag-v2-restore-') as temp:
        dump=Path(temp)/'scratch.dump'
        # Consistent exported snapshot includes concurrent browser activity safely.
        with v2_scratch.connect() as c:
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            snapshot=c.execute('SELECT pg_export_snapshot()').fetchone()[0]
            counts={t:c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in tables}
            version=c.execute('SHOW server_version').fetchone()[0]
            subprocess.run(['/opt/homebrew/bin/pg_dump',*args,'-d','rag_test_scratch','--snapshot',snapshot,'-Fc','-f',str(dump)],env=env,check=True,capture_output=True)
        # connect() verifies scratch before switching autocommit for CREATE DATABASE.
        with v2_scratch.connect() as c:
            c.commit();c.autocommit=True;c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        target=dict(info,dbname=name)
        try:
            with psycopg.connect(make_conninfo(**target)) as c:
                if c.execute('SELECT current_database()').fetchone()[0]!=name:raise ValueError('restore identity mismatch')
            subprocess.run(['/opt/homebrew/bin/pg_restore',*args,'-d',name,'--exit-on-error',str(dump)],env=env,check=True,capture_output=True)
            with psycopg.connect(make_conninfo(**target)) as c:
                if c.execute('SELECT current_database()').fetchone()[0]!=name:raise ValueError('restore identity mismatch')
                restored={t:c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in tables}
                rls=c.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relrowsecurity AND relforcerowsecurity").fetchone()[0]
                assert restored==counts,(counts,restored)
                assert rls==8,rls
        finally:
            with v2_scratch.connect() as c:
                c.commit();c.autocommit=True;c.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
    finally:
        with v2_scratch.connect() as c:
            c.execute('DELETE FROM job_events WHERE owner_id=%s',(seed,))
            c.execute('DELETE FROM jobs WHERE owner_id=%s',(seed,))
            c.execute('DELETE FROM document_chunks WHERE owner_id=%s',(seed,))
            c.execute('DELETE FROM documents WHERE owner_id=%s',(seed,))
            c.execute('DELETE FROM conversations WHERE owner_id=%s',(seed,))
            c.execute('DELETE FROM users WHERE id=%s',(seed,))
    return {'status':'PASS','source_database':'rag_test_scratch','restored_database':name,'server_version':version,'table_counts':counts,'force_rls_tables':rls,'restored_scratch_removed':True}
if __name__=='__main__':print(json.dumps(run(),indent=2))
