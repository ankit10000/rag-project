"""Deterministic exclusive development-bundle publication and failure injection."""
import testsafe
testsafe.require_scratch_db()
import concurrent.futures
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from eval.runner_preparation import artifacts as A


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def build(self, stage):
        for name in A.REQUIRED_FILES:
            (stage/name).write_text(name+'\n', encoding='utf-8')

    def publish(self, run='run1', build=None):
        return A.publish_bundle(self.root, run, scorer_version='2.1.0', build_fn=build or self.build)

    def namespace(self):
        return self.root/'development-comparisons'/'scorer-2.1.0'

    def test_complete_versioned_manifest_and_hashes(self):
        final = self.publish()
        self.assertEqual(final, self.namespace()/'run1')
        manifest = A.verify_bundle(final)
        self.assertEqual(manifest['scorer_version'], '2.1.0')
        self.assertFalse(manifest['acceptance_eligible'])
        self.assertEqual(set(manifest['files']), A.REQUIRED_FILES)
        for name, record in manifest['files'].items():
            self.assertEqual(record['sha256'], hashlib.sha256((final/name).read_bytes()).hexdigest())
        self.assertFalse(any(p.name.startswith('.') for p in self.namespace().iterdir()))

    def test_repeated_same_id_refused_without_builder_or_mutation(self):
        final = self.publish(); before = {p.name:p.read_bytes() for p in final.iterdir()}
        with self.assertRaises(FileExistsError):
            self.publish(build=lambda p: self.fail('builder ran on existing ID'))
        self.assertEqual(before, {p.name:p.read_bytes() for p in final.iterdir()})

    def test_different_ids_have_reproducible_content(self):
        first = self.publish('first'); second = self.publish('second')
        self.assertEqual({p.name:p.read_bytes() for p in first.iterdir()}, {p.name:p.read_bytes() for p in second.iterdir()})

    def test_build_partial_failure_safe_retry_and_no_completed_final(self):
        def fail(stage):
            (stage/'comparison.v2.jsonl').write_text('partial')
            raise RuntimeError('injected builder failure')
        with self.assertRaises(RuntimeError): self.publish(build=fail)
        self.assertEqual(list(self.namespace().iterdir()), [])
        A.verify_bundle(self.publish())

    def test_metadata_write_and_precommit_fsync_failure_cleanup(self):
        for target in ('_write_exclusive', 'fsync'):
            with self.subTest(target=target):
                owner = A.os if target == 'fsync' else A
                with patch.object(owner, target, side_effect=OSError(errno.EIO,'injected failure')):
                    with self.assertRaises(OSError): self.publish()
                self.assertEqual(list(self.namespace().iterdir()), [])
        A.verify_bundle(self.publish())

    def test_publish_failure_preserves_foreign_target(self):
        foreign = self.namespace()/'run1'
        def collide(parent, source, target):
            foreign.mkdir()
            (foreign/'foreign.txt').write_text('keep')
            raise FileExistsError('injected publish collision')
        with patch.object(A,'_rename_exclusive', side_effect=collide):
            with self.assertRaises(FileExistsError): self.publish()
        self.assertEqual((foreign/'foreign.txt').read_text(), 'keep')
        self.assertEqual([p.name for p in self.namespace().iterdir()], ['run1'])

    def test_native_no_replace_rejects_empty_directory_race(self):
        native = A._rename_exclusive
        def collide(parent, source, target):
            (self.namespace()/target).mkdir()
            native(parent,source,target)
        with patch.object(A,'_rename_exclusive', side_effect=collide):
            with self.assertRaises(FileExistsError): self.publish()
        self.assertEqual(list((self.namespace()/'run1').iterdir()), [])

    def test_concurrent_claim_exactly_one_builder(self):
        entered = threading.Event(); release = threading.Event(); calls=[]
        def build(stage):
            calls.append(stage); entered.set()
            self.assertTrue(release.wait(3)); self.build(stage)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.publish, build=build)
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.publish, build=build)
            with self.assertRaises(FileExistsError): second.result(timeout=3)
            release.set(); A.verify_bundle(first.result(timeout=3))
        self.assertEqual(len(calls),1)

    def test_claim_crash_leftover_is_never_stolen(self):
        ns = self.namespace(); ns.mkdir(parents=True)
        claim = ns/'.run1.claim'; claim.mkdir(); (claim/'owner').write_text('foreign')
        with self.assertRaises(FileExistsError): self.publish()
        self.assertEqual((claim/'owner').read_text(),'foreign')

    def test_identifiers_and_official_results_root_rejected(self):
        for value in ('', '../run', '.', '/tmp/run', 'a/b', 'a.b', 'a'*81):
            with self.subTest(value=value), self.assertRaises(ValueError): self.publish(value)
        with self.assertRaises(ValueError):
            A.publish_bundle(A._OFFICIAL, 'run', scorer_version='2.1.0', build_fn=self.build)
        with self.assertRaises(ValueError):
            A.publish_bundle(self.root, 'run', scorer_version='../2.1', build_fn=self.build)

    def test_symlink_parents_and_dangling_target_refused(self):
        real = self.root/'real'; real.mkdir()
        linked = self.root/'linked'; linked.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            A.publish_bundle(linked,'run',scorer_version='2.1.0',build_fn=self.build)
        ns = self.namespace(); ns.mkdir(parents=True)
        target=ns/'run1'; target.symlink_to(self.root/'missing')
        with self.assertRaises(FileExistsError): self.publish()
        self.assertTrue(target.is_symlink())

    def test_builder_symlink_hardlink_reserved_and_missing_files_rejected(self):
        source=self.root/'source'; source.write_text('preserve')
        for mode in ('symlink','hardlink','reserved','missing','directory'):
            def build(stage):
                self.build(stage); target=stage/'comparison.v2.jsonl'
                if mode=='reserved': (stage/A.COMPLETED).write_text('{}')
                else:
                    target.unlink()
                    if mode=='symlink': target.symlink_to(source)
                    elif mode=='hardlink': os.link(source,target)
                    elif mode=='directory': target.mkdir()
            with self.subTest(mode=mode), self.assertRaises((OSError,ValueError)):
                self.publish(build=build)
            self.assertEqual(source.read_text(),'preserve')
            self.assertEqual(list(self.namespace().iterdir()), [])

    def test_tamper_invalidates_completion(self):
        final=self.publish(); (final/'provenance.json').write_text('tampered')
        with self.assertRaises(ValueError): A.verify_bundle(final)

    def test_cleanup_never_deletes_replaced_staging_directory(self):
        moved=[]
        def build(stage):
            self.build(stage); owned=stage.with_name(stage.name+'-owned'); stage.rename(owned)
            stage.mkdir(); (stage/'foreign.txt').write_text('preserve'); moved.append((stage,owned))
        with self.assertRaises(ValueError): self.publish(build=build)
        stage,owned=moved[0]
        self.assertEqual((stage/'foreign.txt').read_text(),'preserve')
        self.assertTrue(owned.exists())

    def test_unsupported_platform_refuses_without_unsafe_rename(self):
        class NoNativeRename:
            pass
        with patch.object(A.ctypes, 'CDLL', return_value=NoNativeRename()):
            with self.assertRaises(NotImplementedError): self.publish()
        self.assertEqual(list(self.namespace().iterdir()), [])

    def test_reader_rejects_nonobject_or_special_metadata(self):
        final=self.publish()
        (final/A.COMPLETED).write_text('[]')
        with self.assertRaises(ValueError): A.verify_bundle(final)
        (final/A.COMPLETED).unlink(); os.mkfifo(final/A.COMPLETED)
        with self.assertRaises(ValueError): A.verify_bundle(final)

    def test_postcommit_fsync_failure_reports_existing_valid_bundle(self):
        native=A._rename_exclusive
        def committed(parent,source,target):
            native(parent,source,target)
            A.os.fsync=fail
        def fail(fd): raise OSError(errno.EIO,'postcommit failure')
        original=A.os.fsync
        try:
            with patch.object(A,'_rename_exclusive',side_effect=committed):
                with self.assertRaises(A.PublicationDurabilityError) as error: self.publish()
        finally: A.os.fsync=original
        A.verify_bundle(error.exception.path)
        with self.assertRaises(FileExistsError): self.publish()


if __name__ == '__main__': unittest.main()
