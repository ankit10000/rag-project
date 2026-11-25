"""Quiesced, encrypted export and guarded fresh-database restore.

The encryption certificate is public. Keep its private key OFF the AWS host.
No additional cloud storage service is used. Copy ciphertext off-host with scp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid


def run(args, **kwargs):
    # Docker exec otherwise consumes the caller's streamed SSH shell commands.
    # Restore explicitly supplies its dump stream; other commands need no input.
    kwargs.setdefault('stdin',subprocess.DEVNULL)
    return subprocess.run(args, check=True, **kwargs)


def compose(args, command):
    return ["docker", "compose", "--env-file", str(args.env_file), "-f", str(args.compose), *command]


def db(args, shell, *, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE):
    # Credential content never enters command arguments or captured output.
    guard = ('export PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"; '
             'actual=$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT current_database() || chr(124) || current_user"); '
             '[ "$actual" = "$POSTGRES_DB|$POSTGRES_USER" ]; '
             '[ "$POSTGRES_DB" = "rag_v2_demo" ] || [ "$POSTGRES_DB" = "rag_aws_scratch" ]; ')
    return run(compose(args, ["exec", "-T", "db", "sh", "-ec", guard + shell]),
               stdin=stdin, stdout=stdout, stderr=subprocess.PIPE)


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):result.update(block)
    return result.hexdigest()


def counts(args, name=None):
    tables = ("users", "documents", "jobs", "job_events", "conversations", "messages",
              "conversation_memories", "memory_sources", "document_chunks", "v2_turn_receipts")
    query = "SELECT json_build_object(" + ",".join(f"'{table}',(SELECT count(*) FROM {table})" for table in tables) + ")"
    database = name if name else '"$POSTGRES_DB"'
    return json.loads(db(args, f'psql -U "$POSTGRES_USER" -d {database} -Atc "{query}"').stdout)


def backup(args):
    if not args.recipient or not args.uploads or not args.output:
        raise ValueError("recipient certificate, upload directory and output required")
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = uuid.uuid4().hex
    target = args.output / f"rag-export-{stamp}.tar.cms"
    # Stop writers before capturing BOTH database and file store; always resume.
    active = subprocess.check_output(compose(args, ["ps", "--services", "--status", "running"]), text=True).split()
    writers = [service for service in ("api", "worker") if service in active]
    if writers:run(compose(args, ["stop", *writers]), stdout=subprocess.DEVNULL)
    try:
        with tempfile.TemporaryDirectory(prefix="rag-private-export-") as temporary:
            folder = Path(temporary)
            os.chmod(folder, 0o700)
            dump = folder / "database.dump"
            with dump.open("xb") as output:
                os.chmod(dump, 0o600)
                db(args, 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner', stdout=output)
            uploads = args.uploads.resolve()
            manifest = {"format": 1, "database_sha256": sha(dump), "table_counts": counts(args), "uploads": {
                str(file.relative_to(uploads)): sha(file) for file in uploads.rglob("*") if file.is_file()
            }}
            (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
            archive = folder / "export.tar"
            with tarfile.open(archive, "w") as package:
                package.add(dump, arcname="database.dump")
                package.add(folder / "manifest.json", arcname="manifest.json")
                package.add(uploads, arcname="uploads", recursive=True)
            run(["openssl", "cms", "-encrypt", "-aes256", "-binary", "-outform", "DER",
                 "-in", str(archive), "-out", str(target), str(args.recipient)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            os.chmod(target, 0o600)
    finally:
        if writers:run(compose(args, ["up", "-d", *writers]), stdout=subprocess.DEVNULL)
    # Delete only older exports from THIS tool, never arbitrary user backups.
    exports = sorted(args.output.glob("rag-export-*.tar.cms"), key=lambda file:file.stat().st_mtime, reverse=True)
    for file in exports[args.keep:]:file.unlink()
    print(json.dumps({"status": "PASS", "encrypted_export": str(target), "sha256": sha(target),
                      "bytes": target.stat().st_size, "off_host_copy_required": True, "retention": args.keep}))


def restore(args):
    if not args.archive or not args.private_key or not args.certificate or not args.restore_uploads:
        raise ValueError("encrypted archive, off-host private key/certificate and empty restore directory required")
    target = "rag_aws_restore_" + uuid.uuid4().hex
    upload_target = args.restore_uploads.resolve()
    if upload_target.exists() and any(upload_target.iterdir()):
        raise ValueError("restore upload directory must be empty")
    with tempfile.TemporaryDirectory(prefix="rag-private-restore-") as temporary:
        folder = Path(temporary)
        os.chmod(folder, 0o700)
        archive = folder / "export.tar"
        run(["openssl", "cms", "-decrypt", "-binary", "-inform", "DER", "-in", str(args.archive),
             "-recip", str(args.certificate), "-inkey", str(args.private_key), "-out", str(archive)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with tarfile.open(archive) as package:
            package.extractall(folder / "contents", filter="data")
        content = folder / "contents"
        manifest = json.loads((content / "manifest.json").read_text())
        if sha(content / "database.dump") != manifest["database_sha256"]:
            raise ValueError("database export checksum mismatch")
        for name, digest in manifest["uploads"].items():
            file = (content / "uploads" / name).resolve()
            if not file.is_relative_to((content / "uploads").resolve()) or sha(file) != digest:
                raise ValueError("upload export checksum mismatch")
        # Target name is generated, never supplied by the caller or an archive.
        db(args, f'createdb -U "$POSTGRES_USER" {target}')
        try:
            db(args, f'[ "$(psql -U "$POSTGRES_USER" -d {target} -Atc "SELECT current_database()")" = "{target}" ]')
            with (content / "database.dump").open("rb") as source:
                db(args, f'pg_restore -U "$POSTGRES_USER" -d {target} --exit-on-error --no-owner', stdin=source)
            result = db(args, f'psql -U "$POSTGRES_USER" -d {target} -Atc "SELECT count(*) FROM pg_class WHERE relnamespace=\x27public\x27::regnamespace AND relrowsecurity AND relforcerowsecurity"')
            if result.stdout.strip() != b"9":raise ValueError("restored RLS policies missing")
            if counts(args, target) != manifest["table_counts"]:
                raise ValueError("restored database row counts differ")
            shutil.copytree(content / "uploads", upload_target, dirs_exist_ok=True)
            print(json.dumps({"status": "PASS", "restored_database": target, "force_rls_tables": 9,
                              "upload_files": len(manifest["uploads"]), "restore_uploads": str(upload_target),
                              "table_counts": manifest["table_counts"],
                              "source_database_untouched": True}))
        except BaseException:
            # Only this invocation's generated failed target may be removed.
            db(args, f'dropdb -U "$POSTGRES_USER" {target}')
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["backup", "restore"])
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--compose", type=Path, default=Path(__file__).parents[1] / "compose.yaml")
    parser.add_argument("--recipient", type=Path)
    parser.add_argument("--uploads", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep", type=int, default=3)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--restore-uploads", type=Path)
    args = parser.parse_args()
    if not 1 <= args.keep <= 7:raise ValueError("retention must be one to seven exports")
    os.umask(0o077)
    (backup if args.mode == "backup" else restore)(args)


if __name__ == "__main__":
    try:main()
    except Exception as error:raise SystemExit(f"export/restore refused ({type(error).__name__})") from None
