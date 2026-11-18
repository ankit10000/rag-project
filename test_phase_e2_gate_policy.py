"""Synthetic proposal tests; no official evaluation or external resources."""
import testsafe
testsafe.require_scratch_db()

import copy
import unittest

from eval.acceptance_preparation.gate_policy import (
    identity_digest, validate_identity, evaluate_proposal, contract_digest,
)


class GatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.identity = dict(scorer_name='synthetic-v2', scorer_version='2.1.0',
            scorer_hash='a'*64, source_revision='1'*40,
            module_hashes={'synthetic.py': 'b'*64}, annotation_hash='c'*64,
            dataset_revision='2'*40, dataset_identity='3'*64,
            tier='tier1', split='dev', threshold_profile_id='synthetic-profile-1',
            gate_policy_id='synthetic-policy-1', run_header_hash='d'*64,
            acceptance_status='DEVELOPMENT_ONLY', threshold_profile_hash='e'*64,
            gate_policy_hash='f'*64)
        key = 'temporary-unbound'
        # Arbitrary synthetic threshold exercises operators; no project value proposed.
        self.profile = dict(id='synthetic-profile-1', identity_digest=key,
            metrics={'synthetic_score': dict(role='HARD_GATE', operator='>=', value=4)},
            owner_decision=None)
        self.policy = dict(id='synthetic-policy-1', identity_digest=key,
            threshold_profile_id='synthetic-profile-1', error_policy='BLOCK',
            incomplete_policy='BLOCK', rollback='KEEP_OFFICIAL_V1', owner_decision=None)
        self.run = dict(identity_digest=key, run_header_hash='d'*64, complete=True,
                        errors=0, invalid_records=0, metrics={'synthetic_score': 5})
        self.rebind()

    def rebind(self):
        self.identity['threshold_profile_hash'] = contract_digest(self.profile)
        self.identity['gate_policy_hash'] = contract_digest(self.policy)
        key = identity_digest(self.identity)
        for obj in (self.profile, self.policy, self.run): obj['identity_digest'] = key
        self.registry = {key: copy.deepcopy(self.identity)}

    def evaluate(self):
        return evaluate_proposal(self.identity, self.registry, self.profile, self.policy, self.run)

    def blocked(self):
        result = self.evaluate()
        self.assertEqual(result['diagnostic_status'], 'BLOCKED')
        self.assertTrue(result['reasons'])
        self.assertFalse(result['official_acceptance'])

    def test_positive_is_only_structural(self):
        before = copy.deepcopy((self.identity, self.registry, self.profile, self.policy, self.run))
        result = self.evaluate()
        self.assertEqual(result['diagnostic_status'], 'STRUCTURALLY_VERIFIED_PROPOSAL')
        self.assertFalse(result['official_acceptance'])
        self.assertFalse(result['adoption_allowed'])
        self.assertEqual(result['official_default'], 'v1')
        self.assertEqual(before, (self.identity, self.registry, self.profile, self.policy, self.run))
        self.assertEqual(result, self.evaluate())

    def test_full_identity_changes_never_inherit(self):
        original = copy.deepcopy(self.identity)
        for field in self.identity:
            with self.subTest(field=field):
                self.identity = copy.deepcopy(original)
                if field == 'module_hashes': self.identity[field]['synthetic.py'] = 'e'*64
                elif field.endswith('_hash'): self.identity[field] = 'e'*64
                elif field == 'tier': self.identity[field] = 'tier2'
                else: self.identity[field] += '-changed'
                self.blocked()

    def test_missing_provenance(self):
        original = copy.deepcopy(self.identity)
        for field in original:
            self.identity = copy.deepcopy(original)
            del self.identity[field]
            self.blocked()

    def test_mismatched_bindings(self):
        for obj, field in ((self.profile, 'id'), (self.policy, 'id'),
                           (self.policy, 'threshold_profile_id'), (self.run, 'run_header_hash'),
                           (self.profile, 'identity_digest'), (self.run, 'identity_digest')):
            old = obj[field]
            obj[field] = 'mismatch'
            self.blocked()
            obj[field] = old

    def test_incomplete_errors_invalid_records(self):
        for field, value in [('complete', False), ('complete', 1), ('errors', 1),
                             ('errors', -1), ('errors', False), ('invalid_records', 1)]:
            old = self.run[field]
            self.run[field] = value
            self.blocked()
            self.run[field] = old

    def test_unresolved_and_invalid_thresholds(self):
        rule = self.profile['metrics']['synthetic_score']
        for value in [None, True, float('nan'), float('inf'), '4']:
            rule['value'] = value
            self.blocked()

    def test_gate_failure_and_missing_metrics(self):
        for metrics in [{}, {'synthetic_score': 3}, {'synthetic_score': True}]:
            self.run['metrics'] = metrics
            self.blocked()

    def test_diagnostic_metric_has_no_gate(self):
        self.profile['metrics'] = {'diagnostic': dict(role='DIAGNOSTIC', operator=None, value=None)}
        self.rebind()
        self.assertEqual(self.evaluate()['diagnostic_status'], 'STRUCTURALLY_VERIFIED_PROPOSAL')

    def test_forged_approval_never_authorizes(self):
        self.profile['owner_decision'] = {'approved': True, 'reviewer': 'assistant'}
        self.policy['owner_decision'] = 'APPROVED'
        self.assertFalse(self.evaluate()['official_acceptance'])
        self.assertFalse(self.evaluate()['adoption_allowed'])

    def test_unsupported_policies_block(self):
        for field in ['error_policy', 'incomplete_policy', 'rollback']:
            old = self.policy[field]
            self.policy[field] = 'IGNORE'
            self.blocked()
            self.policy[field] = old

    def test_canonical_identity_and_bad_paths(self):
        self.assertEqual(identity_digest(self.identity), identity_digest(dict(reversed(list(self.identity.items())))))
        for path in ['../outside.py', '/absolute.py', 'a\\b.py']:
            self.identity['module_hashes'] = {path: 'b'*64}
            with self.assertRaises(ValueError): validate_identity(self.identity)

    def test_heldout_and_acceptance_claim_rejected(self):
        self.identity['split'] = 'heldout'
        self.blocked()
        self.identity['split'] = 'dev'
        self.identity['acceptance_status'] = 'ACCEPTED'
        self.blocked()

    def test_same_label_changed_content_blocks(self):
        self.profile['metrics']['synthetic_score']['value'] = 0
        self.blocked()
        self.profile['metrics']['synthetic_score']['value'] = 4
        self.policy['error_policy'] = 'IGNORE'
        self.blocked()


if __name__ == '__main__':
    unittest.main()
