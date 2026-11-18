"""WP7 real offline integration and fixed pre-WP7 integrity pins; no live evaluation."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import copy
import errno
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from eval.runner_preparation import offline, artifacts, provenance
from eval.runner_preparation.selection import select_scorer
from eval.scoring_v2 import rescore as wp6
from eval.framework.integrity import dataset_hash
from eval.phase35.run_eval import score_generic
from test_stage9_v2_integrity import PROTECTED, MANIFEST_PIN
ROOT=Path(__file__).resolve().parent
# Raw bytes captured before WP7 implementation, embedded permanently; no /tmp dependency.
WP6_PINS={'docs/remediation/phase_e2_engineering/WP6_IMPLEMENTATION_REPORT.md': '0c623f85bf863753c1578d3c6f92f030a70b593121a149629faff05a41991e5a',
 'docs/remediation/phase_e2_engineering/WP7_WP8_DEPENDENCIES.md': '329285156c5b2409af27645bf8b8a83e95bfa040720d885c9eb0b4742a310206',
 'eval/probes/probes_e2.py': 'f018ee5dc2dcbc67353cce96473aaa65115b764f5ed306ab8698c16d19ec2f06',
 'eval/probes/probes_phase_d.py': '55ec78aab5c3ab6a1c009362350fe145044cc7b405374c572f18e080a4caef37',
 'eval/probes/schema.py': '6958bb714d9a38ec08b95ddbb9b2d585e3034b1f93689b4f86e9f4dd4643bae0',
 'eval/probes/scorer_regression.py': '051e27372e3ba843557f997fed0fd67e6d05f685265116353426654595eeb6a0',
 'eval/probes/v2_spec_fixtures.py': '501d8ebfb33b3ba7294054d7d8bd7f8424a9ef13ef71b5ecac678ef029e65998',
 'eval/scoring_v2/__init__.py': '748d800afa0cc46e46fd83d32840c0342fd6d409f3b9d0870c2e095879a65c98',
 'eval/scoring_v2/annotations.json': 'd3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0',
 'eval/scoring_v2/annotations.py': '37d5be1ce4cc9814d47a2dfdb3f54d02534f71eed46d5a59f045088df07e75e5',
 'eval/scoring_v2/context.py': 'b0cee83e9bf4266b9146fbb557b1f0ff53cc0708488ed5d5539f36015658e229',
 'eval/scoring_v2/forbidden.py': '342161b3d80070f3ec7ac4d670aa7a0dae6b630fe1da22827ecaf056f5c5c74e',
 'eval/scoring_v2/history.py': '6cc63e382b6cc50ca965c07c95cf9602926261d63698fc1217b08cad19f5efea',
 'eval/scoring_v2/negation.py': '01b7fed46ba484f5e84ba036903a423db7a5e82c4f9dfe51c13691d166a40bcc',
 'eval/scoring_v2/normalize.py': 'c91248a2b8ae36699d416a6ff655c53136626c89430ab8dec0ce844431846daf',
 'eval/scoring_v2/numbers.py': '4d03be838f5f5f2c33583e6c8abb7ff27a98268b46621ede5ffb525f0af805c9',
 'eval/scoring_v2/rescore.py': '3764685b399a99b9c85e72bf53cc55c44a54910d3baf3ab253bc6af2e256fd30',
 'eval/scoring_v2/rescore_meta.py': '13f3552004dfe17d9da7f92f4437d1ada64bdebd7130b8109a19c8196d0dc97c',
 'eval/scoring_v2/score.py': 'd5ab048df410865041d7c1d21295289d31ec553e1ecc9b26c8b68698e1f611e4',
 'eval/scoring_v2/signals.py': '1eb406fdc95651287f1ec1e581bff600611be04d4bb495717dff77588e6d4818',
 'eval/scoring_v2/tables.py': '882d9932ecb034005d71241f66751f4b6777e9b75cee6a2b06f2120183e6a761',
 'eval/scoring_v2/text_units.py': '25463d90407a019f8712e8d1b944654deff9d0859f6789eb4d2e4c8e4c61dcb5',
 'test_stage9_scorer_probes.py': '27c12a9f745d71fad8b3639d8cd1d007aa625e13aaa17cb25b2be4d2372765f2',
 'test_stage9_scoring_v2.py': '7a39ae75d12699ddf8d158f10788c329e4a52847ea233da41588f9ac8757654f',
 'test_stage9_v2_integrity.py': '20665e155d864df00422fbf5e605c09062d6ea8ad0cfe98c6585418f2a220607',
 'test_stage9_v2_runner.py': 'ea96e10472de5b51fd5dbbb08cee53c72271dba0aaab92e5337760e5a964520f'}


# Authorized 2026-11-18 input-boundary corrections; historical WP6 pins above
# remain recorded. Frozen/protected assets retain their original pins.
WP6_PINS.update({
 'eval/scoring_v2/context.py': '8cf10a44f56be9b29b83f3aa30730c3f14daa40d112f700ca6aaf8c47f97c7cb',
 'eval/scoring_v2/rescore.py': '481cbc9f86337ba7d0ce18189c7a94170f4f32fde8d630a3edd82e19517b0f99',
})


def digest(data): return hashlib.sha256(data).hexdigest()


class WP7IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,cls.pin=wp6.load_pinned_dataset(ROOT,'c1bbcae')
        cls.annotation={'schema':'phase35-scorer-annotations/1','dataset_version':'historical-dev-diagnostic',
            'dataset_sha256':dataset_hash(cls.cases),'cases':{
                c['id']:{'forbidden':[{'text':t,'kind':'literal','source':'dataset'} for t in c['forbidden']]}
                for c in cls.cases}}

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/private/tmp');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name).resolve();self.root=self.folder/'outputs'
        self.source=self.folder/'source.jsonl';self.ann=self.folder/'annotations.json'
        self.source.write_bytes((ROOT/'eval/phase35/results/tier1_dev.jsonl').read_bytes())
        self.ann.write_text(json.dumps(self.annotation))

    def prepare(self,run_id='integration',tier=1,**options):
        kw=dict(tier=tier,scorer_version='2.1.0',dataset_rev='c1bbcae',chunk_config='100,20,words' if tier==2 else None)
        kw.update(options)
        return offline.prepare_comparison(self.source,self.ann,self.root,run_id,**kw)

    def assert_bundle(self,final,tier,count):
        self.assertEqual(final.parent,self.root/'development-comparisons/scorer-2.1.0')
        manifest=json.loads((final/'artifact-manifest.json').read_text())
        complete=json.loads((final/'COMPLETED.json').read_text())
        self.assertEqual(complete['manifest_sha256'],digest((final/'artifact-manifest.json').read_bytes()))
        self.assertFalse(complete['acceptance_eligible']);self.assertTrue(manifest['development_only'])
        self.assertEqual(set(manifest['files']),artifacts.REQUIRED_FILES)
        for name,record in manifest['files'].items():
            data=(final/name).read_bytes();self.assertEqual(record,{'sha256':digest(data),'bytes':len(data)})
        rows=[json.loads(line) for line in (final/'comparison.v2.jsonl').read_text().splitlines()]
        side=json.loads((final/'comparison.v2.jsonl.scoring.json').read_text())
        proof=json.loads((final/'provenance.json').read_text())
        self.assertEqual(len(rows),count);self.assertEqual(side['counts']['exact'],count)
        self.assertEqual(side['counts']['drift'],0);self.assertFalse(side['acceptance_eligible'])
        self.assertEqual(side['scorer']['version'],'2.1.0');self.assertEqual(proof['scorer'],side['scorer'])
        self.assertEqual(proof['source_sha256'],digest(self.source.read_bytes()))
        self.assertEqual(proof['annotations_sha256'],digest(self.ann.read_bytes()))
        self.assertEqual(proof,provenance.validate_comparison_inputs(self.source.read_bytes(),self.ann.read_bytes(),side,rows))
        self.assertEqual(proof['dataset_pin']['pin_source'],'operator_git_rev')
        self.assertTrue(all(r['tier']==tier and r['split']=='dev' and r['reconstruction_status']=='exact' for r in rows))
        self.assertTrue(all(r['v1_stored']==r['v1_current'] for r in rows))
        return rows,side,proof

    def test_native_pinned_historical_dev_bundles_47_and_42_zero_drift(self):
        before={p:digest(p.read_bytes()) for p in [self.source,self.ann]}
        self.assert_bundle(self.prepare('tier1'),1,47)
        self.assertEqual(before,{p:digest(p.read_bytes()) for p in before})
        self.source.write_bytes((ROOT/'eval/phase35/results/tier2_dev.jsonl').read_bytes())
        before={p:digest(p.read_bytes()) for p in [self.source,self.ann]}
        rows,side,_=self.assert_bundle(self.prepare('tier2',tier=2),2,42)
        self.assertEqual(side['context_config']['tier2']['chunk_count'],135)
        self.assertEqual(before,{p:digest(p.read_bytes()) for p in before})

    def test_reproducible_scores_hashes_and_isolated_run_namespaces(self):
        first=self.prepare('first');second=self.prepare('second')
        self.assertNotEqual(first,second)
        self.assertEqual((first/'comparison.v2.jsonl').read_bytes(),(second/'comparison.v2.jsonl').read_bytes())
        a=json.loads((first/'comparison.v2.jsonl.scoring.json').read_text());b=json.loads((second/'comparison.v2.jsonl.scoring.json').read_text())
        a.pop('generated_at_utc');b.pop('generated_at_utc');self.assertEqual(a,b)
        self.assertEqual((first/'provenance.json').read_bytes(),(second/'provenance.json').read_bytes())
        snapshot={p.name:p.read_bytes() for p in first.iterdir()}
        with self.assertRaises(FileExistsError): self.prepare('first')
        self.assertEqual(snapshot,{p.name:p.read_bytes() for p in first.iterdir()})

    def test_mutating_source_or_annotations_before_publication_cannot_complete(self):
        original=wp6.rescore
        for target in [self.source,self.ann]:
            original_bytes=target.read_bytes()
            def mutate(args):
                side=original(args);target.write_bytes(original_bytes+b'\n');return side
            with self.subTest(target=target.name),patch.object(wp6,'rescore',side_effect=mutate),self.assertRaises(ValueError):
                self.prepare('mutated')
            self.assertFalse(list(self.root.rglob('COMPLETED.json')))
            target.write_bytes(original_bytes)
        self.assert_bundle(self.prepare('mutated'),1,47)

    def test_native_publish_failure_and_builder_failure_allow_safe_retry(self):
        original=wp6.rescore
        def builder_fail(args): original(args);raise RuntimeError('injected after scoring writes')
        with patch.object(wp6,'rescore',side_effect=builder_fail),self.assertRaises(RuntimeError): self.prepare('retry')
        self.assertFalse(list(self.root.rglob('COMPLETED.json')))
        with patch.object(artifacts,'_rename_exclusive',side_effect=OSError(errno.EIO,'injected native publish failure')),self.assertRaises(OSError):
            self.prepare('retry')
        self.assertFalse(list(self.root.rglob('COMPLETED.json')))
        self.assertEqual(list((self.root/'development-comparisons/scorer-2.1.0').iterdir()),[])
        self.assert_bundle(self.prepare('retry'),1,47)

    def test_inconsistent_missing_and_duplicate_context_refuse_completion(self):
        row=json.loads(self.source.read_text().splitlines()[0])
        for mutate in [lambda r:r.pop('context'),lambda r:r['context'].append(copy.deepcopy(r['context'][0])),
                       lambda r:r['context'][0].update(page=999),lambda r:r['citations'].append({'chunk_id':999,'document':'missing','page':1})]:
            bad=copy.deepcopy(row);mutate(bad);self.source.write_text(json.dumps(bad)+'\n')
            with self.subTest(row=bad),self.assertRaises(ValueError): self.prepare('bad-ref')
            self.assertFalse(list(self.root.rglob('COMPLETED.json')))

    def test_v1_identity_and_explicit_v2_development_selection(self):
        self.assertIs(select_scorer(),score_generic)
        for kw in [{},{'development':True},{'annotations':self.annotation}]:
            with self.subTest(options=kw),self.assertRaises(ValueError): select_scorer('2.1.0',**kw)
        bound=select_scorer('2.1.0',development=True,annotations=self.annotation)
        self.assertTrue(callable(bound));self.assertIs(select_scorer('v1'),score_generic)
        for split in ['heldout','all']:
            with self.subTest(split=split),self.assertRaises(ValueError): self.prepare(split=split)
        for flag in ['--acceptance','--allow-page-superset','--split=heldout','--split=all']:
            argv=['--results',str(self.source),'--annotations',str(self.ann),'--tier','1','--scorer-version','2.1.0',
                  '--dataset-rev','c1bbcae','--output-root',str(self.root),'--run-id','cli',flag]
            with self.subTest(flag=flag),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised: offline.main(argv)
            self.assertEqual(raised.exception.code,2)
        self.assertFalse(self.root.exists())

    def test_tier2_missing_duplicate_and_misowned_refs_never_complete(self):
        row=json.loads((ROOT/'eval/phase35/results/tier2_dev.jsonl').read_text().splitlines()[0])
        self.assertTrue(row['retrieved'])
        for mutate in [lambda r:r.pop('retrieved'),lambda r:r['retrieved'].append(copy.deepcopy(r['retrieved'][0])),
                       lambda r:r['retrieved'][0].update(document_name='unrelated.pdf')]:
            bad=copy.deepcopy(row);mutate(bad);self.source.write_text(json.dumps(bad)+'\n')
            with self.subTest(retrieved=bad.get('retrieved')),self.assertRaises(ValueError): self.prepare('tier2-bad-ref',tier=2)
            self.assertFalse(list(self.root.rglob('COMPLETED.json')))

    def test_duplicate_json_and_malformed_header_provenance_never_complete(self):
        original_source,original_ann=self.source.read_bytes(),self.ann.read_bytes()
        first=json.loads(original_source.splitlines()[0])
        duplicate_source=(json.dumps(first)[:-1]+',"id":'+json.dumps(first['id'])+'}\n').encode()
        duplicate_ann=(json.dumps(self.annotation)[:-1]+',"dataset_version":"historical-dev-diagnostic"}').encode()
        for source_bytes,annotation_bytes in [(duplicate_source,original_ann),(original_source,duplicate_ann)]:
            self.source.write_bytes(source_bytes);self.ann.write_bytes(annotation_bytes)
            with self.subTest(duplicate='source' if source_bytes!=original_source else 'annotations'),self.assertRaises(ValueError): self.prepare('duplicate-json')
            self.assertFalse(list(self.root.rglob('COMPLETED.json')))
        self.source.write_bytes(original_source);self.ann.write_bytes(original_ann)
        header=self.folder/'header.json'
        for value in [None,[],['bad'],True,{'git_head':'c1bbcae','file_sha256':None},{'git_head':123}]:
            header.write_text(json.dumps(value))
            with self.subTest(header=value),self.assertRaises(ValueError): self.prepare('bad-header',dataset_rev=None,run_header=header)
            self.assertFalse(list(self.root.rglob('COMPLETED.json')))

    def test_existing_wp6_and_44_protected_files_are_byte_identical(self):
        for path,expected in dict(PROTECTED,**WP6_PINS).items():
            with self.subTest(path=path): self.assertEqual(digest((ROOT/path).read_bytes()),expected)
        manifest=json.loads((ROOT/'eval/phase35/frozen_manifest.json').read_text())
        self.assertEqual(manifest['content_sha256'],MANIFEST_PIN)
        from eval.answer_scoring import INSUFFICIENCY_PHRASES,DISAGREEMENT_PHRASES
        self.assertEqual(INSUFFICIENCY_PHRASES,["couldn't find","could not find","can't find","cannot find","not enough information",
            "insufficient information","does not contain","doesn't contain","do not contain","no information","not available",
            "cannot answer","can't answer","unable to answer","not mentioned","not specified","not provided","not stated",
            "isn't mentioned","is not included","not covered","no mention"])
        self.assertEqual(DISAGREEMENT_PHRASES,['differ','conflict','disagree','inconsistent','however','whereas','while'])

    def test_fresh_import_no_io_and_offline_tier2_only_pure_chunker(self):
        self.source.write_bytes((ROOT/'eval/phase35/results/tier2_dev.jsonl').read_bytes())
        code="""import builtins,sys,socket
original_import=builtins.__import__;original_open=builtins.open;offline_stage=False
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden'))
def guarded(name,*a,**kw):
 if name=='services' or name.startswith('services.'):
  if not offline_stage or name not in ('services','services.chunker'): raise AssertionError('service import '+name)
 return original_import(name,*a,**kw)
builtins.__import__=guarded
from eval.phase35.run_eval import score_generic
# Warm frozen v1 third-party imports before testing the NEW namespace's I/O.
# macOS sysconfig reads SystemVersion.plist during psycopg initialization.
builtins.open=lambda *a,**k: (_ for _ in ()).throw(AssertionError('import file I/O'))
from eval.runner_preparation import offline
from eval.runner_preparation.selection import select_scorer
assert select_scorer() is score_generic
assert not any(x=='services' or x.startswith('services.') for x in sys.modules)
builtins.open=original_open;offline_stage=True
final=offline.prepare_comparison(sys.argv[1],sys.argv[2],sys.argv[3],'fresh-tier2',tier=2,scorer_version='2.1.0',dataset_rev='c1bbcae',chunk_config='100,20,words')
assert (final/'COMPLETED.json').is_file()
assert {x for x in sys.modules if x=='services' or x.startswith('services.')} <= {'services','services.chunker'}
"""
        done=subprocess.run([sys.executable,'-B','-c',code,str(self.source),str(self.ann),str(self.root)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)


if __name__=='__main__': unittest.main()
