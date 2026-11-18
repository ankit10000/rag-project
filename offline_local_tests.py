"""Run explicit local-v1 unit scripts without contacting any database/provider.

Uses an unreachable scratch-shaped URL rather than fingerprinting the application
DB. Database integration/restore rehearsals are separate scratch-only commands in
scripts/local_v1_scratch.py. No old run_tests.py application fingerprint is used.
"""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
TESTS=(
    'test_local_v1_security.py', 'test_local_v1_deadlines.py',
    'test_local_v1_api.py', 'test_local_v1_budget.py',
    'test_local_v1_retrieval.py', 'test_local_v1_database.py',
)
BOOTSTRAP="""
import runpy, socket, sys

def blocked(*args, **kwargs):
    raise AssertionError('network disabled by offline local-v1 runner')
socket.socket.connect=blocked
socket.socket.connect_ex=blocked
socket.create_connection=blocked
path=sys.argv[1]
sys.argv=[path]
runpy.run_path(path,run_name='__main__')
"""

def main():
    environment=dict(os.environ)
    environment.update(DATABASE_URL='postgresql://nobody@127.0.0.1:1/rag_test_scratch',
        TESTSAFE_BLOCK_NETWORK='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        LOCAL_V1_PROFILE='1', GEMINI_API_KEY='offline-placeholder-not-a-real-key')
    failures=[]
    for filename in TESTS:
        path=ROOT/filename
        if not path.is_file():
            print('MISSING '+filename,flush=True);failures.append(filename);continue
        print('RUN '+filename,flush=True)
        completed=subprocess.run([sys.executable,'-B','-c',BOOTSTRAP,str(path)],cwd=ROOT,env=environment)
        print('EXIT '+str(completed.returncode)+' '+filename,flush=True)
        if completed.returncode:failures.append(filename)
    print(f'{len(TESTS)-len(failures)}/{len(TESTS)} offline scripts passed',flush=True)
    return int(bool(failures))

if __name__=='__main__':raise SystemExit(main())
