"""Scoped runtime hash capture for the unchanged official v1 functions.

This module imports no application services, database or provider. Attach only
inside an already authorized execution envelope, to preloaded module objects.
The provider boundary is _generate_with_model: records are model attempts, not
claims about every internal HTTP retry. No prompt/source text, private document
names, credentials or DSNs are retained. This is mechanical evidence, not proof
of human review or authorization. Single-process/synchronous use only.
"""
from contextlib import ExitStack, contextmanager
from functools import wraps
import hashlib
import inspect
import json
from pathlib import Path
import platform
import re
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()
_RETRIEVAL_KEYS = (
    'VECTOR_TOP_K', 'BM25_TOP_K', 'BM25_DROP_STOPWORDS', 'BM25_BACKEND',
    'RRF_K', 'RRF_TOP_K', 'RERANK_ENABLED', 'RERANK_MODEL', 'RERANK_TOP_K',
    'FINAL_TOP_K', 'RERANK_SCORE_MARGIN', 'RERANK_MIN_SCORE',
    'SIMILARITY_THRESHOLD', 'EMBEDDING_MODEL', 'EMBEDDING_DIM',
    'EMBEDDING_QUERY_CACHE_SIZE', 'BM25_CACHE_MAX_ENTRIES', 'PERF_METRICS_ENABLED',
    'MAX_PDF_SIZE_MB', 'MAX_PDF_PAGES', 'CHUNK_SIZE', 'CHUNK_OVERLAP',
    'CHUNK_STRATEGY', 'CONTEXT_MAX_CHARS', 'CONTEXT_MAX_CHUNKS',
    'HISTORY_MAX_TURNS', 'HISTORY_MAX_CHARS', 'ANSWER_MAX_RETRIES')
_RUN_KEYS = {'tier', 'split', 'pause', 'fresh', 'no_ingest',
             'database_name', 'request_budget_seconds', 'local_v1_profile'}
_SOURCE_PATHS = (
    'eval/phase35/run_eval.py', 'eval/answer_scoring.py',
    'eval/official_v1_capture.py', 'eval/official_v1_execution.py',
    'eval/framework/safety.py',
    'services/llm_service.py', 'services/llm_config.py',
    'services/gemini_retry_service.py', 'services/answer_service.py',
    'services/answer_prompt.py', 'services/context_assembly_service.py',
    'services/retrieval_config.py', 'services/rag_service.py',
    'services/embedding_service.py', 'services/hybrid_search_service.py',
    'services/reranker_service.py', 'services/request_budget.py',
    'services/database.py', 'services/citation_service.py',
    'services/answer_semantics.py')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _text(text):
    if not isinstance(text, str):
        raise ValueError('exact text required for runtime capture')
    raw = text.encode('utf-8')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'utf8_bytes': len(raw)}


def resolve_runtime_config(provider, retrieval, run_config):
    """Read only explicitly allowed resolved attributes, never os.environ/.env."""
    if not isinstance(run_config, dict) or set(run_config) - _RUN_KEYS:
        raise ValueError('unknown runtime setting; credentials/DSNs are forbidden')
    if run_config.get('tier') not in (1, 2) or type(run_config.get('tier')) is not int:
        raise ValueError('explicit tier required')
    if run_config.get('split') not in ('dev', 'heldout'):
        raise ValueError('explicit split required')
    database = run_config.get('database_name')
    if not isinstance(database, str) or not re.fullmatch(r'rag_[a-z0-9_]+', database) or database == 'rag_db':
        raise ValueError('explicit permitted scratch database name required')
    if database != 'rag_phase35_eval' and 'test' not in database:
        raise ValueError('database must be the evaluation scratch or a test database')
    for key in ('fresh', 'no_ingest', 'local_v1_profile'):
        if key in run_config and type(run_config[key]) is not bool:
            raise ValueError('runtime flags must be booleans')
    for key in ('pause', 'request_budget_seconds'):
        if key in run_config and (type(run_config[key]) not in (int, float) or run_config[key] < 0):
            raise ValueError('invalid runtime duration')
    primary = provider.MODEL_NAME
    fallbacks = provider.FALLBACK_MODELS
    if not isinstance(primary, str) or not primary or not isinstance(fallbacks, (list, tuple)) or not all(isinstance(m, str) and m for m in fallbacks):
        raise ValueError('resolved model identity required')
    config = dict(provider={
        'primary_model': primary, 'fallback_models': list(fallbacks),
        'request_timeout_ms': provider.REQUEST_TIMEOUT_MS,
        'quota_cooldown_seconds': provider.QUOTA_COOLDOWN_SECONDS,
        'default_quota_wait_seconds': provider.DEFAULT_QUOTA_WAIT_SECONDS},
        retrieval={key: getattr(retrieval, key) for key in _RETRIEVAL_KEYS},
        run=dict(run_config), python=platform.python_version(),
        platform=platform.platform(), source_sha256={
            path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
            for path in _SOURCE_PATHS})
    # Reject non-finite/non-JSON resolved settings before installing hooks.
    _json(config)
    return json.loads(_json(config))


class RuntimeCapture:
    """Hash exact frozen score inputs, assembled bundles and provider prompts.

    Usage: capture = RuntimeCapture(provider, retrieval, run_config)
      with capture.attach(runner, rag=preloaded_rag_or_none): ... unchanged calls
      evidence = capture.snapshot()
    Aliases of provider.generate_answer still resolve the patched module-global
    _generate_with_model, including classification, rewrite and fallback calls.
    """
    def __init__(self, provider, retrieval, run_config):
        self.provider = provider
        self.retrieval = retrieval
        self.resolved_config = resolve_runtime_config(provider, retrieval, run_config)
        self._run_config = json.loads(_json(run_config))
        self._events = []
        self._complete = False
        self._attached = False
        self._used = False

    def _assert_config_stable(self):
        actual = resolve_runtime_config(self.provider, self.retrieval, self._run_config)
        if actual != self.resolved_config:
            raise ValueError('runtime configuration or source changed during capture')

    def _add(self, kind, **data):
        event = dict(sequence=len(self._events), kind=kind, **data)
        _json(event)
        self._events.append(event)
        return event

    def _provider(self, original):
        @wraps(original)
        def wrapped(*args, **kwargs):
            bound = inspect.signature(original).bind(*args, **kwargs)
            prompt = bound.arguments['prompt']; model = bound.arguments['model']
            if not isinstance(model, str):
                raise ValueError('model identity must be a string')
            event = self._add('provider_prompt', requested_model=model,
                              prompt=_text(prompt), retry_options_sha256=_digest(
                                  bound.arguments.get('retry_options', {})))
            try:
                result = original(*args, **kwargs)
            except BaseException as error:
                event.update(outcome='raised', exception_type=type(error).__name__)
                raise
            event['outcome'] = 'returned'
            return result
        return wrapped

    def _assemble(self, original, boundary):
        @wraps(original)
        def wrapped(*args, **kwargs):
            bundle = original(*args, **kwargs)
            sources = bundle['sources']
            self._add('assembled_prompt_context', boundary=boundary,
                      context=_text(bundle['context_text']),
                      ordered_source_sha256=[_digest(source) for source in sources],
                      ordered_source_content=[_text(s['content']) for s in sources],
                      bundle_sha256=_digest(bundle))
            return bundle
        return wrapped

    def _score(self, original):
        @wraps(original)
        def wrapped(*args, **kwargs):
            bound = inspect.signature(original).bind(*args, **kwargs)
            values = bound.arguments
            event = self._add('scoring_context',
                case_id_sha256=_text(values['case']['id'])['sha256'],
                case_sha256=_digest(values['case']), result_sha256=_digest(values['result']),
                exact_context=_text(values['context_text']),
                ordered_chunk_pair_sha256=_digest(list(values['chunk_pair'].items())),
                context_ids_sha256=_digest(sorted(values['context_ids'])))
            try:
                result = original(*args, **kwargs)
            except BaseException as error:
                event.update(outcome='raised', exception_type=type(error).__name__)
                raise
            event.update(outcome='returned', score_sha256=_digest(result))
            return result
        return wrapped

    @contextmanager
    def attach(self, runner, *, rag=None):
        """Install only scoped hooks; restore even if provider/scoring raises."""
        if self._used:
            raise RuntimeError('capture object is single-use')
        self._assert_config_stable()
        if self.resolved_config['run']['tier'] == 2 and rag is None:
            raise ValueError('Tier 2 capture requires the preloaded RAG module')
        if not all(callable(item) for item in (
                self.provider._generate_with_model, runner.score_generic,
                runner.assemble_context)):
            raise ValueError('attach only after authorized runner bootstrap')
        if not _LOCK.acquire(blocking=False):
            raise RuntimeError('concurrent runtime capture is not supported')
        self._used = True
        self._attached = True
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(self.provider, '_generate_with_model',
                    self._provider(self.provider._generate_with_model)))
                stack.enter_context(patch.object(runner, 'score_generic', self._score(runner.score_generic)))
                stack.enter_context(patch.object(runner, 'assemble_context',
                    self._assemble(runner.assemble_context, 'tier1_runner')))
                if rag is not None:
                    stack.enter_context(patch.object(rag, 'assemble_context',
                        self._assemble(rag.assemble_context, 'tier2_rag')))
                yield self
            self._assert_config_stable()
            self._complete = True
        finally:
            self._attached = False
            _LOCK.release()

    def snapshot(self):
        """Return a detached hash-only snapshot; missing capture is never inferred."""
        if self._complete:
            self._assert_config_stable()
        body = dict(schema='official-v1-runtime-capture/1',
            capture_complete=self._complete and not self._attached,
            resolved_config=self.resolved_config,
            config_sha256=_digest(self.resolved_config),
            installed_hooks=['provider._generate_with_model', 'runner.score_generic',
                             'runner.assemble_context'] + (
                ['rag.assemble_context'] if self.resolved_config['run']['tier'] == 2 else []),
            events=self._events,
            limitations=['Provider events are model attempts, not internal HTTP retry counts.',
                'Hashes prove captured input consistency, not human review or approval authenticity.',
                'No historical prompt/context provenance is reconstructed.'])
        detached = json.loads(_json(body))
        detached['capture_sha256'] = _digest(detached)
        return detached


def report_from_bundle(path):
    """Feed a sealed execution bundle into the existing v1 diagnostic reporter.

    The exact opened bundle bytes are hashed once by the verifier. No JSONL is
    fabricated or substituted for the saved input: results_sha256 identifies
    the sealed bundle, and input_format names that representation explicitly.
    Fresh frozen identity and case metadata checks still apply. Seals establish
    consistency, not authenticity of execution, review or approving authority.
    """
    from eval import official_v1_execution as execution
    from eval.framework.integrity import load_dataset
    from scripts import formal_v1_report as reporting
    body, bundle_hash = execution.verify_bundle(path, with_digest=True)
    identity = reporting.current_identity()
    scope = body['scope']
    if (scope['manifest_sha256'] != identity['manifest_sha256'] or
            scope['dataset_sha256'] != identity['dataset_sha256'] or
            scope['scorer_sha256'] != identity['source_sha256']):
        raise ValueError('bundle identity differs from the verified official v1 freeze')
    _, cases = load_dataset()
    metadata = dict(identity, results_sha256=bundle_hash)
    report = reporting.make_report(body['rows'], cases, metadata, identity,
                                   split=scope['split'], tier=scope['tier'])
    report.update(input_format='v1-execution-bundle/1', execution_evidence={
        'bundle_sha256': bundle_hash, 'rows_sha256': body['rows_sha256'],
        'runtime_sha256': body['runtime_sha256'],
        'capture_sha256': body['runtime']['capture_sha256'],
        'runtime_config_sha256': scope['runtime_config_sha256'],
        'scope_sha256': execution.digest(execution.canonical(scope)),
        'approval_sha256': body['approval_sha256']})
    report['limitations'].append(
        'Execution bundle seals bind bytes; they do not independently authenticate human review or approval.')
    return report
