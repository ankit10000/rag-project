#!/usr/bin/env bash
# Public encryption certificate only; the decryption key stays off this host.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run as the dedicated host administrator' >&2; exit 1; }
exec 9>/run/lock/rag-backup.lock
flock -n 9 || { echo 'A RAG export is already running' >&2; exit 1; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$root/data/backup.py" backup \
  --env-file /srv/rag/config/deployment.env --compose "$root/compose.yaml" \
  --recipient /srv/rag/config/backup-recipient.crt \
  --uploads /srv/rag/state/uploads --output /srv/rag/backups --keep 3
# Only this tool's generated ciphertext is exposed to the key-authorized SSH
# operator for off-host retrieval; database/upload/secret permissions stay intact.
chown ubuntu:ubuntu /srv/rag/backups
chmod 700 /srv/rag/backups
find /srv/rag/backups -maxdepth 1 -type f -name 'rag-export-*.tar.cms' -exec chown ubuntu:ubuntu {} +
