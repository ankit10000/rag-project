"""Synthetic capture adapter checks; no DB/provider/protected-case execution."""
import copy
import hashlib
import hmac
import json
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://nobody@127.0.0.1:1/rag_test_scratch')
os.environ.setdefault('TESTSAFE_BLOCK_NETWORK', '1')
import testsafe
testsafe.require_scratch_db()
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

from eval import official_v1_capture as C
from eval.phase35.run_eval import score_generic
from eval import official_v1_execution as E
from eval.framework.integrity import split_of


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.provider = ModuleType('synthetic_provider')
        self.provider.MODEL_NAME = 'synthetic-primary'
        self.provider.FALLBACK_MODELS = ['synthetic-fallback']
        self.provider.REQUEST_TIMEOUT_MS = 100
        self.provider.QUOTA_COOLDOWN_SECONDS = 1
        self.provider.DEFAULT_QUOTA_WAIT_SECONDS = 1
        self.provider.GEMINI_API_KEY = 'SENSITIVE-KEY-MUST-NOT-APPEAR'
        def attempt(model, prompt, **retry_options):
            self.calls.append((model, prompt, retry_options))
            return self.answer
        self.provider._generate_with_model = attempt
        # Aliases keep this function; it looks up the live module attribute.
        self.provider.generate_answer = lambda prompt: self.provider._generate_with_model(
            self.provider.MODEL_NAME, prompt, max_retries=1)
        self.retrieval = SimpleNamespace(**{key:1 for key in C._RETRIEVAL_KEYS})
        self.run = dict(tier=1, split='heldout', database_name='rag_test_synthetic',
                        local_v1_profile=False, pause=0, fresh=False, no_ingest=False)
        self.answer = object()
        self.bundle = dict(sources=[dict(ref='S1', chunk_id=7,
            document_name='PRIVATE-DOCUMENT-NAME.pdf', page_number=1,
            content='PRIVATE-SOURCE-TEXT 30 days')],
            context_text='PRIVATE-PROMPT-CONTEXT [S1] 30 days', dropped=[], total_chars=14)
        self.assembly_calls = []
        def assemble_context(value, **kwargs):
            self.assembly_calls.append((value, kwargs))
            return value
        self.runner = ModuleType('synthetic_runner')
        self.runner.score_generic = score_generic
        self.runner.assemble_context = assemble_context
        self.runner.generate_answer = self.provider.generate_answer
        self.rag = SimpleNamespace(assemble_context=assemble_context,
                                   generate_answer=self.provider.generate_answer)
        self.case = dict(id='synthetic-only', question='How long?', history=[],
            gold_sources=[dict(document='PRIVATE-DOCUMENT-NAME.pdf',page=1)],
            gold_facts=[['30 days']], forbidden=[], expect_partial=False,
            expect_abstain=False, expect_conflict=False)
        self.result = dict(answer='30 days [S1]', status='answered',
                           citations=[dict(chunk_id=7)])

    def capture(self):
        return C.RuntimeCapture(self.provider,self.retrieval,self.run)

    def score(self):
        return self.runner.score_generic(self.case,self.result,
            {7:('PRIVATE-DOCUMENT-NAME.pdf',1)},{7},'PRIVATE-SCORING-CONTEXT 30 days')

    def test_aliases_exact_arguments_return_identity_and_distinct_contexts(self):
        before_score=self.score()
        capture=self.capture()
        original=(self.provider._generate_with_model,self.runner.assemble_context,self.runner.score_generic)
        with capture.attach(self.runner):
            self.assertFalse(capture.snapshot()['capture_complete'])
            self.assertIs(self.runner.assemble_context(self.bundle,max_chars=100),self.bundle)
            self.assertIs(self.runner.generate_answer('PRIVATE-ACTUAL-PROMPT'),self.answer)
            self.assertEqual(self.score(),before_score)
        trace=capture.snapshot()
        self.assertTrue(trace['capture_complete'])
        self.assertEqual([e['kind'] for e in trace['events']],
            ['assembled_prompt_context','provider_prompt','scoring_context'])
        self.assertEqual([e['sequence'] for e in trace['events']],[0,1,2])
        prompt=trace['events'][1]['prompt']['sha256']
        assembled=trace['events'][0]['context']['sha256']
        scored=trace['events'][2]['exact_context']['sha256']
        self.assertEqual(len({prompt,assembled,scored}),3)
        self.assertEqual(prompt,hashlib.sha256(b'PRIVATE-ACTUAL-PROMPT').hexdigest())
        self.assertEqual(self.calls,[('synthetic-primary','PRIVATE-ACTUAL-PROMPT',{'max_retries':1})])
        self.assertIs(self.assembly_calls[0][0],self.bundle)
        self.assertEqual(self.assembly_calls[0][1],{'max_chars':100})
        self.assertEqual(original,(self.provider._generate_with_model,self.runner.assemble_context,self.runner.score_generic))
        self.assertNotIn('PRIVATE-',json.dumps(trace))
        self.assertNotIn('SENSITIVE-',json.dumps(trace))

    def test_tier2_rag_binding_and_ordered_sources(self):
        self.run['tier']=2
        capture=self.capture()
        with self.assertRaises(ValueError),capture.attach(self.runner):pass
        second=copy.deepcopy(self.bundle['sources'][0]);second.update(chunk_id=8,content='Second text')
        self.bundle['sources'].append(second)
        with capture.attach(self.runner,rag=self.rag):
            self.assertIs(self.rag.assemble_context(self.bundle),self.bundle)
            self.assertIs(self.rag.generate_answer('rewrite/classify/generate synthetic'),self.answer)
            self.score()
        trace=capture.snapshot()
        event=trace['events'][0]
        self.assertEqual(event['boundary'],'tier2_rag')
        self.assertEqual(event['ordered_source_content'],[C._text(s['content']) for s in self.bundle['sources']])
        self.assertIn('rag.assemble_context',trace['installed_hooks'])
        self.assertEqual(trace['events'][-1]['exact_context'],C._text('PRIVATE-SCORING-CONTEXT 30 days'))

    def test_fallback_attempts_and_exception_restoration(self):
        def attempt(model,prompt,**retry_options):
            if model=='synthetic-primary':raise RuntimeError('PRIVATE-ERROR-TEXT')
            return self.answer
        self.provider._generate_with_model=attempt
        capture=self.capture()
        with capture.attach(self.runner):
            try:self.provider._generate_with_model('synthetic-primary','same prompt')
            except RuntimeError:pass
            self.assertIs(self.provider._generate_with_model('synthetic-fallback','same prompt'),self.answer)
        events=capture.snapshot()['events']
        self.assertEqual([e['outcome'] for e in events],['raised','returned'])
        self.assertEqual(events[0]['prompt'],events[1]['prompt'])
        self.assertNotIn('PRIVATE-ERROR',json.dumps(events))
        self.assertIs(self.provider._generate_with_model,attempt)
        capture=self.capture()
        with self.assertRaises(RuntimeError),capture.attach(self.runner):
            self.provider._generate_with_model('synthetic-primary','different prompt')
        self.assertFalse(capture.snapshot()['capture_complete'])
        self.assertIs(self.provider._generate_with_model,attempt)

    def test_strict_allowlist_scratch_identity_and_no_credentials(self):
        config=self.capture().resolved_config
        self.assertNotIn('GEMINI_API_KEY',json.dumps(config))
        for key,value in [('DATABASE_URL','secret'),('api_key','secret'),('headers',{})]:
            self.run[key]=value
            with self.assertRaises(ValueError):self.capture()
            del self.run[key]
        for name in ('rag_db','postgres','rag_other','postgresql://secret@localhost/rag_test'):
            self.run['database_name']=name
            with self.assertRaises(ValueError):self.capture()
        self.run['database_name']='rag_phase35_eval'
        self.assertEqual(self.capture().resolved_config['run']['database_name'],'rag_phase35_eval')
        self.run['pause']=float('nan')
        with self.assertRaises(ValueError):self.capture()

    def test_snapshots_detached_deterministic_and_source_hash_bound(self):
        capture=self.capture()
        with capture.attach(self.runner):
            self.runner.generate_answer('synthetic')
            self.score()
        first=capture.snapshot();second=capture.snapshot()
        self.assertEqual(first,second)
        self.assertEqual(first['config_sha256'],C._digest(first['resolved_config']))
        digest=first.pop('capture_sha256')
        self.assertEqual(digest,C._digest(first))
        first['resolved_config']['run']['tier']=2
        self.assertEqual(second['resolved_config']['run']['tier'],1)
        for source,digest in second['resolved_config']['source_sha256'].items():
            self.assertEqual(digest,hashlib.sha256((C.ROOT/source).read_bytes()).hexdigest())
        with self.assertRaises(RuntimeError),capture.attach(self.runner):pass

    def test_abstention_dependencies_are_bound_to_actual_source_bytes(self):
        sources=self.capture().resolved_config['source_sha256']
        for name in ('services/citation_service.py','services/answer_semantics.py'):
            with self.subTest(name=name):
                self.assertIn(name,C._SOURCE_PATHS)
                self.assertEqual(sources[name],hashlib.sha256((C.ROOT/name).read_bytes()).hexdigest())

    def test_nested_capture_and_unbootstrapped_runner_refused(self):
        capture=self.capture();nested=self.capture()
        with capture.attach(self.runner):
            with self.assertRaises(RuntimeError),nested.attach(self.runner):pass
        self.runner.assemble_context=None
        with self.assertRaises(ValueError),self.capture().attach(self.runner):pass

    def test_resolved_config_drift_refuses_capture_and_restores_hooks(self):
        capture=self.capture()
        self.provider.MODEL_NAME='changed-model'
        with self.assertRaises(ValueError),capture.attach(self.runner):pass
        self.provider.MODEL_NAME='synthetic-primary'
        original=self.provider._generate_with_model
        with self.assertRaises(ValueError),capture.attach(self.runner):
            self.runner.generate_answer('synthetic')
            self.retrieval.FINAL_TOP_K=999
        self.assertIs(self.provider._generate_with_model,original)
        self.assertFalse(capture.snapshot()['capture_complete'])

    def envelope(self, root, capture):
        ledger=root/'ledger';ledger.mkdir()
        scope=dict(manifest_sha256='a'*64,dataset_sha256='b'*64,
            scorer_sha256={name:capture.resolved_config['source_sha256'][name]
                           for name in E.SCORER_FILES},
            tier=1,split='heldout',output_path=str(root/'bundle.json'),
            ledger_root=str(ledger),runtime_config_sha256=C._digest(capture.resolved_config))
        authority=E.TrustedAuthority('synthetic-test-authority',b'synthetic-test-key-32-bytes-only!!')
        payload=dict(schema='v1-execution-approval/1',approval_id='synthetic-only',
            key_id=authority.key_id,scope=scope,review_evidence_sha256='c'*64,
            policy_evidence_sha256='d'*64)
        approval=dict(payload=payload,hmac_sha256=hmac.new(authority.key,
            E.canonical(payload),hashlib.sha256).hexdigest())
        return scope,approval,authority,ledger

    def test_envelope_capture_saved_bundle_to_existing_reporter(self):
        from scripts import formal_v1_report as reporting
        capture=self.capture()
        cases=[]
        for i in range(1000):
            cid=f'synthetic-capture-{i}'
            if split_of(cid)=='heldout':
                cases.append(dict(self.case,id=cid,tier='both',category='synthetic'))
            if len(cases)==113:break
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            scope,approval,authority,ledger=self.envelope(root,capture)
            def executor(emit):
                with capture.attach(self.runner):
                    for i,case in enumerate(cases):
                        self.runner.assemble_context(self.bundle)
                        self.runner.generate_answer('synthetic actual prompt')
                        result=dict(self.result,answer='30 days [S1]' if i<97 else 'wrong')
                        score=self.runner.score_generic(case,result,
                            {7:('PRIVATE-DOCUMENT-NAME.pdf',1)},{7},
                            'PRIVATE-SCORING-CONTEXT 30 days')
                        emit(dict(id=case['id'],category=case['category'],tier=1,
                            split='heldout',status=result['status'],answer=result['answer'],
                            latency_s=.125,llm_calls=1,prompt_tokens=3,output_tokens=1,score=score))
            result=E.execute(scope,approval,authority=authority,ledger_root=ledger,
                runtime_config=capture.resolved_config,
                verify_prerequisites=lambda *args:None,executor=executor,
                capture_snapshot=capture.snapshot,
                identity_verifier=lambda *args:E.VerifiedInputs(tuple(c['id'] for c in cases)))
            original=Path(result['path']).read_bytes()
            body=E.verify_bundle(result['path'])
            self.assertEqual(len(body['rows']),113)
            self.assertEqual(body['runtime']['capture_sha256'],capture.snapshot()['capture_sha256'])
            identity=dict(scorer='v1',manifest_sha256=scope['manifest_sha256'],
                dataset_sha256=scope['dataset_sha256'],dataset_version='synthetic-only',
                source_sha256=scope['scorer_sha256'],annotation_identity='NOT_APPLICABLE_V1')
            with patch.object(reporting,'current_identity',return_value=identity),\
                 patch('eval.framework.integrity.load_dataset',return_value=({},cases)):
                report=C.report_from_bundle(result['path'])
                self.assertEqual(report['threshold']['status'],'PASS')
                self.assertEqual(report['metrics']['overall']['correct'],97)
                self.assertEqual(report['provider_usage']['latency_seconds']['total'],14.125)
                self.assertEqual(report['formal_outcome'],'FORMAL_EVALUATION_INCOMPLETE')
                self.assertFalse(report['acceptance_eligible'])
                self.assertEqual(report['input_format'],'v1-execution-bundle/1')
                self.assertEqual(report['results_sha256'],hashlib.sha256(original).hexdigest())
                self.assertEqual(report['execution_evidence']['rows_sha256'],body['rows_sha256'])
                wrong=dict(identity,manifest_sha256='e'*64)
                with patch.object(reporting,'current_identity',return_value=wrong),self.assertRaises(ValueError):
                    C.report_from_bundle(result['path'])
            self.assertEqual(Path(result['path']).read_bytes(),original)

    def test_config_drift_retains_consumption_without_final_publication(self):
        capture=self.capture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            scope,approval,authority,ledger=self.envelope(root,capture)
            def executor(emit):
                with capture.attach(self.runner):
                    self.runner.generate_answer('synthetic')
                    self.provider.MODEL_NAME='unapproved-model'
            with self.assertRaises(ValueError):
                E.execute(scope,approval,authority=authority,ledger_root=ledger,
                    runtime_config=capture.resolved_config,
                    verify_prerequisites=lambda *args:None,executor=executor,
                    capture_snapshot=capture.snapshot,
                    identity_verifier=lambda *args:E.VerifiedInputs(('synthetic-only',)))
            self.assertFalse(Path(scope['output_path']).exists())
            self.assertTrue((ledger/'approval-synthetic-only.json').is_file())
            journals=list(root.glob('.*.attempt-*.jsonl'))
            self.assertEqual(len(journals),1)
            self.assertIn('INTERRUPTED_OR_FAILED',journals[0].read_text())

    def test_abstention_dependency_drift_refuses_closure_and_publication(self):
        original_read=Path.read_bytes
        for name in ('services/citation_service.py','services/answer_semantics.py'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                capture=self.capture()
                root=Path(folder).resolve()
                scope,approval,authority,ledger=self.envelope(root,capture)
                target=C.ROOT/name
                original=original_read(target)
                drift={'enabled':False}
                def changed_read(path):
                    value=original_read(path)
                    return value+b'\n# synthetic source drift\n' if path==target and drift['enabled'] else value
                def executor(emit):
                    # The source reads normally at attach, then drifts before
                    # automatic closure; no actual source file is edited.
                    with patch.object(Path,'read_bytes',changed_read):
                        with capture.attach(self.runner):
                            self.runner.generate_answer('synthetic')
                            drift['enabled']=True
                with self.assertRaises(ValueError):
                    E.execute(scope,approval,authority=authority,ledger_root=ledger,
                        runtime_config=capture.resolved_config,
                        verify_prerequisites=lambda *args:None,executor=executor,
                        capture_snapshot=capture.snapshot,
                        identity_verifier=lambda *args:E.VerifiedInputs(('synthetic-only',)))
                self.assertFalse(capture.snapshot()['capture_complete'])
                self.assertFalse(Path(scope['output_path']).exists())
                self.assertTrue((ledger/'approval-synthetic-only.json').is_file())
                journals=list(root.glob('.*.attempt-*.jsonl'))
                self.assertEqual(len(journals),1)
                self.assertIn('INTERRUPTED_OR_FAILED',journals[0].read_text())
                self.assertEqual(original_read(target),original)


if __name__=='__main__':unittest.main()
