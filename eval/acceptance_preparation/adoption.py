"""WP8 reviewable adoption preparation; no official activation or gate changes.

Caller evidence is an untrusted claim, never independent review or authorization.
Even a proposed manifest or a truthy approval object cannot enable v2 here.
The only executable opt-in path delegates WP7's offline development comparison.
"""
import copy
import hashlib
import json

PLAN_SCHEMA = 'phase35-wp8-runner-adoption-plan/1'
_REQUIREMENTS = (
    ('annotation_review', 'V-3', 'Independent real-case annotation review and provenance'),
    ('flip_golden_list', 'WP5 §16.5', 'Human-approved complete scorer flip golden list'),
    ('specification_review', 'V-6–V-11', 'Formal disposition of specification clarifications and scoring policies'),
    ('scorer_adoption', 'V-5', 'Owner acceptance-scorer selection before official evaluation'),
    ('threshold_review', 'WP5 §15', 'Separate owner review of scorer-keyed thresholds'),
    ('error_policy', 'V-9', 'Owner-selected error-row and provider-outage policy'),
    ('gate_policy', 'WP7/WP8', 'Approved run-once, consumed-approval, output and review-completion policies'),
    ('runtime_provenance', 'WP5 §12.4', 'Approved runtime context, model and resolved-configuration capture'),
    ('refreeze', 'WP5 §15', 'Reviewed lineage-aware manifest and approved asset re-freeze'),
)
_LOCATIONS = (
    ('eval/phase35/run_eval.py', 'main/enforce_split_gate/run_tier1/run_tier2',
     'Future explicit selector, provenance capture and exclusive official output; preserve default v1'),
    ('eval/framework/safety.py', 'runner_gate/check_run_request/approval_problems/FROZEN_THRESHOLDS',
     'Future owner-approved scorer binding, run-once claim and consumed-approval policy'),
    ('eval/framework/frozen_manifest.py', 'MANIFEST_FORMAT/FROZEN_ASSETS/build_content/load_frozen_manifest',
     'Future reviewed scorer asset group, identity, lineage and format transition'),
    ('eval/framework/cli.py', 'cmd_report',
     'Future explicit version-aware reporting; never reinterpret v1 rows as v2'),
    ('eval/review/cli.py', 'DATASET_VERSION/_manifest_sha/cmd_build_dev_review',
     'Future review-version binding to approved manifest; preserve existing reviews'),
)


class AdoptionBlockedError(ValueError):
    """Official adoption is unavailable in this preparation-only module."""


def _json_object(value, name):
    if not isinstance(value, dict):
        raise ValueError(name + ' must be a JSON object')
    def validate(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError(name + ' contains a non-text key')
            for child in item.values():
                validate(child)
        elif isinstance(item, list):
            for child in item:
                validate(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError(name + ' contains a non-JSON value')
    validate(value)
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError(name + ' contains invalid JSON values') from exc
    return copy.deepcopy(value)


def build_adoption_plan(manifest, evidence):
    """Return deterministic pending requirements, without granting authorization.

    The content digest is verified internally, not against the filesystem or an
    approval authority. Evidence is retained as explicitly unverified claims;
    passing evidence with approved=True cannot clear any requirement.
    """
    manifest = _json_object(manifest, 'manifest')
    claims = _json_object(evidence, 'evidence')
    content = manifest.get('content')
    valid_content = isinstance(content, dict)
    digest = None
    if valid_content:
        canonical = json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return dict(schema=PLAN_SCHEMA, official_default='v1', proposed_development_scorer='2.1.0',
        activation_allowed=False, official_execution_available=False,
        independent_review_required=True, status='PENDING_OWNER_DECISION',
        manifest_reference=dict(format=content.get('manifest_format') if valid_content else None,
            declared_content_sha256=manifest.get('content_sha256'), computed_content_sha256=digest,
            internally_consistent=valid_content and digest == manifest.get('content_sha256'),
            filesystem_verified=False, lineage_adopted=False),
        pending_requirements=[dict(id=rid,authority=authority,requirement=text,
            status='PENDING_OWNER_DECISION') for rid,authority,text in _REQUIREMENTS],
        frozen_integration=[dict(path=path,interface=interface,required_change=change,applied=False)
                            for path,interface,change in _LOCATIONS],
        evidence=dict(authority='UNVERIFIED_CALLER_CLAIMS',claims=claims,adoption_authorization=False),
        rollback=dict(default='v1',method='select_official_scorer()',mutates_files=False,
                      deletes_artifacts=False,changes_gate=False))


def assert_official_adoption_allowed(manifest=None, evidence=None, **untrusted_claims):
    """Always refuse; this module has no official activation capability.

    Extra claim fields are accepted only to ensure fake caller-supplied approvals
    cannot become an authorization channel. Nothing is persisted or consumed.
    """
    raise AdoptionBlockedError('official scorer adoption remains owner-controlled; preparation cannot authorize it')


def select_official_scorer(scorer_version='v1', *, manifest=None, evidence=None):
    """Return exactly frozen v1; official v2 selection is unavailable here."""
    if scorer_version != 'v1':
        assert_official_adoption_allowed(manifest,evidence)
    from eval.runner_preparation.selection import select_scorer
    return select_scorer()


def rollback_to_v1():
    """Select the existing v1 callable without changing files, gates or artifacts."""
    return select_official_scorer()


def rehearse_development_comparison(results, annotations, output_root, run_id, *,
        tier, scorer_version, development=False, dataset_rev=None, run_header=None,
        chunk_config=None, split='dev'):
    """Explicit offline rehearsal only; delegate unchanged WP7 isolation checks."""
    if development is not True or scorer_version != '2.1.0' or split != 'dev':
        raise AdoptionBlockedError('rehearsal requires explicit development=True, scorer 2.1.0 and dev split')
    if type(tier) is not int or tier not in (1,2):
        raise ValueError('rehearsal tier must be 1 or 2')
    from eval.runner_preparation.offline import prepare_comparison
    return prepare_comparison(results,annotations,output_root,run_id,tier=tier,
        scorer_version=scorer_version,dataset_rev=dataset_rev,run_header=run_header,
        chunk_config=chunk_config,split=split)
