"""Structural/identity checks for an unadopted policy document, not a run gate.

All negative approvals below are in-memory fixtures. Passing these checks cannot
authenticate an owner, adopt a policy, or execute/accept an evaluation.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PATH = ROOT/'AI_ACCEPTANCE_POLICY_CANDIDATE.json'


def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def structural_problems(policy):
    problems = []
    if policy.get('status') != 'CANDIDATE_NOT_ADOPTED':
        problems.append('candidate must remain unadopted')
    adoption = policy.get('adoption', {})
    if (adoption.get('status') != 'PENDING_SPECIFIC_OWNER_DECISION'
            or adoption.get('activated') is not False
            or any(adoption.get(k) is not None for k in (
                'owner_decision', 'approved_policy_sha256', 'approved_dataset_sha256',
                'approved_threshold_profile', 'approved_gate_policy'))
            or adoption.get('local_approved_flag_is_authority') is not False):
        problems.append('local document is not adoption evidence')
    if policy.get('approved') is True:
        problems.append('self-supplied approved flag is not authority')
    execution = policy.get('execution_scope', {})
    if (execution.get('protected_original_heldout_execution') is not False
            or execution.get('original_dataset_case_ids_permitted') != []
            or execution.get('original_human_freeze_remains_in_force') is not True):
        problems.append('protected scope must stay inactive')
    ledger = [json.loads(line) for line in (ROOT/'AI_HELDOUT_113_REVIEW.jsonl').read_text().splitlines()]
    reference = policy.get('dataset', {}).get('review_reference', {})
    if (reference.get('case_ids') != sorted(r['case_id'] for r in ledger)
            or reference.get('execution_authorized') is not False):
        problems.append('review identity/coverage is not execution authority')
    for path, digest in policy.get('scorer', {}).get('source_sha256', {}).items():
        if digest != sha(path):
            problems.append('scorer bytes differ')
    for path, digest in policy.get('evidence_sha256', {}).items():
        if digest != sha(path):
            problems.append('referenced evidence differs')
    return problems


class CandidatePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(PATH.read_text())

    def test_versioned_candidate_is_not_original_freeze_or_an_adoption(self):
        self.assertEqual(structural_problems(self.policy), [])
        self.assertEqual(self.policy['schema'], 'ai-reviewed-acceptance-policy-candidate/1')
        self.assertEqual(self.policy['version'], 1)
        self.assertFalse(self.policy['adoption']['candidate_document_is_authorization'])
        self.assertFalse(self.policy['adoption']['general_engineering_permission_is_adoption'])
        self.assertFalse(self.policy['outcome_labels']['candidate_or_structural_tests_can_accept'])

    def test_exact_113_review_scope_and_unselected_acceptance_dataset(self):
        dataset = self.policy['dataset']
        self.assertEqual(len(dataset['review_reference']['case_ids']), 113)
        self.assertEqual(len(set(dataset['review_reference']['case_ids'])), 113)
        self.assertEqual(len(dataset['outstanding_correction_cases']), 22)
        self.assertEqual(len(dataset['unresolved_ambiguity_cases']), 8)
        selected = dataset['candidate_acceptance_dataset']
        for field in ('dataset_id', 'dataset_version', 'dataset_sha256', 'case_ids', 'eligible_case_count'):
            self.assertIsNone(selected[field])
        self.assertFalse(dataset['conditional_retention_is_final_label_acceptance'])
        self.assertFalse(dataset['silent_case_removal_or_reclassification'])
        self.assertFalse(dataset['remove_difficult_cases_to_pass'])

    def test_missing_hard_case_or_protected_execution_flag_is_rejected(self):
        modified = copy.deepcopy(self.policy)
        modified['dataset']['review_reference']['case_ids'].remove('A-conflict-03')
        self.assertTrue(structural_problems(modified))
        modified = copy.deepcopy(self.policy)
        modified['execution_scope']['protected_original_heldout_execution'] = True
        self.assertTrue(structural_problems(modified))
        self.assertFalse(self.policy['dataset']['copy_protected_cases_into_development'])

    def test_all_scorer_evidence_and_runtime_fingerprints_match_actual_bytes(self):
        frozen = json.loads((ROOT/'eval/phase35/frozen_manifest.json').read_text())
        reference = self.policy['dataset']['review_reference']
        self.assertEqual(reference['frozen_manifest_content_sha256'], frozen['content_sha256'])
        self.assertEqual(reference['dataset_sha256'], frozen['content']['dataset']['dataset_sha256'])
        for path, digest in self.policy['runtime_and_publication']['required_resolved_configuration_and_source_sha256'].items():
            with self.subTest(path=path):
                self.assertEqual(digest, sha(path))
        modified = copy.deepcopy(self.policy)
        modified['scorer']['source_sha256']['eval/answer_scoring.py'] = '0'*64
        self.assertTrue(structural_problems(modified))

    def test_no_inherited_or_invented_approved_acceptance_thresholds(self):
        thresholds = self.policy['thresholds']
        self.assertIsNone(thresholds['adopted_profile'])
        self.assertFalse(thresholds['inherit_original_v1_thresholds'])
        self.assertFalse(thresholds['use_83_of_113_review_judgments_as_answer_accuracy'])
        self.assertFalse(thresholds['definition_review_counts_are_performance'])
        for field in ('owner_approved_accuracy_rate', 'approved_eligible_case_count',
                      'minimum_correct', 'unsupported_rate_limit',
                      'citation_correctness_minimum', 'citation_completeness_minimum'):
            self.assertIsNone(thresholds['derivation_proposal'][field])
        self.assertEqual(thresholds['derivation_proposal']['minimum_correct_formula'],
                         'ceil(owner_approved_accuracy_rate * approved_eligible_case_count)')
        self.assertTrue(thresholds['must_be_set_before_observing_acceptance_results'])
        self.assertFalse(self.policy['scorer']['unknown_source_identity_may_inherit_thresholds'])

    def test_behavior_contract_distinguishes_omission_negative_and_partial(self):
        semantics = self.policy['response_semantics']
        self.assertEqual(semantics['missing_information'],
                         {'status':'abstained', 'valid_omission_citations':'optional'})
        self.assertEqual(semantics['explicit_negative_fact'],
                         {'status':'answered', 'valid_factual_citations':'required'})
        self.assertEqual(semantics['partial_information']['status'], 'partial')
        self.assertTrue(semantics['document_omission_does_not_establish_service_nonexistence'])
        self.assertFalse(semantics['broad_does_not_provide_abstention_rule'])
        self.assertFalse(self.policy['scorer']['response_behavior_contract']['factual_entailment_judge'])
        self.assertFalse(self.policy['metrics']['semantic_groundedness']['available_from_current_automatic_fields'])

    def test_error_publication_and_runtime_controls_remain_proposals(self):
        failure = self.policy['failure_treatment']
        self.assertEqual(failure['status'], 'PROPOSED_PENDING_ADOPTION')
        self.assertTrue(failure['raw_canonical_error_rows_preserved'])
        self.assertFalse(failure['existing_frozen_error_semantics_changed'])
        self.assertTrue(failure['no_automatic_rerun_after_score_or_interruption'])
        runtime = self.policy['runtime_and_publication']
        for field in ('separate_ordered_prompt_assembled_and_scoring_context_hashes',
                      'external_trust_anchor_and_genuine_signed_scope_required',
                      'one_time_approval_and_output_reservation',
                      'failed_attempt_consumption_and_private_journal_preserved',
                      'atomic_no_replace_complete_output'):
            self.assertTrue(runtime[field])
        self.assertFalse(runtime['official_runner_integration_activated'])
        self.assertFalse(runtime['bundle_checksum_is_authentic_review_proof'])

    def test_historical_review_provenance_is_not_reattributed_or_humanized(self):
        provenance = self.policy['review_provenance']
        self.assertEqual(provenance['required_initial_records'], 339)
        manifest = json.loads((ROOT/provenance['initial_hash_manifest']).read_text())
        self.assertEqual(len(manifest['initial_file_sha256']), 3)
        count = 0
        for path, digest in manifest['initial_file_sha256'].items():
            self.assertEqual(sha(path), digest)
            initial_rows = [json.loads(line) for line in (ROOT/path).read_text().splitlines()]
            count += len(initial_rows)
            self.assertTrue(all(r['reviewer_type'] == 'AI' for r in initial_rows))
        self.assertEqual(count, 339)
        self.assertFalse(provenance['historical_attribution']['retroactive_author_reassignment'])
        self.assertIsNone(self.policy['policy_author']['exact_runtime_model_id'])
        self.assertFalse(provenance['human_independent_review_equivalence'])
        self.assertEqual(provenance['human_review_completed'], 0)
        self.assertFalse(self.policy['outcome_labels']['formal_human_certification_from_ai_only'])

    def test_local_approval_shape_cannot_turn_candidate_into_acceptance(self):
        modified = copy.deepcopy(self.policy)
        modified['approved'] = True
        modified['status'] = 'ADOPTED'
        modified['adoption'].update(status='APPROVED', activated=True,
            owner_decision={'approved_by':'synthetic fixture, not real authority'},
            approved_policy_sha256='a'*64, approved_dataset_sha256='b'*64)
        self.assertTrue(structural_problems(modified))
        self.assertEqual(self.policy['outcome_labels']['original_official_status'],
                         'OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING')
        self.assertIn('3/4', self.policy['outcome_labels']['original_fail_must_remain'])


if __name__ == '__main__':
    unittest.main()
