"""Cross-process scoped serialization, with no open transaction during inference."""
from contextlib import contextmanager
import time
from services.database import get_connection
from services.request_budget import check_deadline

@contextmanager
def resource_lock(resource_id, timeout=60):
    from services.tenant_context import current_owner
    owner=current_owner()
    if not owner:raise PermissionError('tenant required')
    key=f'{owner}:{resource_id}'
    conn=get_connection()
    conn.commit()
    conn.autocommit=True
    acquired=False
    start=time.monotonic()
    try:
        while not acquired:
            check_deadline()
            acquired=conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))',(key,)).fetchone()[0]
            if not acquired:
                if time.monotonic()-start>timeout:raise TimeoutError('resource busy')
                time.sleep(.05)
        yield
    finally:
        try:
            if acquired:conn.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))',(key,))
        finally:
            conn.close()
