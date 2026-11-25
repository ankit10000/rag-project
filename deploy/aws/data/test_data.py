"""Offline regressions for deployment identity, secrets and graceful draining."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading
import subprocess
import shlex
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from runtime import database_name, secret, verify

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts import run_v2_worker


class GuardTests(unittest.TestCase):
    def test_database_allowlist(self):
        for name in ("rag_v2_demo", "rag_aws_scratch", "rag_aws_restore_" + "a" * 32):
            self.assertEqual(database_name(name), name)
        for name in ("rag_db", "postgres", "rag_test_scratch", "rag_v2_demo;DROP DATABASE x", ""):
            with self.assertRaises(ValueError):database_name(name)

    def test_actual_identity_and_role_flags(self):
        with patch.dict(os.environ, {"RAG_DATABASE_NAME": "rag_aws_scratch"}):
            def connection(rows):
                iterator = iter(rows)
                return SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda:next(iterator)))
            verify(connection([("rag_aws_scratch", "rag_v2_app"), (False, False)]))
            for rows in ([ ("rag_db", "rag_v2_app") ],
                         [ ("rag_aws_scratch", "postgres") ],
                         [ ("rag_aws_scratch", "rag_v2_app"), (True, False) ],
                         [ ("rag_aws_scratch", "rag_v2_app"), (False, True) ]):
                with self.assertRaises(ValueError):verify(connection(rows))

    def test_secret_no_multiline_or_short_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "secret"
            for value in ("short", "a" * 24 + "\nembedded"):
                file.write_text(value)
                with self.assertRaises(ValueError):secret(str(file))
            file.write_text("a" * 24 + "\n")
            self.assertEqual(secret(str(file)), "a" * 24)


class WorkerDrainTests(unittest.TestCase):
    def test_stop_during_attempt_finishes_it_and_claims_no_next_owner(self):
        stopped = threading.Event()
        events = []
        def process(owner, *_args, **_kwargs):
            events.append((owner, "started"))
            stopped.set()
            events.append((owner, "finished"))
            return True
        with patch.object(run_v2_worker, "active_owner_batch", return_value=["owner-a", "owner-b"]), \
             patch("services.v2_worker.process_one", side_effect=process):
            result = run_v2_worker.work_loop(SimpleNamespace(owner=None, once=False, lease_seconds=120), "worker", stopped)
        self.assertEqual(result, 0)
        self.assertEqual(events, [("owner-a", "started"), ("owner-a", "finished")])

    def test_already_stopped_does_not_read_or_claim(self):
        stopped = threading.Event();stopped.set()
        with patch.object(run_v2_worker, "active_owner_batch") as owners, \
             patch("services.v2_worker.process_one") as process:
            run_v2_worker.work_loop(SimpleNamespace(owner=None, once=False, lease_seconds=120), "worker", stopped)
            owners.assert_not_called();process.assert_not_called()


class BackupInputTests(unittest.TestCase):
    def test_backup_child_cannot_consume_remaining_streamed_operator_commands(self):
        code=('from deploy.aws.data.backup import run; import sys; '
              'print("CHILD_READY",flush=True); '
              'run([sys.executable,"-c","import sys; sys.stdin.read()"] )')
        process=subprocess.Popen(['bash','-s'],cwd=ROOT,stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            process.stdin.write(shlex.join([sys.executable,'-c',code])+'\n');process.stdin.flush()
            self.assertEqual(process.stdout.readline().strip(),'CHILD_READY')
            process.stdin.write("printf 'OPERATOR_COMMAND_COMPLETED\\n'\n");process.stdin.close();process.stdin=None
            output,error=process.communicate(timeout=5)
            self.assertEqual(process.returncode,0,error)
            self.assertEqual(output,'OPERATOR_COMMAND_COMPLETED\n')
        finally:
            if process.poll() is None:process.kill();process.wait()


if __name__ == "__main__":unittest.main()
