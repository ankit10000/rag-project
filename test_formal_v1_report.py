"""Synthetic-only report controls; no database, provider or evaluation execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import formal_v1_report as R
from eval.framework.integrity import split_of


class FormalV1ReportTests(unittest.TestCase):
    def setUp(self):
        ids = (f'synthetic-formal-{i}' for i in range(1000))
        self.cases = [dict(id=cid, tier='both', category='synthetic',
                           expect_abstain=False, expect_partial=False, expect_conflict=False)
                      for cid in ids if split_of(cid) == 'heldout'][:113]
        self.rows = [dict(id=c['id'], tier=1, split='heldout', category='synthetic',
            status='answered', latency_s=2., llm_calls=1, prompt_tokens=3, output_tokens=1,
            score=dict(status='answered', correct=i < 97, correct_lenient=i < 97,
                fact_recall=1., citation_correctness=1., citation_completeness=.5,
                abstain_ok=None, partial_ok=None, conflict_ok=None, fabricated=0,
                forbidden_hits=[], ungrounded_numbers=[], unsupported=False))
            for i,c in enumerate(self.cases)]
        self.identity = dict(scorer='v1', manifest_sha256='a'*64,
            dataset_sha256='b'*64, dataset_version='synthetic-only',
            source_sha256={'synthetic.py':'c'*64}, annotation_identity='NOT_APPLICABLE_V1')
        self.metadata = dict(self.identity, results_sha256='d'*64)

    def report(self, rows=None, tier=1):
        return R.make_report(self.rows if rows is None else rows, self.cases,
                             self.metadata, self.identity, split='heldout', tier=tier)

    def test_threshold_boundaries_and_metrics(self):
        report = self.report()
        self.assertEqual(report['threshold']['status'], 'PASS')
        self.assertEqual(report['metrics']['overall']['correct'], 97)
        self.assertEqual(report['metrics']['overall']['citation_completeness']['mean'], .5)
        self.assertEqual(report['provider_usage']['latency_seconds']['total'], 226.)
        self.assertEqual(report['metrics']['overall']['unsupported_claims']['rate'], 0.)
        self.rows[96]['score']['correct'] = False
        self.assertEqual(self.report()['threshold']['status'], 'FAIL')
        # Frozen Tier 2 denominator is 106; seven answer-only cases stay excluded.
        for case in self.cases[-7:]: case['tier'] = 'answer_only'
        rows = copy.deepcopy(self.rows[:106])
        for i,row in enumerate(rows):
            row['tier'] = 2; row['score']['correct'] = i < 69
        self.assertEqual(self.report(rows, 2)['threshold']['status'], 'PASS')
        rows[68]['score']['correct'] = False
        self.assertEqual(self.report(rows, 2)['threshold']['status'], 'FAIL')
        with self.assertRaises(ValueError): self.report(rows + [dict(self.rows[-1], tier=2)], 2)

    def test_complete_incomplete_and_error_are_distinct_from_acceptance(self):
        self.assertEqual(self.report(self.rows[:-1])['threshold']['status'], 'INCOMPLETE')
        self.rows[-1]['status'] = 'error'; self.rows[-1]['score']['status'] = 'error'
        result = self.report()
        self.assertEqual(result['error_rows'], 1)
        self.assertEqual(result['threshold']['status'], 'PASS')  # unchanged frozen counting
        self.assertEqual(result['formal_outcome'], 'FORMAL_EVALUATION_INCOMPLETE')
        self.assertFalse(result['acceptance_eligible'])
        self.metadata['human_review_status'] = 'HUMAN_REVIEWED'
        self.metadata['approved_by'] = 'synthetic claimed owner'
        self.assertFalse(self.report()['acceptance_eligible'])
        # The frozen runner uses null conditional flags on canonical exceptions,
        # including cases that normally require an abstention/conflict decision.
        self.cases[-1].update(expect_abstain=True, expect_conflict=True)
        canonical = self.report()
        self.assertEqual(canonical['error_rows'], 1)
        self.assertEqual(canonical['metrics']['overall']['abstention_correctness'], {'rate':0.,'n':1})

    def test_duplicate_unknown_split_tier_and_identity_rejected(self):
        for change in ({'id':'unknown'}, {'split':'dev'}, {'tier':True}, {'category':'wrong'}):
            rows=copy.deepcopy(self.rows);rows[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):self.report(rows)
        with self.assertRaises(ValueError):self.report(self.rows+[self.rows[0]])
        self.metadata['source_sha256']={'synthetic.py':'e'*64}
        with self.assertRaises(ValueError):self.report()

    def test_invalid_shapes_nonfinite_numbers_and_boolean_coercions_rejected(self):
        for key,value in [('correct',1),('unsupported','false'),('fact_recall',float('nan')),
                          ('citation_correctness',1.1),('citation_completeness',True),
                          ('abstain_ok','yes'),('fabricated',False),('forbidden_hits',None)]:
            rows=copy.deepcopy(self.rows);rows[0]['score'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.report(rows)
        for key,value in [('latency_s',float('inf')),('latency_s',10**1000),('latency_s',-1),('llm_calls',False),
                          ('prompt_tokens',-1),('output_tokens',1.1)]:
            rows=copy.deepcopy(self.rows);rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.report(rows)
        rows=copy.deepcopy(self.rows);rows[0]['status']='error';rows[0]['score']['status']='error'
        with self.assertRaises(ValueError):self.report(rows)

    def test_abstention_citation_and_unsupported_aggregation(self):
        self.cases[0]['expect_abstain']=True
        self.rows[0]['score'].update(abstain_ok=True,unsupported=True)
        report=self.report()
        self.assertEqual(report['metrics']['overall']['abstention_correctness'],{'rate':1.,'n':1})
        self.assertAlmostEqual(report['metrics']['overall']['unsupported_claims']['rate'],1/113)
        self.rows[0]['score']['abstain_ok']=None
        with self.assertRaises(ValueError):self.report()

    def test_strict_json_and_deterministic_row_order(self):
        for raw in (b'{"id":1,"id":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.assertRaises(ValueError):R.read_rows(raw)
        self.assertEqual(self.report(),self.report(list(reversed(self.rows))))
        self.assertNotIn('per_case',self.report()['metrics'])

    def test_atomic_no_replace_and_parent_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve(); target=root/'report.json';report=self.report()
            R.publish_new(target,report)
            original=target.read_bytes()
            self.assertEqual(json.loads(original),report)
            with self.assertRaises(FileExistsError):R.publish_new(target,report)
            self.assertEqual(target.read_bytes(),original)
            dangling=root/'dangling.json';dangling.symlink_to(root/'not-created')
            with self.assertRaises(FileExistsError):R.publish_new(dangling,report)
            self.assertFalse((root/'not-created').exists())
            directory=root/'linked';directory.symlink_to(root,target_is_directory=True)
            with self.assertRaises(OSError):R.publish_new(directory/'new.json',report)
            self.assertEqual(sorted(p.name for p in root.iterdir()),['dangling.json','linked','report.json'])

    def test_publication_failure_never_exposes_partial_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder).resolve()/'report.json'
            with patch.object(R.os,'fsync',side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):R.publish_new(target,self.report())
            self.assertEqual(list(target.parent.iterdir()),[])

    def test_post_link_durability_error_preserves_complete_output_and_refuses_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder).resolve()/'report.json';report=self.report()
            with patch.object(R.os,'fsync',side_effect=[None,OSError('synthetic durability failure')]):
                with self.assertRaises(OSError):R.publish_new(target,report)
            original=target.read_bytes()
            self.assertEqual(json.loads(original),report)
            self.assertEqual(list(target.parent.iterdir()),[target])
            with self.assertRaises(FileExistsError):R.publish_new(target,report)
            self.assertEqual(target.read_bytes(),original)

    def test_cli_raw_hash_binding_without_real_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();raw=('\n'.join(json.dumps(r) for r in self.rows)+'\n').encode()
            (root/'rows.jsonl').write_bytes(raw)
            metadata=dict(self.metadata,results_sha256=hashlib.sha256(raw).hexdigest())
            (root/'meta.json').write_text(json.dumps(metadata))
            args=['--results',str(root/'rows.jsonl'),'--metadata',str(root/'meta.json'),
                  '--split','heldout','--tier','1','--output',str(root/'result.json')]
            with patch.object(R,'current_identity',return_value=self.identity),\
                 patch('eval.framework.integrity.load_dataset',return_value=({},self.cases)):
                self.assertEqual(R.main(args),0)
                self.assertFalse(json.loads((root/'result.json').read_text())['acceptance_eligible'])
                (root/'rows.jsonl').write_bytes(raw+b'\n')
                with self.assertRaises(ValueError):R.main(args)


if __name__ == '__main__':unittest.main()
