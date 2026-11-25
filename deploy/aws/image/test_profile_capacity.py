"""Regression for retaining measurements during an actual container replacement."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy.aws import profile_capacity


class CapacitySamplingTests(unittest.TestCase):
    def test_replacement_error_remains_visible_and_later_samples_survive(self):
        failed = subprocess.CompletedProcess([], 1, "", "No such container: old-id")
        successful = subprocess.CompletedProcess([], 0, '{"Name":"proxy","MemUsage":"10MiB / 96MiB"}\n', "")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new-run.json"
            with patch.object(profile_capacity.subprocess, "run", side_effect=[failed, successful]), \
                 patch.object(profile_capacity.subprocess, "check_output", side_effect=[
                     '{"OOMKilled":false}',
                     '{"Memory":100663296,"MemorySwap":100663296,"NanoCpus":250000000,"CpusetCpus":"0,1"}',
                     '10485760\n12582912\noom 0\noom_kill 0\nusage_usec 1000000\n',
                 ]), \
                 patch.object(profile_capacity.time, "monotonic", side_effect=[0, 0, .25, .5, .75, 2, 2.5]), \
                 patch.object(profile_capacity.time, "sleep"), redirect_stdout(io.StringIO()):
                profile_capacity.sample(["proxy"], 1, output)
            result = json.loads(output.read_text())
            self.assertEqual(result["status"], "complete_with_probe_errors")
            self.assertEqual(result["probe_errors"], 1)
            self.assertEqual(result["samples"][0]["probe_error"]["return_code"], 1)
            self.assertNotIn("containers", result["samples"][0])
            self.assertEqual(result["samples"][1]["containers"][0]["Name"], "proxy")
            self.assertEqual(result["inspections"][0]["cpuset_cpus"], "0,1")
            self.assertEqual(result["inspections"][0]["cgroup"]["memory_peak_bytes"], 12582912)

    def test_existing_run_is_refused_before_any_docker_call(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preserved.json"
            output.write_text("historical result")
            with patch.object(profile_capacity.subprocess, "run") as call:
                with self.assertRaises(FileExistsError):
                    profile_capacity.sample(["proxy"], 1, output)
                call.assert_not_called()
            self.assertEqual(output.read_text(), "historical result")


if __name__ == "__main__":
    unittest.main()
