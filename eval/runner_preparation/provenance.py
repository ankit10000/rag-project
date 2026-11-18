"""Pure experimental WP7 input proofs; no official gate/schema adoption.

Exact UTF-8 text hashes are intentionally not newline-normalized. Source files
retain raw hashes; scorer annotations additionally retain their portable hash.
Callers supply evidence: missing history, annotations or context is never inferred.
"""
import copy
import hashlib
import json
import re
from eval.framework.hashing import portable_sha256

CONTEXT_SCHEMA = 'phase35-wp7-exact-context/1'
PROVENANCE_SCHEMA = 'phase35-wp7-input-provenance/1'
COMPARISON_SCHEMA = 'phase35-wp7-comparison-provenance/1'
_SHA = re.compile(r'[0-9a-f]{64}')
_DATA_FILES = {f'eval/phase35/data_{letter}.py' for letter in 'ABCD'}


def canonical_bytes(value):
    """Deterministic UTF-8 JSON, preserving array order and rejecting NaN."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError('invalid canonical JSON input') from exc


def _hash(data):
    if not isinstance(data, bytes):
        raise ValueError('source and annotation inputs must be bytes')
    return hashlib.sha256(data).hexdigest()


def _digest(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _json(data):
    _hash(data)
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    except (ValueError, UnicodeError) as exc:
        raise ValueError('malformed provenance JSON input') from exc


def _annotations(data):
    ann = _json(data)
    if not isinstance(ann, dict) or ann.get('schema') != 'phase35-scorer-annotations/1' or not isinstance(ann.get('cases'), dict) or not _digest(ann.get('dataset_sha256')) or not isinstance(ann.get('dataset_version'), str) or not ann['dataset_version']:
        raise ValueError('missing annotation provenance')
    return ann


def _pin(pin):
    required = {'manifest_content_sha256', 'dataset_version', 'pin_source', 'git_rev', 'file_sha256'}
    if not isinstance(pin, dict) or set(pin) != required:
        raise ValueError('incomplete dataset pin')
    if pin['pin_source'] not in ('operator_git_rev', 'run_header') or not isinstance(pin['git_rev'], str) or not re.fullmatch(r'[0-9a-f]{40}', pin['git_rev']):
        raise ValueError('invalid dataset revision pin')
    if not isinstance(pin['dataset_version'], str) or not pin['dataset_version']:
        raise ValueError('dataset version is required')
    if not _digest(pin['manifest_content_sha256']) and not (pin['manifest_content_sha256'] is None and pin['pin_source'] == 'operator_git_rev'):
        raise ValueError('invalid manifest pin')
    files = pin['file_sha256']
    if not isinstance(files, dict) or set(files) != _DATA_FILES or not all(_digest(v) for v in files.values()):
        raise ValueError('incomplete pinned dataset file hashes')
    return copy.deepcopy(pin)


def make_context_record(case_id, tier, items, history, *, context_text=None):
    """Capture ordered chunks with the WP6 Tier 1/Tier 2 joining rules.

    Items are {id, document, page, text, gold}. Tier 1 permits missing metadata
    (both document and page null), preserving WP6's missing-metadata fixture.
    The supplied history must be explicit; user and assistant roles stay intact.
    """
    if not isinstance(case_id, str) or not case_id or type(tier) is not int or tier not in (1, 2):
        raise ValueError('invalid case identity or tier')
    if not isinstance(items, list) or (not items and context_text != '') or not isinstance(history, list):
        raise ValueError('explicit context and history list required; empty context must be explicit')
    chunks, ids, normalized = [], set(), set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'id', 'document', 'page', 'text', 'gold'}:
            raise ValueError('incomplete chunk input')
        cid, doc, page, text = (item[k] for k in ('id', 'document', 'page', 'text'))
        missing = doc is None and page is None and tier == 1
        if type(cid) is not int or cid <= 0 or cid in ids or type(item['gold']) is not bool:
            raise ValueError('invalid or duplicate chunk identity')
        if not missing and (not isinstance(doc, str) or not doc.strip() or type(page) is not int or page < 1):
            raise ValueError('inconsistent chunk reference')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('missing chunk text')
        key = re.sub(r'\s+', ' ', text).strip().lower()
        if key in normalized:
            raise ValueError('duplicate normalized context')
        ids.add(cid); normalized.add(key)
        chunks.append(dict(item, sha256=_hash(text.encode('utf-8'))))
    if tier == 1 and (len(chunks) > 8 or sum(len(c['text'].strip()) for c in chunks) > 12000):
        raise ValueError('tier1 context assembly limits exceeded')
    for turn in history:
        if not isinstance(turn, dict) or set(turn) != {'role', 'content'} or turn['role'] not in ('user', 'assistant') or not isinstance(turn['content'], str):
            raise ValueError('malformed history; role separation required')
    joined = ' '.join(c['text'].strip() if tier == 1 else c['text'] for c in chunks)
    if context_text is not None and context_text != joined:
        raise ValueError('context text differs from exact ordered chunks')
    record = dict(schema=CONTEXT_SCHEMA, case_id=case_id, tier=tier, chunks=chunks,
                history=copy.deepcopy(history), history_sha256=_hash(canonical_bytes(history)),
                context_text=joined, context_sha256=_hash(joined.encode('utf-8')))
    record['record_sha256'] = _hash(canonical_bytes(record))
    return record


def verify_context_record(record):
    if not isinstance(record, dict) or set(record) != {'schema', 'case_id', 'tier', 'chunks', 'history', 'history_sha256', 'context_text', 'context_sha256', 'record_sha256'} or record['schema'] != CONTEXT_SCHEMA or not isinstance(record['chunks'], list):
        raise ValueError('invalid experimental context record')
    items = []
    for chunk in record['chunks']:
        if not isinstance(chunk, dict) or set(chunk) != {'id', 'document', 'page', 'text', 'gold', 'sha256'}:
            raise ValueError('invalid captured chunk')
        items.append({key: value for key, value in chunk.items() if key != 'sha256'})
    rebuilt = make_context_record(record['case_id'], record['tier'], items, record['history'], context_text=record['context_text'])
    if record != rebuilt:
        raise ValueError('context, chunk or history digest mismatch')
    return rebuilt


def build_provenance(source_bytes, annotation_bytes, dataset_pin, context_records, *, scorer_identity=None):
    _hash(source_bytes)
    ann = _annotations(annotation_bytes)
    pin = _pin(dataset_pin)
    if ann['dataset_version'] != pin['dataset_version']:
        raise ValueError('annotation dataset version differs from pin')
    if not isinstance(context_records, list) or not context_records:
        raise ValueError('explicit context records required')
    records = [verify_context_record(r) for r in context_records]
    ids = [r['case_id'] for r in records]
    if len(ids) != len(set(ids)) or any(cid not in ann['cases'] for cid in ids):
        raise ValueError('duplicate case or missing annotation')
    source_rows = [_json(line) for line in source_bytes.splitlines() if line.strip()]
    if len(source_rows) != len(records) or any(not isinstance(row, dict) or row.get('id') != record['case_id'] or type(row.get('tier')) is not int or row.get('tier') != record['tier'] for row, record in zip(source_rows, records)):
        raise ValueError('captured contexts do not match source row identities')
    identity = copy.deepcopy(scorer_identity)
    if identity is not None and (not isinstance(identity, dict) or not _digest(identity.get('sha256')) or identity.get('annotations_sha256') != portable_sha256(annotation_bytes, 'text')):
        raise ValueError('inconsistent scorer annotation identity')
    proof = dict(schema=PROVENANCE_SCHEMA, source_sha256=_hash(source_bytes),
                 annotations_sha256=_hash(annotation_bytes),
                 annotations_portable_sha256=portable_sha256(annotation_bytes, 'text'),
                 dataset_pin=pin, scorer=identity, contexts=records)
    proof['proof_sha256'] = _hash(canonical_bytes(proof))
    return proof


def validate_provenance(provenance, source_bytes, annotation_bytes, *, dataset_pin=None):
    if not isinstance(provenance, dict) or provenance.get('schema') != PROVENANCE_SCHEMA:
        raise ValueError('invalid experimental input provenance')
    if dataset_pin is not None and provenance.get('dataset_pin') != dataset_pin:
        raise ValueError('dataset pin mismatch')
    expected = build_provenance(source_bytes, annotation_bytes, provenance.get('dataset_pin'),
                                provenance.get('contexts'), scorer_identity=provenance.get('scorer'))
    if expected != provenance:
        raise ValueError('source, annotation or proof mismatch')
    return expected


def validate_comparison_inputs(source_bytes, annotation_bytes, sidecar, comparison_rows):
    """Bind a WP6 dev comparison to actual source bytes without inventing text.

    Full chunk capture is separate. WP6's sidecar only supplies context digests;
    these remain digests here and never imply historical text was available.
    """
    ann = _annotations(annotation_bytes)
    if not isinstance(sidecar, dict) or sidecar.get('sidecar_format') != 'phase35-scoring-sidecar/1':
        raise ValueError('invalid WP6 scoring sidecar')
    source = sidecar.get('source_results', {})
    scorer = sidecar.get('scorer', {})
    dataset = sidecar.get('dataset', {})
    if not all(isinstance(value, dict) for value in (source, scorer, dataset)) or type(source.get('rows')) is not int:
        raise ValueError('malformed sidecar provenance objects')
    if source.get('sha256') != _hash(source_bytes) or scorer.get('annotations_sha256') != portable_sha256(annotation_bytes, 'text') or not _digest(scorer.get('sha256')):
        raise ValueError('comparison source or annotation identity mismatch')
    pin = _pin(dataset.get('run_time'))
    if pin['dataset_version'] != ann['dataset_version']:
        raise ValueError('comparison annotation pin mismatch')
    rows = [_json(line) for line in source_bytes.splitlines() if line.strip()]
    metadata = sidecar.get('rows')
    if not isinstance(comparison_rows, list) or not isinstance(metadata, list) or not rows or len(rows) != len(comparison_rows) or len(rows) != len(metadata) or source.get('rows') != len(rows):
        raise ValueError('comparison row count mismatch')
    seen = set()
    for original, output, meta in zip(rows, comparison_rows, metadata):
        if not all(isinstance(row, dict) for row in (original, output, meta)):
            raise ValueError('invalid comparison row')
        if not isinstance(original.get('score'), dict) or type(meta.get('tier')) is not int:
            raise ValueError('malformed source score or context tier')
        cid = original.get('id')
        if not isinstance(cid, str) or cid in seen or cid not in ann['cases']:
            raise ValueError('duplicate case or missing annotation')
        seen.add(cid)
        if any(output.get(key) != original.get(key) for key in ('id', 'tier', 'split')) or meta.get('id') != cid or meta.get('tier') != original.get('tier') or output.get('v1_stored') != original.get('score'):
            raise ValueError('comparison source rows changed')
        if any(output.get(key) != meta.get(key) for key in ('context_mode', 'reconstruction_status')):
            raise ValueError('comparison context metadata mismatch')
        if type(original.get('tier')) is not int or original['tier'] not in (1, 2) or original.get('split') != 'dev':
            raise ValueError('development comparison identity required')
        chunk_hashes = meta.get('chunk_sha256')
        if not isinstance(chunk_hashes, dict) or any(not isinstance(key, str) or not key.isascii() or not key.isdecimal() or int(key) < 1 or not _digest(value) for key, value in chunk_hashes.items()):
            raise ValueError('invalid context chunk hashes')
        modes = {f'tier{original["tier"]}_reconstructed_exact', f'tier{original["tier"]}_exact_hash_verified'}
        if meta.get('context_mode') not in modes or meta.get('reconstruction_status') != 'exact' or not _digest(meta.get('context_sha256')):
            raise ValueError('exact context required for preparation')
        if 'context_sha256' in original and original['context_sha256'] != meta['context_sha256']:
            raise ValueError('source context digest mismatch')
    proof = dict(schema=COMPARISON_SCHEMA, source_sha256=_hash(source_bytes),
                 annotations_sha256=_hash(annotation_bytes), dataset_pin=pin,
                 scorer=copy.deepcopy(scorer), context_records=copy.deepcopy(metadata),
                 comparison_sha256=_hash(canonical_bytes(comparison_rows)))
    proof['proof_sha256'] = _hash(canonical_bytes(proof))
    return proof


def verify_reconstruction(row, case, docs, *, tier, table=None, header=None):
    """Stricter opt-in WP7 preflight over unchanged WP6 reconstruction.

    Returns WP6's (pair, ids, text, status, mode). Legacy reconstructed modes
    remain legacy; a proof generated now never becomes a historical capture.
    """
    from eval.scoring_v2 import context
    if not isinstance(row, dict) or not isinstance(case, dict) or not isinstance(docs, dict) or type(tier) is not int or tier not in (1, 2):
        raise ValueError('invalid reconstruction inputs')
    citations = row.get('citations')
    if not isinstance(citations, list):
        raise ValueError('explicit citation array required')
    citation_ids = []
    for citation in citations:
        if not isinstance(citation, dict) or type(citation.get('chunk_id')) is not int or citation['chunk_id'] <= 0:
            raise ValueError('invalid citation identity')
        citation_ids.append(citation['chunk_id'])
    if len(citation_ids) != len(set(citation_ids)):
        raise ValueError('duplicate citation identity')
    if tier == 1:
        refs = row.get('context')
        if not isinstance(refs, list) or not refs:
            raise ValueError('missing exact tier1 context')
        ids = [ref.get('chunk_id') if isinstance(ref, dict) else None for ref in refs]
        if any(type(cid) is not int or cid <= 0 for cid in ids) or len(ids) != len(set(ids)):
            raise ValueError('invalid or duplicate tier1 context identity')
        result = context.verify_tier1(row, case, docs)
        known = {ref['chunk_id']:ref for ref in refs}
        for citation in citations:
            ref = known.get(citation['chunk_id'])
            if ref is None:
                raise ValueError('citation is absent from reconstructed tier1 context')
            for key, alias in (('document', 'document_name'), ('page', 'page_number')):
                values = [citation[k] for k in (key, alias) if k in citation]
                if any(value != ref.get(key) or type(value) is not type(ref.get(key)) for value in values):
                    raise ValueError('citation metadata conflicts with reconstructed tier1 context')
    else:
        retrieved = row.get('retrieved')
        if not isinstance(table, list) or not isinstance(retrieved, list):
            raise ValueError('missing exact tier2 context')
        by_id = {}
        for chunk in table:
            if not isinstance(chunk, dict) or type(chunk.get('id')) is not int or chunk['id'] <= 0 or chunk['id'] in by_id or not isinstance(chunk.get('content'), str) or not chunk['content'].strip():
                raise ValueError('invalid or duplicate chunk table identity')
            if chunk.get('sha256') != _hash(chunk['content'].encode('utf-8')):
                raise ValueError('chunk table text hash mismatch')
            by_id[chunk['id']] = chunk
        seen = set()
        for ref in retrieved + citations:
            if not isinstance(ref, dict) or type(ref.get('chunk_id')) is not int or ref['chunk_id'] <= 0:
                raise ValueError('invalid context reference')
            if ('document_name' in ref and 'document' in ref and ref['document_name'] != ref['document']) or ('page_number' in ref and 'page' in ref and ref['page_number'] != ref['page']):
                raise ValueError('conflicting context reference aliases')
            chunk = by_id.get(ref['chunk_id'])
            doc, page = ref.get('document_name', ref.get('document')), ref.get('page_number', ref.get('page'))
            if chunk is None or not isinstance(doc, str) or type(page) is not int or page <= 0 or (doc, page) != (chunk.get('document'), chunk.get('page')):
                raise ValueError('inconsistent context reference')
        for ref in retrieved:
            if ref['chunk_id'] in seen:
                raise ValueError('duplicate retrieved identity')
            seen.add(ref['chunk_id'])
        result = context.verify_tier2(row, table, case, header)
    if result[3] != 'exact' or not isinstance(result[2], str):
        raise ValueError('context reconstruction is not exact: ' + result[3])
    return result
