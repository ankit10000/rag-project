"""Scorer-specific proposal verification, never an official acceptance gate.

Registry membership is supplied evidence, not proof of approval. Human authority,
source authenticity and byte-to-hash verification belong to independent review.
No frozen gate, scorer, provider, database or production service is imported.
"""
import json
import math
import re

from eval.framework.hashing import raw_sha256

IDENTITY_FIELDS = frozenset({
    'scorer_name', 'scorer_version', 'scorer_hash', 'source_revision',
    'module_hashes', 'annotation_hash', 'dataset_revision', 'dataset_identity',
    'tier', 'split', 'threshold_profile_id', 'gate_policy_id', 'run_header_hash',
    'acceptance_status', 'threshold_profile_hash', 'gate_policy_hash',
})
HASH = re.compile(r'[0-9a-f]{64}')
STATUSES = {'OFFICIAL_V1_BASELINE', 'DEVELOPMENT_ONLY', 'PENDING_OWNER_DECISION'}


def _hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def validate_identity(identity):
    """Reject incomplete identities; labels cannot replace any content identity."""
    if not isinstance(identity, dict) or set(identity) != IDENTITY_FIELDS:
        raise ValueError('identity requires the exact documented provenance fields')
    for key, value in identity.items():
        if key == 'module_hashes':
            if not isinstance(value, dict) or not value:
                raise ValueError('module hashes are required')
            for path, digest in value.items():
                if (not isinstance(path, str) or not path or path.startswith('/')
                        or '\\' in path or '..' in path.split('/') or not _hash(digest)):
                    raise ValueError('invalid module identity')
        elif key in {'scorer_hash', 'annotation_hash', 'run_header_hash',
                     'threshold_profile_hash', 'gate_policy_hash', 'dataset_identity'}:
            if not _hash(value):
                raise ValueError('invalid hash: ' + key)
        elif key in {'source_revision', 'dataset_revision'}:
            if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{40}', value) is None:
                raise ValueError('revision requires full commit pin: ' + key)
        elif not isinstance(value, str) or not value.strip():
            raise ValueError('missing identity: ' + key)
    if identity['tier'] not in {'tier1', 'tier2'} or identity['split'] != 'dev':
        raise ValueError('proposal diagnostics permit explicit development splits only')
    if identity['acceptance_status'] not in STATUSES:
        raise ValueError('unsupported acceptance claim')
    return identity


def identity_digest(identity):
    """Canonical exact-identity key using the existing repository hash primitive."""
    validate_identity(identity)
    return raw_sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                allow_nan=False).encode('utf-8'))


def contract_digest(contract):
    """Hash policy content excluding run binding and unauthenticated review claims.

    Excluding identity_digest avoids circular content identities. All metric rules,
    threshold values, failure rules, IDs and schema keys remain content-bound.
    """
    if not isinstance(contract, dict):
        raise ValueError('contract must be an object')
    payload = {k: v for k, v in contract.items()
               if k not in {'identity_digest', 'owner_decision'}}
    return raw_sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                allow_nan=False).encode('utf-8'))


def evaluate_proposal(identity, registry, profile, policy, run):
    """Fail-closed diagnostic of an explicitly bound proposal.

    A structurally verified result is not acceptance. Even self-consistent caller
    evidence cannot authorize adoption, threshold changes or official gate use.
    """
    result = {'diagnostic_status': 'BLOCKED', 'reasons': [],
              'official_acceptance': False, 'adoption_allowed': False,
              'official_default': 'v1', 'authority': 'UNVERIFIED_CALLER_EVIDENCE'}
    try:
        key = identity_digest(identity)
        if not isinstance(registry, dict) or registry.get(key) != identity:
            raise ValueError('unknown exact scorer/run identity; no profile inheritance')
        for obj, fields, label in (
            (profile, {'id', 'identity_digest', 'metrics', 'owner_decision'}, 'profile'),
            (policy, {'id', 'identity_digest', 'threshold_profile_id', 'error_policy',
                      'incomplete_policy', 'rollback', 'owner_decision'}, 'policy'),
            (run, {'identity_digest', 'run_header_hash', 'complete', 'errors',
                   'invalid_records', 'metrics'}, 'run'),
        ):
            if not isinstance(obj, dict) or set(obj) != fields:
                raise ValueError('invalid ' + label + ' schema')
            if obj['identity_digest'] != key:
                raise ValueError(label + ' provenance mismatch')
        if (profile['id'] != identity['threshold_profile_id']
                or policy['id'] != identity['gate_policy_id']
                or policy['threshold_profile_id'] != profile['id']
                or run['run_header_hash'] != identity['run_header_hash']):
            raise ValueError('profile/policy/header binding mismatch')
        if (contract_digest(profile) != identity['threshold_profile_hash']
                or contract_digest(policy) != identity['gate_policy_hash']):
            raise ValueError('threshold or gate content changed; new identity required')
        if (policy['error_policy'] != 'BLOCK' or policy['incomplete_policy'] != 'BLOCK'
                or policy['rollback'] != 'KEEP_OFFICIAL_V1'):
            raise ValueError('unsupported failure or rollback policy')
        if (run['complete'] is not True or type(run['errors']) is not int
                or type(run['invalid_records']) is not int
                or run['errors'] != 0 or run['invalid_records'] != 0):
            raise ValueError('incomplete, erroneous or invalid run')
        if not isinstance(profile['metrics'], dict) or not profile['metrics']:
            raise ValueError('metric policy requires owner definition')
        if not isinstance(run['metrics'], dict):
            raise ValueError('invalid observed metrics')
        for name, rule in profile['metrics'].items():
            if not isinstance(name, str) or not name or not isinstance(rule, dict):
                raise ValueError('invalid metric rule')
            if set(rule) != {'role', 'operator', 'value'}:
                raise ValueError('invalid metric rule schema')
            if rule['role'] not in {'HARD_GATE', 'DIAGNOSTIC'}:
                raise ValueError('metric role undecided')
            if rule['role'] == 'DIAGNOSTIC':
                if rule['operator'] is not None or rule['value'] is not None:
                    raise ValueError('diagnostic metric cannot carry a threshold')
                continue
            threshold, observed = rule['value'], run['metrics'].get(name)
            if (type(threshold) not in {int, float} or not math.isfinite(threshold)
                    or type(observed) not in {int, float} or not math.isfinite(observed)):
                raise ValueError('missing/invalid hard-gate threshold or observation')
            op = rule['operator']
            if op not in {'>=', '<='}:
                raise ValueError('unknown threshold operator')
            if not (observed >= threshold if op == '>=' else observed <= threshold):
                raise ValueError('proposed metric gate failed: ' + name)
        # Caller owner_decision fields are deliberately not interpreted as authority.
        result['diagnostic_status'] = 'STRUCTURALLY_VERIFIED_PROPOSAL'
    except (ValueError, TypeError, KeyError) as exc:
        result['reasons'].append(str(exc))
    return result
