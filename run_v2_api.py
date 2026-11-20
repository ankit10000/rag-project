"""Opt-in multi-user localhost server. Never inherits rag_db silently."""
import argparse
import os

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8000)
    p.add_argument('--workers',type=int,default=1)
    a=p.parse_args()
    if not 1<=a.port<=65535 or not 1<=a.workers<=8:p.error('invalid port/worker count')
    # Require the connection explicitly in the process environment, before dotenv.
    url=os.getenv('DATABASE_URL')
    if not url:p.error('set DATABASE_URL explicitly to a v2 database and restricted role')
    from psycopg.conninfo import conninfo_to_dict
    if conninfo_to_dict(url).get('dbname')=='rag_db':p.error('v2 must not access rag_db')
    if os.getenv('RAG_V2_COMPAT')=='1':p.error('legacy compatibility is forbidden')
    os.environ['RAG_V2']='1'
    os.environ.setdefault('LOCAL_V1_PROFILE','0')
    import uvicorn
    uvicorn.run('backend.v2.app:app',host='127.0.0.1',port=a.port,workers=a.workers,access_log=False)
if __name__=='__main__':main()
