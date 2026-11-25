"""Run on the administrator's machine to retain encrypted off-host exports.

Only generated ciphertext basenames are accepted. SSH host keys must already be
verified; this tool never disables host verification or downloads private keys.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="authorized SSH user@host")
    parser.add_argument("--remote-directory", default="/srv/rag/backups")
    parser.add_argument("--filename", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--identity-file", type=Path, help="existing private SSH key, kept off-host")
    parser.add_argument("--known-hosts", type=Path, help="previously verified SSH host keys")
    parser.add_argument("--sudo-remote", action="store_true", help="read ciphertext through key-authorized noninteractive sudo; keep server parents private")
    parser.add_argument("--keep", type=int, default=3)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]+", args.host):raise ValueError("invalid SSH host")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.remote_directory) or ".." in args.remote_directory.split("/"):
        raise ValueError("invalid remote backup directory")
    if not re.fullmatch(r"rag-export-[a-f0-9]{32}\.tar\.cms", args.filename):raise ValueError("invalid backup name")
    if not 1 <= args.keep <= 7:raise ValueError("retention must be one to seven exports")
    os.umask(0o077)
    args.destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = args.destination / args.filename
    if target.exists():raise ValueError("existing backup must not be overwritten")
    temporary = target.with_suffix(".partial")
    options=["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
    for file in (args.identity_file,args.known_hosts):
        if file is not None and (not file.is_file() or not file.stat().st_size):
            raise ValueError("SSH key/host verification file unavailable")
    if args.identity_file:options.extend(["-i",str(args.identity_file.resolve())])
    if args.known_hosts:options.extend(["-o",f"UserKnownHostsFile={args.known_hosts.resolve()}"])
    try:
        remote=f"{args.remote_directory}/{args.filename}"
        if args.sudo_remote:
            with temporary.open('xb') as output:
                subprocess.run(["ssh",*options,args.host,"sudo","-n","cat","--",remote],
                               stdout=output,check=True)
        else:
            subprocess.run(["scp", *options,f"{args.host}:{remote}",str(temporary)],check=True)
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)
    files = sorted(args.destination.glob("rag-export-*.tar.cms"), key=lambda file:file.stat().st_mtime, reverse=True)
    for file in files[args.keep:]:
        if re.fullmatch(r"rag-export-[a-f0-9]{32}\.tar\.cms", file.name):file.unlink()
    print(json.dumps({"status":"PASS", "encrypted_off_host_backup":str(target),
                      "sha256":hashlib.file_digest(target.open("rb"), "sha256").hexdigest(), "retention":args.keep}))


if __name__ == "__main__":main()
