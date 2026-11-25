#!/usr/bin/env bash
# Run on the dedicated host. Images are built locally and loaded over SSH.
# Configuration and persistent data live outside versioned release directories.
set -euo pipefail
umask 077
operation=${1:?Usage: release.sh check|start|stop|migrate|status}
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
env_file=${RAG_DEPLOY_ENV:-/srv/rag/config/deployment.env}
[[ -r "$env_file" ]] || { echo 'Missing private deployment configuration' >&2; exit 1; }
compose=(docker compose --env-file "$env_file" -f "$release_dir/compose.yaml")
case "$operation" in
  check)
    # Do not print interpolated environment, mounted secrets or connection URLs.
    "${compose[@]}" config --quiet
    ;;
  migrate)
    "${compose[@]}" up -d --wait db
    "${compose[@]}" --profile tools run --rm migrate
    ;;
  start)
    "${compose[@]}" config --quiet
    "${compose[@]}" up -d --wait --wait-timeout 180
    ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  *) echo 'Unknown operation' >&2; exit 1 ;;
esac
