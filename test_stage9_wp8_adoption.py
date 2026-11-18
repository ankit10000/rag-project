"""WP8 adoption rehearsal and refusal tests; no official evaluation or policy change."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from eval.acceptance_preparation import adoption
from eval.phase35.run_eval import score_generic
from eval.runner_preparation import offline
from eval.runner_preparation.artifacts import verify_bundle
from eval.scoring_v2 import rescore as wp6
from test_stage9_v2_integrity import PROTECTED
from test_stage9_wp7_integration import WP6_PINS
from test_stage9_wp7_runner import fixture

ROOT=Path(__file__).resolve().parent


class AdoptionTests(unittest.TestCase):
    def manifest(self):
        return json.loads((ROOT/'eval/phase35/frozen_manifest.json').read_text())

    def test_current_manifest_never_authorizes_adoption(self):
        plan=adoption.build_adoption_plan(self.manifest(),{})
        self.assertEqual(plan['official_default'],'v1')
        self.assertFalse(plan['activation_allowed'])
        self.assertFalse(plan['official_execution_available'])
        self.assertTrue(plan['manifest_reference']['internally_consistent'])
        self.assertFalse(plan['manifest_reference']['filesystem_verified'])
        self.assertTrue(all(r['status']=='PENDING_OWNER_DECISION' for r in plan['pending_requirements']))
        self.assertTrue(all(not r['applied'] for r in plan['frozen_integration']))

    def test_plan_deterministic_and_claims_are_not_approvals(self):
        claims={'approved':True,'review_status':'COMPLETE','reviewer':'synthetic-owner',
                'acceptance_eligible':True,'pending_requirements':[]}
        first=adoption.build_adoption_plan(self.manifest(),claims)
        second=adoption.build_adoption_plan(self.manifest(),claims)
        self.assertEqual(first,second)
        claims['review_status']='mutated'
        self.assertEqual(first['evidence']['claims']['review_status'],'COMPLETE')
        self.assertEqual(first['evidence']['authority'],'UNVERIFIED_CALLER_CLAIMS')
        self.assertFalse(first['evidence']['adoption_authorization'])
        self.assertGreater(len(first['pending_requirements']),0)
        self.assertFalse(first['activation_allowed'])

    def test_forged_future_manifest_and_sidecar_cannot_activate(self):
        manifest=self.manifest()
        manifest['content']['manifest_format']='phase35-frozen-manifest/2'
        manifest['content']['acceptance_scorer']={'name':'phase35-scorer','version':'2.1.0','sha256':'0'*64}
        for claims in ({'approved':True},{'owner_approval':{'signed':True,'approved_by':'owner'}},
                       {'acceptance_eligible':True,'sidecar':{'scorer_version':'2.1.0'}},
                       {'all_decisions_approved':True,'human_review_complete':True}):
            with self.subTest(claims=claims):
                self.assertFalse(adoption.build_adoption_plan(manifest,claims)['activation_allowed'])
                with self.assertRaises(adoption.AdoptionBlockedError):
                    adoption.assert_official_adoption_allowed(manifest,claims,approved=True)
                with self.assertRaises(adoption.AdoptionBlockedError):
                    adoption.select_official_scorer('2.1.0',manifest=manifest,evidence=claims)

    def test_default_and_rollback_are_genuine_frozen_v1(self):
        self.assertIs(adoption.select_official_scorer(),score_generic)
        self.assertIs(adoption.rollback_to_v1(),score_generic)
        _,case,row,_,_=fixture()
        self.assertEqual(adoption.select_official_scorer()(case,row,{},set(),''),
                         score_generic(case,row,{},set(),''))

    def test_unknown_versions_cannot_upgrade_official_default(self):
        for version in ('v2','latest','2.1.0',True,None,''):
            with self.subTest(version=version),self.assertRaises(adoption.AdoptionBlockedError):
                adoption.select_official_scorer(version)
        self.assertIs(adoption.select_official_scorer(),score_generic)

    def test_malformed_evidence_does_not_gain_authority(self):
        for manifest,evidence in (([],{}),({},[]),({'content':float('nan')},{}),
                                  ({},{'x':object()}),({},{1:'non-text-key'})):
            with self.subTest(evidence_type=type(evidence).__name__),self.assertRaises(ValueError):
                adoption.build_adoption_plan(manifest,evidence)
        plan=adoption.build_adoption_plan({'content':{},'content_sha256':'forged'},{})
        self.assertFalse(plan['manifest_reference']['internally_consistent'])
        self.assertFalse(plan['activation_allowed'])

    def test_rehearsal_requires_explicit_development_version_and_dev_split(self):
        with patch.object(offline,'prepare_comparison') as delegate:
            for options in ({},{'development':True,'split':'heldout'},
                            {'development':True,'split':'all'}, {'development':1},
                            {'development':True,'scorer_version':'v1'},
                            {'development':True,'tier':True}):
                arguments=dict(tier=1,scorer_version='2.1.0');arguments.update(options)
                with self.subTest(options=options),self.assertRaises(ValueError):
                    adoption.rehearse_development_comparison('source','ann','out','run',**arguments)
            delegate.assert_not_called()

    def test_rehearsal_delegates_unchanged_wp7_interface(self):
        expected=Path('/private/tmp/not-created-comparison')
        with patch.object(offline,'prepare_comparison',return_value=expected) as delegate:
            actual=adoption.rehearse_development_comparison('source','ann','out','run',
                tier=1,scorer_version='2.1.0',development=True,dataset_rev='pinned')
        self.assertEqual(actual,expected)
        delegate.assert_called_once_with('source','ann','out','run',tier=1,scorer_version='2.1.0',
            dataset_rev='pinned',run_header=None,chunk_config=None,split='dev')

    def test_rehearsal_has_no_caller_approval_or_acceptance_switch(self):
        for key in ('acceptance','approval','approved','official','allow_live_provider'):
            with self.subTest(key=key),self.assertRaises(TypeError):
                adoption.rehearse_development_comparison('source','ann','out','run',
                    tier=1,scorer_version='2.1.0',development=True,**{key:True})

    def test_real_synthetic_rehearsal_is_isolated_and_rollback_preserves_artifacts(self):
        docs,case,row,ann,pin=fixture()
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            folder=Path(temporary)
            source=folder/'source.jsonl';source.write_text(json.dumps(row)+'\n')
            annotations=folder/'annotations.json';annotations.write_text(json.dumps(ann))
            before=(source.read_bytes(),annotations.read_bytes())
            with patch.object(wp6,'load_pinned_dataset',return_value=(docs,[case],pin)):
                final=adoption.rehearse_development_comparison(source,annotations,folder/'outputs','rehearsal',
                    tier=1,scorer_version='2.1.0',development=True,dataset_rev='synthetic-fixture-only')
            self.assertEqual(final,folder/'outputs/development-comparisons/scorer-2.1.0/rehearsal')
            self.assertFalse(verify_bundle(final)['acceptance_eligible'])
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in final.iterdir()}
            self.assertIs(adoption.rollback_to_v1(),score_generic)
            self.assertEqual(hashes,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in final.iterdir()})
            self.assertEqual(before,(source.read_bytes(),annotations.read_bytes()))
            with self.assertRaises(adoption.AdoptionBlockedError):
                adoption.assert_official_adoption_allowed(self.manifest(),{'bundle':str(final),'approved':True})

    def test_official_result_root_is_never_a_rehearsal_output(self):
        docs,case,row,ann,pin=fixture()
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            folder=Path(temporary)
            source=folder/'source.jsonl';source.write_text(json.dumps(row)+'\n')
            annotations=folder/'annotations.json';annotations.write_text(json.dumps(ann))
            with patch.object(wp6,'load_pinned_dataset',return_value=(docs,[case],pin)),self.assertRaises(ValueError):
                adoption.rehearse_development_comparison(source,annotations,ROOT/'eval/phase35/results','no-write',
                    tier=1,scorer_version='2.1.0',development=True,dataset_rev='synthetic-fixture-only')

    def test_frozen_and_existing_wp6_bytes_unchanged(self):
        pins=dict(PROTECTED,**WP6_PINS)
        for path,digest in pins.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
        self.assertNotIn('acceptance_preparation',(ROOT/'eval/phase35/run_eval.py').read_text())
        self.assertNotIn('scoring_v2',(ROOT/'eval/phase35/run_eval.py').read_text())


if __name__=='__main__':
    unittest.main()
