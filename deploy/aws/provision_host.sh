#!/usr/bin/env bash
# Run on the newly provisioned Ubuntu 24.04 host after key-based SSH succeeds.
# This script creates no AWS resources and never modifies an account plan.
set -euo pipefail
umask 077

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ ${EUID} -eq 0 ]] || fail 'Run with sudo on the dedicated demo host.'
[[ -r /etc/os-release ]] || fail 'Missing OS identity.'
# shellcheck source=/dev/null
. /etc/os-release
[[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 ]] || fail 'Only Ubuntu 24.04 LTS is verified by this script.'
[[ $(dpkg --print-architecture) == amd64 || $(dpkg --print-architecture) == arm64 ]] || fail 'Unsupported CPU architecture.'
: "${ADMIN_CIDR:?Set the exact administrative public IP /32 or /128.}"
: "${DOCKER_VERSION:?Set an explicit official Docker CE/CLI apt version verified for this Ubuntu release.}"
: "${CONTAINERD_VERSION:?Set an explicit containerd.io apt version.}"
: "${BUILDX_VERSION:?Set an explicit docker-buildx-plugin apt version.}"
: "${COMPOSE_VERSION:?Set an explicit docker-compose-plugin apt version.}"
ADMIN_USER=${ADMIN_USER:-ubuntu}
[[ ${ADMIN_USER} =~ ^[a-z_][a-z0-9_-]*$ ]] || fail 'Invalid administrative user.'
getent passwd "${ADMIN_USER}" >/dev/null || fail 'Administrative user does not exist.'
admin_home=$(getent passwd "${ADMIN_USER}" | cut -d: -f6)
[[ -s ${admin_home}/.ssh/authorized_keys ]] || fail 'Install and verify a key before disabling password login.'
python3 - "${ADMIN_CIDR}" "${SSH_CONNECTION:-}" <<'PY'
import ipaddress, sys
network = ipaddress.ip_network(sys.argv[1], strict=True)
if network.prefixlen != network.max_prefixlen:
    raise SystemExit('ADMIN_CIDR must identify a single administrative address')
if sys.argv[2] and ipaddress.ip_address(sys.argv[2].split()[0]) not in network:
    raise SystemExit('Current SSH client is outside ADMIN_CIDR; refusing lockout')
PY

# Dedicated host, 4 GB bundle: leave headroom for the kernel and disk caches.
memory_kib=$(awk '/MemTotal/{print $2}' /proc/meminfo)
[[ ${memory_kib} -ge 3500000 && ${memory_kib} -le 5000000 ]] || fail 'Expected the approved 4 GB host; recheck the selected bundle.'
free_kib=$(df --output=avail / | tail -n 1 | tr -d ' ')
[[ ${free_kib} -ge 20000000 ]] || fail 'Need at least 20 GB free for images, model cache, uploads and recovery.'
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active' && [[ ! -f /var/lib/rag-monitor/provisioned ]]; then
  fail 'UFW already active on an unrecognized host: inspect its rules first.'
fi
if [[ -f /var/lib/rag-monitor/provisioned && $(cat /var/lib/rag-monitor/provisioned) != "${ADMIN_CIDR}" ]]; then
  fail 'Administrative IP changed: explicitly review/remove the old SSH firewall rule first.'
fi

export DEBIAN_FRONTEND=noninteractive
# The approved host is IPv4-only. Bound mirror stalls and skip translation
# indexes; signed repository/package verification remains enabled.
cat > /etc/apt/apt.conf.d/90-rag-network <<'APT'
Acquire::ForceIPv4 "true";
Acquire::Retries "2";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
Acquire::Languages "none";
APT
# The regional archive is fast, but the image's security HTTP mirror stalled in
# the real preflight. Keep Canonical's signed source and use its verified HTTPS
# endpoint, retaining the original vendor configuration for rollback.
python3 - <<'PY'
from pathlib import Path
import shutil
source=Path('/etc/apt/sources.list.d/ubuntu.sources')
if source.exists():
    original=source.read_text()
    updated=original.replace('URIs: http://security.ubuntu.com/ubuntu',
                             'URIs: https://security.ubuntu.com/ubuntu')
    if original!=updated:
        saved=Path('/var/lib/rag-provision/ubuntu.sources.original')
        saved.parent.mkdir(mode=0o700,exist_ok=True)
        if not saved.exists():shutil.copy2(source,saved)
        source.write_text(updated)
PY
apt-get update
apt-get install -y ca-certificates curl gnupg openssl ufw
install -m 0755 -d /etc/apt/keyrings
key_dir=$(mktemp -d)
key_tmp=${key_dir}/docker.asc
trap 'rm -rf -- "${key_dir}"' EXIT
curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o "${key_tmp}"
# Verified from the official HTTPS key endpoint on 2026-11-23. Accept only the
# primary signing identity; a changed/rotated key requires an explicit review.
key_fingerprint=$(GNUPGHOME="${key_dir}" gpg --batch --no-options --with-colons --show-keys "${key_tmp}" \
  | awk -F: '$1=="pub"{primary=1;next} primary && $1=="fpr"{print $10;exit}')
[[ ${key_fingerprint} == 9DC858229FC7DD38854AE2D88D81803C0EBFCD88 ]] || fail 'Official Docker repository signing-key fingerprint changed; refusing installation.'
install -m 0644 "${key_tmp}" /etc/apt/keyrings/docker.asc
printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/docker.sources
apt-get update
apt-get install -y "docker-ce=${DOCKER_VERSION}" "docker-ce-cli=${DOCKER_VERSION}" \
  "containerd.io=${CONTAINERD_VERSION}" "docker-buildx-plugin=${BUILDX_VERSION}" \
  "docker-compose-plugin=${COMPOSE_VERSION}"

# Do not overwrite an existing daemon config or restart unrelated containers.
install -m 0755 -d /etc/docker
if [[ ! -e /etc/docker/daemon.json ]]; then
  printf '%s\n' '{"log-driver":"local","log-opts":{"max-size":"10m","max-file":"3"},"live-restore":true}' > /etc/docker/daemon.json
fi
systemctl enable --now docker
docker compose version

install -m 0755 -d /etc/ssh/sshd_config.d
ssh_tmp=$(mktemp /etc/ssh/sshd_config.d/.rag-demo.XXXXXX)
cat > "${ssh_tmp}" <<'SSH'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
SSH
chmod 0644 "${ssh_tmp}"
# Verify the candidate include, and verify the effective configuration after.
candidate_config=${key_dir}/sshd-test.conf
printf 'Include %s\nInclude /etc/ssh/sshd_config\n' "${ssh_tmp}" > "${candidate_config}"
sshd -t -f "${candidate_config}"
mv "${ssh_tmp}" /etc/ssh/sshd_config.d/00-rag-demo.conf
sshd -t
sshd -T | awk '/^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) /{if($2!="no")exit 1}' || fail 'Existing SSH directives override hardening.'
systemctl reload ssh

# UFW protects host sockets. Published Docker ports can bypass UFW: the Compose
# contract must publish only Caddy 80/443, and Lightsail must independently permit
# only 80/443 plus this administrative SSH address (for IPv4 and IPv6 separately).
# Refuse an unrecognized existing firewall above. Repeating these exact rules is
# idempotent; changed admin addresses require a deliberate firewall review.
ufw default deny incoming
ufw default allow outgoing
ufw allow from "${ADMIN_CIDR}" to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

install -m 0700 -d /srv/rag /srv/rag/config /srv/rag/secrets /srv/rag/backups /srv/rag/state /srv/rag/models /var/lib/rag-monitor
cat > /usr/local/sbin/rag-host-health <<'MONITOR'
#!/usr/bin/env python3
import datetime, json, os, pathlib, shutil, subprocess
memory = {}
for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
    key, rest = line.split(':', 1)
    memory[key] = int(rest.split()[0])
disk = shutil.disk_usage('/srv/rag')
free_ratio = disk.free / disk.total
available_ratio = memory['MemAvailable'] / memory['MemTotal']
result = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'memory_available_kib': memory['MemAvailable'], 'memory_total_kib': memory['MemTotal'],
          'disk_free_bytes': disk.free, 'disk_total_bytes': disk.total, 'load_average': os.getloadavg(),
          'warning': available_ratio < .15 or free_ratio < .20}
pathlib.Path('/var/lib/rag-monitor/host.json').write_text(json.dumps(result) + '\n')
if result['warning']:
    subprocess.run(['logger', '-p', 'daemon.warning', '-t', 'rag-host', 'Low memory or disk; inspect /var/lib/rag-monitor/host.json'], check=False)
MONITOR
chmod 0755 /usr/local/sbin/rag-host-health
cat > /etc/systemd/system/rag-host-health.service <<'UNIT'
[Unit]
Description=Record bounded RAG demo host capacity metrics
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/rag-host-health
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/rag-monitor
UNIT
cat > /etc/systemd/system/rag-host-health.timer <<'UNIT'
[Unit]
Description=Measure RAG demo host memory and disk every minute
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now rag-host-health.timer

# Only the public encryption certificate belongs on this host. The private key
# and off-host ciphertext pull remain on the administrator's machine. The timer
# is inert until a reviewed release, private env file and recipient are present.
cat > /etc/systemd/system/rag-encrypted-backup.service <<'UNIT'
[Unit]
Description=Quiesced encrypted RAG database and source export
After=docker.service rag-compose.service
Requires=docker.service
ConditionPathExists=/srv/rag/current/backup-now.sh
ConditionPathExists=/srv/rag/current/compose.yaml
ConditionPathExists=/srv/rag/config/deployment.env
ConditionPathExists=/srv/rag/config/backup-recipient.crt
[Service]
Type=oneshot
WorkingDirectory=/srv/rag/current
ExecStart=/bin/bash /srv/rag/current/backup-now.sh
TimeoutStartSec=900
UMask=0077
NoNewPrivileges=true
UNIT
cat > /etc/systemd/system/rag-encrypted-backup.timer <<'UNIT'
[Unit]
Description=Daily encrypted RAG export with three-file retention
[Timer]
OnCalendar=*-*-* 02:30:00 UTC
RandomizedDelaySec=120
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now rag-encrypted-backup.timer
printf '%s\n' "${ADMIN_CIDR}" > /var/lib/rag-monitor/provisioned
printf '%s\n' 'Host preparation finished. Verify Lightsail firewall, Compose port publication, DNS and HTTPS independently.'
