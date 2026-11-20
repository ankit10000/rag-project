"""Disposable v2 verification DB only. Never reads .env or connects to rag_db.

The default container is dedicated to this sprint, bound to loopback port55432.
No existing rows are assigned ownership. No production migration command exists.
"""
from pathlib import Path
import os
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
ROOT=Path(__file__).resolve().parents[1]
DEFAULT='postgresql://postgres:rag-v2-scratch-only@127.0.0.1:55432/rag_test_scratch'
MIGRATIONS=('000_base_schema.sql','001_add_messages_context_excluded.sql','002_add_memory_sources.sql','003_memory_sources_provenance.sql','007_v2_identity_jobs.sql','008_v2_turn_results.sql')
def connect(url=None):
    url=url or os.getenv('RAG_V2_SCRATCH_ADMIN_URL',DEFAULT)
    info=conninfo_to_dict(url)
    if info.get('dbname')!='rag_test_scratch' or info.get('host') not in ('127.0.0.1','localhost','::1'):
        raise ValueError('only explicitly identified localhost rag_test_scratch is allowed')
    c=psycopg.connect(url,connect_timeout=5)
    if c.execute('SELECT current_database()').fetchone()[0]!='rag_test_scratch':
        c.close();raise ValueError('scratch identity could not be established')
    c.commit();return c

def app_url():
    info=conninfo_to_dict(os.getenv('RAG_V2_SCRATCH_ADMIN_URL',DEFAULT));info.update(user='rag_v2_app',password='rag-v2-app-scratch-only')
    return make_conninfo(**info)

def initialize():
    with connect() as c:
        for name in MIGRATIONS:c.execute((ROOT/'migrations'/name).read_text())
        c.execute("DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='rag_v2_app') THEN CREATE ROLE rag_v2_app LOGIN PASSWORD 'rag-v2-app-scratch-only' NOSUPERUSER NOBYPASSRLS; END IF; END $$")
        c.execute('GRANT USAGE ON SCHEMA public TO rag_v2_app')
        c.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO rag_v2_app')
        c.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_v2_app')
    print('rag_test_scratch: additive v2 migrations applied; restricted app role ready')
if __name__=='__main__':initialize()
