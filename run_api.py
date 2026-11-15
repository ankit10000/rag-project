"""Start the local RAG API (see docs/remediation/PHASE7_SECURITY_LOCAL_DEPLOYMENT.md).

    .venv\\Scripts\\python.exe run_api.py                    # http://127.0.0.1:8765/api/v1/docs
    .venv\\Scripts\\python.exe run_api.py --port 9000
    .venv\\Scripts\\python.exe run_api.py --show-token-path  # where the API token file lives
    .venv\\Scripts\\python.exe run_api.py --rotate-token     # write a new token (restart the server)

Binds to loopback (127.0.0.1) by default. Any other host is refused unless
--allow-non-loopback is given explicitly AND the host is listed in
RAG_API_ALLOWED_HOSTS (Host-header allow-list). Every endpoint except /health
requires "Authorization: Bearer <token>". There is no TLS: anything beyond this
machine would see the token in clear text — do not expose the API to a network.
Requires: pip install -r backend/requirements-api.txt
"""

import argparse
import ipaddress
import sys

from backend.config import DEFAULT_HOST, DEFAULT_PORT, LOOPBACK_HOSTS


def _normalized_host(value: str) -> str:
    host = (value or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host.lower()


def _is_loopback(host: str) -> bool:
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False          # names other than "localhost" are not trusted as loopback


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--allow-non-loopback", action="store_true",
                        help="permit a non-loopback bind address (no TLS; LAN exposure is unsafe)")
    parser.add_argument("--rotate-token", action="store_true", help="write a new API token file and exit")
    parser.add_argument("--show-token-path", action="store_true", help="print the token file path and exit")
    args = parser.parse_args(argv)

    from backend.security import default_token_path, rotate_token

    if args.show_token_path:
        print(default_token_path())
        return 0
    if args.rotate_token:
        print(f"New API token written to: {rotate_token()} (restart the server to apply)")
        return 0

    host = _normalized_host(args.host)
    if not host:
        parser.error("--host must not be empty")
    if not (1 <= args.port <= 65535):
        parser.error("--port must be between 1 and 65535")
    if not _is_loopback(host):
        if not args.allow_non_loopback:
            parser.error(f"refusing to bind to {args.host!r}: loopback only (use --allow-non-loopback deliberately)")
        if host in ("0.0.0.0", "::"):
            print("WARNING: binding to ALL interfaces. The API has no TLS; the bearer token and all data "
                  "travel in clear text on the network.", file=sys.stderr)
        print("WARNING: non-loopback bind. Requests are still rejected unless their Host header is in "
              "RAG_API_ALLOWED_HOSTS.", file=sys.stderr)

    import uvicorn

    # Single worker: per-conversation locks, the token digest and caches are in-process.
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=args.port,
        workers=1,
        reload=False,
        proxy_headers=False,     # do not trust X-Forwarded-* from anyone
        server_header=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
