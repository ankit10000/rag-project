"""Pure proposal runtime provenance; no DB, ingestion or provider calls."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
import unittest
from eval.acceptance_preparation.provenance import capture_record, verify_record

HEADER=b'{"schema":"synthetic-run-header/1"}'


def fixture():
    identity=dict(scorer_name='phase35-scorer',scorer_version='2.1.0',scorer_hash='a'*64,
        module_hashes={'eval/scoring_v2/score.py':'b'*64},annotation_hash='c'*64,
        source_revision='d'*40,dataset_revision='e'*40,dataset_identity='f'*64,
        run_header_hash=hashlib.sha256(HEADER).hexdigest(),tier='tier2',split='dev')
    config=dict(chunk_size=100,chunk_overlap=20,chunk_strategy='words',min_page_words=10,
        dedupe='sha1(ws-collapsed lower)',extractor='get_text(sort=True)',document_order=['source.pdf'],
        scoring_context_join='space_join_raw',prompt_context_limit_chars=None,prompt_context_truncation='none')
    chunks=[dict(chunk_id=1,document='source.pdf',page=1,text='First café fact.'),
            dict(chunk_id=2,document='source.pdf',page=2,text='Second fact.')]
    text=' '.join(c['text'] for c in chunks)
    return identity,config,chunks,text


def capture(**changes):
    identity,config,chunks,text=fixture()
    values=dict(identity=identity,resolved_config=config,scoring_chunks=chunks,scoring_context=text,
        prompt_context=text,run_header_bytes=HEADER,origin='ORIGINAL_RUNTIME_CAPTURE',prompt_truncated=False)
    values.update(changes)
    return capture_record(**values)


class RuntimeProvenanceTests(unittest.TestCase):
    def test_stable_explicit_records_and_unverified_origin(self):
        record=capture()
        self.assertEqual(record,capture())
        result=verify_record(record,run_header_bytes=HEADER)
        self.assertEqual(result['verification'],'STRUCTURALLY_VERIFIED')
        self.assertEqual(result['authenticity'],'UNVERIFIED_CALLER_CLAIM')
        self.assertFalse(result['official_acceptance'])
        self.assertEqual(result['origin'],'ORIGINAL_RUNTIME_CAPTURE')
        reconstructed=capture(origin='HISTORICAL_RECONSTRUCTION')
        self.assertEqual(verify_record(reconstructed,run_header_bytes=HEADER)['origin'],'HISTORICAL_RECONSTRUCTION')
        self.assertNotEqual(reconstructed['record_sha256'],record['record_sha256'])

    def test_full_identity_and_header_bytes_required(self):
        identity,_,_,_=fixture()
        for key in identity:
            bad=dict(identity);bad.pop(key)
            if key in ('tier','split'): continue
            with self.subTest(key=key),self.assertRaises(ValueError):capture(identity=bad)
        for field in ('source_revision','dataset_revision'):
            with self.assertRaises(ValueError):capture(identity=dict(identity,**{field:'short'}))
        with self.assertRaises(ValueError):capture(run_header_bytes=HEADER+b' ')
        with self.assertRaises(ValueError):capture(identity=dict(identity,scorer_hash='2.1.0'))

    def test_allowlisted_config_rejects_missing_values_and_secrets(self):
        _,config,_,_=fixture()
        for key in config:
            bad=dict(config);bad.pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):capture(resolved_config=bad)
        for key in ('api_key','DATABASE_URL','provider_credentials','environment'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                capture(resolved_config=dict(config,**{key:'must-not-capture'}))
        for key,value in [('chunk_size',True),('chunk_overlap',100),('chunk_strategy','guessed'),('document_order',['source.pdf','source.pdf'])]:
            with self.assertRaises(ValueError):capture(resolved_config=dict(config,**{key:value}))

    def test_order_context_and_per_chunk_tampering_fails(self):
        for change in ('order','text','hash','reference','config','origin','prompt'):
            record=capture()
            if change=='order':record['scoring_context']['ordered_chunks'].reverse()
            if change=='text':record['scoring_context']['ordered_chunks'][0]['text']='altered'
            if change=='hash':record['scoring_context']['ordered_chunks'][0]['sha256']='0'*64
            if change=='reference':record['scoring_context']['ordered_chunks'][0]['page']=3
            if change=='config':record['resolved_config']['chunk_size']=120
            if change=='origin':record['origin']='HISTORICAL_RECONSTRUCTION'
            if change=='prompt':record['prompt_context']['content']['payload']='altered'
            with self.subTest(change=change),self.assertRaises(ValueError):verify_record(record,run_header_bytes=HEADER)

    def test_prompt_prefix_has_separate_exact_identity_and_truncation(self):
        _,config,_,text=fixture()
        config.update(prompt_context_truncation='prefix_chars',prompt_context_limit_chars=10)
        record=capture(resolved_config=config,prompt_context=text[:10],prompt_truncated=True)
        self.assertNotEqual(record['scoring_context']['content']['sha256'],record['prompt_context']['content']['sha256'])
        self.assertTrue(record['prompt_context']['truncated'])
        self.assertEqual(verify_record(record,run_header_bytes=HEADER)['verification'],'STRUCTURALLY_VERIFIED')
        for prompt,truncated in [(text,True),(text[:10],False)]:
            with self.assertRaises(ValueError):capture(resolved_config=config,prompt_context=prompt,prompt_truncated=truncated)

    def test_external_binary_prompt_is_exact_bytes_without_text_guessing(self):
        _,config,_,_=fixture();config.update(prompt_context_truncation='external',prompt_context_limit_chars=None)
        actual=b'\xff actual prompt context\x00'
        record=capture(resolved_config=config,prompt_context=actual,prompt_truncated=False)
        self.assertEqual(record['prompt_context']['content']['sha256'],hashlib.sha256(actual).hexdigest())
        self.assertEqual(record['prompt_context']['content']['encoding'],'base64')
        self.assertEqual(verify_record(record,run_header_bytes=HEADER)['verification'],'STRUCTURALLY_VERIFIED')

    def test_empty_context_is_explicit_and_missing_chunks_fail(self):
        record=capture(scoring_chunks=[],scoring_context='',prompt_context='')
        self.assertEqual(record['scoring_context']['content']['byte_length'],0)
        for chunks in (None,[{}]):
            with self.assertRaises(ValueError):capture(scoring_chunks=chunks)
        _,_,chunks,_=fixture()
        with self.assertRaises(ValueError):capture(scoring_chunks=chunks+chunks)
        with self.assertRaises(ValueError):capture(scoring_context='reordered or guessed')

    def test_external_identity_and_configuration_constraints_are_checked(self):
        record=capture()
        bad=dict(record['identity'],annotation_hash='0'*64)
        with self.assertRaises(ValueError):verify_record(record,run_header_bytes=HEADER,expected_identity=bad)
        with self.assertRaises(ValueError):verify_record(record,run_header_bytes=HEADER,expected_config={})
        with self.assertRaises(ValueError):capture(origin=[])
        with self.assertRaises(ValueError):capture(identity=dict(record['identity'],gate_policy_id={'credential':'forbidden'}))
        with self.assertRaises(ValueError):capture(identity=dict(record['identity'],acceptance_status='ACCEPTED'))

    def test_external_untruncated_formatted_context_has_no_inferred_relation(self):
        _,config,_,_=fixture()
        config.update(prompt_context_truncation='external',prompt_context_limit_chars=None)
        actual='[S1] Formatted context with references and different assembly.'
        record=capture(resolved_config=config,prompt_context=actual,prompt_truncated=False)
        self.assertNotEqual(record['prompt_context']['content']['sha256'],record['scoring_context']['content']['sha256'])
        self.assertFalse(record['prompt_context']['truncated'])
        self.assertEqual(verify_record(record,run_header_bytes=HEADER)['authenticity'],'UNVERIFIED_CALLER_CLAIM')

    def test_typed_metadata_and_unknown_fields_cannot_hide_behind_python_equality(self):
        _,_,chunks,_=fixture()
        chunks=[dict(chunks[0],text='x')]
        record=capture(scoring_chunks=chunks,scoring_context='x',prompt_context='x')
        for value in (True,1.0):
            altered=copy.deepcopy(record)
            altered['prompt_context']['content']['byte_length']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                verify_record(altered,run_header_bytes=HEADER)
        altered=copy.deepcopy(record);altered['official_acceptance']=0
        with self.assertRaises(ValueError):verify_record(altered,run_header_bytes=HEADER)
        altered=copy.deepcopy(record);altered['unknown']='extra'
        with self.assertRaises(ValueError):verify_record(altered,run_header_bytes=HEADER)

    def test_upload_register_preserves_unknown_original_byte_equality(self):
        from pathlib import Path
        register=json.loads((Path(__file__).parent/'eval/acceptance_preparation/provenance/upload_identity_register.json').read_text())
        self.assertEqual(len(register['uploads']),7)
        for item in register['uploads']:
            self.assertFalse(item['original_bytes_available'])
            self.assertEqual(item['original_to_retained_byte_equality'],'NOT_ESTABLISHED')
            self.assertEqual(hashlib.sha256((Path(__file__).parent/item['retained_repository_path']).read_bytes()).hexdigest(),item['retained_raw_sha256'])
        known=[item for item in register['uploads'] if item['expected_original_sha256'] is not None]
        self.assertEqual(len(known),1)
        self.assertEqual(known[0]['expected_upload_name'],'literal-annotations.c1bbcae(1).json')


if __name__=='__main__':unittest.main()
