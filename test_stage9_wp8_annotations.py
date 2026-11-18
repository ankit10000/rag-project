"""Deterministic WP8 annotation audit and evidence-preservation tests."""
import testsafe
testsafe.require_scratch_db()
import copy
import csv
import io
import json
import unittest
from zipfile import ZipFile
from eval.acceptance_preparation.annotations import audit_annotations, ledger_csv, workbook_inventory
from eval.framework.integrity import dataset_hash


def fixtures():
    docs = {'source.pdf': ['The fee is 65 dollars. A previous quote said 85 dollars.']}
    case = dict(id='synthetic', question='What fee?', category='direct_factual',
                gold_facts=[['65 dollars']], forbidden=['85 dollars'],
                gold_sources=[dict(document='source.pdf', page=1, span='The fee is 65 dollars.')],
                history=[dict(role='user', content='Fee?'), dict(role='assistant', content='85 dollars')],
                expect_conflict=False)
    cases = [case]
    ann = dict(schema='phase35-scorer-annotations/1', dataset_version='synthetic',
               dataset_sha256=dataset_hash(cases), cases={'synthetic': {'forbidden': [dict(text='85 dollars',kind='literal',source='dataset')]}})
    pin = dict(dataset_version='synthetic', dataset_sha256=dataset_hash(cases),
               file_sha256={f'eval/phase35/data_{letter}.py': 'a'*64 for letter in 'ABCD'},
               git_rev='b'*40, manifest_content_sha256='c'*64)
    return docs, cases, ann, pin


def run(ann=None, **kwargs):
    docs, cases, default, pin = fixtures()
    return audit_annotations(json.dumps(default if ann is None else ann).encode(),
                             kwargs.get('cases', cases), kwargs.get('docs', docs), dataset_pin=kwargs.get('pin', pin))


class AnnotationAuditTests(unittest.TestCase):
    def test_valid_structure_remains_independent_review_pending(self):
        result = run()
        self.assertEqual(result['structural_counts'], {'VALID': 1})
        self.assertEqual(result['disposition_counts'], {'NEEDS_INDEPENDENT_REVIEW': 1})
        original = fixtures()[2]['cases']['synthetic']
        self.assertEqual(json.loads(result['records'][0]['original_annotation_json']), original)
        references = json.loads(result['records'][0]['source_refs_json'])
        self.assertEqual(references[0]['document'], 'source.pdf')
        self.assertEqual(references[0]['page'], 1)
        self.assertEqual(references[0]['page_text'], fixtures()[0]['source.pdf'][0])
        self.assertEqual(len(references[0]['page_text_sha256']), 64)

    def test_av1_to_av10_invalid_inputs_are_reported_without_repair(self):
        for code in range(1,11):
            docs, cases, ann, pin = fixtures()
            entry = ann['cases']['synthetic']
            if code == 1: entry['invented_key'] = []
            if code == 2: ann['dataset_sha256'] = '0'*64
            if code == 3: ann['cases'].clear()
            if code == 4: entry['forbidden'].clear()
            if code == 5: entry['forbidden'][0]['allowed_with'] = ['fee']
            if code == 6: entry['forbidden'].append(dict(text='65 dollars', kind='assertion',source='annotation'))
            if code == 7: entry['history_wrong_values'] = [dict(text='85 dollars',turn=0)]
            if code == 8: entry['negatable_groups'] = [99]
            if code == 9: entry['disclosure'] = [dict(pattern_set='generic_leak_v1')]
            if code == 10: entry['forbidden'].append(copy.deepcopy(entry['forbidden'][0]))
            original = copy.deepcopy(ann)
            result = run(ann)
            errors = ' '.join(result['validation_errors']) + ' '.join(record['validation_errors_json'] for record in result['records'])
            with self.subTest(rule=code):
                self.assertIn(f'AV-{code}:', errors)
                self.assertEqual(ann, original)
                self.assertTrue(all(record['review_disposition']=='INVALID' for record in result['records']))

    def test_duplicate_json_and_malformed_original_documents_preserved(self):
        docs, cases, _, pin = fixtures()
        for data in [b'{"cases":{"same":{},"same":{}}}', b'null', b'NaN', b'not json']:
            with self.subTest(data=data):
                result = audit_annotations(data,cases,docs,dataset_pin=pin)
                self.assertEqual(result['records'][0]['case_id'], '__FILE__')
                self.assertEqual(result['records'][0]['original_annotation_json'], data.decode())
                self.assertEqual(result['records'][0]['review_disposition'], 'INVALID')

    def test_missing_unknown_and_provenance_mismatch_cases(self):
        docs,cases,ann,pin = fixtures()
        ann['cases']['unknown'] = {}
        result=run(ann)
        record=next(row for row in result['records'] if row['case_id']=='unknown')
        self.assertIn('unknown case id',record['validation_errors_json'])
        ann['cases'].pop('synthetic')
        result=run(ann)
        record=next(row for row in result['records'] if row['case_id']=='synthetic')
        self.assertEqual(record['original_annotation_json'],'')
        self.assertIn('missing annotation',record['validation_errors_json'])
        for key in pin:
            altered=dict(pin); altered.pop(key)
            self.assertEqual(run(pin=altered)['structural_counts'], {'INVALID':1})
        self.assertEqual(run(pin=dict(pin,dataset_version='wrong'))['structural_counts'], {'INVALID':1})

    def test_source_reference_validation_reports_exact_failed_link(self):
        docs,cases,ann,pin=fixtures()
        docs['source.pdf'][0]='Does not contain the expected span.'
        result=run(ann,docs=docs)
        self.assertIn('gold span absent',result['records'][0]['validation_errors_json'])
        self.assertIn('Does not contain',result['records'][0]['source_refs_json'])
        result=run(ann,docs={})
        self.assertIn('missing document/page',result['records'][0]['validation_errors_json'])

    def test_csv_is_deterministic_and_roundtrips_original_annotations(self):
        audit=run()
        first=ledger_csv(audit)
        self.assertEqual(first,ledger_csv(audit))
        records=list(csv.DictReader(io.StringIO(first)))
        self.assertEqual(records[0]['original_annotation_json'],audit['records'][0]['original_annotation_json'])
        self.assertEqual(records[0]['review_disposition'],'NEEDS_INDEPENDENT_REVIEW')

    def test_readonly_ooxml_inventory_counts_actual_review_cells(self):
        output=io.BytesIO()
        with ZipFile(output,'w') as archive:
            archive.writestr('xl/worksheets/sheet1.xml', '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row><c r="A1" t="inlineStr"><is><t>case_id</t></is></c><c r="B1" t="inlineStr"><is><t>reviewer_decision</t></is></c></row>
<row><c r="A2" t="inlineStr"><is><t>one</t></is></c><c r="B2" t="inlineStr"><is><t>VALID</t></is></c></row>
<row><c r="A3" t="inlineStr"><is><t>two</t></is></c></row></sheetData></worksheet>''')
        data=output.getvalue()
        result=workbook_inventory(data)
        self.assertEqual(result['worksheets'][0]['decisions'], {'VALID':1,'BLANK':1})
        self.assertEqual(result['worksheets'][0]['case_records'],2)
        self.assertEqual(data,output.getvalue())


if __name__ == '__main__':
    unittest.main()
