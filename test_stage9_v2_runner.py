"""Offline reconstruction and opt-in runner regression tests; no live evaluation."""
import testsafe
testsafe.require_scratch_db()
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from eval.framework.integrity import dataset_hash
from eval.scoring_v2 import context
from eval.scoring_v2 import rescore as runner
from eval.scoring_v2.rescore_meta import scorer_identity

ROOT = Path(__file__).resolve().parent


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs, cls.cases, cls.pin = runner.load_pinned_dataset(ROOT, 'c1bbcae')

    def args(self, folder, tier=1, **kwargs):
        annotation = {'schema':'phase35-scorer-annotations/1','dataset_version':'synthetic-test-pin',
                      'dataset_sha256':dataset_hash(self.cases),'cases':{
                          c['id']:{'forbidden':[dict(text=f,kind='literal',source='dataset') for f in c['forbidden']]}
                          for c in self.cases}}
        path = folder/'annotations.json'
        path.write_text(json.dumps(annotation))
        args = argparse.Namespace(results=str(ROOT/f'eval/phase35/results/tier{tier}_dev.jsonl'),
            tier=tier,run_header=None,dataset_rev='c1bbcae',chunk_config='100,20,words' if tier==2 else None,
            annotations=str(path),output=str(folder/'output.v2.jsonl'),acceptance=False,allow_page_superset=False)
        for key,value in kwargs.items():
            setattr(args,key,value)
        return args

    def test_dataset_pin_required(self):
        with self.assertRaises(runner.RescoreError) as raised:
            runner.load_pinned_dataset(ROOT)
        self.assertEqual(raised.exception.code,5)

    def test_pin_is_full_commit_with_all_module_hashes(self):
        self.assertTrue(self.pin['git_rev'].startswith('c1bbcae'))
        self.assertEqual(len(self.pin['git_rev']),40)
        self.assertEqual(set(self.pin['file_sha256']),set(runner.DATA_FILES))
        self.assertEqual(self.pin['pin_source'],'operator_git_rev')

    def test_header_dataset_hash_mismatch(self):
        header = dict(git_head='c1bbcae',dataset_version='test',dataset_manifest_content_sha256='0'*64,
                      file_sha256={name:'0'*64 for name in runner.DATA_FILES})
        with self.assertRaises(runner.RescoreError) as raised:
            runner.load_pinned_dataset(ROOT,header=header)
        self.assertEqual(raised.exception.code,5)

    def test_tier1_all_stored_dev_contexts_exact(self):
        rows = [json.loads(line) for line in (ROOT/'eval/phase35/results/tier1_dev.jsonl').read_text().splitlines()]
        by_id = {c['id']:c for c in self.cases}
        self.assertEqual(len(rows),47)
        for row in rows:
            with self.subTest(case=row['id']):
                _,_,text,status,_ = context.verify_tier1(row,by_id[row['id']],self.docs)
                self.assertEqual(status,'exact')
                self.assertIsInstance(text,str)

    def test_tier1_modified_ref_fails_closed(self):
        row = json.loads((ROOT/'eval/phase35/results/tier1_dev.jsonl').read_text().splitlines()[0])
        case = next(c for c in self.cases if c['id']==row['id'])
        row['context'][0]['page'] += 1
        _,_,text,status,mode = context.verify_tier1(row,case,self.docs)
        self.assertIsNone(text)
        self.assertEqual(status,'mismatch:order_or_ref')
        self.assertEqual(mode,'unavailable_mismatch')

    def test_context_hash_proof_checked(self):
        row = json.loads((ROOT/'eval/phase35/results/tier1_dev.jsonl').read_text().splitlines()[0])
        case = next(c for c in self.cases if c['id']==row['id'])
        row['context_sha256']='0'*64
        self.assertEqual(context.verify_tier1(row,case,self.docs)[3],'mismatch:context_sha256')

    def test_pipeline_pin_refuses_changed_minimum(self):
        original = Path.read_bytes
        def altered(path):
            data = original(path)
            return data.replace(b'MIN_PAGE_WORDS = 10',b'MIN_PAGE_WORDS = 5') if path.name=='ingestion_service.py' else data
        with patch.object(Path,'read_bytes',altered):
            with self.assertRaises(runner.RescoreError) as raised:
                runner.pipeline_metadata(ROOT)
        self.assertEqual(raised.exception.code,6)

    def test_scorer_hash_portable_and_content_sensitive(self):
        first = scorer_identity({'eval/scoring_v2/a.py':b'a\nb\n'},b'{}\n')
        second = scorer_identity({'eval/scoring_v2/a.py':b'a\r\nb\r\n'},b'{}\r\n')
        self.assertEqual(first,second)
        self.assertNotEqual(first['sha256'],scorer_identity({'eval/scoring_v2/a.py':b'a\nc\n'},b'{}\n')['sha256'])

    def test_invalid_config(self):
        for cfg in ('0,0,words','100,100,words','100,-1,words','100,20,other','nope'):
            with self.subTest(config=cfg),self.assertRaises(runner.RescoreError):
                runner.parse_config(cfg)

    def test_missing_pin_cli_exit5_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp),dataset_rev=None)
            with self.assertRaises(runner.RescoreError) as raised:
                runner.rescore(args)
            self.assertEqual(raised.exception.code,5)
            self.assertFalse(Path(args.output).exists())

    def test_invalid_annotations_exit7(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            Path(args.annotations).write_text('{}')
            with self.assertRaises(runner.RescoreError) as raised:
                runner.rescore(args)
            self.assertEqual(raised.exception.code,7)
            self.assertFalse(Path(args.output).exists())

    def test_offline_tier1_three_way_drift_zero_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp))
            before = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
            sidecar = runner.rescore(args)
            self.assertEqual(sidecar['counts']['exact'],47)
            self.assertEqual(sidecar['counts']['drift'],0)
            self.assertFalse(sidecar['acceptance_eligible'])
            self.assertEqual(before,hashlib.sha256(Path(args.results).read_bytes()).hexdigest())
            self.assertEqual(len(Path(args.output).read_text().splitlines()),47)
            self.assertTrue(Path(args.output+'.scoring.json').exists())
            self.assertTrue(Path(args.output).with_suffix('.diff.md').exists())
            with self.assertRaises(FileExistsError):
                runner.rescore(args)

    def test_acceptance_without_frozen_identity_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.args(Path(tmp),acceptance=True)
            with self.assertRaises(runner.RescoreError) as raised:
                runner.rescore(args)
            self.assertEqual(raised.exception.code,2)
            self.assertFalse(Path(args.output).exists())

    def test_reconstruction_mismatch_acceptance_exit4_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            args=self.args(folder,acceptance=True)
            rows=[json.loads(line) for line in Path(args.results).read_text().splitlines()]
            rows[0]['context'][0]['page'] += 1
            path=folder/'bad.jsonl'; path.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            args.results=str(path)
            with self.assertRaises(runner.RescoreError) as raised:
                runner.rescore(args)
            self.assertEqual(raised.exception.code,4)
            self.assertFalse(Path(args.output).exists())

    def test_tier2_chunks_exact_and_stored_current_scores_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.args(Path(tmp),tier=2)
            sidecar=runner.rescore(args)
            self.assertEqual(sidecar['context_config']['tier2']['chunk_count'],135)
            self.assertEqual(sidecar['counts']['exact'],42)
            self.assertEqual(sidecar['counts']['drift'],0)
            self.assertFalse(sidecar['acceptance_eligible'])


    def test_drift_acceptance_exit8_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); args=self.args(folder,acceptance=True)
            rows=[json.loads(line) for line in Path(args.results).read_text().splitlines()]
            rows[0]['score']['correct']=not rows[0]['score']['correct']
            args.results=str(folder/'drift.jsonl')
            Path(args.results).write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            with self.assertRaises(runner.RescoreError) as raised:
                runner.rescore(args)
            self.assertEqual(raised.exception.code,8)
            self.assertFalse(Path(args.output).exists())

    def test_sidecar_collision_leaves_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.args(Path(tmp)); side=Path(args.output+'.scoring.json')
            side.write_text('existing')
            with self.assertRaises(FileExistsError):
                runner.rescore(args)
            self.assertEqual(side.read_text(),'existing')
            self.assertFalse(Path(args.output).exists())

    def test_error_row_skips_context_and_has_canonical_v1_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); args=self.args(folder)
            row=json.loads(Path(args.results).read_text().splitlines()[0])
            row.update(status='error',answer='RUNNER ERROR: synthetic',citations=[])
            row.pop('context')
            row['score']=dict(correct=False,correct_lenient=False,unsupported=False,citation_correctness=0.0,
                citation_completeness=0.0,fabricated=0,abstain_ok=None,fact_recall=0.0,forbidden_hits=[],
                ungrounded_numbers=[],partial_ok=None,conflict_ok=None,status='error')
            args.results=str(folder/'error.jsonl'); Path(args.results).write_text(json.dumps(row)+'\n')
            sidecar=runner.rescore(args)
            result=json.loads(Path(args.output).read_text())
            self.assertEqual(result['context_mode'],'unavailable_error_row')
            self.assertEqual(sidecar['counts']['error_row'],1)
            self.assertEqual(sidecar['counts']['drift'],0)
            self.assertFalse(sidecar['acceptance_eligible'])

    def test_non_dev_rows_rejected(self):
        rows=json.loads((ROOT/'eval/phase35/results/tier1_dev.jsonl').read_text().splitlines()[0])
        rows['split']='heldout'
        with self.assertRaises(runner.RescoreError):
            runner.read_rows(json.dumps(rows).encode(),1,self.cases)

    def test_tier2_page_superset_is_never_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); args=self.args(folder,tier=2,chunk_config='120,20,words',allow_page_superset=True)
            sidecar=runner.rescore(args)
            self.assertGreater(sidecar['counts']['fallback'],0)
            self.assertFalse(sidecar['acceptance_eligible'])
            rows=[json.loads(line) for line in Path(args.output).read_text().splitlines()]
            for row in rows:
                if row['reconstruction_status'].startswith('mismatch'):
                    self.assertEqual(row['context_mode'],'tier2_page_superset_NON_ACCEPTANCE')


    def test_header_is_independently_bound_to_pinned_manifest(self):
        manifest=json.loads((ROOT/'eval/phase35/frozen_manifest.json').read_text())
        dataset=manifest['content']['dataset']
        header=dict(git_head='HEAD',dataset_version=dataset['dataset_version'],
                    dataset_manifest_content_sha256=manifest['content_sha256'],file_sha256=dataset['file_sha256'])
        _,_,pin=runner.load_pinned_dataset(ROOT,header=header)
        self.assertEqual(pin['pin_source'],'run_header')
        for field in ('dataset_version','dataset_manifest_content_sha256'):
            bad=dict(header);bad[field]='forged'
            with self.subTest(field=field),self.assertRaises(runner.RescoreError) as raised:
                runner.load_pinned_dataset(ROOT,header=bad)
            self.assertEqual(raised.exception.code,5)

    def test_old_revision_without_manifest_cannot_claim_header_pin(self):
        header=dict(git_head='c1bbcae',dataset_version='historical',dataset_manifest_content_sha256='0'*64,
                    file_sha256=self.pin['file_sha256'])
        with self.assertRaises(runner.RescoreError) as raised:
            runner.load_pinned_dataset(ROOT,header=header)
        self.assertEqual(raised.exception.code,5)


if __name__=='__main__':
    unittest.main()
