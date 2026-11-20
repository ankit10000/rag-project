"""Tenant-safe PostgreSQL worker; defaults to a fair rotating active-user scheduler."""
import argparse
import os
import sys
from pathlib import Path
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def active_owner_batch(after=None, limit=100):
    """Read account identities only; tenant data still requires its owner's scope.

    Keyset pagination bounds scheduler memory. Each cycle wraps, so newly registered
    users are discovered without restarting workers or administering per-user daemons.
    """
    from services.tenant_context import auth_system_context
    from services.database import get_connection
    if not 1<=limit<=100:raise ValueError('invalid scheduler batch')
    with auth_system_context(),get_connection() as conn:
        rows=conn.execute("SELECT id FROM users WHERE status='active' AND (%s::uuid IS NULL OR id>%s::uuid) ORDER BY id LIMIT %s",(after,after,limit)).fetchall()
    return [str(row[0]) for row in rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',type=uuid.UUID,help='restrict this worker to one owner; default: fair active-user scheduler')
    parser.add_argument('--once',action='store_true',help='one owner attempt or one scheduler batch')
    parser.add_argument('--lease-seconds',default=120,type=int)
    args=parser.parse_args()
    if not 5<=args.lease_seconds<=600:parser.error('lease must be between5 and600seconds')
    os.environ['RAG_V2']='1'
    if os.getenv('RAG_V2_COMPAT')=='1':parser.error('legacy compatibility is forbidden')
    from services.v2_worker import process_one
    from services.tenant_context import auth_system_context
    from services.database import get_connection,DATABASE_URL
    from psycopg.conninfo import conninfo_to_dict
    expected=conninfo_to_dict(DATABASE_URL or '').get('dbname')
    if not expected or expected=='rag_db':parser.error('explicit non-production database required; rag_db is forbidden')
    with auth_system_context(),get_connection() as conn:
        actual=conn.execute('SELECT current_database()').fetchone()[0]
        if actual!=expected or actual=='rag_db':parser.error('database identity mismatch')
        role=conn.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        if any(role):parser.error('worker requires non-superuser non-BYPASSRLS role')
        if args.owner:
            row=conn.execute("SELECT 1 FROM users WHERE id=%s AND status='active'",(args.owner,)).fetchone()
            if not row:parser.error('owner is not active')
    wid=f'{os.getpid()}-{uuid.uuid4().hex[:12]}'
    cursor=None
    while True:
        owners=[str(args.owner)] if args.owner else active_owner_batch(cursor)
        if not owners:
            cursor=None
            if args.once:return 0
            time.sleep(1);continue
        handled=False
        for owner in owners:
            handled=process_one(owner,wid,lease_seconds=args.lease_seconds) or handled
        cursor=owners[-1] if not args.owner else None
        if args.once:return 0
        if not handled:time.sleep(1)
if __name__=='__main__':raise SystemExit(main())
