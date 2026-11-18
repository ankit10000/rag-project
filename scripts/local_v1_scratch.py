"""Explicit scratch-only initialization and backup/restore rehearsal.

Never connects to the configured application database: only its connection
credentials are reused after replacing dbname. No production fingerprinting.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import sys
from urllib.parse import quote, urlencode
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ('000_base_schema.sql', '001_add_messages_context_excluded.sql',
              '002_add_memory_sources.sql', '003_memory_sources_provenance.sql')

TEST_BOOTSTRAP = '''
import runpy, socket, sys
allowed = {'localhost', '127.0.0.1', '::1'}
original = socket.socket.connect_ex
def connect_ex(sock, address):
    if not isinstance(address, tuple) or address[0] not in allowed:
        raise OSError('external network disabled by local-v1 scratch runner')
    return original(sock, address)
socket.socket.connect_ex = connect_ex
path = sys.argv[1]
sys.argv = [path]
runpy.run_path(path, run_name='__main__')
'''


def registered_tests():
    tree = ast.parse((ROOT/'run_tests.py').read_text())
    registry = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'CATEGORIES' for t in node.targets))
    return registry['unit'] + registry['integration']


def run_tests(names, results_file=None):
    results = []
    environment = dict(os.environ, DATABASE_URL=scratch_url(),
        TESTSAFE_BLOCK_NETWORK='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        PYTHONDONTWRITEBYTECODE='1')
    for test in names:
        if Path(test).name != test or not test.startswith('test_') or not test.endswith('.py'):
            raise ValueError('test must be an explicit root-level test filename')
        # Every test batch gets a fresh actual-database identity check. The
        # application database is never opened, even for a fingerprint.
        with connect():
            pass
        child_env = dict(environment, LOCAL_V1_PROFILE='1' if test.startswith('test_local_v1_') else '0',
                         LOCAL_V1_DB_INTEGRATION='1')
        started = time.monotonic()
        try:
            process = subprocess.run([str(ROOT/'.venv/bin/python'), '-B', '-c',
                                      TEST_BOOTSTRAP, str(ROOT/test)],
                env=child_env, cwd=ROOT, capture_output=True, text=True, timeout=180)
            code, output = process.returncode, process.stdout + process.stderr
        except subprocess.TimeoutExpired:
            code, output = 124, 'test exceeded 180-second subprocess limit'
        results.append(dict(test=test, exit_code=code,
                            seconds=round(time.monotonic()-started, 3), output=output))
        print(('PASS ' if code == 0 else 'FAIL ') + test, flush=True)
    if results_file:
        with Path(results_file).open('x') as handle:
            json.dump(results, handle, indent=2)
            handle.write('\n')
    print(f'{sum(r["exit_code"] == 0 for r in results)}/{len(results)} scratch scripts passed', flush=True)
    return int(any(r['exit_code'] != 0 for r in results))


def safe_name(name):
    if name != 'rag_test_scratch' and not re.fullmatch(r'rag_local_v1_test_[a-z0-9_]+', name or ''):
        raise ValueError('only explicit local-v1 scratch database names are allowed')
    return name


def scratch_info(name='rag_test_scratch'):
    safe_name(name)
    base = os.environ.get('LOCAL_V1_SCRATCH_BASE_URL') or dotenv_values(ROOT/'.env').get('DATABASE_URL')
    if not base:
        raise ValueError('scratch server credentials unavailable')
    info = conninfo_to_dict(base)
    info['dbname'] = name
    return info


def scratch_url(name='rag_test_scratch'):
    """Keep legacy harness URL consumers compatible without exposing credentials."""
    info = dict(scratch_info(name))
    database = info.pop('dbname')
    user, password = info.pop('user', ''), info.pop('password', None)
    host, port = info.pop('host', ''), info.pop('port', '')
    if ':' in host and not host.startswith('/'):
        host = '[' + host + ']'
    if host.startswith('/'):
        info['host'], host = host, ''
    auth = quote(user, safe='')
    if password is not None:
        auth += ':' + quote(password, safe='')
    if auth:
        auth += '@'
    query = urlencode(info)
    return ('postgresql://' + auth + host + (':' + str(port) if port else '')
            + '/' + quote(database, safe='') + ('?' + query if query else ''))


def connect(name='rag_test_scratch'):
    safe_name(name)
    connection = psycopg.connect(make_conninfo(**scratch_info(name)), connect_timeout=5)
    try:
        actual = connection.execute('SELECT current_database()').fetchone()[0]
        if actual != name:
            raise ValueError('scratch database identity differs from the requested target')
        connection.commit()
    except BaseException:
        connection.close()
        raise
    return connection


def initialize(name='rag_test_scratch'):
    with connect(name) as connection:
        # Only the approved application migrations 000–003 are allowed here.
        for filename in MIGRATIONS:
            connection.execute((ROOT/'migrations'/filename).read_text())
        tables = [row[0] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()]
    return dict(database=name, migrations=list(MIGRATIONS), tables=tables)


def create_database(name):
    safe_name(name)
    if name == 'rag_test_scratch':
        raise ValueError('bootstrap database is never created or replaced by this helper')
    with connect() as bootstrap:
        bootstrap.autocommit = True
        bootstrap.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
    # Independent connection verifies the actual newly created restore target.
    with connect(name):
        pass


def _tool_environment(name):
    info = scratch_info(name)
    environment = dict(os.environ)
    for key, variable in [('host','PGHOST'),('port','PGPORT'),('user','PGUSER'),('password','PGPASSWORD'),('dbname','PGDATABASE')]:
        if key in info:
            environment[variable] = str(info[key])
    environment['PGCONNECT_TIMEOUT'] = '5'
    return environment


def _run_tool(name, args, database):
    with connect(database):
        pass
    tool = shutil.which(name)
    if not tool:
        raise ValueError(name + ' is unavailable')
    process = subprocess.run([tool]+args,env=_tool_environment(database),
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    if process.returncode:
        # Tool stderr can contain sensitive connection details; report status only.
        raise RuntimeError(f'{name} failed with exit {process.returncode}')
    return process.stdout


def restore_drill():
    # Verify the explicitly authorized existing scratch database before CREATE DATABASE.
    with connect():
        pass
    suffix = str(int(time.time())) + '_' + uuid.uuid4().hex[:6]
    source, target = 'rag_local_v1_test_backup_'+suffix, 'rag_local_v1_test_restore_'+suffix
    create_database(source)
    initialize(source)
    initialize(source)  # A fresh setup must also tolerate an idempotent re-run.
    conversation_id = uuid.uuid4()
    with connect(source) as conn:
        conn.execute('INSERT INTO conversations(id,title) VALUES(%s,%s)',(conversation_id,'local-v1 restore fixture'))
        mid = conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES(%s,'user','I prefer tea.') RETURNING id",(conversation_id,)).fetchone()[0]
        vector = '[' + ','.join(['1']+['0']*383) + ']'
        memory_id = conn.execute('INSERT INTO conversation_memories(conversation_id,memory,embedding,source_message_id) VALUES(%s,%s,%s::vector,%s) RETURNING id',(conversation_id,'User prefers tea.',vector,mid)).fetchone()[0]
        conn.execute("INSERT INTO memory_sources(conversation_id,memory_id,source_message_id,link_kind,source_role) VALUES(%s,%s,%s,'origin','user')",(conversation_id,memory_id,mid))
        conn.execute('INSERT INTO document_chunks(document_name,page_number,chunk_id,content,embedding) VALUES(%s,1,1,%s,%s::vector)',
                     ('local-v1-restore.pdf','Permit duration is 30 days.',vector))
    with tempfile.TemporaryDirectory(prefix='local-v1-backup-') as temporary:
        backup = Path(temporary)/'scratch.dump'
        _run_tool('pg_dump',['--format=custom','--no-owner','--file',str(backup)],source)
        size=backup.stat().st_size
        create_database(target)
        with connect(target):
            pass
        _run_tool('pg_restore',['--no-owner','--exit-on-error','--dbname',target,str(backup)],target)
        with connect(target) as conn:
            rows = conn.execute('''SELECT cm.memory, cm.source_message_id, m.role, ms.source_role,
                 m.context_excluded, vector_dims(cm.embedding)
                 FROM conversation_memories cm JOIN memory_sources ms ON ms.memory_id=cm.id
                 JOIN messages m ON m.id=ms.source_message_id AND m.conversation_id=cm.conversation_id
                 WHERE cm.conversation_id=%s''',(conversation_id,)).fetchall()
            if rows != [('User prefers tea.',mid,'user','user',False,384)]:
                raise AssertionError('restored provenance fixture differs from backup')
            chunks = conn.execute('SELECT page_number,chunk_id,content,vector_dims(embedding) FROM document_chunks WHERE document_name=%s',
                                  ('local-v1-restore.pdf',)).fetchall()
            if chunks != [(1,1,'Permit duration is 30 days.',384)]:
                raise AssertionError('restored document/vector fixture differs from backup')
    return dict(source_database=source,restore_database=target,backup_bytes=size,
                provenance_rows_verified=len(rows), document_chunks_verified=len(chunks),
                original_application_database_accessed=False,
                databases_retained_for_inspection=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--restore-drill',action='store_true')
    parser.add_argument('--run-tests',nargs='*',default=None)
    parser.add_argument('--run-registered',action='store_true')
    parser.add_argument('--results-file')
    args=parser.parse_args()
    with connect() as conn:
        print('Verified current_database() = '+conn.execute('SELECT current_database()').fetchone()[0])
    if args.initialize:print(json.dumps(initialize(),sort_keys=True))
    if args.restore_drill:print(json.dumps(restore_drill(),sort_keys=True))
    if args.run_tests is not None or args.run_registered:
        if args.run_tests is not None and args.run_registered:
            raise ValueError('choose explicit tests or the registered offline suite')
        return run_tests(registered_tests() if args.run_registered else args.run_tests, args.results_file)
    return 0


if __name__=='__main__':raise SystemExit(main())
