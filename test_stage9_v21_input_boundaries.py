"""Focused regressions for ambiguous annotation bytes and accepted ref aliases."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from eval.scoring_v2 import context, rescore


class InputBoundaryTests(unittest.TestCase):
    def test_duplicate_annotation_keys_exit7_before_scoring_or_outputs(self):
        fixtures = [b'{"schema":"first","schema":"second"}',
                    b'{"cases":{"same":{},"same":{}}}',
                    b'{"cases":{"same":{"forbidden":[],"forbidden":[]}}}']
        for data in fixtures:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source, annotations, output = root/'source.jsonl', root/'annotations.json', root/'output.v2.jsonl'
                source.write_bytes(b'original-source\n')
                annotations.write_bytes(data)
                with patch.object(rescore, 'load_pinned_dataset', return_value=({}, [], {})), \
                     patch.object(rescore, 'read_rows') as read_rows, \
                     contextlib.redirect_stderr(io.StringIO()) as stderr:
                    code = rescore.main(['--results',str(source),'--tier','1','--dataset-rev','synthetic',
                                         '--annotations',str(annotations),'--output',str(output)])
                self.assertEqual(code, 7)
                self.assertIn('duplicate annotation JSON key', stderr.getvalue())
                read_rows.assert_not_called()
                self.assertEqual(source.read_bytes(), b'original-source\n')
                self.assertEqual(annotations.read_bytes(), data)
                self.assertEqual(sorted(path.name for path in root.iterdir()), ['annotations.json','source.jsonl'])

    def test_unique_annotation_json_values_remain_unchanged(self):
        source = {'cases': {'one': {'forbidden': [{'text':'original','kind':'literal'}]}}}
        self.assertEqual(json.loads(json.dumps(source), object_pairs_hook=rescore._unique_json_object), source)

    def inputs(self):
        text = 'Exact source text.'
        table = [dict(id=1, document='source.pdf', page=2, content=text, sha256=context.text_sha256(text))]
        case = dict(gold_sources=[dict(document='source.pdf',page=2)])
        return table, case

    def test_tier2_alias_and_canonical_references_have_identical_results(self):
        table, case = self.inputs()
        canonical = dict(chunk_id=1, document_name='source.pdf',page_number=2)
        alias = dict(chunk_id=1, document='source.pdf',page=2)
        expected = context.verify_tier2(dict(retrieved=[canonical],citations=[alias]),table,case)
        for retrieved, citation in [(alias,alias),(canonical,canonical),(alias,canonical), (dict(alias,**canonical),alias)]:
            with self.subTest(retrieved=retrieved,citation=citation):
                self.assertEqual(context.verify_tier2(dict(retrieved=[retrieved],citations=[citation]),table,case),expected)
        self.assertEqual(expected[3], 'exact')

    def test_conflicting_or_missing_reference_aliases_return_mismatch(self):
        table, case = self.inputs()
        reference = dict(chunk_id=1,document_name='source.pdf',page_number=2)
        for bad in [dict(reference,document='other.pdf'), dict(reference,page=3),
                    {'chunk_id':1}, dict(reference,page_number='2')]:
            with self.subTest(reference=bad):
                result=context.verify_tier2(dict(retrieved=[bad],citations=[]),table,case)
                self.assertEqual(result[3:], ('mismatch:ref','unavailable_mismatch'))
                self.assertIsNone(result[2])

    def test_malformed_citation_array_returns_mismatch_not_typeerror(self):
        table,case=self.inputs()
        ref=dict(chunk_id=1,document_name='source.pdf',page_number=2)
        for citations in [None, '', {}, [None]]:
            with self.subTest(citations=citations):
                result=context.verify_tier2(dict(retrieved=[ref],citations=citations),table,case)
                self.assertEqual(result[3:], ('mismatch:ref','unavailable_mismatch'))

    def test_rescore_alias_references_keep_retrieval_metrics_and_publish(self):
        table, case = self.inputs()
        case = dict(case,id='synthetic',question='Question?',history=[])
        row = dict(id='synthetic',tier=2,split='dev',question='Question?',answer='Exact source text.',
                   status='answered',citations=[],score={'correct':True},
                   retrieved=[dict(chunk_id=1,document='source.pdf',page=2)])
        pin=dict(pin_source='operator_git_rev',dataset_version='synthetic')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source.jsonl'; annotation=root/'annotations.json'
            source.write_text(json.dumps(row)+'\n')
            annotation.write_text(json.dumps({'dataset_version':'synthetic','cases':{'synthetic':{}}}))
            args=SimpleNamespace(results=str(source),annotations=str(annotation),output=str(root/'out.v2.jsonl'),
                run_header=None,dataset_rev='synthetic',tier=2,chunk_config='100,20,words',acceptance=False,allow_page_superset=False)
            with patch.object(rescore,'load_pinned_dataset',return_value=({},[case],pin)), \
                 patch.object(rescore,'pipeline_metadata',return_value={}), \
                 patch.object(rescore,'read_rows',return_value=([row],{'synthetic':case})), \
                 patch.object(rescore,'render_pages',return_value={}), \
                 patch.object(context,'build_tier2_chunks',return_value=table), \
                 patch.object(rescore,'score_generic',return_value={'correct':True}), \
                 patch('eval.scoring_v2.validate_annotations',return_value=[]), \
                 patch('eval.scoring_v2.score_case',return_value={'correct':True}):
                sidecar=rescore.rescore(args)
            emitted=json.loads(Path(args.output).read_text())
            self.assertEqual(sidecar['counts']['exact'],1)
            self.assertEqual(emitted['v1_current']['retrieval_page_recall'],1)
            self.assertEqual(emitted['v1_current']['retrieval_first_gold_rank'],1)

    def test_page_superset_aliases_preserve_same_nonacceptance_text(self):
        docs={'source.pdf':['first','second']}
        canonical=dict(retrieved=[dict(chunk_id=1,document_name='source.pdf',page_number=2)])
        alias=dict(retrieved=[dict(chunk_id=1,document='source.pdf',page=2)])
        self.assertEqual(context.page_superset(alias,docs),context.page_superset(canonical,docs))


if __name__ == '__main__':
    unittest.main()
