"""Pure WP8 evidence checklists and unapproved re-freeze proposals.

This is not an execution/adoption gate and cannot authenticate human authority.
Review assertions remain unverified; no API here can activate v2 or re-freeze.
"""
import copy
import hashlib
import json
from pathlib import PurePosixPath
import re
from eval.framework.hashing import portable_sha256

READINESS_SCHEMA = 'phase35-wp8-acceptance-readiness/1'
PROPOSAL_SCHEMA = 'phase35-wp8-refreeze-proposal/1'
EVIDENCE_REQUIREMENTS = (
    'annotation_validation', 'flip_accounting', 'clarification_register',
    'v1_compatibility', 'v2_correctness', 'runner_preparation',
    'output_isolation', 'manifest_integrity', 'protected_hashes',
    'rollback_preparation',
)
REQUIRED_DECISIONS = (
    'real_case_annotation_review', 'independent_human_review',
    'human_approved_flip_golden_list', 'specification_clarification_acceptance',
    'V5_scorer_adoption', 'scorer_keyed_threshold_review',
    'V9_error_and_gate_policy', 'frozen_runner_gate_integration_approval',
    'refreeze_approval',
)
_SHA = re.compile(r'[0-9a-f]{64}')


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _path(value):
    return (isinstance(value, str) and bool(value)
            and not PurePosixPath(value).is_absolute()
            and '..' not in PurePosixPath(value).parts and '\\' not in value)


def assess_readiness(evidence, review_records=None):
    """Return a diagnostic engineering checklist, never approval.

    ``evidence`` maps known requirement names to {status, summary, artifacts};
    artifacts contain repo-relative path and actual SHA-256. Missing requirements
    remain NOT_RUN. This pure function checks evidence structure, not filesystem
    truth or human identity. Even well-formed review claims remain UNVERIFIED.
    """
    if not isinstance(evidence, dict) or set(evidence)-set(EVIDENCE_REQUIREMENTS):
        raise ValueError('unknown or malformed engineering evidence')
    checks = []
    for key in EVIDENCE_REQUIREMENTS:
        entry = evidence.get(key, dict(status='NOT_RUN', summary='Evidence not supplied', artifacts=[]))
        if not isinstance(entry, dict) or set(entry) != {'status', 'summary', 'artifacts'}:
            raise ValueError('invalid evidence entry: '+key)
        if entry['status'] not in ('PASS', 'FAIL', 'NOT_RUN') or not isinstance(entry['summary'], str) or not entry['summary']:
            raise ValueError('invalid evidence status or summary: '+key)
        artifacts = entry['artifacts']
        if not isinstance(artifacts, list) or any(not isinstance(a, dict) or set(a) != {'path','sha256'} or not _path(a['path']) or not _sha(a['sha256']) for a in artifacts):
            raise ValueError('invalid evidence artifact: '+key)
        if len({a['path'] for a in artifacts}) != len(artifacts) or (entry['status']=='PASS' and not artifacts):
            raise ValueError('duplicate or absent passing evidence: '+key)
        checks.append(dict(id=key, **copy.deepcopy(entry)))
    if review_records is None:
        review_records = []
    if not isinstance(review_records, list):
        raise ValueError('review records must be a list, never an approval boolean')
    claims = []
    for record in review_records:
        if not isinstance(record, dict) or set(record) != {'decision','claimed_status','artifact'}:
            raise ValueError('malformed review assertion')
        artifact = record['artifact']
        if record['decision'] not in REQUIRED_DECISIONS or record['claimed_status'] not in ('APPROVED','REJECTED','DEFERRED','PENDING_OWNER_DECISION'):
            raise ValueError('unknown review decision or status')
        if not isinstance(artifact, dict) or set(artifact) != {'path','sha256'} or not _path(artifact['path']) or not _sha(artifact['sha256']):
            raise ValueError('review assertion requires traceable artifact identity')
        claims.append(dict(copy.deepcopy(record), verification='UNVERIFIED'))
    gaps = [row['id'] for row in checks if row['status'] != 'PASS']
    return dict(schema=READINESS_SCHEMA, engineering_preparation_complete=not gaps,
                checks=checks, engineering_gaps=gaps, review_assertions=claims,
                pending_owner_decisions=list(REQUIRED_DECISIONS),
                formal_acceptance_ready=False, adoption_allowed=False,
                refreeze_allowed=False, accepted_default='v1',
                limitation='A structured artifact or caller assertion is not authenticated independent review or owner approval.')


def propose_refreeze(frozen_manifest, sources):
    """Build a deterministic proposal inventory, not a frozen manifest.

    Existing frozen inputs must reproduce their portable hashes. Additional
    WP6/WP7 sources are candidate snapshots only; future patched runner hashes,
    accepted scorer identity and v2 thresholds are deliberately unknown.
    ``sources`` maps explicit repo-relative paths to bytes; no I/O occurs.
    """
    if not isinstance(frozen_manifest, dict) or not isinstance(frozen_manifest.get('content'), dict):
        raise ValueError('a complete existing frozen manifest is required')
    manifest = copy.deepcopy(frozen_manifest)
    digest = hashlib.sha256(_canonical(manifest['content'])).hexdigest()
    if manifest.get('content_sha256') != digest:
        raise ValueError('parent frozen manifest content hash mismatch')
    if not isinstance(sources, dict) or any(not _path(path) or not isinstance(data, bytes) for path,data in sources.items()):
        raise ValueError('sources must be explicit relative paths and bytes')
    assets = manifest['content'].get('assets')
    if not isinstance(assets, list) or not assets:
        raise ValueError('missing parent frozen asset inventory')
    records, seen = [], set()
    for asset in assets:
        if not isinstance(asset, dict) or not _path(asset.get('path')) or asset['path'] in seen or asset.get('kind') not in ('text','binary') or not _sha(asset.get('portable_sha256')):
            raise ValueError('invalid or duplicate parent frozen asset')
        path = asset['path']; seen.add(path)
        if path not in sources or portable_sha256(sources[path],asset['kind']) != asset['portable_sha256']:
            raise ValueError('parent frozen asset is missing or changed: '+path)
        records.append(dict(path=path, kind=asset['kind'], group=asset.get('group'),
                            portable_sha256=asset['portable_sha256'], disposition='PRESERVE_EXISTING'))
    additions = []
    for path in sorted(set(sources)-seen):
        if not path.startswith(('eval/scoring_v2/','eval/runner_preparation/')) or not path.endswith(('.py','.json')):
            raise ValueError('candidate outside explicitly prepared WP6/WP7 scope')
        additions.append(dict(path=path, kind='text', portable_sha256=portable_sha256(sources[path],'text'),
                              proposed_group='scorer_v2' if path.startswith('eval/scoring_v2/') else 'runner_preparation',
                              disposition='CANDIDATE_SNAPSHOT_NOT_APPROVED'))
    proposal = dict(schema=PROPOSAL_SCHEMA, status='PENDING_OWNER_REVIEW',
        parent_frozen_manifest_content_sha256=digest,
        activation_allowed=False, refreeze_executed=False, accepted_default='v1',
        preserved_assets=sorted(records,key=lambda a:a['path']), candidate_assets=additions,
        future_manifest_format='phase35-frozen-manifest/2',
        approved_acceptance_scorer=None, approved_v2_thresholds=None,
        future_patched_runner_gate_hashes=None,
        required_decisions=list(REQUIRED_DECISIONS),
        procedure=[
            'Record independent annotation and dataset review without overwriting original records.',
            'Approve a provenance-bound flip golden list and specification clarifications.',
            'Record V5 adoption, scorer-keyed threshold review and V9/error/gate policy decisions.',
            'Review isolated integration changes and capture their actual post-approval hashes.',
            'Run deterministic compatibility, refusal, output-isolation and reproducibility checks.',
            'Generate a NEW lineage-bound manifest and review package only after authorization.',
            'Verify the new freeze; retain the prior v1 manifest, inputs and historical results.',
        ], rollback=[
            'Before activation, rollback is a no-op: official v1 files and selection are unchanged.',
            'After a separately approved integration, use a separately reviewed reverse patch and retained v1 manifest; never reset or rewrite historical results.',
            'Reproduce frozen v1 hashes, phrase tables and probe results before enabling any evaluation.',
        ])
    proposal['proposal_sha256'] = hashlib.sha256(_canonical(proposal)).hexdigest()
    return proposal
