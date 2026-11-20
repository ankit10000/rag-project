"""Opt-in development evidence traces; never emit document text to normal logs.

Runtime hooks are no-ops unless a caller explicitly opens a trace *and* sets
RAG_DEVELOPMENT_TRACE=1. Raw question/source/answer text requires a second
explicit opt-in. Trace artifacts are exclusive-create, owner-readable files.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time

_active = ContextVar('rag_development_evidence_trace', default=None)
_PRIVATE = {'question', 'content', 'answer', 'prompt', 'context_text', 'text',
            'history', 'memory_summary', 'feedback', 'generated_answer', 'search_query'}
_SECRETS = {'password', 'secret', 'api_key', 'apikey', 'authorization', 'cookie',
            'token', 'access_token', 'refresh_token', 'session', 'credentials'}


def fingerprint(value):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return {'chars': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def _safe(value, *, raw=False):
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            name = str(key).casefold()
            if name in _SECRETS or any(name.endswith('_' + secret) for secret in _SECRETS):
                output[str(key)] = '[redacted]'
            elif name in _PRIVATE and not raw:
                output[str(key)] = fingerprint(item)
            else:
                output[str(key)] = _safe(item, raw=raw)
        return output
    if isinstance(value, (list, tuple)):
        return [_safe(item, raw=raw) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class EvidenceTrace:
    def __init__(self, question, authorized_documents, include_raw=False):
        self.include_raw = bool(include_raw)
        self.started = time.monotonic()
        self.events = []
        self.header = _safe({'question': question,
                             'authorized_documents': list(authorized_documents or []),
                             'policy': 'development-answer-evidence-trace/1'}, raw=self.include_raw)

    def record(self, stage, metadata=None, raw=None):
        event = {'stage': str(stage), 'elapsed_ms': round((time.monotonic() - self.started) * 1000, 2),
                 'metadata': _safe(metadata or {})}
        if raw is not None:
            sanitized = _safe(raw, raw=True)
            # Raw payloads may contain new/nested keys (rewritten queries,
            # source-derived headings, coverage clauses). A private-key list
            # alone cannot safely redact an evolving payload schema.
            event['raw'] = (sanitized if self.include_raw else
                            {key: fingerprint(value) for key, value in sanitized.items()}
                            if isinstance(sanitized, dict) else fingerprint(sanitized))
        self.events.append(event)

    def snapshot(self):
        return deepcopy({'header': self.header, 'raw_enabled': self.include_raw,
                         'events': self.events})

    def write(self, path):
        """Never overwrite a prior run. Keep even raw artifacts owner-readable.

        The caller supplies a development scratch artifact location. Reject a
        symlinked final directory or non-private existing directory rather than
        chmodding unrelated user directories.
        """
        destination = Path(path)
        directory = destination.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or directory.stat().st_mode & 0o077:
            raise PermissionError('trace artifact directory must be private (0700)')
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.snapshot(), stream, indent=2, allow_nan=False)
            stream.write('\n')


@contextmanager
def answer_evidence_trace(question, authorized_documents=(), *, include_raw=False):
    if os.getenv('RAG_DEVELOPMENT_TRACE') != '1':
        raise RuntimeError('development tracing requires RAG_DEVELOPMENT_TRACE=1')
    trace = EvidenceTrace(question, authorized_documents, include_raw)
    token = _active.set(trace)
    try:
        yield trace
    finally:
        _active.reset(token)


def trace_event(stage, metadata=None, raw=None):
    trace = _active.get()
    if trace is not None:
        trace.record(stage, metadata, raw)


def trace_candidates(stage, candidates, *, selected_ids=None, removal_reason=None):
    """Support retriever tuples and fused/reranked dictionaries without mutation."""
    trace = _active.get()
    if trace is None:
        return
    selected = None if selected_ids is None else set(selected_ids)
    records, passages = [], []
    for rank, item in enumerate(candidates or [], start=1):
        chunk = item.get('chunk') if isinstance(item, dict) else item
        if not chunk or len(chunk) < 4:
            continue
        cid, document, page, content = chunk[:4]
        record = {'rank': rank, 'chunk_id': cid, 'document': document, 'page': page,
                  'content_fingerprint': fingerprint(content), 'selected': selected is None or cid in selected}
        if isinstance(item, dict):
            record.update({key: item[key] for key in ('rrf_score', 'rerank_score', 'context_policy') if key in item})
        if selected is not None and cid not in selected:
            record['removal_reason'] = (removal_reason or {}).get(cid, 'not_selected') if isinstance(removal_reason, dict) else (removal_reason or 'not_selected')
        records.append(record)
        passages.append({'chunk_id': cid, 'content': content})
    trace.record(stage, {'candidates': records}, raw={'passages': passages})


def diagnose_expected_evidence(trace, required_chunk_ids, *, source_information_absent=False,
                               question_ambiguous=False, answer_missing_items=(), validation_issues=()):
    """Deterministic stage attribution against an independently declared oracle.

    Required IDs must be source-review labels, not an LLM's unproved assertion.
    The helper reports evidence loss and explicit signals, not semantic truth.
    """
    if question_ambiguous:
        return ['QUESTION_AMBIGUOUS']
    if source_information_absent:
        return ['SOURCE_INFORMATION_ABSENT']
    data = trace.snapshot() if isinstance(trace, EvidenceTrace) else trace
    stages = {}
    for event in data.get('events', []):
        ids = {c['chunk_id'] for c in event.get('metadata', {}).get('candidates', [])}
        stages.setdefault(event['stage'], set()).update(ids)
    required = set(required_chunk_ids)
    initial = stages.get('vector_candidates', set()) | stages.get('lexical_candidates', set())
    fused = stages.get('rrf_results', initial)
    final = stages.get('final_context', stages.get('context_selected', set()))
    filtered = stages.get('after_adaptive_filter', stages.get('rerank_filter', set()))
    # Selected booleans distinguish retained from recorded rejected candidates.
    for event in data.get('events', []):
        if event['stage'] == 'rerank_filter' and 'after_adaptive_filter' not in stages:
            filtered = {c['chunk_id'] for c in event.get('metadata', {}).get('candidates', []) if c.get('selected')}
    findings = []
    missing = required - final
    # Fusion limits are part of candidate retrieval, not a cross-encoder
    # decision. A vector hit lost before reranking must retain that distinction.
    if (missing - initial) or ((missing & initial) - fused):
        findings.append('RETRIEVAL_MISS')
    if (missing & fused) - filtered:
        findings.append('RERANK_FILTER_LOSS')
    if missing & filtered:
        findings.append('CONTEXT_BUDGET_LOSS')
    if not missing and answer_missing_items:
        findings.append('GENERATION_OMISSION')
    if validation_issues:
        findings.append('ANSWER_VALIDATION_ERROR')
    return findings
