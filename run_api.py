"""Start the local RAG API (documentation: docs/remediation/PHASE6_BACKEND_API_APPLICATION_LAYER.md).

    .venv\\Scripts\\python.exe run_api.py                 # http://127.0.0.1:8765/api/v1/docs
    .venv\\Scripts\\python.exe run_api.py --port 9000

Binds to loopback (127.0.0.1) by default. Any other host is refused unless
--allow-non-loopback is given explicitly; there is NO authentication yet
(Phase 7), so exposing the API beyond this machine is unsafe.
Requires: pip install -r backend/requirements-api.txt
"""

import argparse
import sys

from backend.config import DEFAULT_HOST, DEFAULT_PORT, LOOPBACK_HOSTS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--allow-non-loopback", action="store_true",
                        help="permit binding to a non-loopback address (no auth exists yet)")
    args = parser.parse_args(argv)

    if args.host not in LOOPBACK_HOSTS and not args.allow_non_loopback:
        parser.error(f"refusing to bind to {args.host!r}: loopback only (no authentication until Phase 7)")

    import uvicorn

    # Single worker: the app keeps per-conversation locks and in-process caches.
    uvicorn.run("backend.app:app", host=args.host, port=args.port, workers=1, reload=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
