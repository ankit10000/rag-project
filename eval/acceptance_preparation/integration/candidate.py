"""Pure, non-authorizing integration snapshots, reusing the WP8 proposal builder."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from eval.acceptance_preparation.readiness import propose_refreeze, REQUIRED_DECISIONS
from eval.framework.hashing import portable_sha256
from eval.scoring_v2 import load_annotations
from eval.scoring_v2.rescore_meta import scorer_identity

SCHEMA='phase-e2-integration-candidate/1'
FUTURE_SCOPE=(
    'eval/framework/safety.py','eval/framework/frozen_manifest.py',
    'eval/framework/hashing.py','eval/framework/integrity.py','eval/framework/cli.py',
    'eval/harness.py','eval/review/cli.py',
    'services/answer_service.py','services/answer_prompt.py','services/rag_service.py',
    'services/context_assembly_service.py','services/citation_service.py',
    'services/hybrid_search_service.py','services/reranker_service.py',
    'services/ingestion_service.py','services/retrieval_config.py',
    'services/pdf_parser.py','services/chunker.py','services/llm_service.py',
    'eval/acceptance_preparation/adoption.py',
    'eval/acceptance_preparation/readiness.py',
    'eval/acceptance_preparation/clarifications.py',
    'eval/acceptance_preparation/gate_policy/',
    'eval/acceptance_preparation/provenance/',
    'eval/acceptance_preparation/clarifications/',
    'eval/acceptance_preparation/integration/',
    'independent_review/flip_review_package/',
)


def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _relative(path):
    if (not isinstance(path,str) or not path or PurePosixPath(path).is_absolute()
            or '..' in PurePosixPath(path).parts or '\\' in path or str(PurePosixPath(path))!=path):
        raise ValueError('annotation source must be an exact repository-relative path')
    return path


def _revision(value):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{40}',value) is None:
        raise ValueError('a full Git commit identity is required')
    return value


def build_candidate(parent_manifest, sources, annotation_inputs, *, source_head):
    """Snapshot actual bytes; it cannot create an accepted manifest or policy.

    Each annotation input is {path, data:bytes, dataset_revision,
    dataset_sha256}. Dataset-aware validation happens in the I/O wrapper.
    The pure builder checks the binding shape and annotation hash identity.
    """
    source_head=_revision(source_head)
    proposal=propose_refreeze(parent_manifest,sources)
    if not isinstance(annotation_inputs,list) or not annotation_inputs:
        raise ValueError('explicit annotation input bindings are required')
    modules={p:b for p,b in sources.items() if p.startswith('eval/scoring_v2/') and p.endswith('.py')}
    bindings=[];seen=set()
    for entry in annotation_inputs:
        if not isinstance(entry,dict) or set(entry)!={'path','data','dataset_revision','dataset_sha256'}:
            raise ValueError('malformed annotation input binding')
        path=_relative(entry['path']); revision=_revision(entry['dataset_revision'])
        if path in seen or not isinstance(entry['data'],bytes):
            raise ValueError('duplicate or non-byte annotation source')
        seen.add(path)
        def pairs(items):
            out={}
            for key,value in items:
                if key in out:
                    raise ValueError('duplicate annotation JSON key')
                out[key]=value
            return out
        parsed=json.loads(entry['data'],object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite annotation JSON')))
        ann=load_annotations(parsed)
        if ann['dataset_sha256']!=entry['dataset_sha256'] or re.fullmatch('[0-9a-f]{64}',entry['dataset_sha256']) is None:
            raise ValueError('annotation dataset identity mismatch')
        if path in sources and sources[path]!=entry['data']:
            raise ValueError('annotation bytes differ from candidate snapshot')
        bindings.append(dict(path=path,source_sha256=hashlib.sha256(entry['data']).hexdigest(),
            portable_sha256=portable_sha256(entry['data'],'text'),dataset_revision=revision,
            dataset_version=ann['dataset_version'],dataset_sha256=ann['dataset_sha256'],
            scorer=scorer_identity(modules,entry['data']),authority='UNAPPROVED_INPUT_SNAPSHOT'))
    if 'eval/scoring_v2/annotations.json' not in seen:
        raise ValueError('current package annotation snapshot binding is required')
    candidate=dict(schema=SCHEMA,status='PREPARED_FOR_REVIEW',activation_allowed=False,
        refreeze_executed=False,official_default='v1',snapshot_proposal=proposal,
        source_snapshot=dict(git_head=source_head,scope='WORKING_TREE_BYTES_NOT_COMMITTED_SOURCE_AT_HEAD'),
        annotation_bindings=sorted(bindings,key=lambda r:r['path']),
        selection_contract=dict(official_default='v1',development_version='2.1.0',
            identity_key=['name','version','sha256','module_sha256','annotations_sha256'],
            pending_conditions=list(REQUIRED_DECISIONS),official_v2_selection_available=False,
            approved_threshold_profile_identity=None,approved_gate_policy_identity=None,
            approved_run_header_identity=None,activation_allowed=False),
        future_freeze_scope=[dict(path=p,disposition='UNHASHED_FUTURE_REVIEW_SCOPE',
            approved_post_integration_sha256=None) for p in FUTURE_SCOPE],
        limitation='Candidate bytes and caller claims are not independent review, adoption or re-freeze authority.')
    candidate['candidate_sha256']=digest(candidate)
    return candidate


def validate_candidate(candidate,parent_manifest,sources,annotation_inputs,*,source_head):
    """Compare a candidate with actual inputs supplied by a trusted I/O caller."""
    if not isinstance(candidate,dict) or candidate.get('schema')!=SCHEMA:
        raise ValueError('this is not a preparation candidate')
    expected=build_candidate(parent_manifest,sources,annotation_inputs,source_head=source_head)
    if canonical_bytes(candidate)!=canonical_bytes(expected):
        raise ValueError('candidate is stale, tampered, unauthorized or bound to different inputs')
    return dict(schema='phase-e2-candidate-validation/1',status='PASS',
        candidate_sha256=expected['candidate_sha256'],
        parent_manifest_content_sha256=expected['snapshot_proposal']['parent_frozen_manifest_content_sha256'],
        preserved_assets=len(expected['snapshot_proposal']['preserved_assets']),
        candidate_assets=len(expected['snapshot_proposal']['candidate_assets']),
        annotation_bindings=len(expected['annotation_bindings']),
        activation_allowed=False,accepted_default='v1',refreeze_executed=False,
        pending_owner_decisions=list(REQUIRED_DECISIONS))
