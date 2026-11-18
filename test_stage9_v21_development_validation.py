"""Full dev-output behavioral replay, separated from historical source identity.

No held-out scoring, provider calls or database connections. Archived comparisons
are evidence only: matching results under changed source is behavioral parity,
not reproduction of the archived scorer's implementation identity.
"""
import testsafe
testsafe.require_scratch_db()
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from eval.scoring_v2 import context,score_case,validate_annotations
from eval.scoring_v2 import rescore
from eval.scoring_v2.rescore_meta import scorer_identity
from eval.phase35.run_eval import score_generic
from eval.runner_preparation.offline import prepare_comparison
from eval.runner_preparation.provenance import verify_reconstruction

ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT/'docs/remediation/phase_e2_engineering/wp8_evidence/flip_inputs/final'
REV='c1bbcae9a21e389c16c3f1587de5acc1b5209e37'


def load_rows(path): return [json.loads(line) for line in path.read_text().splitlines()]


def pinned_chunker():
    blob=subprocess.check_output(['git','show',f'{REV}:services/chunker.py'],cwd=ROOT)
    namespace={};exec(compile(blob,'pinned-pure-chunker','exec'),namespace)
    return namespace['chunk_page']


class DevelopmentValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,cls.pin=rescore.load_pinned_dataset(ROOT,REV)
        cls.by_id={case['id']:case for case in cls.cases}
        cls.ann_bytes=(ARCHIVE/'literal-annotations.c1bbcae.json').read_bytes()
        cls.ann=json.loads(cls.ann_bytes)
        cls.table=context.build_tier2_chunks(rescore.render_pages(cls.docs),(100,20,'words'),pinned_chunker())
        modules={p.relative_to(ROOT).as_posix():p.read_bytes() for p in sorted((ROOT/'eval/scoring_v2').glob('*.py'))}
        cls.current_identity=scorer_identity(modules,cls.ann_bytes)
        cls.source={tier:load_rows(ROOT/f'eval/phase35/results/tier{tier}_dev.jsonl') for tier in (1,2)}
        cls.archived={tier:load_rows(ARCHIVE/f'tier{tier}_dev.v2.jsonl') for tier in (1,2)}
        cls.sidecars={tier:json.loads((ARCHIVE/f'tier{tier}_dev.v2.jsonl.scoring.json').read_text()) for tier in (1,2)}
        cls.rebuilt={}
        for tier,rows in cls.source.items():
            for row in rows:
                case=cls.by_id[row['id']]
                pair,ids,text,status,mode=verify_reconstruction(row,case,cls.docs,tier=tier,table=cls.table if tier==2 else None)
                v1=score_generic(case,row,pair,ids,text)
                if tier==2:
                    gold={(s['document'],s['page']) for s in case['gold_sources']}
                    refs=[(ref['document_name'],ref['page_number']) for ref in row['retrieved']]
                    v1.update(retrieval_page_recall=len(gold&set(refs))/len(gold) if gold else None,
                              retrieval_first_gold_rank=next((i for i,ref in enumerate(refs,1) if ref in gold),None))
                # Always execute current scorer: never skip because hashes differ.
                v2=score_case(case,row,pair,ids,text,case['history'],cls.ann['cases'][case['id']])
                cls.rebuilt[tier,row['id']]=dict(pair=pair,ids=ids,text=text,status=status,mode=mode,v1=v1,v2=v2)

    def test_all_89_complete_current_v2_dicts_match_final_archive_behavior(self):
        self.assertEqual(validate_annotations(self.ann,self.cases,self.docs),[])
        self.assertEqual(len(self.rebuilt),89)
        for tier,expected_count in [(1,47),(2,42)]:
            self.assertEqual(len(self.archived[tier]),expected_count)
            for archived in self.archived[tier]:
                with self.subTest(tier=tier,id=archived['id']):
                    actual=self.rebuilt[tier,archived['id']]
                    self.assertEqual(actual['v2'],archived['v2'])
                    self.assertEqual(actual['v1'],archived['v1_current'])
                    self.assertEqual(actual['v1'],archived['v1_stored'])
                    self.assertEqual(actual['status'],'exact')

    def test_all_context_and_135_chunk_hashes_match_pinned_evidence(self):
        self.assertEqual(len(self.table),135)
        self.assertEqual(context.chunk_table_sha256(self.table),self.sidecars[2]['context_config']['tier2']['chunk_table_sha256'])
        for tier in (1,2):
            side=self.sidecars[tier]
            self.assertEqual(side['dataset']['run_time']['git_rev'],self.pin['git_rev'])
            self.assertEqual(side['dataset']['run_time']['file_sha256'],self.pin['file_sha256'])
            self.assertEqual(side['scorer']['annotations_sha256'],self.current_identity['annotations_sha256'])
            for meta in side['rows']:
                actual=self.rebuilt[tier,meta['id']]
                with self.subTest(tier=tier,id=meta['id']):
                    self.assertEqual(context.text_sha256(actual['text']),meta['context_sha256'])
                    self.assertEqual(actual['mode'],meta['context_mode'])
                    self.assertEqual(actual['status'],meta['reconstruction_status'])
                    if tier==2:
                        hashes={str(cid):self.table[cid-1]['sha256'] for cid in actual['ids']}
                        self.assertEqual(hashes,meta['chunk_sha256'])

    def test_four_occurrences_and_shared_case_keep_tier_contexts_separate(self):
        flips={(tier,cid):(r['v1']['correct'],r['v2']['correct']) for (tier,cid),r in self.rebuilt.items()
               if r['v1']['correct']!=r['v2']['correct']}
        self.assertEqual(flips,{(1,'B-comp-04'):(False,True),(1,'B-conf-04'):(False,True),
                                (1,'D-conflicting-01'):(True,False),(2,'B-conf-04'):(False,True)})
        a,b=self.rebuilt[1,'B-conf-04'],self.rebuilt[2,'B-conf-04']
        self.assertNotEqual(a['text'],b['text'])
        self.assertNotEqual(context.text_sha256(a['text']),context.text_sha256(b['text']))
        self.assertIsNot(a,b)
        self.assertTrue(a['v2']['conflict_ok'] and b['v2']['conflict_ok'])
        self.assertTrue(a['v2']['signals']['disagreement'] and b['v2']['signals']['disagreement'])

    def test_identity_comparison_is_explicit_without_hardcoded_aggregate(self):
        modules={p.relative_to(ROOT).as_posix():p.read_bytes() for p in sorted((ROOT/'eval/scoring_v2').glob('*.py'))}
        self.assertEqual(scorer_identity(modules,self.ann_bytes),self.current_identity)
        for side in self.sidecars.values():
            identity_matches=side['scorer']==self.current_identity
            old_modules=side['scorer']['module_sha256'];new_modules=self.current_identity['module_sha256']
            differing=[path for path in set(old_modules)|set(new_modules)
                       if new_modules.get(path)!=old_modules.get(path)]
            self.assertEqual(identity_matches,not differing)
            # Historical diagnostic evidence never becomes an acceptance claim,
            # regardless of whether current source identity happens to match.
            self.assertFalse(side['acceptance_eligible'])
            self.assertEqual(side['dataset']['run_time']['pin_source'],'operator_git_rev')

    def test_new_comparison_sidecars_are_stable_and_keep_current_identity(self):
        source=ROOT/'eval/phase35/results/tier1_dev.jsonl'
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temp:
            folder=Path(temp).resolve();ann=folder/'literal-annotations.json';ann.write_bytes(self.ann_bytes)
            finals=[prepare_comparison(source,ann,folder/'outputs',run,tier=1,scorer_version='2.1.0',dataset_rev=REV)
                    for run in ['current-a','current-b']]
            rows=[(p/'comparison.v2.jsonl').read_bytes() for p in finals]
            self.assertEqual(rows[0],rows[1])
            sides=[json.loads((p/'comparison.v2.jsonl.scoring.json').read_text()) for p in finals]
            for side in sides:
                self.assertEqual(side['scorer'],self.current_identity)
                self.assertEqual(side['counts']['exact'],47);self.assertEqual(side['counts']['drift'],0)
                self.assertFalse(side['acceptance_eligible']);self.assertIn('generated_at_utc',side)
                side.pop('generated_at_utc')
            self.assertEqual(sides[0],sides[1])
            for p in finals:
                self.assertTrue((p/'COMPLETED.json').is_file())
                for row in load_rows(p/'comparison.v2.jsonl'):
                    self.assertEqual(row['v2'],self.rebuilt[1,row['id']]['v2'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)


if __name__=='__main__': unittest.main()
