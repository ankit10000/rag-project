"""WP7 opt-in selection and atomic integration, using synthetic offline inputs."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from eval.runner_preparation.selection import select_scorer
from eval.runner_preparation import offline
from eval.phase35.run_eval import score_generic, split_of, tier1_context
from eval.framework.integrity import dataset_hash
from eval.scoring_v2 import rescore as wp6

ROOT = Path(__file__).resolve().parent


def fixture():
    cid = next('SYN-WP7-'+str(i) for i in range(100) if split_of('SYN-WP7-'+str(i))=='dev')
    docs = {'synthetic.pdf':['The permit lasts 30 days.','An unrelated synthetic page.','Another unrelated synthetic page.']}
    case = dict(id=cid,category='direct_factual',question='How long does the permit last?',history=[],
                gold_facts=[['30 days']],forbidden=[],gold_sources=[dict(document='synthetic.pdf',page=1,span='30 days')],
                expect_abstain=False,expect_partial=False,expect_conflict=False,tier='both',tier1_chunks=[])
    items,pair,ids=tier1_context(case,docs)
    gold_id=next(cid for cid in ids if pair[cid] is not None)
    result=dict(answer='It lasts 30 days.',status='answered',citations=[dict(chunk_id=gold_id,document='synthetic.pdf',page=1)])
    text=' '.join(i['chunk'][3].strip() for i in items)
    row=dict(result,id=case['id'],tier=1,split='dev',question=case['question'],
             context=[dict(chunk_id=i['chunk'][0],document=i['chunk'][1],page=i['chunk'][2],gold=pair[i['chunk'][0]] is not None) for i in items],
             score=score_generic(case,result,pair,ids,text))
    ann=dict(schema='phase35-scorer-annotations/1',dataset_version='synthetic-wp7',dataset_sha256=dataset_hash([case]),cases={case['id']:{}})
    pin=dict(manifest_content_sha256=None,dataset_version='synthetic-wp7',pin_source='operator_git_rev',git_rev='a'*40,
             file_sha256={f'eval/phase35/data_{letter}.py':'0'*64 for letter in 'ABCD'})
    return docs,case,row,ann,pin


class SelectionTests(unittest.TestCase):
    def test_default_is_original_v1_callable_and_signature(self):
        import inspect
        self.assertIs(select_scorer(),score_generic)
        self.assertEqual(list(inspect.signature(select_scorer()).parameters),
                         ['case','result','chunk_pair','context_ids','context_text'])
        docs,case,row,_,_=fixture()
        items,pair,ids=tier1_context(case,docs)
        text=' '.join(i['chunk'][3].strip() for i in items)
        self.assertEqual(select_scorer()(case,row,pair,ids,text),score_generic(case,row,pair,ids,text))

    def test_v2_requires_explicit_development_and_annotations(self):
        _,_,_,ann,_=fixture()
        for kwargs in ({},{'development':True},{'annotations':ann}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                select_scorer('2.1.0',**kwargs)
        for version in ('v2','2.1','2','latest','',None):
            with self.subTest(version=version),self.assertRaises(ValueError):
                select_scorer(version,development=True,annotations=ann)

    def test_v2_bound_adapter_explicit_annotations_and_history(self):
        docs,case,row,ann,_=fixture()
        case['history']=[dict(role='assistant',content='It lasts 85 days.')]
        fn=select_scorer('2.1.0',development=True,annotations=ann)
        items,pair,ids=tier1_context(case,docs)
        result=fn(case,row,pair,ids,' '.join(i['chunk'][3] for i in items))
        self.assertEqual(result['scorer_version'],'2.1.0')
        self.assertEqual(result['history_echo'],[])
        self.assertTrue(result['correct'])
        with self.assertRaises(KeyError):
            fn(dict(case,id='missing'),row,pair,ids,'')

    def test_malformed_full_annotations_refused(self):
        for ann in ({},{'cases':{}},{'cases':{},'schema':'wrong'},[]):
            with self.subTest(annotation=ann),self.assertRaises(ValueError):
                select_scorer('2.1.0',development=True,annotations=ann)


class OfflineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.docs,self.case,self.row,self.ann,self.pin=fixture()
        self.source=self.folder/'source.jsonl'
        self.annotations=self.folder/'annotations.json'
        self.write_inputs()
        self.root=self.folder/'comparisons'

    def write_inputs(self):
        self.source.write_text(json.dumps(self.row)+'\n')
        self.annotations.write_text(json.dumps(self.ann))

    def prepare(self,run_id='test-run',**kwargs):
        options=dict(tier=1,scorer_version='2.1.0',dataset_rev='synthetic-test-only',split='dev')
        options.update(kwargs)
        with patch.object(wp6,'load_pinned_dataset',return_value=(self.docs,[self.case],self.pin)):
            return offline.prepare_comparison(self.source,self.annotations,self.root,run_id,**options)

    def test_delegate_publishes_provenance_bound_version_namespace(self):
        before=(self.source.read_bytes(),self.annotations.read_bytes())
        final=self.prepare()
        self.assertEqual(final,self.root/'development-comparisons/scorer-2.1.0/test-run')
        files={p.name for p in final.iterdir()}
        self.assertEqual(files,{'comparison.v2.jsonl','comparison.v2.jsonl.scoring.json','comparison.v2.diff.md',
                               'provenance.json','artifact-manifest.json','COMPLETED.json'})
        proof=json.loads((final/'provenance.json').read_text())
        self.assertEqual(proof['source_sha256'],hashlib.sha256(before[0]).hexdigest())
        self.assertEqual(proof['annotations_sha256'],hashlib.sha256(before[1]).hexdigest())
        self.assertEqual(proof['scorer']['version'],'2.1.0')
        self.assertEqual(before,(self.source.read_bytes(),self.annotations.read_bytes()))
        self.assertFalse(json.loads((final/'COMPLETED.json').read_text())['acceptance_eligible'])
        with self.assertRaises(FileExistsError):
            self.prepare()

    def test_exact_context_mismatch_never_publishes_and_retry_succeeds(self):
        self.row['context'][0]['page']=99;self.write_inputs()
        with self.assertRaises(ValueError):
            self.prepare()
        namespace=self.root/'development-comparisons/scorer-2.1.0'
        self.assertFalse(namespace.exists())
        self.docs,self.case,self.row,self.ann,self.pin=fixture();self.write_inputs()
        self.assertTrue((self.prepare()/'COMPLETED.json').is_file())

    def test_missing_duplicate_context_fail_before_output(self):
        for mutate in (lambda row:row.pop('context'),lambda row:row['context'].append(copy.deepcopy(row['context'][0]))):
            self.docs,self.case,self.row,self.ann,self.pin=fixture()
            mutate(self.row);self.write_inputs()
            with self.subTest(context=self.row.get('context')),self.assertRaises(ValueError):
                self.prepare()
            self.assertFalse(self.root.exists())

    def test_only_dev_explicit_v2_is_allowed(self):
        for options in ({'split':'heldout'},{'split':'all'},{'scorer_version':'v1'},{'scorer_version':None},
                        {'tier':True},{'dataset_rev':None},{'run_header':'header.json'}):
            with self.subTest(options=options),self.assertRaises(ValueError):
                self.prepare(**options)
        self.assertFalse(self.root.exists())

    def test_changed_inputs_prevent_completed_output(self):
        original=wp6.rescore
        def change(args):
            side=original(args)
            self.source.write_bytes(self.source.read_bytes()+b'\n')
            return side
        with patch.object(wp6,'rescore',side_effect=change),self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.root/'development-comparisons/scorer-2.1.0/test-run').exists())

    def test_tampered_sidecar_never_publishes(self):
        original=wp6.rescore
        def alter(args):
            side=original(args)
            path=Path(args.output+'.scoring.json')
            saved=json.loads(path.read_text());saved['source_results']['sha256']='0'*64
            path.write_text(json.dumps(saved))
            return side
        with patch.object(wp6,'rescore',side_effect=alter),self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.root/'development-comparisons/scorer-2.1.0/test-run').exists())

    def test_partial_wp6_failure_is_cleaned_then_retry_same_id_succeeds(self):
        original=wp6.rescore
        def fail_after_writes(args):
            original(args)
            raise RuntimeError('synthetic post-write failure')
        with patch.object(wp6,'rescore',side_effect=fail_after_writes),self.assertRaises(RuntimeError):
            self.prepare()
        namespace=self.root/'development-comparisons/scorer-2.1.0'
        self.assertEqual(list(namespace.iterdir()),[])
        self.assertTrue((self.prepare()/'COMPLETED.json').is_file())

    def test_reconstructed_hash_mismatch_rejects_bundle(self):
        original=wp6.rescore
        def alter(args):
            side=original(args)
            side['rows'][0]['context_sha256']='0'*64
            Path(args.output+'.scoring.json').write_text(json.dumps(side))
            return side
        with patch.object(wp6,'rescore',side_effect=alter),self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.root/'development-comparisons/scorer-2.1.0/test-run').exists())

    def test_tier2_explicit_empty_retrieval_is_valid_exact_context(self):
        self.case.update(category='no_answer',gold_facts=[],gold_sources=[],expect_abstain=True)
        self.row.update(tier=2,answer='Cannot find information.',status='abstained',citations=[],retrieved=[])
        self.row.pop('context')
        self.row['score']=dict(score_generic(self.case,self.row,{},set(),''),
                               retrieval_page_recall=None,retrieval_first_gold_rank=None)
        self.ann['dataset_sha256']=dataset_hash([self.case]);self.write_inputs()
        final=self.prepare(tier=2,chunk_config='100,20,words')
        output=json.loads((final/'comparison.v2.jsonl').read_text())
        self.assertEqual(output['reconstruction_status'],'exact')
        self.assertEqual(output['v2']['numeric_grounded'],True)
        self.assertTrue(output['v2']['correct'])

    def test_invalid_annotations_are_never_fabricated(self):
        self.ann['cases']={};self.write_inputs()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.root/'development-comparisons/scorer-2.1.0/test-run').exists())

    def test_cli_no_acceptance_heldout_or_implicit_version(self):
        base=['--results',str(self.source),'--annotations',str(self.annotations),'--tier','1',
              '--dataset-rev','test','--scorer-version','2.1.0','--output-root',str(self.root),'--run-id','test']
        for args in (['--acceptance'],['--split','all'],['--split','heldout']):
            with self.subTest(args=args),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:
                offline.main(base+args)
            self.assertEqual(raised.exception.code,2)


if __name__=='__main__':
    unittest.main()
