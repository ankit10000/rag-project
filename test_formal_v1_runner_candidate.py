"""Replay the narrow output-path fix on temporary copies; never run evaluation.

No production source is changed, no approval or runtime identity is fabricated,
and no database/provider service is imported. Synthetic symlinks stay in tmp.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'eval/framework/safety.py'
PATCH = ROOT/'scripts/formal_v1_runner_candidate.patch'


class CandidateOutputGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = SOURCE.read_bytes()
        cls.original = cls.production.replace(b'    if os.path.lexists(path):\n',
                                              b'    if os.path.exists(path):\n', 1)
        if cls.original == cls.production:
            raise AssertionError('production output guard must use lexists')
        cls.tmp = tempfile.TemporaryDirectory(prefix='formal-v1-candidate-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        target = cls.root/'eval/framework/safety.py'
        target.parent.mkdir(parents=True)
        target.write_bytes(cls.original)
        patch_program = shutil.which('patch')
        if not patch_program:
            raise RuntimeError('local patch utility required for candidate-copy test')
        subprocess.run([patch_program, '-s', '-p1', '-i', str(PATCH)],
                       cwd=cls.root, check=True, capture_output=True, text=True)
        cls.patched = target.read_bytes()
        cls.module = types.ModuleType('_formal_candidate_output_guard')
        cls.module.__file__ = str(target)
        sys.modules[cls.module.__name__] = cls.module
        cls.addClassCleanup(sys.modules.pop, cls.module.__name__, None)
        exec(compile(cls.patched, str(target), 'exec'), cls.module.__dict__)
        cls.original_module = types.ModuleType('_formal_original_output_guard')
        cls.original_module.__file__ = str(SOURCE)
        sys.modules[cls.original_module.__name__] = cls.original_module
        cls.addClassCleanup(sys.modules.pop, cls.original_module.__name__, None)
        exec(compile(cls.original, str(SOURCE), 'exec'), cls.original_module.__dict__)

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='synthetic-output-')
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_patch_is_one_guard_change_and_source_stays_identical(self):
        self.assertEqual(self.patched, self.original.replace(
            b'    if os.path.exists(path):\n',
            b'    if os.path.lexists(path):\n', 1))
        self.assertEqual(self.patched, self.production)
        self.assertEqual(SOURCE.read_bytes(), self.production)

    def test_dangling_symlink_is_refused_without_touching_target_or_link(self):
        target = self.folder/'absent-target.jsonl'
        output = self.folder/'result.jsonl'
        output.symlink_to(target)
        self.assertFalse(output.exists())
        self.assertTrue(output.is_symlink())
        self.assertEqual(self.original_module.protect_output(str(output)), [])
        self.assertTrue(self.module.protect_output(str(output)))
        self.assertTrue(output.is_symlink())
        self.assertEqual(output.readlink(), target)
        self.assertFalse(target.exists())

    def test_existing_file_and_directory_are_refused_and_preserved(self):
        output = self.folder/'existing.jsonl'
        output.write_bytes(b'original historical bytes\n')
        self.assertTrue(self.module.protect_output(str(output)))
        self.assertEqual(output.read_bytes(), b'original historical bytes\n')
        self.assertTrue(self.module.protect_output(str(self.folder)))

    def test_unused_path_remains_allowed_without_creating_it(self):
        output = self.folder/'new.jsonl'
        self.assertEqual(self.module.protect_output(str(output)), [])
        self.assertFalse(output.exists())
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_empty_path_and_missing_parent_are_refused_without_writes(self):
        self.assertTrue(self.module.protect_output(''))
        self.assertTrue(self.module.protect_output(str(self.folder/'missing'/'result.jsonl')))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_request_refuses_symlink_before_any_execution_side_effect(self):
        output = self.folder/'result.jsonl'
        output.symlink_to(self.folder/'not-created')
        request = self.module.RunRequest(mode='offline', splits=['dev'], tiers=[1],
                                         output_paths=[str(output)])
        problems = self.module.check_run_request(request)
        self.assertEqual(len(problems), 1)
        self.assertIn('output already exists', problems[0])
        self.assertEqual([p.name for p in self.folder.iterdir()], ['result.jsonl'])
        self.assertEqual(SOURCE.read_bytes(), self.production)


if __name__ == '__main__':
    unittest.main()
