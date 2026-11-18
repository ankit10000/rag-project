"""Tier 2 dev reconstruction against pinned source; no ingestion/provider/DB execution."""
import testsafe
testsafe.require_scratch_db()
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import unittest
from eval.scoring_v2 import context, score_case
from eval.scoring_v2 import rescore
from eval.phase35.run_eval import score_generic
from eval.runner_preparation.provenance import verify_reconstruction

ROOT=Path(__file__).resolve().parent
REV='c1bbcae9a21e389c16c3f1587de5acc1b5209e37'
ARTIFACTS=ROOT/'docs/remediation/phase_e2_engineering/wp8_evidence/flip_inputs/final'


def pinned_source(path):
    return subprocess.check_output(['git','show',f'{REV}:{path}'],cwd=ROOT).decode('utf-8')


def pinned_chunk_function():
    """Execute the pinned pure chunker only; imports just re, no services."""
    namespace={}
    exec(compile(pinned_source('services/chunker.py'),'pinned-chunker','exec'),namespace)
    return namespace['chunk_page']


def pinned_ingestion_chunk_stage():
    """Extract ONLY the historical inline chunk stage, ending before embeddings.

    This preserves the actual pin's AST rather than substituting today's
    build_chunks helper. No ingestion module imports or later stages execute.
    """
    tree=ast.parse(pinned_source('services/ingestion_service.py'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='ingest_pdf')
    start=next(i for i,n in enumerate(function.body) if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='all_chunks' for t in n.targets))
    stop=next(i for i,n in enumerate(function.body[start:],start) if isinstance(n,ast.If)
              and ast.unparse(n.test)=='not all_chunks')
    derived=ast.parse('def chunk_stage(pages, document_name, cfg, chunk_page):\n    pass').body[0]
    derived.body=copy.deepcopy(function.body[start:stop])+[ast.Return(value=ast.Name(id='all_chunks',ctx=ast.Load()))]
    module=ast.fix_missing_locations(ast.Module(body=[derived],type_ignores=[]))
    namespace={'hashlib':hashlib,'re':re}
    exec(compile(module,'pinned-inline-chunk-stage','exec'),namespace)
    return namespace['chunk_stage']


class Tier2ReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,cls.pin=rescore.load_pinned_dataset(ROOT,REV)
        cls.by_id={c['id']:c for c in cls.cases}
        cls.extracted=rescore.render_pages(cls.docs)
        cls.chunk_fn=staticmethod(pinned_chunk_function())
        cls.table=context.build_tier2_chunks(cls.extracted,(100,20,'words'),cls.chunk_fn)
        cls.rows=[json.loads(line) for line in (ROOT/'eval/phase35/results/tier2_dev.jsonl').read_text().splitlines()]
        cls.comparisons=[json.loads(line) for line in (ARTIFACTS/'tier2_dev.v2.jsonl').read_text().splitlines()]
        cls.sidecar=json.loads((ARTIFACTS/'tier2_dev.v2.jsonl.scoring.json').read_text())
        cls.ann=json.loads((ARTIFACTS/'literal-annotations.c1bbcae.json').read_text())

    def test_pinned_defaults_match_assumptions_but_remain_environment_overridable(self):
        source=pinned_source('services/retrieval_config.py')
        tree=ast.parse(source)
        assignments={t.id:n.value for n in tree.body if isinstance(n,ast.Assign)
                     for t in n.targets if isinstance(t,ast.Name)}
        for key,value in (('CHUNK_SIZE',100),('CHUNK_OVERLAP',20),('CHUNK_STRATEGY','words')):
            call=assignments[key]
            self.assertIsInstance(call,ast.Call)
            self.assertEqual(ast.literal_eval(call.args[1]),value)
        self.assertIn('load_dotenv()',source)
        self.assertIn('os.getenv(name, default)',source)
        self.assertEqual(self.sidecar['context_config']['tier2']['chunk_config_source'],'assumed_default')
        self.assertFalse(self.sidecar['context_config']['tier1']['assumption_checked'])

    def test_pinned_extractor_and_render_parameters(self):
        parser=ast.parse(pinned_source('services/pdf_parser.py'))
        calls=[n for n in ast.walk(parser) if isinstance(n,ast.Call)]
        get_text=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='get_text']
        self.assertEqual(len(get_text),1)
        self.assertTrue(next(ast.literal_eval(k.value) for k in get_text[0].keywords if k.arg=='sort'))
        runner=ast.parse(pinned_source('eval/phase35/run_eval.py'))
        function=next(n for n in runner.body if isinstance(n,ast.FunctionDef) and n.name=='build_scratch_corpus')
        text=ast.unparse(function)
        self.assertIn('TRUNCATE document_chunks RESTART IDENTITY',text)
        self.assertIn('pymupdf.Rect(36, 36, 559, 806)',text)
        self.assertIn('fontsize=9',text)
        self.assertIn('for name, pages in docs.items()',text)

    def test_independent_historical_inline_ingestion_rebuild_matches_every_chunk(self):
        stage=pinned_ingestion_chunk_stage()
        cfg=SimpleNamespace(CHUNK_SIZE=100,CHUNK_OVERLAP=20,CHUNK_STRATEGY='words')
        independently=[]
        for name,pages in self.extracted.items():
            records=stage([dict(page_number=p,text=t) for p,t in pages],name,cfg,self.chunk_fn)
            for r in records:
                independently.append(dict(id=len(independently)+1,document=r['document_name'],page=r['page_number'],
                    content=r['content'],sha256=hashlib.sha256(r['content'].encode()).hexdigest()))
        self.assertEqual(independently,self.table)
        self.assertEqual(len(self.table),135)
        self.assertEqual(context.chunk_table_sha256(self.table),self.sidecar['context_config']['tier2']['chunk_table_sha256'])

    def test_historical_page_filter_and_document_scoped_dedup_boundaries(self):
        stage=pinned_ingestion_chunk_stage()
        cfg=SimpleNamespace(CHUNK_SIZE=100,CHUNK_OVERLAP=20,CHUNK_STRATEGY='words')
        nine=' '.join(['word']*9);ten=' '.join(['word']*10)
        pages=[dict(page_number=1,text=nine),dict(page_number=2,text=ten),dict(page_number=3,text=ten.upper())]
        first=stage(pages,'first.pdf',cfg,self.chunk_fn)
        second=stage(pages,'second.pdf',cfg,self.chunk_fn)
        self.assertEqual([(r['page_number'],r['content']) for r in first],[(2,ten)])
        self.assertEqual(len(second),1)
        combined=context.build_tier2_chunks({'first.pdf':[(p['page_number'],p['text']) for p in pages],
            'second.pdf':[(p['page_number'],p['text']) for p in pages]},(100,20,'words'),self.chunk_fn)
        self.assertEqual([r['id'] for r in combined],[1,2])

    def test_all_42_contexts_chunks_and_current_v1_v2_signals_reproduce(self):
        metadata={r['id']:r for r in self.sidecar['rows']}
        compared={r['id']:r for r in self.comparisons}
        self.assertEqual(len(self.rows),42)
        refs=set()
        for row in self.rows:
            with self.subTest(case=row['id']):
                case=self.by_id[row['id']]
                pair,ids,text,status,mode=verify_reconstruction(row,case,self.docs,tier=2,table=self.table)
                self.assertEqual(status,'exact')
                self.assertEqual(context.text_sha256(text),metadata[row['id']]['context_sha256'])
                self.assertEqual({str(cid):self.table[cid-1]['sha256'] for cid in ids},metadata[row['id']]['chunk_sha256'])
                current=score_generic(case,row,pair,ids,text)
                stored={k:v for k,v in row['score'].items() if not k.startswith('retrieval_')}
                self.assertEqual(current,stored)
                self.assertEqual(score_case(case,row,pair,ids,text,case['history'],self.ann['cases'][case['id']]),compared[row['id']]['v2'])
                refs.update((r['chunk_id'],r['document_name'],r['page_number']) for r in row['retrieved'])
                refs.update((r['chunk_id'],r['document'],r['page']) for r in row['citations'])
        self.assertEqual(len(refs),58)

    def test_changed_chunk_config_and_wrong_table_hash_fail_closed(self):
        alternative=context.build_tier2_chunks(self.extracted,(120,20,'words'),self.chunk_fn)
        self.assertTrue(any(context.verify_tier2(row,alternative,self.by_id[row['id']])[3]!='exact' for row in self.rows))
        row=self.rows[0]
        result=context.verify_tier2(row,self.table,self.by_id[row['id']],{'chunk_table_sha256':'0'*64})
        self.assertEqual(result[3],'mismatch:chunk_table_sha256')
        self.assertIsNone(result[2])

    def test_b_conf_04_tier2_contrast_qualifies_without_claiming_approval(self):
        row=next(r for r in self.rows if r['id']=='B-conf-04')
        case=self.by_id[row['id']]
        pair,ids,text,_,_=verify_reconstruction(row,case,self.docs,tier=2,table=self.table)
        scored=score_case(case,row,pair,ids,text,case['history'],self.ann['cases'][case['id']])
        self.assertFalse(row['score']['conflict_ok'])
        self.assertTrue(scored['conflict_ok'])
        self.assertEqual(scored['signals']['disagreement'],[dict(groups=[0,1],lexicon=[],list_scope=False,sentence_index=0)])
        self.assertIn('though another section mentions 15 months',row['answer'])
        self.assertEqual({pair[c['chunk_id']] for c in row['citations']},
                         {('calder_sound_tile_study_TR-2026-07.pdf',1),('calder_sound_tile_study_TR-2026-07.pdf',4)})
        self.assertFalse(self.sidecar['acceptance_eligible'])


if __name__=='__main__':
    unittest.main()
