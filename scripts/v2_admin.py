"""Local operator bootstrap/reset; passwords are read privately, never CLI args."""
import argparse
import getpass
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['bootstrap','reset'])
    p.add_argument('--email',required=True)
    p.add_argument('--target-id')
    a=p.parse_args()
    if not os.getenv('DATABASE_URL'):p.error('DATABASE_URL must be explicitly set')
    os.environ['RAG_V2']='1'
    from backend.v2 import auth
    if a.operation=='bootstrap':auth.bootstrap_admin(a.email,getpass.getpass('New administrator password: '))
    else:
        if not a.target_id:p.error('reset requires --target-id')
        user,token,_=auth.login(a.email,getpass.getpass('Administrator password: '))
        try:auth.admin_reset_password(user,a.target_id,getpass.getpass('New target password: '))
        finally:auth.logout(token)
    print('Administrative operation recorded.')
if __name__=='__main__':main()
