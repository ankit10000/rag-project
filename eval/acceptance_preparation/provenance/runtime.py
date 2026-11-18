"""Pure proposed runtime evidence: byte identity, not authenticity or acceptance.

No environment/default reads, provider imports, database access or official gate
integration. Origin is an unsigned caller claim. Verification never proves an
original runtime occurred, even when every supplied digest is self-consistent.
"""
import base64
import copy
import hashlib
import json
import re

SCHEMA = 'phase35-proposed-runtime-provenance/1'
ORIGINS = {'ORIGINAL_RUNTIME_CAPTURE', 'HISTORICAL_RECONSTRUCTION'}
CORE_IDENTITY = {'scorer_name', 'scorer_version', 'scorer_hash', 'module_hashes',
                 'annotation_hash', 'source_revision', 'dataset_revision',
                 'dataset_identity', 'run_header_hash'}
OPTIONAL_IDENTITY = {'tier', 'split', 'acceptance_status', 'threshold_profile_id',
                     'threshold_profile_hash', 'gate_policy_id', 'gate_policy_hash'}
CONFIG_FIELDS = {'chunk_size', 'chunk_overlap', 'chunk_strategy', 'min_page_words',
                 'dedupe', 'extractor', 'document_order', 'scoring_context_join',
                 'prompt_context_limit_chars', 'prompt_context_truncation'}


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError('invalid canonical evidence value') from exc


def _sha(data):
    if not isinstance(data, bytes):
        raise ValueError('actual byte inputs are required')
    return hashlib.sha256(data).hexdigest()


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _identity(identity):
    if not isinstance(identity, dict) or not CORE_IDENTITY <= set(identity) or set(identity) - CORE_IDENTITY - OPTIONAL_IDENTITY:
        raise ValueError('incomplete or unknown identity fields')
    for key in ('scorer_name', 'scorer_version'):
        if not isinstance(identity[key], str) or not identity[key].strip():
            raise ValueError('missing scorer name/version')
    for key in ('source_revision', 'dataset_revision'):
        if not isinstance(identity[key], str) or not re.fullmatch('[0-9a-f]{40}', identity[key]):
            raise ValueError('full source and dataset revisions required')
    for key in ('scorer_hash', 'annotation_hash', 'dataset_identity', 'run_header_hash',
                'threshold_profile_hash', 'gate_policy_hash'):
        if key in identity and not _digest(identity[key]):
            raise ValueError('invalid content digest: ' + key)
    modules = identity['module_hashes']
    if not isinstance(modules, dict) or not modules or any(not isinstance(path, str) or not path or path.startswith('/') or '\\' in path or '..' in path.split('/') or not _digest(digest) for path, digest in modules.items()):
        raise ValueError('explicit repository module identities required')
    for key in ('threshold_profile_id', 'gate_policy_id'):
        if key in identity and (not isinstance(identity[key], str) or not identity[key].strip()):
            raise ValueError('profile/policy identifiers must be nonempty text')
    if 'split' in identity and identity['split'] != 'dev':
        raise ValueError('proposal evidence is development-only')
    if 'tier' in identity and identity['tier'] not in ('tier1', 'tier2'):
        raise ValueError('invalid explicit tier')
    if 'acceptance_status' in identity and identity['acceptance_status'] not in ('DEVELOPMENT_ONLY', 'PENDING_OWNER_DECISION', 'OFFICIAL_V1_BASELINE'):
        raise ValueError('acceptance cannot be asserted by runtime evidence')
    return copy.deepcopy(identity)


def _config(config):
    if not isinstance(config, dict) or set(config) != CONFIG_FIELDS:
        raise ValueError('all resolved allowlisted config values required; unknown/secret keys refused')
    for key in ('chunk_size', 'min_page_words'):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError('positive resolved configuration required')
    if type(config['chunk_overlap']) is not int or not 0 <= config['chunk_overlap'] < config['chunk_size']:
        raise ValueError('invalid resolved chunk overlap')
    if config['chunk_strategy'] not in ('words', 'sentences') or config['dedupe'] != 'sha1(ws-collapsed lower)' or config['extractor'] != 'get_text(sort=True)':
        raise ValueError('unknown explicitly proposed chunk pipeline')
    order = config['document_order']
    if not isinstance(order, list) or any(not isinstance(name, str) or not name.strip() for name in order) or len(order) != len(set(order)):
        raise ValueError('explicit unique document order required')
    if config['scoring_context_join'] not in ('space_join_raw', 'space_join_stripped'):
        raise ValueError('explicit scoring join rule required')
    limit, policy = config['prompt_context_limit_chars'], config['prompt_context_truncation']
    if policy not in ('none', 'prefix_chars', 'external'):
        raise ValueError('explicit prompt truncation policy required')
    if policy == 'none':
        if limit is not None:
            raise ValueError('untruncated context has no character limit')
    elif not (policy == 'external' and limit is None) and (type(limit) is not int or limit < 0):
        raise ValueError('explicit nonnegative prompt limit required, or external null')
    return copy.deepcopy(config)


def _content(value):
    if isinstance(value, str):
        data, encoding, payload = value.encode('utf-8'), 'utf-8', value
    elif isinstance(value, bytes):
        data, encoding, payload = value, 'base64', base64.b64encode(value).decode('ascii')
    else:
        raise ValueError('actual prompt context must be text or bytes')
    return dict(encoding=encoding, payload=payload, byte_length=len(data), sha256=_sha(data))


def _decode(content):
    if not isinstance(content, dict) or set(content) != {'encoding', 'payload', 'byte_length', 'sha256'}:
        raise ValueError('malformed actual context content')
    if not isinstance(content['payload'], str) or type(content['byte_length']) is not int or content['byte_length'] < 0 or not _digest(content['sha256']):
        raise ValueError('malformed content payload or identity')
    try:
        if content['encoding'] == 'utf-8':
            return content['payload']
        if content['encoding'] == 'base64':
            return base64.b64decode(content['payload'], validate=True)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid encoded context') from exc
    raise ValueError('unknown actual content encoding')


def capture_record(identity, resolved_config, scoring_chunks, scoring_context,
                   prompt_context, *, run_header_bytes, origin, prompt_truncated):
    """Bind actual ordered text and prompt bytes to explicit supplied identities.

    Empty ordered chunks + empty scoring text are valid explicit evidence.
    No missing field is populated from defaults or historical reconstruction.
    """
    identity, config = _identity(identity), _config(resolved_config)
    if not isinstance(origin, str) or origin not in ORIGINS or type(prompt_truncated) is not bool:
        raise ValueError('explicit origin and truncation boolean required')
    if identity['run_header_hash'] != _sha(run_header_bytes):
        raise ValueError('actual run header bytes differ from identity')
    if not isinstance(scoring_chunks, list) or not isinstance(scoring_context, str):
        raise ValueError('actual ordered scoring chunks and text required')
    chunks, seen, texts = [], set(), []
    for chunk in scoring_chunks:
        if not isinstance(chunk, dict) or set(chunk) != {'chunk_id', 'document', 'page', 'text'}:
            raise ValueError('incomplete ordered chunk identity')
        cid, doc, page, text = (chunk[key] for key in ('chunk_id', 'document', 'page', 'text'))
        missing_metadata = doc is None and page is None
        if type(cid) is not int or cid <= 0 or cid in seen or not isinstance(text, str) or not text.strip():
            raise ValueError('invalid or duplicate ordered chunk identity')
        if missing_metadata and identity.get('tier') != 'tier1':
            raise ValueError('missing metadata is only explicit tier1 evidence')
        if not missing_metadata and (doc not in config['document_order'] or type(page) is not int or page <= 0):
            raise ValueError('unbound document/page identity')
        seen.add(cid)
        chunks.append(dict(chunk, sha256=_sha(text.encode('utf-8'))))
        texts.append(text.strip() if config['scoring_context_join'] == 'space_join_stripped' else text)
    if scoring_context != ' '.join(texts):
        raise ValueError('actual scoring context differs from ordered chunks')
    prompt = _content(prompt_context)
    prompt_bytes = prompt_context.encode('utf-8') if isinstance(prompt_context, str) else prompt_context
    if config['prompt_context_truncation'] == 'none':
        if prompt_truncated or prompt_bytes != scoring_context.encode('utf-8'):
            raise ValueError('untruncated prompt context must equal scoring context')
    elif config['prompt_context_truncation'] == 'prefix_chars':
        limit = config['prompt_context_limit_chars']
        if prompt_bytes != scoring_context[:limit].encode('utf-8') or prompt_truncated != (len(scoring_context) > limit):
            raise ValueError('actual prompt prefix/truncation differs from resolved values')
    record = dict(schema=SCHEMA, identity=identity, identity_sha256=_sha(_canonical(identity)),
                  resolved_config=config, resolved_config_sha256=_sha(_canonical(config)),
                  scoring_context=dict(ordered_chunks=chunks, content=_content(scoring_context),
                                       ordered_chunks_sha256=_sha(_canonical(chunks))),
                  prompt_context=dict(content=prompt, truncated=prompt_truncated),
                  origin=origin, authenticity='UNVERIFIED_CALLER_CLAIM',
                  official_acceptance=False)
    record['record_sha256'] = _sha(_canonical(record))
    return record


def verify_record(record, *, run_header_bytes, expected_identity=None, expected_config=None):
    """Verify structural/byte consistency; return no approval or authenticity."""
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise ValueError('invalid proposed capture schema')
    if not _digest(record.get('record_sha256')) or _sha(_canonical({key: value for key, value in record.items() if key != 'record_sha256'})) != record['record_sha256']:
        raise ValueError('incoming runtime record digest mismatch')
    if expected_identity is not None and _canonical(record.get('identity')) != _canonical(expected_identity):
        raise ValueError('unexpected identity')
    if expected_config is not None and _canonical(record.get('resolved_config')) != _canonical(expected_config):
        raise ValueError('unexpected resolved configuration')
    try:
        chunks = [{key: value for key, value in chunk.items() if key != 'sha256'}
                  for chunk in record['scoring_context']['ordered_chunks']]
        rebuilt = capture_record(record['identity'], record['resolved_config'], chunks,
                                 _decode(record['scoring_context']['content']),
                                 _decode(record['prompt_context']['content']),
                                 run_header_bytes=run_header_bytes, origin=record['origin'],
                                 prompt_truncated=record['prompt_context']['truncated'])
    except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError('incomplete actual runtime evidence') from exc
    if _canonical(record) != _canonical(rebuilt):
        raise ValueError('runtime evidence digest, order or content mismatch')
    return dict(verification='STRUCTURALLY_VERIFIED', authenticity='UNVERIFIED_CALLER_CLAIM',
                origin=record['origin'], record_sha256=record['record_sha256'],
                official_acceptance=False)
