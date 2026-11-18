"""Non-authorizing candidate integration snapshots; no providers, DB or evaluation."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from eval.acceptance_preparation.integration import (
    build_candidate,validate_candidate,select_official_scorer,rollback_to_v1,
    assert_official_adoption_allowed,rehearse_development_comparison,
)
from eval.acceptance_preparation.integration.candidate import digest
from eval.acceptance_preparation.integration.snapshot import (
    capture_inputs,build_current_candidate,validate_current_candidate,write_candidate,
)
from eval.acceptance_preparation.adoption import AdoptionBlockedError
from eval.phase35.run_eval import score_generic
from eval.runner_preparation import offline
from test_stage9_v2_integrity import PROTECTED

ROOT=Path(__file__).resolve().parent


class CandidateIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent,cls.sources,cls.annotations,cls.head=capture_inputs(ROOT)
        cls.candidate=build_candidate(cls.parent,cls.sources,cls.annotations,source_head=cls.head)

    def validate(self,candidate=None,parent=None,sources=None,annotations=None,head=None):
        return validate_candidate(self.candidate if candidate is None else candidate,
            self.parent if parent is None else parent,self.sources if sources is None else sources,
            self.annotations if annotations is None else annotations,source_head=self.head if head is None else head)

    def test_candidate_inventory_uses_current_27_parent_and_20_existing_snapshots(self):
        report=self.validate()
        self.assertEqual((report['preserved_assets'],report['candidate_assets'],report['annotation_bindings']),(27,20,2))
        self.assertEqual(report['status'],'PASS')
        self.assertFalse(report['activation_allowed'])
        self.assertFalse(report['refreeze_executed'])
        self.assertEqual(report['accepted_default'],'v1')
        self.assertNotIn('content',self.candidate)
        self.assertNotIn('acceptance_scorer',self.candidate)
        proposal=self.candidate['snapshot_proposal']
        self.assertIsNone(proposal['approved_acceptance_scorer'])
        self.assertIsNone(proposal['approved_v2_thresholds'])
        self.assertIsNone(proposal['future_patched_runner_gate_hashes'])
        self.assertEqual(len(proposal['required_decisions']),9)

    def test_annotation_bindings_do_not_conflate_default_and_historical_identity(self):
        records={r['path']:r for r in self.candidate['annotation_bindings']}
        current=records['eval/scoring_v2/annotations.json']
        historical=next(r for path,r in records.items() if 'literal-annotations' in path)
        self.assertEqual(historical['portable_sha256'],'b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a')
        self.assertEqual(historical['scorer']['sha256'],'0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf')
        self.assertEqual(current['portable_sha256'],'d3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0')
        self.assertNotEqual(current['scorer']['sha256'],historical['scorer']['sha256'])
        self.assertNotEqual(current['dataset_sha256'],historical['dataset_sha256'])
        self.assertEqual(current['scorer']['version'],historical['scorer']['version'])

    def test_actual_current_file_validator_reproduces_pure_report(self):
        self.assertEqual(validate_current_candidate(ROOT,self.candidate),self.validate())
        self.assertEqual(build_current_candidate(ROOT),self.candidate)

    def test_candidate_reproducible_under_input_map_order_and_crlf(self):
        reversed_sources=dict(reversed(list(self.sources.items())))
        rebuilt=build_candidate(self.parent,reversed_sources,list(reversed(self.annotations)),source_head=self.head)
        self.assertEqual(rebuilt,self.candidate)
        converted={path:data.replace(b'\n',b'\r\n') if path.endswith('.py') else data for path,data in self.sources.items()}
        # Portable module source hashes are preserved; binary parent assets stay raw.
        portable=build_candidate(self.parent,converted,self.annotations,source_head=self.head)
        self.assertEqual(portable,self.candidate)

    def test_self_consistent_candidate_tamper_still_rejected(self):
        tampered=copy.deepcopy(self.candidate)
        tampered['activation_allowed']=True
        tampered['candidate_sha256']=digest({k:v for k,v in tampered.items() if k!='candidate_sha256'})
        with self.assertRaises(ValueError):
            self.validate(tampered)
        tampered=copy.deepcopy(self.candidate)
        tampered['snapshot_proposal']['approved_v2_thresholds']={'approved':True,'threshold':0}
        with self.assertRaises(ValueError):
            self.validate(tampered)

    def test_json_type_tamper_never_passes_python_bool_numeric_equality(self):
        for field in ('activation_allowed','refreeze_executed'):
            changed=copy.deepcopy(self.candidate);changed[field]=0
            self.assertEqual(changed,self.candidate)  # Python's permissive equality is insufficient.
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.validate(changed)
        changed=copy.deepcopy(self.candidate)
        changed['snapshot_proposal']['activation_allowed']=0.0
        with self.assertRaises(ValueError):
            self.validate(changed)

    def test_stale_parent_or_current_module_bytes_are_rejected(self):
        parent=copy.deepcopy(self.parent)
        parent['content']['dataset']['dataset_version']='unapproved-change'
        parent['content_sha256']=digest(parent['content'])
        with self.assertRaises(ValueError):
            self.validate(parent=parent)
        changed=dict(self.sources)
        changed['eval/scoring_v2/context.py']+=b'\n# synthetic stale candidate test\n'
        with self.assertRaises(ValueError):
            self.validate(sources=changed)

    def test_parent_frozen_asset_change_and_invalid_parent_digest_fail(self):
        changed=dict(self.sources)
        changed['eval/phase35/data_A.py']+=b'\n'
        with self.assertRaises(ValueError):
            build_candidate(self.parent,changed,self.annotations,source_head=self.head)
        bad=copy.deepcopy(self.parent);bad['content_sha256']='0'*64
        with self.assertRaises(ValueError):
            build_candidate(bad,self.sources,self.annotations,source_head=self.head)

    def test_annotation_tamper_duplicate_source_or_dataset_mismatch_fail(self):
        duplicate=copy.deepcopy(self.annotations)+[copy.deepcopy(self.annotations[0])]
        with self.assertRaises(ValueError):
            build_candidate(self.parent,self.sources,duplicate,source_head=self.head)
        mismatch=copy.deepcopy(self.annotations);mismatch[0]['dataset_sha256']='0'*64
        with self.assertRaises(ValueError):
            build_candidate(self.parent,self.sources,mismatch,source_head=self.head)
        unknown=copy.deepcopy(self.annotations);unknown[0]['path']='../escape.json'
        with self.assertRaises(ValueError):
            build_candidate(self.parent,self.sources,unknown,source_head=self.head)

    def test_future_scope_records_no_invented_hashes_or_thresholds(self):
        scope=self.candidate['future_freeze_scope']
        self.assertTrue(any(r['path']=='eval/acceptance_preparation/provenance/' for r in scope))
        self.assertTrue(any(r['path']=='eval/framework/safety.py' for r in scope))
        self.assertTrue(all(r['approved_post_integration_sha256'] is None for r in scope))
        self.assertTrue(all(r['disposition']=='UNHASHED_FUTURE_REVIEW_SCOPE' for r in scope))
        selection=self.candidate['selection_contract']
        for key in ('approved_threshold_profile_identity','approved_gate_policy_identity','approved_run_header_identity'):
            self.assertIsNone(selection[key])

    def test_candidate_new_file_only_and_official_manifest_unchanged(self):
        official=ROOT/'eval/phase35/frozen_manifest.json'
        old_proposal=ROOT/'docs/remediation/phase_e2_engineering/WP8_PROPOSED_REFREEZE_PLAN.json'
        before=(official.read_bytes(),old_proposal.read_bytes())
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            output=Path(temporary)/'candidate_manifest.json'
            created=write_candidate(ROOT,output)
            self.assertEqual(created,self.candidate)
            self.assertEqual(json.loads(output.read_text()),created)
            with self.assertRaises(FileExistsError):
                write_candidate(ROOT,output)
        with self.assertRaises(ValueError):
            write_candidate(ROOT,official)
        self.assertEqual(before,(official.read_bytes(),old_proposal.read_bytes()))

    def test_candidate_cannot_target_official_result_subtree(self):
        output=ROOT/'eval/phase35/results/new-unapproved-candidate.json'
        self.assertFalse(output.exists())
        with self.assertRaises(ValueError):
            write_candidate(ROOT,output)
        self.assertFalse(output.exists())

    def test_caller_approvals_cannot_activate_and_v1_rollback_is_identity(self):
        self.assertIs(select_official_scorer(),score_generic)
        self.assertIs(rollback_to_v1(),score_generic)
        with self.assertRaises(AdoptionBlockedError):
            select_official_scorer('2.1.0',manifest=self.candidate,evidence={'approved':True})
        with self.assertRaises(AdoptionBlockedError):
            assert_official_adoption_allowed(self.candidate,{'approved':True},owner_signature='pretend')

    def test_development_rehearsal_reuses_wp7_without_new_infrastructure(self):
        expected=Path('/private/tmp/not-created')
        with patch.object(offline,'prepare_comparison',return_value=expected) as delegate:
            result=rehearse_development_comparison('source','annotations','root','run',tier=1,
                scorer_version='2.1.0',development=True,dataset_rev='pin')
        self.assertEqual(result,expected)
        delegate.assert_called_once()
        self.assertEqual(delegate.call_args.kwargs['split'],'dev')
        with self.assertRaises(AdoptionBlockedError):
            rehearse_development_comparison('source','annotations','root','run',tier=1,
                scorer_version='2.1.0',development=True,dataset_rev='pin',split='heldout')

    def test_all_44_protected_asset_raw_hashes_unchanged(self):
        for path,expected in PROTECTED.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected)


if __name__=='__main__':
    unittest.main()
