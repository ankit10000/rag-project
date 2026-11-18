"""Verify staged independent-review evidence without supplying a review judgment."""
import testsafe
testsafe.require_scratch_db()
import copy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
PACKAGE=ROOT/'independent_review/flip_review_package'
spec=importlib.util.spec_from_file_location('flip_review_package',PACKAGE/'package.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


def load(name): return json.loads((PACKAGE/name).read_bytes())


class FlipReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rebuilt=P.build_payloads(ROOT)
        cls.index=load('review_status_index.json')

    def test_every_payload_exactly_rebuilds_and_manifest_verifies(self):
        for name,data in self.rebuilt.items():
            with self.subTest(name=name): self.assertEqual((PACKAGE/name).read_bytes(),data)
        manifest=load('package_manifest.json')
        for name,digest in manifest['files'].items():
            self.assertEqual(P.digest((PACKAGE/name).read_bytes()),digest)
        self.assertEqual(manifest['generator_sha256'],P.digest((PACKAGE/'package.py').read_bytes()))

    def test_four_unique_records_eight_historical_occurrences(self):
        self.assertEqual(self.index['unique_case_tier_records'],4)
        self.assertEqual(self.index['historical_occurrences'],8)
        keys={(r['tier'],r['case_id']) for r in self.index['records']}
        self.assertEqual(keys,set(P.TARGETS))
        historical=[]
        for row in self.index['records']:
            after=load(row['stage_b_after_judgment'])
            self.assertEqual(len(after['historical_occurrences']),2)
            historical.extend(after['historical_occurrences'])
        self.assertEqual(len(historical),8)
        self.assertEqual(len({x['recorded_scorer']['sha256'] for x in historical}),2)
        self.assertTrue(all(x['identity_relation']=='HISTORICAL_DISTINCT_IDENTITY_BEHAVIORAL_PARITY_ONLY' for x in historical))

    def test_stage_a_has_full_context_and_hashes_without_outcomes_or_ai_mechanics(self):
        blocked={'v1','v2','gold_facts','gold_sources','expected_case_flags','recommended_outcome',
                 'neutral_mechanical_explanation','specification_clauses','historical_occurrences'}
        for row in self.index['records']:
            blind=load(row['blind_evidence'])
            self.assertFalse(set(blind)&blocked)
            text=' '.join(c['text'] for c in blind['ordered_scoring_context'])
            self.assertEqual(text,blind['scoring_context_text'])
            self.assertEqual(P.digest(text.encode()),blind['context_sha256'])
            for chunk in blind['ordered_scoring_context']:
                self.assertEqual(P.digest(chunk['text'].encode()),chunk['text_sha256'])
            for page in blind['source_pages']:
                self.assertEqual(P.digest(page['text'].encode()),page['text_sha256'])
            for passage in blind['relevant_source_passages']:
                page=next(p for p in blind['source_pages'] if p['document']==passage['document'] and p['page']==passage['page'])
                self.assertIn(passage['text'].casefold(),page['text'].casefold())

    def test_stage_b_current_identity_full_scores_and_source_provenance(self):
        expected={(1,'B-comp-04'):(False,True),(1,'B-conf-04'):(False,True),
                  (1,'D-conflicting-01'):(True,False),(2,'B-conf-04'):(False,True)}
        for row in self.index['records']:
            after=load(row['stage_b_after_judgment'])
            self.assertEqual(after['scorer']['sha256'],P.EXPECTED_SCORER)
            self.assertEqual((after['v1']['correct'],after['v2']['correct']),expected[row['tier'],row['case_id']])
            self.assertTrue(set(after['v1'])-{'retrieval_page_recall','retrieval_first_gold_rank'}<=set(after['v2']))
            self.assertIn('uncommitted scorer identity',after['source_revision_role'])
            source=after['source_results'];self.assertEqual(P.digest((ROOT/source['path']).read_bytes()),source['raw_sha256'])
            self.assertEqual(after['dataset_pin']['git_rev'],P.PIN)
            self.assertEqual(after['reconstruction_status'],'exact')
            self.assertIsNone(after['recommended_outcome'])
            for clause in after['specification_clauses']:
                original=(ROOT/clause['path']).read_bytes()
                self.assertEqual(P.digest(original),clause['source_sha256'])
                self.assertIn(clause['text'],original.decode())

    def test_all_review_fields_blank_no_claimed_approval(self):
        self.assertFalse(self.index['review_completed']);self.assertFalse(self.index['acceptance_approved'])
        with (PACKAGE/'reviewer_decisions.csv').open(newline='') as source:
            decisions=list(csv.DictReader(source))
        self.assertEqual(len(decisions),4)
        for decision in decisions:
            self.assertEqual(decision['review_status'],P.STATUS)
            self.assertTrue(all(value=='' for key,value in decision.items() if key not in ('record_id','review_status')))
        for row in self.index['records']:
            self.assertEqual(row['review_status'],P.STATUS);self.assertFalse(row['human_approved'])
            self.assertEqual(row['reviewer_judgment'],'');self.assertEqual(row['reviewer_rationale'],'')

    def test_same_case_tier_contexts_remain_distinct(self):
        records=[load(r['blind_evidence']) for r in self.index['records'] if r['case_id']=='B-conf-04']
        self.assertEqual(len(records),2)
        self.assertNotEqual(records[0]['context_sha256'],records[1]['context_sha256'])
        self.assertNotEqual(records[0]['raw_answer'],records[1]['raw_answer'])

    def test_exposure_instructions_require_blind_stage_before_ai_stage(self):
        text=(PACKAGE/'README.md').read_text()
        self.assertIn('before AI analysis',text)
        self.assertIn('Only after Stage A is recorded',text)
        self.assertIn('not filesystem access control',text)
        self.assertIn('Do not open the historical WP8 AI flip ledger/analysis before Stage A',text)

    def test_writer_new_directory_only_and_repeated_write_refused(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
            output=Path(tmp)/'new-package';P.write_package(ROOT,output)
            before={p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()}
            with self.assertRaises(FileExistsError): P.write_package(ROOT,output)
            self.assertEqual(before,{p.relative_to(output).as_posix():p.read_bytes() for p in output.rglob('*') if p.is_file()})


if __name__=='__main__': unittest.main()
