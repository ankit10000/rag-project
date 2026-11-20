import os,sys,runpy
os.environ.update(DATABASE_URL="postgresql:///rag_test_scratch", TESTSAFE_BLOCK_NETWORK="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", GEMINI_API_KEY="offline-placeholder")
import testsafe
testsafe.require_scratch_db()
import psycopg,socket
def forbidden(*args,**kwargs):
    raise AssertionError("provider-free deterministic regression forbids database/network I/O")
psycopg.connect=forbidden
psycopg.Connection.connect=classmethod(forbidden)
socket.socket.connect=forbidden
sys.argv=[sys.argv[1]]
runpy.run_path(sys.argv[0],run_name="__main__")
