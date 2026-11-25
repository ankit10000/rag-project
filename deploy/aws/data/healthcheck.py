"""Readiness checks: exact restricted DB, FORCE RLS, pinned assets, live process."""
from pathlib import Path
import json
import os
import sys
import time
import urllib.request

import psycopg

from prepare_assets import verify_assets
from runtime import connection_info, verify


def main():
    verify_assets(Path("/models"))
    with psycopg.connect(connection_info()) as connection:
        verify(connection)
        count = connection.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace "
                                   "AND relrowsecurity AND relforcerowsecurity").fetchone()[0]
        if count != 9:
            raise ValueError("tenant schema is not ready")
    if sys.argv[1] == "api":
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v2/health", timeout=5) as response:
            if response.status != 200:
                raise ValueError("API is not ready")
    elif sys.argv[1] == "worker":
        heartbeat = json.loads(Path("/tmp/worker-heartbeat.json").read_text())
        if time.time() - heartbeat["unix"] > 20:
            raise ValueError("worker heartbeat expired")
        os.kill(heartbeat["pid"], 0)
    else:
        raise ValueError("unknown service")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
