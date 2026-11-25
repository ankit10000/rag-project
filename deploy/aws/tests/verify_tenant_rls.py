"""Read-only RLS proof for retained synthetic deployment owners and exact IDs.

No embeddings/provider imports, data writes, migrations or production connections.
Run through the container secrets adapter while its real acceptance rows exist.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))


def verify_identity(connection,expected):
    actual,role,superuser,bypass=connection.execute(
        'SELECT current_database(),current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user'
    ).fetchone()
    if (actual!=expected or actual not in {'rag_v2_demo','rag_aws_scratch'}
        or role!='rag_v2_app' or superuser or bypass):
        raise ValueError('exact dedicated database/restricted role required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--deleted',action='store_true')
    parser.add_argument('--deletion-receipt',type=Path)
    args=parser.parse_args()
    expected=os.environ['RAG_DATABASE_NAME']
    if expected not in {'rag_v2_demo','rag_aws_scratch'}:
        raise ValueError('only dedicated AWS demonstration/scratch DB permitted')
    url=os.environ['DATABASE_URL']
    if conninfo_to_dict(url).get('dbname')!=expected:
        raise ValueError('connection database differs from explicit expected identity')
    original=psycopg.connect
    def guarded(*a,**kw):
        connection=original(*a,**kw)
        try:
            connection.read_only=True
            verify_identity(connection,expected)
            connection.commit()
            return connection
        except BaseException:
            connection.close();raise
    psycopg.connect=guarded
    state=json.loads(args.state.read_text())
    if not state.get('run_id','').startswith('aws-demo-'):
        raise ValueError('synthetic deployment state required')
    owner,other=str(uuid.UUID(state['owner_id'])),str(uuid.UUID(state['other_id']))
    if owner==other:raise ValueError('two independent owners required')
    documents=[str(uuid.UUID(doc['id'])) for doc in state['documents'].values()]
    jobs=[str(uuid.UUID(doc['job_id'])) for doc in state['documents'].values()]
    if args.deletion_receipt:
        if not args.deleted:raise ValueError('cancelled lease proof is a post-deletion check')
        race=json.loads(args.deletion_receipt.read_text())
        documents.append(str(uuid.UUID(race['document_id'])));jobs.append(str(uuid.UUID(race['job_id'])))
    conversations=list({str(uuid.UUID(turn['conversation_id'])) for turn in state['turns']})
    memory=state['memory']['memory_id']
    from services.tenant_context import tenant_scope,auth_system_context
    from services.database import get_connection
    with auth_system_context(),get_connection() as connection:
        flags=connection.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace "
                                 'AND relrowsecurity AND relforcerowsecurity').fetchone()[0]
        if flags!=9:raise ValueError('nine FORCE RLS tables required')
        for identity,email in ((owner,state['owner']),(other,state['other'])):
            if connection.execute('SELECT id FROM users WHERE id=%s AND email=%s',(identity,email)).fetchone() is None:
                raise ValueError('state account identity mismatch')
    clauses={
        'documents':("id=ANY(%s::uuid[]) AND status<>'deleted'",(documents,)),
        'jobs':("document_id=ANY(%s::uuid[])"+(" AND status IN ('queued','running')" if args.deleted else ''),(documents,)),
        'job_events':('job_id=ANY(%s::uuid[])',(jobs,)),
        'document_chunks':('document_id=ANY(%s::uuid[])',(documents,)),
        'conversations':('id=ANY(%s::uuid[])',(conversations,)),
        'messages':('conversation_id=ANY(%s::uuid[])',(conversations,)),
        'conversation_memories':('id=%s',(memory,)),
        'memory_sources':('memory_id=%s',(memory,)),
        'v2_turn_receipts':('conversation_id=ANY(%s::uuid[])',(conversations,)),
    }
    counts={}
    for label,identity in (('owner',owner),('other',other)):
        with tenant_scope(identity),get_connection() as connection:
            count={table:connection.execute(f'SELECT count(*) FROM {table} WHERE {clause}',parameters).fetchone()[0]
                   for table,(clause,parameters) in clauses.items()}
        if label=='other' and any(count.values()):raise ValueError('cross-owner tenant rows visible')
        if label=='owner':
            for table,value in count.items():
                if args.deleted and table!='job_events' and value!=0:
                    raise ValueError('deleted tenant content or queued work remains')
                if not args.deleted and value<1:
                    raise ValueError('owner fixture does not establish positive control for '+table)
        counts[label]=count
    print(json.dumps({'status':'PASS','database':expected,'role':'rag_v2_app','read_only':True,
                      'force_rls_tables':flags,'after_deletion':args.deleted,'counts':counts,
                      'providers':0,'raw_content_logged':False}))


if __name__=='__main__':
    try:main()
    except Exception as error:raise SystemExit('RLS proof refused ('+type(error).__name__+')') from None
