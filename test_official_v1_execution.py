"""Synthetic envelope mechanics only: no genuine approvals, database or provider."""
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from eval import official_v1_execution as E


class ExecutionEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-v1-execution-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.ledger = self.root/'ledger'; self.ledger.mkdir()
        self.authority = E.TrustedAuthority('synthetic-owner', b'SYNTHETIC-NOT-REAL-OWNER-KEY-123456')
        self.config = {'run': {'tier': 1, 'split': 'heldout'}, 'synthetic': True}
        self.scope = {'manifest_sha256':'a'*64, 'dataset_sha256':'b'*64,
            'scorer_sha256': {name:'c'*64 for name in E.SCORER_FILES},
            'tier':1, 'split':'heldout', 'output_path':str(self.root/'bundle.json'),
            'ledger_root':str(self.ledger), 'runtime_config_sha256':E._capture_digest(self.config)}
        self.rows = [dict(id='synthetic-case', tier=1, split='heldout', status='answered',
                          latency_s=1.,llm_calls=1,prompt_tokens=2,output_tokens=1,
                          score={'correct':True,'correct_lenient':True,'unsupported':False,
                          'status':'answered','fact_recall':1.,'citation_correctness':1.,
                          'citation_completeness':1.,'fabricated':0,'forbidden_hits':[],
                          'ungrounded_numbers':[],'abstain_ok':True,'partial_ok':None,'conflict_ok':None})]
        self.calls=[]

    def approval(self, scope=None, identifier='synthetic-approval'):
        payload={'schema':'v1-execution-approval/1','approval_id':identifier,
            'key_id':self.authority.key_id,'scope':copy.deepcopy(scope or self.scope),
            'review_evidence_sha256':'d'*64,'policy_evidence_sha256':'e'*64}
        return {'payload':payload,'hmac_sha256':hmac.new(self.authority.key,E.canonical(payload),hashlib.sha256).hexdigest()}

    def capture(self):
        data={'schema':'official-v1-runtime-capture/1','capture_complete':True,
            'resolved_config':copy.deepcopy(self.config), 'config_sha256':E._capture_digest(self.config),
            'events':[{'sequence':0,'kind':'provider_prompt','requested_model':'synthetic-model',
             'prompt':{'sha256':'f'*64,'utf8_bytes':4},'retry_options_sha256':'e'*64,'outcome':'returned'}, {'sequence':1,'kind':'scoring_context','outcome':'returned',
             'case_sha256':'a'*64,'result_sha256':'b'*64,
             'ordered_chunk_pair_sha256':'c'*64,'context_ids_sha256':'d'*64,
             'exact_context':{'sha256':'e'*64,'utf8_bytes':5},
             'case_id_sha256':E.digest(self.rows[0]['id'].encode()),'score_sha256':E._capture_digest(self.rows[0]['score'])}]}
        data['capture_sha256']=E._capture_digest(data)
        return data

    def run_envelope(self, approval=None, **kwargs):
        def executor(emit):
            self.calls.append('executor')
            for row in self.rows:emit(row)
        options=dict(authority=self.authority, ledger_root=self.ledger, runtime_config=self.config,
            verify_prerequisites=lambda payload,scope: self.calls.append('prerequisites'),
            identity_verifier=lambda scope,config: E.VerifiedInputs(('synthetic-case',)),
            executor=executor, capture_snapshot=self.capture)
        options.update(kwargs)
        return E.execute(self.scope, approval or self.approval(), **options)

    def test_success_hashes_capture_and_v1_rows_remain_unchanged(self):
        original=copy.deepcopy(self.rows)
        result=self.run_envelope()
        body=E.verify_bundle(result['path'])
        self.assertEqual(body['rows'],original)
        self.assertEqual(body['error_rows'],0)
        self.assertEqual(Path(result['path']).stat().st_mode & 0o777,0o400)
        self.assertFalse(body['acceptance_eligible'])
        self.assertEqual(body['formal_outcome'],'FORMAL_EVALUATION_INCOMPLETE')
        self.assertEqual(result['sha256'],E.digest(Path(result['path']).read_bytes()))
        self.assertEqual(len(list(self.ledger.iterdir())),2)
        self.assertNotIn(self.authority.key.decode(),repr(self.authority))

    def test_approval_mutation_after_authentication_cannot_change_bound_evidence(self):
        approval=self.approval();original_hash=E.digest(E.canonical(approval))
        def executor(emit):
            approval['payload']['review_evidence_sha256']='f'*64
            emit(self.rows[0])
        result=self.run_envelope(approval,executor=executor)
        body=E.verify_bundle(result['path'])
        self.assertEqual(body['approval_sha256'],original_hash)
        self.assertEqual(body['review_evidence_sha256'],'d'*64)

    def test_callback_mutation_cannot_change_internal_signed_scope_or_runtime(self):
        unsigned=self.root/'unsigned.json'
        def identity(scope,config):
            scope['output_path']=str(unsigned);config['synthetic']=False
            return E.VerifiedInputs(('synthetic-case',))
        def prerequisites(payload,scope):
            scope['output_path']=str(unsigned)
            payload['review_evidence_sha256']='f'*64
        result=self.run_envelope(identity_verifier=identity,verify_prerequisites=prerequisites)
        body=E.verify_bundle(result['path'])
        self.assertEqual(body['scope'],self.scope)
        self.assertEqual(body['runtime']['resolved_config'],self.config)
        self.assertFalse(unsigned.exists())
        self.assertEqual(body['review_evidence_sha256'],'d'*64)

    def test_invalid_signature_refuses_before_any_callback_or_write(self):
        approval=self.approval();approval['hmac_sha256']='f'*64
        with self.assertRaises(ValueError):self.run_envelope(approval)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.ledger.iterdir()),[])
        self.assertFalse(Path(self.scope['output_path']).exists())

    def test_each_signed_scope_identity_is_bound(self):
        for key,value in [('manifest_sha256','f'*64),('dataset_sha256','f'*64),
                          ('tier',2),('split','dev'),('output_path',str(self.root/'other')),
                          ('runtime_config_sha256','f'*64),('ledger_root',str(self.root))]:
            approval=self.approval();approval['payload']['scope'][key]=value
            approval['hmac_sha256']=hmac.new(self.authority.key,E.canonical(approval['payload']),hashlib.sha256).hexdigest()
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_envelope(approval)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.ledger.iterdir()),[])

    def test_prerequisite_refusal_or_false_flag_never_executes_or_consumes(self):
        def refuse(*args):raise ValueError('synthetic missing actual human evidence')
        for function in (refuse,lambda *args:False,lambda *args:True):
            with self.assertRaises(ValueError):self.run_envelope(verify_prerequisites=function)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.ledger.iterdir()),[])

    def test_pre_execution_runtime_mismatch_refuses(self):
        config=copy.deepcopy(self.config);config['synthetic']=False
        with self.assertRaises(ValueError):self.run_envelope(runtime_config=config)
        self.assertEqual(self.calls,[])
        self.assertEqual(list(self.ledger.iterdir()),[])

    def test_approval_consumption_and_ledger_cannot_be_relocated_after_interruption(self):
        def interrupted(emit):
            self.calls.append('executor');emit(self.rows[0]);raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_envelope(executor=interrupted)
        self.assertFalse(Path(self.scope['output_path']).exists())
        with self.assertRaises(FileExistsError):self.run_envelope()
        other=self.root/'other-ledger';other.mkdir()
        with self.assertRaises(ValueError):self.run_envelope(ledger_root=other)
        self.assertEqual(self.calls.count('executor'),1)
        journal=next(self.root.glob('.*attempt*.jsonl')).read_text()
        self.assertIn('INTERRUPTED_OR_FAILED',journal)
        self.assertIn('synthetic-case',journal)

    def test_output_reservation_blocks_different_signed_approval_after_failure(self):
        def fail(emit):raise RuntimeError('SENSITIVE synthetic failure text')
        with self.assertRaises(RuntimeError):self.run_envelope(executor=fail)
        with self.assertRaises(FileExistsError):self.run_envelope(self.approval(identifier='second'))
        journal=next(self.root.glob('.*attempt*.jsonl')).read_text()
        self.assertNotIn('SENSITIVE',journal)
        self.assertNotIn('executor',self.calls)

    def test_concurrent_different_approvals_same_output_execute_once(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def executor(emit):
            self.calls.append('executor');entered.set();release.wait(3);emit(self.rows[0])
        def first():
            try:self.run_envelope(executor=executor)
            except BaseException as error:errors.append(error)
        worker=threading.Thread(target=first);worker.start()
        self.assertTrue(entered.wait(3))
        try:
            with self.assertRaises(FileExistsError):self.run_envelope(self.approval(identifier='other'))
        finally:release.set();worker.join(3)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,[])
        self.assertEqual(self.calls.count('executor'),1)

    def test_existing_output_and_symlink_parents_refuse_before_executor(self):
        target=Path(self.scope['output_path']);target.symlink_to(self.root/'missing')
        with self.assertRaises(FileExistsError):self.run_envelope()
        self.assertTrue(target.is_symlink());self.assertEqual(self.calls,['prerequisites'])
        self.assertEqual(list(self.ledger.iterdir()),[])
        target.unlink()
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        self.scope['output_path']=str(alias/'new.json')
        with self.assertRaises(OSError):self.run_envelope()
        self.assertEqual(list(self.ledger.iterdir()),[])

    def test_incomplete_or_duplicate_rows_never_publish(self):
        for mode in ('missing','duplicate'):
            with self.subTest(mode=mode):
                scope=copy.deepcopy(self.scope);scope['output_path']=str(self.root/(mode+'.json'))
                old=self.scope;self.scope=scope
                try:
                    def executor(emit):
                        if mode=='duplicate':emit(self.rows[0]);emit(self.rows[0])
                    with self.assertRaises((ValueError,E.IncompleteRunError)):
                        self.run_envelope(self.approval(identifier=mode),executor=executor)
                    self.assertFalse(Path(scope['output_path']).exists())
                finally:self.scope=old

    def test_missing_or_tampered_runtime_capture_cannot_publish(self):
        for index,change in enumerate((lambda c:{},lambda c:dict(c,capture_complete=False),
                                      lambda c:dict(c,capture_sha256='f'*64))):
            old=self.scope;self.scope=copy.deepcopy(old);self.scope['output_path']=str(self.root/f'bad-{index}.json')
            try:
                with self.assertRaises(ValueError):self.run_envelope(self.approval(identifier=f'bad-{index}'),capture_snapshot=lambda:change(self.capture()))
                self.assertFalse(Path(self.scope['output_path']).exists())
            finally:self.scope=old

    def test_complete_canonical_error_rows_keep_nulls_and_not_acceptance(self):
        self.rows[0]['status']='error'
        self.rows[0]['score'].update(correct=False,correct_lenient=False,status='error',abstain_ok=None)
        result=self.run_envelope()
        body=E.verify_bundle(result['path'])
        self.assertEqual(body['error_rows'],1)
        self.assertIsNone(body['rows'][0]['score']['abstain_ok'])
        self.assertFalse(body['acceptance_eligible'])

    def test_final_publication_collision_preserves_foreign_bytes(self):
        original_link=E.os.link
        def collide(*args,**kwargs):
            Path(self.scope['output_path']).write_bytes(b'FOREIGN')
            return original_link(*args,**kwargs)
        with patch.object(E.os,'link',side_effect=collide),self.assertRaises(FileExistsError):self.run_envelope()
        self.assertEqual(Path(self.scope['output_path']).read_bytes(),b'FOREIGN')
        with self.assertRaises(FileExistsError):self.run_envelope()

    def test_post_link_fsync_failure_keeps_complete_bundle_and_consumed_claim(self):
        original_link=E.os.link;original_sync=E.os.fsync;linked=[False]
        def link(*args,**kwargs):
            value=original_link(*args,**kwargs);linked[0]=True;return value
        def sync(fd):
            if linked[0] and os.path.isdir('/dev/fd/'+str(fd)):
                raise OSError('synthetic directory durability failure')
            return original_sync(fd)
        with patch.object(E.os,'link',side_effect=link),patch.object(E.os,'fsync',side_effect=sync):
            with self.assertRaises(E.PublicationDurabilityError):self.run_envelope()
        self.assertTrue(E.verify_bundle(self.scope['output_path'])['execution_complete'])
        with self.assertRaises(FileExistsError):self.run_envelope()


    def test_malformed_v1_rows_are_not_sealed_as_complete(self):
        mutations=[lambda r:r.update(status='mystery'),lambda r:r['score'].update(correct=1),
            lambda r:r['score'].update(citation_correctness=1.1),
            lambda r:r.update(latency_s=float('nan')),lambda r:r.update(llm_calls=True),
            lambda r:r['score'].update(unsupported='false'),lambda r:r['score'].update(status='error')]
        original=copy.deepcopy(self.rows)
        for index,mutation in enumerate(mutations):
            old=self.scope;self.scope=copy.deepcopy(old);self.scope['output_path']=str(self.root/f'malformed-{index}.json')
            self.rows=copy.deepcopy(original);mutation(self.rows[0])
            try:
                with self.subTest(index=index),self.assertRaises(ValueError):
                    self.run_envelope(self.approval(identifier=f'malformed-{index}'))
                self.assertFalse(Path(self.scope['output_path']).exists())
            finally:self.scope=old
        self.rows=original

    def test_case_context_cannot_be_substituted_even_with_recomputed_capture_hash(self):
        def wrong_context():
            capture=self.capture();capture['events'][1]['case_id_sha256']='f'*64
            capture.pop('capture_sha256');capture['capture_sha256']=E._capture_digest(capture)
            return capture
        with self.assertRaises(ValueError):self.run_envelope(capture_snapshot=wrong_context)
        self.assertFalse(Path(self.scope['output_path']).exists())

    def test_kind_only_events_do_not_establish_actual_hash_capture(self):
        def incomplete_fields():
            capture=self.capture();capture['events'][0].pop('prompt')
            capture.pop('capture_sha256');capture['capture_sha256']=E._capture_digest(capture)
            return capture
        with self.assertRaises(ValueError):self.run_envelope(capture_snapshot=incomplete_fields)
        self.assertFalse(Path(self.scope['output_path']).exists())

    def test_source_eligibility_drift_during_execution_refuses_publication(self):
        values=iter([E.VerifiedInputs(('synthetic-case',)),E.VerifiedInputs(('changed-case',))])
        with self.assertRaises(ValueError):self.run_envelope(identity_verifier=lambda *args:next(values))
        self.assertFalse(Path(self.scope['output_path']).exists())

    def test_bundle_parser_rejects_duplicate_keys_and_nonfinite_json(self):
        for raw in (b'{"body":{},"body":{},"body_sha256":"x"}',b'{"body":NaN}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):E.verify_bundle_bytes(raw)

    def test_tampered_bundle_cannot_hide_duplicate_rows(self):
        result=self.run_envelope();envelope=json.loads(Path(result['path']).read_bytes())
        body=envelope['body'];body['rows'].append(copy.deepcopy(body['rows'][0]))
        body['rows_sha256']=E.digest(E.canonical(body['rows']))
        envelope['body_sha256']=E.digest(E.canonical(body))
        with self.assertRaises(ValueError):E.verify_bundle_bytes(E.canonical(envelope))


if __name__=='__main__':unittest.main()
