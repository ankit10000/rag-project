"""WP7 pure exact-input evidence tests; no database, providers or evaluation."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from eval.runner_preparation import provenance as p
from eval.framework.hashing import portable_sha256


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixtures():
    annotation = p.canonical_bytes({'schema': 'phase35-scorer-annotations/1',
        'dataset_version': 'synthetic', 'dataset_sha256': 'a'*64,
        'cases': {'synthetic-dev': {}}})
    pin = dict(manifest_content_sha256='b'*64, dataset_version='synthetic',
        pin_source='run_header', git_rev='c'*40,
        file_sha256={f'eval/phase35/data_{letter}.py': 'd'*64 for letter in 'ABCD'})
    source = p.canonical_bytes(dict(id='synthetic-dev', tier=1, split='dev', score={'correct': True})) + b'\n'
    items = [dict(id=1, document='synthetic.pdf', page=1, text='  Exact café facts.  ', gold=True)]
    history = [dict(role='user', content='What is the fee?'), dict(role='assistant', content='An earlier wrong answer.')]
    record = p.make_context_record('synthetic-dev', 1, items, history)
    identity = dict(name='phase35-scorer', version='2.1.0', sha256='e'*64,
                    annotations_sha256=portable_sha256(annotation, 'text'))
    return source, annotation, pin, items, history, record, identity


class ProvenanceTests(unittest.TestCase):
    def test_exact_context_hashes_and_history_roles_are_preserved(self):
        _, _, _, items, history, record, _ = fixtures()
        self.assertEqual(record['context_text'], items[0]['text'].strip())
        self.assertEqual(record['context_sha256'], digest(items[0]['text'].strip().encode()))
        self.assertEqual(record['chunks'][0]['sha256'], digest(items[0]['text'].encode()))
        self.assertEqual(record['history'], history)
        self.assertEqual(p.verify_context_record(record), record)
        record['history'][0]['content'] = 'mutated'
        self.assertNotEqual(history[0]['content'], 'mutated')
        with self.assertRaises(ValueError):
            p.verify_context_record(record)

    def test_tier2_preserves_unstripped_text_and_order(self):
        _, _, _, items, history, _, _ = fixtures()
        items.append(dict(id=2, document='synthetic.pdf', page=1, text='Other exact text\n', gold=False))
        record = p.make_context_record('synthetic-dev', 2, items, history)
        self.assertEqual(record['context_text'], ' '.join(item['text'] for item in items))
        reordered = p.make_context_record('synthetic-dev', 2, list(reversed(items)), history)
        self.assertNotEqual(record['context_sha256'], reordered['context_sha256'])
        with self.assertRaises(ValueError):
            p.make_context_record('synthetic-dev', 2, items, history, context_text=' '.join(i['text'].strip() for i in items))

    def test_missing_metadata_is_preserved_only_for_tier1(self):
        _, _, _, items, history, _, _ = fixtures()
        items[0].update(document=None, page=None)
        self.assertIsNone(p.make_context_record('synthetic-dev', 1, items, history)['chunks'][0]['document'])
        with self.assertRaises(ValueError):
            p.make_context_record('synthetic-dev', 2, items, history)
        items[0]['document'] = 'incomplete.pdf'
        with self.assertRaises(ValueError):
            p.make_context_record('synthetic-dev', 1, items, history)

    def test_missing_duplicate_and_malformed_context_is_rejected(self):
        _, _, _, items, history, _, _ = fixtures()
        invalid = [[], None, [dict(items[0], id=True)], [dict(items[0], page=False)],
                   [dict(items[0], text=' ')], [items[0], dict(items[0], text='distinct')],
                   [items[0], dict(items[0], id=2, text='EXACT   café facts.')]]
        for bad in invalid:
            with self.subTest(items=bad), self.assertRaises(ValueError):
                p.make_context_record('synthetic-dev', 1, bad, history)
        for history in [None, [{'role': 'system', 'content': 'guess'}], [{'content': 'no role'}]]:
            with self.subTest(history=history), self.assertRaises(ValueError):
                p.make_context_record('synthetic-dev', 1, items, history)

    def test_context_limits_and_per_chunk_digest_tampering_fail(self):
        _, _, _, items, history, record, _ = fixtures()
        for mutation in [('sha256', '0'*64), ('text', 'altered'), ('page', 3)]:
            altered = copy.deepcopy(record)
            altered['chunks'][0][mutation[0]] = mutation[1]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                p.verify_context_record(altered)
        for bad in [[dict(items[0], text='x'*12001)], [dict(items[0], id=i, text=str(i)) for i in range(1, 10)]]:
            with self.assertRaises(ValueError):
                p.make_context_record('synthetic-dev', 1, bad, history)

    def test_complete_input_proof_is_deterministic_and_binds_all_inputs(self):
        source, ann, pin, _, _, record, identity = fixtures()
        proof = p.build_provenance(source, ann, pin, [record], scorer_identity=identity)
        self.assertEqual(proof, p.build_provenance(source, ann, pin, [record], scorer_identity=identity))
        self.assertEqual(p.validate_provenance(proof, source, ann, dataset_pin=pin), proof)
        for changed_source, changed_ann in [(source+b' ', ann), (source, ann+b' ')]:
            with self.assertRaises(ValueError):
                p.validate_provenance(proof, changed_source, changed_ann)
        altered = copy.deepcopy(proof)
        altered['contexts'][0]['chunks'][0]['page'] = 3
        with self.assertRaises(ValueError):
            p.validate_provenance(altered, source, ann)
        self.assertEqual(proof['scorer'], identity)
        with self.assertRaises(ValueError):
            p.build_provenance(b'{}\n', ann, pin, [record])

    def test_missing_annotations_pins_and_duplicates_never_fabricated(self):
        source, ann, pin, _, _, record, identity = fixtures()
        for malformed in (None, '', [], b'{"id":"synthetic-dev","tier":true}'):
            with self.subTest(source=malformed), self.assertRaises(ValueError):
                p.build_provenance(malformed, ann, pin, [record])
        for bad_ann in [b'{}', b'null', b'{"schema":"a","schema":"b"}', b'NaN']:
            with self.subTest(annotation=bad_ann), self.assertRaises(ValueError):
                p.build_provenance(source, bad_ann, pin, [record])
        for key in pin:
            bad = dict(pin); bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.build_provenance(source, ann, bad, [record])
        with self.assertRaises(ValueError):
            p.build_provenance(source, ann, pin, [record, record])
        with self.assertRaises(ValueError):
            p.build_provenance(source, ann, pin, [dict(record, case_id='unknown')])
        with self.assertRaises(ValueError):
            p.build_provenance(source, ann, pin, [record], scorer_identity=dict(identity, annotations_sha256='0'*64))

    def test_comparison_proof_binds_actual_source_metadata_and_annotations(self):
        source, ann, pin, _, _, record, identity = fixtures()
        output = [dict(id='synthetic-dev', tier=1, split='dev', v1_stored={'correct': True},
                       context_mode='tier1_reconstructed_exact', reconstruction_status='exact')]
        meta = dict(id='synthetic-dev', tier=1, context_mode=output[0]['context_mode'],
                    reconstruction_status='exact', context_sha256=record['context_sha256'], chunk_sha256={})
        sidecar = dict(sidecar_format='phase35-scoring-sidecar/1', scorer=identity,
                       source_results=dict(sha256=digest(source), rows=1),
                       dataset=dict(run_time=pin), rows=[meta])
        proof = p.validate_comparison_inputs(source, ann, sidecar, output)
        self.assertEqual(proof['schema'], p.COMPARISON_SCHEMA)
        for key in ('source_results', 'scorer', 'dataset'):
            for value in (None, [], ''):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    p.validate_comparison_inputs(source, ann, dict(sidecar, **{key:value}), output)
        with self.assertRaises(ValueError):
            p.validate_comparison_inputs(source, ann, dict(sidecar, source_results=dict(sha256=digest(source), rows=True)), output)
        for key, value in [('id', 'changed'), ('tier', 2), ('v1_stored', {'correct': False}), ('context_mode', 'fallback')]:
            altered = copy.deepcopy(output); altered[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_comparison_inputs(source, ann, sidecar, altered)
        for alteration in [dict(meta, reconstruction_status='mismatch:ref'), dict(meta, context_sha256=None), dict(meta, chunk_sha256=None), dict(meta, chunk_sha256={'1': 'bad'})]:
            bad = dict(sidecar, rows=[alteration])
            with self.assertRaises(ValueError):
                p.validate_comparison_inputs(source, ann, bad, output)
        with self.assertRaises(ValueError):
            p.validate_comparison_inputs(source+b' ', ann, sidecar, output)

    def test_strict_reconstruction_rejects_duplicate_and_missing_refs(self):
        table = [dict(id=1, document='source.pdf', page=1, content='exact', sha256=digest(b'exact'))]
        ref = dict(chunk_id=1, document_name='source.pdf', page_number=1)
        case = dict(gold_sources=[dict(document='source.pdf', page=1)])
        row = dict(retrieved=[ref], citations=[])
        result = p.verify_reconstruction(row, case, {}, tier=2, table=table)
        self.assertEqual(result[2:], ('exact', 'exact', 'tier2_reconstructed_exact'))
        for bad in [dict(row, retrieved=[ref, ref]), dict(row, citations=None), dict(row, retrieved=None), dict(row, retrieved=[dict(ref, page_number=2)]), dict(row, citations=[ref, ref]), dict(row, retrieved=[dict(ref, document='other.pdf')])]:
            with self.subTest(row=bad), self.assertRaises(ValueError):
                p.verify_reconstruction(bad, case, {}, tier=2, table=table)
        with self.assertRaises(ValueError):
            p.verify_reconstruction(row, case, {}, tier=2, table=table+table)
        with self.assertRaises(ValueError):
            p.verify_reconstruction(dict(context=[], citations=[]), case, {}, tier=1)
        exact = ({1: ('source.pdf', 1)}, {1}, 'exact', 'exact', 'tier1_reconstructed_exact')
        with patch('eval.scoring_v2.context.verify_tier1', return_value=exact):
            self.assertEqual(p.verify_reconstruction(dict(context=[dict(chunk_id=1)], citations=[]), case, {}, tier=1), exact)

    def test_explicit_empty_context_is_distinct_from_missing(self):
        record = p.make_context_record('synthetic-dev', 2, [], [], context_text='')
        self.assertEqual(record['context_sha256'], digest(b''))
        self.assertEqual(p.verify_context_record(record), record)
        with self.assertRaises(ValueError):
            p.make_context_record('synthetic-dev', 2, [], [])
        case = dict(gold_sources=[])
        result = p.verify_reconstruction(dict(retrieved=[], citations=[]), case, {}, tier=2, table=[])
        self.assertEqual(result[2:], ('', 'exact', 'tier2_reconstructed_exact'))
        with self.assertRaises(ValueError):
            p.verify_reconstruction(dict(citations=[]), case, {}, tier=2, table=[])

    def test_canonical_json_order_and_unicode_and_nonfinite_validation(self):
        self.assertEqual(p.canonical_bytes({'b': 'café', 'a': 1}), p.canonical_bytes({'a': 1, 'b': 'café'}))
        self.assertIn('café'.encode(), p.canonical_bytes({'a': 'café'}))
        with self.assertRaises(ValueError):
            p.canonical_bytes({'bad': float('nan')})


if __name__ == '__main__':
    unittest.main()
