"""Unactivated v1 execution-envelope mechanics; no CLI or provider/database imports.

This module does not call the frozen runner or grant approval. An eventual adapter
must be separately reviewed. Trust keys and the persistent ledger are supplied by
the deploying authority; choosing a local key does not establish a real owner.
``verify_prerequisites`` must independently check genuine review and policy
records, not merely trust their presence or a caller's HUMAN_REVIEWED label.

The signed scope is one tier/split and one previously unused JSON bundle path.
Approval and output reservations are durable and never automatically reclaimed,
even after failure. All cooperating invocations must use the same trusted ledger.
Private journals retain partial rows; only a fully sealed bundle is published.
Canonical v1 error rows remain unchanged; this module never accepts a run.
The HMAC envelope is a candidate mechanism, not an approved replacement for the
existing frozen runner gate/approval format. A future adapter must satisfy both
that gate and actual human/owner prerequisites before execution.

Explicit adapter API (no default protected executor is supplied)::
    execute(scope, externally_signed_approval, authority=external_trust_anchor,
            ledger_root=scope['ledger_root'], runtime_config=capture.resolved_config,
            verify_prerequisites=trusted_review_and_policy_verifier,
            executor=unchanged_rows_adapter, capture_snapshot=capture.snapshot)
The adapter's ``executor(emit_row)`` calls emit for each unchanged v1 result;
use RuntimeCapture.attach around the already-authorized synchronous invocation.
No key, owner identity, genuine approval or human judgment is generated here.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCORER_FILES = ('eval/phase35/run_eval.py', 'eval/answer_scoring.py')
HEX = re.compile(r'[0-9a-f]{64}')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}')


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class TrustedAuthority:
    key_id: str
    key: bytes = field(repr=False)


@dataclass(frozen=True)
class VerifiedInputs:
    expected_case_ids: tuple


class IncompleteRunError(RuntimeError):
    pass


class PublicationDurabilityError(OSError):
    """Complete output exists, but directory durability confirmation failed."""


def _hex(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _scope(scope):
    keys = {'manifest_sha256', 'dataset_sha256', 'scorer_sha256', 'tier', 'split', 'output_path', 'ledger_root', 'runtime_config_sha256'}
    if not isinstance(scope, dict) or set(scope) != keys:
        raise ValueError('exact execution scope required')
    if not all(_hex(scope[x]) for x in ('manifest_sha256', 'dataset_sha256', 'runtime_config_sha256')):
        raise ValueError('invalid identity hash')
    if (not isinstance(scope['scorer_sha256'], dict)
            or set(scope['scorer_sha256']) != set(SCORER_FILES)
            or not all(_hex(v) for v in scope['scorer_sha256'].values())):
        raise ValueError('exact v1 source identity required')
    if type(scope['tier']) is not int or scope['tier'] not in (1, 2) or scope['split'] not in ('dev', 'heldout'):
        raise ValueError('explicit tier and split required')
    path = scope['output_path']
    if not isinstance(path, str) or not path or path != os.path.abspath(path):
        raise ValueError('canonical absolute output path required')
    if path != str(Path(path)) or any(c in path for c in ('\x00', '\n', '\r')):
        raise ValueError('ambiguous output path')
    ledger = scope['ledger_root']
    if not isinstance(ledger, str) or not ledger or ledger != os.path.abspath(ledger) or ledger != str(Path(ledger)):
        raise ValueError('canonical signed ledger root required')
    official = ROOT/'eval/phase35'
    if Path(path).is_relative_to(official):
        raise ValueError('unactivated envelope cannot write frozen official tree')
    return scope


def verify_current_inputs(scope, runtime_config):
    """Read-only fresh freeze/source/eligibility verification, no case execution."""
    from eval.framework.frozen_manifest import load_frozen_manifest, verify_frozen_manifest
    from eval.framework.integrity import load_dataset, split_of
    frozen, problems = load_frozen_manifest(str(ROOT/'eval/phase35/frozen_manifest.json'))
    if not problems:
        problems, _ = verify_frozen_manifest(frozen)
    if problems:
        raise ValueError('frozen manifest does not reproduce')
    if (scope['manifest_sha256'] != frozen['content_sha256'] or
            scope['dataset_sha256'] != frozen['content']['dataset']['dataset_sha256'] or
            scope['scorer_sha256'] != {f: digest((ROOT/f).read_bytes()) for f in SCORER_FILES}):
        raise ValueError('requested frozen identity differs from current bytes')
    sources = runtime_config.get('source_sha256')
    if not isinstance(sources, dict) or not set(SCORER_FILES).issubset(sources):
        raise ValueError('actual runtime source identity required')
    for name, expected_hash in sources.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts
                or not _hex(expected_hash) or digest((ROOT/name).read_bytes()) != expected_hash):
            raise ValueError('runtime source identity differs from current bytes')
    _, cases = load_dataset()
    return VerifiedInputs(tuple(c['id'] for c in cases
        if split_of(c['id']) == scope['split'] and (scope['tier'] == 1 or c['tier'] == 'both')))


def _authenticate(approval, scope, authority):
    if (not isinstance(authority, TrustedAuthority) or not isinstance(authority.key, bytes)
            or len(authority.key) < 32 or not isinstance(authority.key_id, str)):
        raise ValueError('external trusted authority required')
    if not isinstance(approval, dict) or set(approval) != {'payload', 'hmac_sha256'}:
        raise ValueError('signed envelope required')
    payload = approval['payload']
    if not isinstance(payload, dict) or set(payload) != {
            'schema', 'approval_id', 'key_id', 'scope', 'review_evidence_sha256', 'policy_evidence_sha256'}:
        raise ValueError('exact approval payload required')
    if (payload['schema'] != 'v1-execution-approval/1' or payload['key_id'] != authority.key_id
            or not isinstance(payload['approval_id'], str)
            or not IDENTIFIER.fullmatch(payload['approval_id'])
            or not _hex(payload['review_evidence_sha256']) or not _hex(payload['policy_evidence_sha256'])
            or not _hex(approval['hmac_sha256'])):
        raise ValueError('invalid approval fields')
    expected = hmac.new(authority.key, canonical(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, approval['hmac_sha256']):
        raise ValueError('approval authentication failed')
    if canonical(payload['scope']) != canonical(scope):
        raise ValueError('approval scope mismatch')
    return payload


def _open_directory(path):
    path = Path(os.path.abspath(path))
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor); descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _write_new(directory, name, data, *, readonly=False):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, 'wb', closefd=False) as output:
            output.write(data); output.flush()
        if readonly:
            os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(directory)


def _unused(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise FileExistsError('output identity already exists')



def _verify_row(row):
    score = row.get('score')
    if (not isinstance(score, dict) or row.get('status') not in
            ('answered', 'abstained', 'partial', 'conflict', 'unverified', 'error')
            or score.get('status') != row.get('status')):
        raise ValueError('canonical result status required')
    for key in ('correct', 'correct_lenient', 'unsupported'):
        if type(score.get(key)) is not bool:
            raise ValueError('strict boolean score required')
    for key in ('abstain_ok', 'partial_ok', 'conflict_ok'):
        if key not in score or (score[key] is not None and type(score[key]) is not bool):
            raise ValueError('canonical conditional score required')
    for key in ('fact_recall', 'citation_correctness', 'citation_completeness'):
        value = score.get(key)
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('finite fraction metric required')
    if type(score.get('fabricated')) is not int or score['fabricated'] < 0:
        raise ValueError('canonical fabricated count required')
    if any(not isinstance(score.get(key), list) for key in ('forbidden_hits', 'ungrounded_numbers')):
        raise ValueError('canonical issue lists required')
    latency = row.get('latency_s')
    if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
        raise ValueError('finite nonnegative latency required')
    for key in ('llm_calls', 'prompt_tokens', 'output_tokens'):
        if type(row.get(key)) is not int or row[key] < 0:
            raise ValueError('nonnegative usage counts required')
    if row['status'] == 'error' and (score['correct'] or score['correct_lenient']):
        raise ValueError('canonical error row cannot be correct')


def _capture_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode())


def _verify_capture(capture, scope, rows):
    if (not isinstance(capture, dict) or capture.get('schema') != 'official-v1-runtime-capture/1'
            or capture.get('capture_complete') is not True or not _hex(capture.get('capture_sha256'))):
        raise ValueError('complete exact runtime capture required')
    detached = dict(capture); signed = detached.pop('capture_sha256')
    if _capture_digest(detached) != signed:
        raise ValueError('runtime capture digest mismatch')
    config = capture.get('resolved_config')
    if (not isinstance(config, dict) or _capture_digest(config) != scope['runtime_config_sha256']
            or capture.get('config_sha256') != scope['runtime_config_sha256']
            or not isinstance(config.get('run'), dict)
            or config['run'].get('tier') != scope['tier'] or config['run'].get('split') != scope['split']):
        raise ValueError('runtime settings differ from approved scope')
    events = capture.get('events')
    if not isinstance(events, list) or any(not isinstance(e, dict) or type(e.get('sequence')) is not int
            or e['sequence'] != n for n, e in enumerate(events)):
        raise ValueError('ordered runtime events required')
    def text_record(value):
        return (isinstance(value, dict) and _hex(value.get('sha256'))
                and type(value.get('utf8_bytes')) is int and value['utf8_bytes'] >= 0)
    for event in events:
        kind = event.get('kind')
        if kind == 'provider_prompt':
            if (not text_record(event.get('prompt')) or not isinstance(event.get('requested_model'), str)
                    or not event['requested_model'] or not _hex(event.get('retry_options_sha256'))
                    or event.get('outcome') not in ('returned', 'raised')):
                raise ValueError('actual provider prompt identity required')
        elif kind == 'scoring_context':
            if (not text_record(event.get('exact_context'))
                    or not all(_hex(event.get(k)) for k in ('case_id_sha256', 'case_sha256',
                        'result_sha256', 'ordered_chunk_pair_sha256', 'context_ids_sha256'))
                    or event.get('outcome') not in ('returned', 'raised')
                    or (event['outcome'] == 'returned' and not _hex(event.get('score_sha256')))):
                raise ValueError('actual scoring context identity required')
        elif kind == 'assembled_prompt_context':
            if (not text_record(event.get('context')) or not _hex(event.get('bundle_sha256'))
                    or not isinstance(event.get('ordered_source_sha256'), list)
                    or not all(_hex(value) for value in event['ordered_source_sha256'])
                    or not isinstance(event.get('ordered_source_content'), list)
                    or not all(text_record(value) for value in event['ordered_source_content'])
                    or len(event['ordered_source_content']) != len(event['ordered_source_sha256'])):
                raise ValueError('actual ordered prompt context identity required')
        else:
            raise ValueError('unknown runtime capture event')
    nonerrors = sum(row.get('status') != 'error' for row in rows)
    scored = [e for e in events if e.get('kind') == 'scoring_context' and e.get('outcome') == 'returned']
    for row in rows:
        if row.get('status') == 'error':
            continue
        matching = [e for e in scored if e.get('case_id_sha256') == digest(row['id'].encode())]
        if len(matching) != 1 or matching[0].get('score_sha256') != _capture_digest(row['score']):
            raise ValueError('case-bound exact scoring evidence missing or duplicated')
    if nonerrors and not any(e.get('kind') == 'provider_prompt' for e in events):
        raise ValueError('exact provider prompt capture missing')


def verify_bundle_bytes(raw):
    """Read-only bundle consistency check, never approval or acceptance proof."""
    from scripts.formal_v1_report import parse_json
    envelope = parse_json(raw.decode('utf-8') if isinstance(raw, bytes) else raw)
    if not isinstance(envelope, dict) or set(envelope) != {'body', 'body_sha256'}:
        raise ValueError('sealed bundle required')
    body = envelope['body']
    if not isinstance(body, dict) or digest(canonical(body)) != envelope['body_sha256']:
        raise ValueError('bundle digest mismatch')
    if (body.get('schema') != 'v1-execution-bundle/1' or body.get('execution_complete') is not True
            or body.get('formal_outcome') != 'FORMAL_EVALUATION_INCOMPLETE'
            or body.get('acceptance_eligible') is not False):
        raise ValueError('complete mechanical bundle required')
    if digest(canonical(body['rows'])) != body['rows_sha256'] or digest(canonical(body['runtime'])) != body['runtime_sha256']:
        raise ValueError('bundle evidence digest mismatch')
    scope = _scope(body['scope'])
    rows = body.get('rows')
    if (not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
            or row.get('split') != scope['split'] or type(row.get('tier')) is not int
            or row['tier'] != scope['tier'] for row in rows)
            or len({row['id'] for row in rows}) != len(rows)
            or type(body.get('error_rows')) is not int
            or body['error_rows'] != sum(row.get('status') == 'error' for row in rows)):
        raise ValueError('canonical unique scoped rows required')
    for row in rows:
        _verify_row(row)
    _verify_capture(body['runtime'], _scope(body['scope']), body['rows'])
    return body


def verify_bundle(path, *, with_digest=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('bundle must be a regular file')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read()
    finally:
        os.close(descriptor)
    body = verify_bundle_bytes(raw)
    return (body, digest(raw)) if with_digest else body


def execute(scope, approval, *, authority, ledger_root, runtime_config, verify_prerequisites,
            executor, capture_snapshot, identity_verifier=verify_current_inputs):
    """Run a separately approved synchronous adapter behind mechanical controls.

    ``executor(emit_row)`` emits unmodified v1 records, synchronously. The caller
    must not retain writers or background tasks. ``capture_snapshot`` returns
    the cooperating exact-context capture snapshot. External prerequisite checks
    return None on success or raise: a false/true flag is never accepted instead.
    No default adapter imports or executes protected cases.
    """
    scope = json.loads(canonical(_scope(scope)))  # detach caller-owned containers
    approval = json.loads(canonical(approval))
    payload = _authenticate(approval, scope, authority)
    if str(ledger_root) != scope['ledger_root']:
        raise ValueError('ledger differs from signed execution namespace')
    runtime_config = json.loads(canonical(runtime_config))
    if (not isinstance(runtime_config, dict) or _capture_digest(runtime_config) != scope['runtime_config_sha256']
            or not isinstance(runtime_config.get('run'), dict)
            or type(runtime_config['run'].get('tier')) is not int
            or runtime_config['run'].get('tier') != scope['tier'] or runtime_config['run'].get('split') != scope['split']):
        raise ValueError('pre-execution runtime differs from approved scope')
    for function in (verify_prerequisites, executor, capture_snapshot, identity_verifier):
        if not callable(function):
            raise ValueError('explicit trusted callbacks required')
    verified = identity_verifier(json.loads(canonical(scope)), json.loads(canonical(runtime_config)))
    if (not isinstance(verified, VerifiedInputs) or not verified.expected_case_ids
            or any(not isinstance(x, str) or not x for x in verified.expected_case_ids)
            or len(set(verified.expected_case_ids)) != len(verified.expected_case_ids)):
        raise ValueError('fresh verified eligibility required')
    if verify_prerequisites(json.loads(canonical(payload)), json.loads(canonical(scope))) is not None:
        raise ValueError('prerequisite verifier must raise on refusal, not return a flag')
    output = Path(scope['output_path'])
    parent = _open_directory(output.parent)
    ledger = None
    journal = None
    try:
        ledger = _open_directory(ledger_root)
        _unused(parent, output.name)
        # Never remove these records, including if later reservation/execution fails.
        claim = canonical({'state': 'CONSUMED', 'approval_sha256': digest(canonical(approval)), 'scope': scope})
        _write_new(ledger, 'approval-'+payload['approval_id']+'.json', claim)
        _write_new(ledger, 'output-'+digest(str(output).encode())+'.json', claim)
        _unused(parent, output.name)
        journal_name = '.'+output.name+'.attempt-'+uuid.uuid4().hex+'.jsonl'
        descriptor = os.open(journal_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        journal = os.fdopen(descriptor, 'wb')
        def event(record):
            journal.write(canonical(record)); journal.flush(); os.fsync(journal.fileno())
        event({'state': 'IN_PROGRESS', 'approval_id': payload['approval_id'], 'scope': scope})
        os.fsync(parent)
        rows = []; seen = set(); expected = set(verified.expected_case_ids)
        def emit(row):
            detached = json.loads(canonical(row))
            if (not isinstance(detached, dict) or detached.get('id') not in expected
                    or detached['id'] in seen or detached.get('split') != scope['split']
                    or type(detached.get('tier')) is not int or detached['tier'] != scope['tier']):
                raise ValueError('invalid, repeated or ineligible result row')
            _verify_row(detached)
            event({'row': detached}); rows.append(detached); seen.add(detached['id'])
        try:
            executor(emit)
            if seen != expected:
                raise IncompleteRunError('expected eligible rows are missing')
            if identity_verifier(json.loads(canonical(scope)), json.loads(canonical(runtime_config))) != verified:
                raise ValueError('verified execution inputs changed during run')
            capture = json.loads(canonical(capture_snapshot()))
            _verify_capture(capture, scope, rows)
            if capture['resolved_config'] != runtime_config:
                raise ValueError('runtime config changed during execution')
            body = {'schema': 'v1-execution-bundle/1', 'execution_complete': True,
                    'formal_outcome': 'FORMAL_EVALUATION_INCOMPLETE', 'acceptance_eligible': False,
                    'scope': scope, 'approval_sha256': digest(canonical(approval)),
                    'review_evidence_sha256': payload['review_evidence_sha256'],
                    'policy_evidence_sha256': payload['policy_evidence_sha256'],
                    'runtime': capture, 'runtime_sha256': digest(canonical(capture)),
                    'rows': rows, 'rows_sha256': digest(canonical(rows)),
                    'error_rows': sum(row.get('status') == 'error' for row in rows)}
            blob = canonical({'body': body, 'body_sha256': digest(canonical(body))})
            sealed = '.'+output.name+'.sealed-'+uuid.uuid4().hex
            _write_new(parent, sealed, blob, readonly=True)
            try:
                os.link(sealed, output.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                try:
                    os.fsync(parent)
                except OSError as error:
                    raise PublicationDurabilityError('complete output exists; durability confirmation failed') from error
            finally:
                os.unlink(sealed, dir_fd=parent)
            event({'state': 'PUBLISHED', 'bundle_sha256': digest(blob)})
            return {'path': str(output), 'sha256': digest(blob), 'execution_complete': True,
                    'formal_outcome': 'FORMAL_EVALUATION_INCOMPLETE'}
        except BaseException as error:
            # No exception message is persisted: provider errors may contain secrets.
            event({'state': 'INTERRUPTED_OR_FAILED', 'error_type': type(error).__name__,
                   'rows_received': len(rows)})
            raise
    finally:
        if journal is not None:
            journal.close()
        if ledger is not None:
            os.close(ledger)
        os.close(parent)
