"""Pure acceptance-preparation status checks; never grants approval or adoption."""
import copy
from pathlib import PurePosixPath
import re

STATES = (
    'ENGINEERING_COMPLETE', 'PREPARED_FOR_REVIEW',
    'PENDING_INDEPENDENT_REVIEW', 'PENDING_OWNER_DECISION',
    'PENDING_EXTERNAL_EVIDENCE', 'BLOCKED_BY_APPROVAL', 'ACCEPTED',
)
CATEGORIES = (
    'engineering', 'review_package', 'independent_review', 'specification',
    'owner_decision', 'external_evidence', 'inactive_integration',
)
FIELDS = {'id', 'status', 'category', 'summary', 'owner_role',
          'next_action', 'can_continue_independently', 'evidence'}


def build_status(records):
    """Validate preparation records and return a detached, inactive dashboard.

    Evidence references are checked structurally; the lead must independently
    verify actual file bytes. This helper cannot authenticate an owner/reviewer.
    ACCEPTED is in the lifecycle vocabulary, but cannot be created here.
    """
    if not isinstance(records, list) or not records:
        raise ValueError('nonempty requirement records required')
    seen = set()
    for row in records:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('invalid requirement fields')
        for field in ('id', 'summary', 'owner_role', 'next_action'):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError('nonempty requirement text required')
        if row['id'] in seen:
            raise ValueError('duplicate requirement id')
        seen.add(row['id'])
        if row['status'] not in STATES or row['category'] not in CATEGORIES:
            raise ValueError('unknown status or category')
        if row['status'] == 'ACCEPTED':
            raise ValueError('preparation evidence cannot authenticate acceptance')
        if type(row['can_continue_independently']) is not bool:
            raise ValueError('explicit independent-work boolean required')
        if row['status'] == 'BLOCKED_BY_APPROVAL' and row['can_continue_independently']:
            raise ValueError('approval-blocked action cannot proceed independently')
        if not isinstance(row['evidence'], list) or not row['evidence']:
            raise ValueError('evidence required for every requirement')
        paths = set()
        for item in row['evidence']:
            if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
                raise ValueError('invalid evidence reference')
            path, digest = item['path'], item['sha256']
            if (not isinstance(path, str) or not path or path in paths
                    or PurePosixPath(path).is_absolute()
                    or '..' in PurePosixPath(path).parts or '\\' in path
                    or not isinstance(digest, str)
                    or re.fullmatch('[0-9a-f]{64}', digest) is None):
                raise ValueError('unsafe or malformed evidence reference')
            paths.add(path)
    return dict(schema='phase-e2-acceptance-status/1',
                official_scorer='v1', experimental_scorer='2.1.0',
                acceptance_approved=False, activation_allowed=False,
                refreeze_executed=False, requirements=copy.deepcopy(records),
                status_counts={state: sum(r['status'] == state for r in records)
                               for state in STATES},
                authority_limitation='Evidence preparation is not independent review, owner authorization, acceptance or re-freezing.')
