"""Offline integrity tests for the separate AI review track; no scoring execution."""
import copy
import json
import unittest
import tempfile
from pathlib import Path
from ai_review import consolidate as C


class AIReviewIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.pages, cls.dataset_sha, cls.modules, cls.sources = C.context()
        cls.originals, cls.normalized, cls.hashes = C.load_initials(cls.cases, cls.pages, cls.dataset_sha, cls.modules)
        cls.cid = 'A-direct-01'
        cls.row = cls.originals['label_review'][cls.cid]

    def validate(self, row):
        return C.validate_review(row, self.cases[self.cid], self.pages, self.dataset_sha, self.modules)

    def test_exact_113_ids_and_three_source_bound_reviews(self):
        self.assertEqual(len(self.cases), 113)
        for name in C.NAMES:
            self.assertEqual(set(self.normalized[name]), set(self.cases))
            self.assertEqual(len(self.normalized[name]), 113)

    def test_duplicate_unknown_and_missing_rows_rejected(self):
        rows = [{'case_id': 'a'}, {'case_id': 'b'}]
        for bad in [rows+[rows[0]], rows+[{'case_id':'unknown'}], rows[:1]]:
            with self.assertRaises(ValueError):
                C.index_rows(bad, {'a', 'b'})

    def test_human_reviewer_or_judgment_rejected(self):
        for key, value in [('reviewer_type','HUMAN'), ('judgment','HUMAN_REVIEW_COMPLETED')]:
            row = copy.deepcopy(self.row); row[key] = value
            with self.assertRaises(ValueError):
                self.validate(row)

    def test_missing_or_boilerplate_case_rationale_rejected(self):
        for text in ['', 'Reviewed', 'Source verified and expected answer supported.']:
            row = copy.deepcopy(self.row); row['source_based_rationale'] = text
            with self.assertRaises(ValueError):
                self.validate(row)

    def test_quote_page_hash_and_document_are_bound(self):
        for key, value in [('quote','This invented quotation is absent from every page.'),
                           ('page',999), ('pdf_sha256','0'*64), ('page_text_sha256','1'*64),
                           ('document','unrelated.pdf'), ('pdf_path','unrelated.pdf')]:
            evidence = copy.deepcopy(self.row['source_evidence'][0]); evidence[key] = value
            with self.assertRaises(ValueError):
                C.validate_evidence(evidence, self.pages)

    def test_dataset_and_module_hashes_are_bound(self):
        for key, value in [('dataset_sha256','0'*64), ('module_sha256',{})]:
            row = copy.deepcopy(self.row); row['dataset_identity'][key] = value
            with self.assertRaises(ValueError):
                self.validate(row)

    def test_missing_evidence_requires_explicit_insufficient_exception(self):
        row = copy.deepcopy(self.row); row['source_evidence'] = []
        with self.assertRaises(ValueError):
            self.validate(row)
        row['judgment'] = 'AI_INSUFFICIENT_EVIDENCE'
        with self.assertRaises(ValueError):
            self.validate(row)
        row['insufficient_evidence_reason'] = 'The actual PDF is unavailable and no supporting page can be inspected for this case.'
        self.validate(row)

    def test_negative_coverage_requires_complete_validated_pdf_scope(self):
        ref = {'document': self.row['source_evidence'][0]['document'],
               'pdf_sha256': self.row['source_evidence'][0]['pdf_sha256'],
               'pages_examined':[1], 'location':'Complete source examined for an unavailable fact.'}
        with self.assertRaises(ValueError):
            C.validate_evidence(ref, self.pages)
        ref['pages_examined'] = [1,2,3,4]
        C.validate_evidence(ref, self.pages)

    def test_immutable_initial_hash_manifest_and_unadjudicated_state(self):
        ledger, pending, manifest = C.build()
        self.assertEqual(manifest['initial_file_sha256'], self.hashes)
        self.assertEqual(manifest['dataset_sha256'], self.dataset_sha)
        self.assertEqual(manifest['source_pdf_sha256'], self.sources)
        self.assertEqual(len(ledger),113)
        self.assertEqual(len(pending),38)
        self.assertTrue(all(row['review_track']=='AI_REVIEW_INCOMPLETE' for row in ledger))
        for row in ledger:
            self.assertEqual(len(row['initial_judgments']),3)
            self.assertIsNone(row['model_identity'])
            self.assertEqual(row['formal_status'],'OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING')

    def test_adjudication_unknown_case_and_false_reviewer_rejected(self):
        decisions = {'reviewer_type':'AI', 'lead_execution_identity':'/root',
                     'prior_exposure':{'previous_AI_findings_read':True}, 'review_timestamp_utc':'2026-11-19T05:49:12+00:00', 'decisions':{'unknown':{}}}
        with self.assertRaises(ValueError):
            C.build(decisions)
        decisions['decisions'] = {}; decisions['reviewer_type'] = 'HUMAN'
        with self.assertRaises(ValueError):
            C.build(decisions)

    def test_published_proof_rejects_tampered_initials_and_final_judgment(self):
        ledger, _, _ = C.build()
        self.assertTrue(C.validate_published(json.loads(json.dumps(ledger)), ledger))
        for change in ('initial_record', 'final_judgment'):
            altered = copy.deepcopy(ledger)
            if change == 'initial_record':
                altered[0]['initial_judgments']['source_verification']['record']['confidence'] = 0
            else:
                altered[0]['reviewer_judgment'] = 'HUMAN_REVIEW_COMPLETED'
            with self.assertRaises(ValueError):
                C.validate_published(altered, ledger)

    def test_final_complete_113_source_bound_and_exclusive_publication(self):
        adjudications = json.loads((C.ROOT/'ai_review/adjudications.json').read_text())
        ledger, pending, _ = C.build(adjudications)
        self.assertEqual(pending, [])
        self.assertEqual(len(ledger), 113)
        self.assertTrue(all(row['review_track'] == 'AI_REVIEW_COMPLETE' for row in ledger))
        self.assertEqual(sum(row['adjudication_status'] == 'UNRESOLVED_POLICY' for row in ledger), 8)
        for row in ledger:
            self.assertGreaterEqual(row['review_timestamp'], adjudications['review_timestamp_utc'])
            for evidence in row['evidence_references']:
                C.validate_evidence(evidence, self.pages)
            if row['lead_adjudication']:
                for evidence in row['lead_adjudication']['evidence_references']:
                    self.assertIn(evidence, row['evidence_references'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'ledger.jsonl'
            C.publish(ledger, pending, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                C.publish(ledger, pending, path)
            self.assertEqual(path.read_bytes(), before)

    def test_incomplete_lead_adjudication_cannot_publish(self):
        adjudications = json.loads((C.ROOT/'ai_review/adjudications.json').read_text())
        del adjudications['decisions']['A-direct-03']
        ledger, pending, _ = C.build(adjudications)
        self.assertIn('A-direct-03', pending)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'ledger.jsonl'
            with self.assertRaises(ValueError):
                C.publish(ledger, pending, path)
            self.assertFalse(path.exists())

    def test_sealed_initials_are_independently_hashed(self):
        manifest = json.loads((C.ROOT/'ai_review/initial_manifest.json').read_text())
        for path, digest in manifest['initial_file_sha256'].items():
            content = (C.ROOT/path).read_bytes()
            self.assertEqual(C.sha(content),digest)
            self.assertNotEqual(C.sha(content+b' '),digest)


if __name__ == '__main__':
    unittest.main()
