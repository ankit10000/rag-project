"""WP6 evaluation-integrity checks; offline, no evaluation or provider calls."""
import testsafe
testsafe.require_scratch_db()

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from eval.framework.hashing import portable_sha256
from eval.framework.integrity import load_dataset

ROOT = Path(__file__).resolve().parent
MANIFEST_PIN = '1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97'
# Raw-byte baseline captured before WP6 edits; review assets and history included.
PROTECTED = {'docs/remediation/HELDOUT_DATASET_CORRECTIONS.md': 'd44573e1a68b43a98ddd50cc9e5344a429079b3e87cf37ae585a26ceaa92eefb',
 'docs/remediation/HELDOUT_THRESHOLD_FREEZE.md': '3e4bd5d71e843dcb2fd5bed13d17d88b7fb67b8fce85723834225641a055be66',
 'docs/remediation/dev_review/dev_review_sheet.xlsx': '6b94f3431c6c1f8e16b5401a824e2b9ddfa9fb0160c16da6485bb4da50922b09',
 'docs/remediation/heldout_review/README.md': '8a6f429607541b127ba8c3dec6de9163a4d916877878b8bc1883ebdfa8a6293b',
 'docs/remediation/heldout_review/REVIEW_SIGNOFF_REPORT.md': '88906a141f54061834071f9a40159d20d9bc4a04e072c97a24ae327f320ef7d0',
 'docs/remediation/heldout_review/heldout_review_sheet.csv': 'a5b90a4fc4ec2452fdd247d1bce642012b321ce6732213df2d8978ecc01fb8bf',
 'docs/remediation/heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx': '300dc43fb76b1884015583d60e12834f7e50086c0afbaad765ad536e8c491467',
 'docs/remediation/heldout_review/heldout_review_sheet_REVIEWED_by_Claude.csv': '250049d282d63d654d6b8d20742a8e34cf1eef5989220b37aac5c5b9f27bbd52',
 'docs/remediation/heldout_review/source_pages.md': 'e76ad9475ab5d82bd863ef50f603dd90e01149267b97eef56adf5030fdf985ea',
 'docs/remediation/heldout_review/source_pdfs/Aquaflow_AF-Series_Maintenance_Manual_RevC.pdf': '98dff714a5b24657fc9bff9569669760e75f7a09e1a7b60a867267dc60bf4df9',
 'docs/remediation/heldout_review/source_pdfs/Brannock_Ridge_Safety_SOP_Rev4.pdf': '7fcaed2dddb495d35f7b95ffc7ac20be7af3a8443eaddac6752b9de4d8596dc9',
 'docs/remediation/heldout_review/source_pdfs/Corvane_Travel_Expense_Policy_FY27.pdf': '89ee34a881b4ee37854829ff1804c6478721f6edf55df24b9c4effea6eb3891c',
 'docs/remediation/heldout_review/source_pdfs/Harbourline_Price_List_and_Care_Plans_v4.1.pdf': '2420dc46b5bc329651e744e80f5184d4a1f26503531bf2ad48b21b3a25d102fc',
 'docs/remediation/heldout_review/source_pdfs/Harbourline_Warranty_and_Returns_Policy.pdf': '9599120817b1ac302cd8e7509002b6c2656b40cdd93114ea73bdd2df06e8e2d9',
 'docs/remediation/heldout_review/source_pdfs/Kestrel_Bay_Hospital_Visitor_and_Patient_Rights_Policy_v4.2.pdf': '021b775ebca833b67a5ab2b36e0a1c954375d347f192a174ab55e9fdf79837b9',
 'docs/remediation/heldout_review/source_pdfs/Kestrel_Vendor_Services_Agreement.pdf': '4ebc0916937aa3e10cdc79e033582ffe5ecff6751692262bcdfe4a9a950e76a6',
 'docs/remediation/heldout_review/source_pdfs/Marlow_Fen_Water_Use_and_Public_Health_Bylaw_2025-14.pdf': '0b95903f956a50d5e4f45e02761e25489dcbbd561cc639524f4d7101e9a55359',
 'docs/remediation/heldout_review/source_pdfs/Orchard_Lane_Clinic_Vaccination_and_Appointments_Guide.pdf': 'c40153cb0f4607732e9d1b1a79d04fcc66296ec58f48a86a5534caf5413b0a1c',
 'docs/remediation/heldout_review/source_pdfs/calder_sound_tile_study_TR-2026-07.pdf': 'aadbe06a7183bb300a9dc502fdd314ca3aa56305bb22a6b634918fd73b1170d4',
 'docs/remediation/heldout_review/source_pdfs/kestrel_fellowship_call_2027.pdf': 'e7277a4f88305eda428aaa095518a60eecfd7234a047c4c34936f648f81de74c',
 'docs/remediation/heldout_review/source_pdfs/velmoor_postgrad_handbook_v4.2.pdf': 'd32da00f266b44a13b18a1dc6564bcd184b06846385c3771afacaf52beb20d14',
 'docs/remediation/phase_d_decision_package/DEV_CORRECTION_PROPOSALS.csv': '05632da76d3733f1f4fa03a3811dd5f6a160d743ba3023b76aa0c125ff3b01fa',
 'docs/remediation/phase_d_decision_package/HELDOUT_CORRECTION_PROPOSALS.csv': '13a5b0dca722c4b8806f7ff224ad4c2d16ccd76a8af2e9e82527f8f4d9daebb5',
 'docs/remediation/phase_e1_multi_agent_audit/DATASET_CORRECTION_AUDIT.md': '02c5bb2bf040ecb2a35e1837c7b7dbaff3e2cd17c4cc26e165a10dcd8394ca29',
 'docs/remediation/phase_e2_engineering/WP4_CORRECTION_PROPOSAL_REPORT.md': '9e1df8a853a0fab0a7153c919ceb8fbd3ac00ef544b430d0f4a6e5d558bb5452',
 'docs/remediation/phase_e2_engineering/wp4/REVISED_DEV_CORRECTION_PROPOSALS.csv': '986b40f21852c49b24ef36192512878bafde31c7ef0d9fc7911c9e13db2a0727',
 'docs/remediation/phase_e2_engineering/wp4/REVISED_HELDOUT_CORRECTION_PROPOSALS.csv': '09b82732911c833498957e51658d27833405fd0eaaccc407e12f0b024d00c6f3',
 'docs/remediation/phase_e2_engineering/wp4/REVISED_POTENTIAL_ISSUE_DECISIONS.md': 'dcfeb034bb2124efd581d730f3f29e246faac0ad6e70df29f98e5bcdc341bf19',
 'docs/remediation/phase_e2_engineering/wp4/REVISED_PROPOSALS.json': '02a5a3a9911548187ea33acea10aae8e3a4424baa1d269bbd5bc509ce1c7699e',
 'docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md': '45d0c0d5a51f67e327162a27dcb58e8996014485414a4e8aa9e0ac924b5a8967',
 'eval/answer_scoring.py': 'c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af',
 'eval/phase35/data_A.py': 'c204fd037d653a27dfed00f7d9b9ad0b38dea4d20f578145aa7bc9b15201714c',
 'eval/phase35/data_B.py': 'f58fc8041bed81682e0bc22be6123364f963b170db5a409204b60922aa5a3548',
 'eval/phase35/data_C.py': '6fc3ca44254f4dc536b2bde59d355134ccdee284ff359c4a6f3ebe7deb6cfea6',
 'eval/phase35/data_D.py': '6341a55f5307cf9cc47fbf1608e7dc26e3041793f6e0184528f1a3b9249d8f64',
 'eval/phase35/frozen_manifest.json': '6a66745490cebe050e1318e6ec959ce4cf6d708a10957604b7e193018d0a8648',
 'eval/phase35/results/log_tier1_dev.txt': 'eb01bc5d7fd6a1ea8c266f0d349235146ba392ce5c3fc7adfef42f45a97f78a6',
 'eval/phase35/results/log_tier1_dev_stageB.txt': '4e4eb6911949c2e5d4ec89bace21c080250f31791bcfd562d5db953436dd273f',
 'eval/phase35/results/log_tier2_dev.txt': '853eee37def8a0645fa946304bd25109bcdb0d48353032c2c98d108ef60bcb05',
 'eval/phase35/results/log_tier2_dev_stageB.txt': '91fce59d5e0be9d1fec7b29a1683148f866cd9f4cabcc0053156671389e88a2e',
 'eval/phase35/results/tier1_dev.jsonl': '4c1a6416f2603f7c0744533b6c3ee99570827aaefbdca003bbe346ea2bfd0988',
 'eval/phase35/results/tier2_dev.jsonl': 'b2c92e582c8e9ddb75e6adc6661a200ab294bc4956002c54f2c6258fb63f4962',
 'eval/phase35/run_eval.py': '9d4670ce5488499ec79f0cc50598993fc2594ba9d1edb95555b1a6ae379ace94',
 'eval/phase35/validate.py': '2f29ba0f1c483bc2fd4a54c1bad2685a3b50d98b104159a6d6365c29ef0222ca'}

class EvaluationIntegrity(unittest.TestCase):
    def test_protected_assets_are_byte_identical(self):
        self.assertEqual(len(PROTECTED), 44)
        for path, expected in PROTECTED.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)

    def test_manifest_identity_and_acceptance_policy_unchanged(self):
        from eval.framework.frozen_manifest import MANIFEST_FORMAT, FROZEN_ASSETS
        manifest = json.loads((ROOT / 'eval/phase35/frozen_manifest.json').read_bytes())
        self.assertEqual(manifest['content_sha256'], MANIFEST_PIN)
        self.assertEqual(MANIFEST_FORMAT, 'phase35-frozen-manifest/1')
        self.assertNotIn('acceptance_scorer', manifest['content'])
        self.assertFalse(any(group == 'scorer_v2' for group, _, _ in FROZEN_ASSETS))

    def test_v1_phrase_contents_and_all_72_probes_survive_import(self):
        from eval import answer_scoring
        from eval.probes.probes_phase_d import PHASE_D_PROBES
        from eval.probes.scorer_regression import dataset, score_probe, v1_mismatches
        phrases = copy.deepcopy((answer_scoring.INSUFFICIENCY_PHRASES, answer_scoring.DISAGREEMENT_PHRASES))
        self.assertEqual(tuple(map(len, phrases)), (22, 7))
        docs, _, by_id = dataset()
        self.assertEqual(len(PHASE_D_PROBES), 72)
        before = [score_probe(probe, docs, by_id) for probe in PHASE_D_PROBES]
        importlib.import_module('eval.scoring_v2')
        after = [score_probe(probe, docs, by_id) for probe in PHASE_D_PROBES]
        self.assertEqual(before, after)
        self.assertEqual(phrases, (answer_scoring.INSUFFICIENCY_PHRASES, answer_scoring.DISAGREEMENT_PHRASES))
        for probe, score in zip(PHASE_D_PROBES, after):
            with self.subTest(probe=probe['id']):
                self.assertEqual(v1_mismatches(probe, score), [])

    def test_fresh_package_import_has_no_runtime_io_or_services(self):
        script = """
import builtins, copy, importlib.abc, socket, sys
from eval import answer_scoring as v1
from eval.phase35 import run_eval
phrase_snapshot = copy.deepcopy((v1.INSUFFICIENCY_PHRASES, v1.DISAGREEMENT_PHRASES))
identities = {name: getattr(run_eval, name) for name in ('score_generic', 'norm_numbers', 'tier1_context', 'NUM_RE', 'REF_RE', 'split_of')}
class DenyServices(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'services' or fullname.startswith('services.'):
            raise AssertionError('service import: ' + fullname)
def refuse(*args, **kwargs):
    raise AssertionError('runtime I/O during package import')
sys.meta_path.insert(0, DenyServices())
builtins.open = refuse
socket.socket = refuse
import eval.scoring_v2 as package
assert callable(package.score_case)
assert phrase_snapshot == (v1.INSUFFICIENCY_PHRASES, v1.DISAGREEMENT_PHRASES)
assert all(getattr(run_eval, name) is value for name, value in identities.items())
assert not hasattr(package, 'score_generic')
assert not any(name == 'services' or name.startswith('services.') for name in sys.modules)
"""
        process = subprocess.run([sys.executable, '-B', '-c', script], cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_complete_annotations_are_only_literal_dataset_baseline(self):
        from eval.scoring_v2.annotations import validate_annotations
        docs, cases = load_dataset()
        annotations = json.loads((ROOT / 'eval/scoring_v2/annotations.json').read_bytes())
        self.assertEqual(len(cases), 160)
        self.assertEqual(len(annotations['cases']), 160)
        self.assertEqual(validate_annotations(annotations, cases, docs), [])
        for case in cases:
            with self.subTest(case=case['id']):
                self.assertEqual(annotations['cases'][case['id']], {'forbidden': [
                    {'text': text, 'kind': 'literal', 'source': 'dataset'} for text in case['forbidden']]})

    def test_scorer_hash_is_repeatable_order_independent_and_crlf_portable(self):
        from eval.scoring_v2.rescore_meta import scorer_identity
        paths = sorted((ROOT / 'eval/scoring_v2').glob('*.py'))
        sources = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}
        annotations = (ROOT / 'eval/scoring_v2/annotations.json').read_bytes()
        identity = scorer_identity(sources, annotations)
        self.assertEqual(identity, scorer_identity(sources, annotations))
        portable = {path: data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n') for path, data in reversed(list(sources.items()))}
        crlf_ann = annotations.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        self.assertEqual(identity, scorer_identity(portable, crlf_ann))
        self.assertEqual(identity['version'], '2.1.0')
        self.assertEqual(identity['annotation_schema'], 'phase35-scorer-annotations/1')
        self.assertEqual(set(identity['module_sha256']), set(sources))
        self.assertEqual(identity['annotations_sha256'], portable_sha256(annotations, 'text'))

    def test_every_scorer_module_and_annotation_affect_identity(self):
        from eval.scoring_v2.rescore_meta import scorer_identity
        sources = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in (ROOT / 'eval/scoring_v2').glob('*.py')}
        annotations = (ROOT / 'eval/scoring_v2/annotations.json').read_bytes()
        expected = scorer_identity(sources, annotations)['sha256']
        for path in sources:
            with self.subTest(path=path):
                altered = dict(sources)
                altered[path] += b'\n# integrity mutation\n'
                self.assertNotEqual(scorer_identity(altered, annotations)['sha256'], expected)
        self.assertNotEqual(scorer_identity(sources, annotations + b'\n')['sha256'], expected)

    def test_proposal_decisions_are_still_pending(self):
        proposals = json.loads((ROOT / 'docs/remediation/phase_e2_engineering/wp4/REVISED_PROPOSALS.json').read_bytes())
        self.assertIn('PENDING_OWNER_DECISION', proposals['_meta']['status'])
        for key, value in proposals.items():
            if key == '_meta':
                continue
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                self.assertIsInstance(entry, dict)
                self.assertEqual(entry.get('status'), 'PENDING_OWNER_DECISION')


if __name__ == '__main__':
    unittest.main()
