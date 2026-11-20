"""Bounded, opt-in development reliability replay. Never a held-out runner.

Default invocation freezes source-review checks and performs no provider I/O.
Live calls require --live, a new identity, and a pre-existing frozen check file.
Raw traces are private exclusive-create scratch artifacts, not ordinary logs.
"""
import argparse
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / 'v2_evidence/reliability-20261119'
PLAN = ARTIFACTS / 'predeclared.json'


def fact(label, *patterns):
    return {'label': label, 'alternatives': list(patterns)}


# Source-review checks declared before any live run. These are observable
# coverage signals, not an automated proof of semantic entailment.
EXAMS = [fact(x, rf'\b{x}\b') for x in ('JEE', 'GATE', 'NEET')]
ACCESS = [fact('Hindi/regional languages', r'\bHindi\b', r'regional languages'),
          fact('offline study', r'\boffline\b'), fact('videos', r'\bvideos?\b'),
          fact('notes', r'\bnotes?\b'), fact('mobile app', r'\bmobile\b')]
PHASES = [fact('planning and prototype', r'planning\s*(?:&|and)\s*prototype'),
          fact('0-6 months', r'\b0\s*(?:-|to)\s*6\b'),
          fact('MVP development', r'MVP\s+development'),
          fact('6-15 months', r'\b6\s*(?:-|to)\s*15\b'),
          fact('pilot and feedback', r'pilot\s*(?:&|and)\s*feedback'),
          fact('15-21 months', r'\b15\s*(?:-|to)\s*21\b'),
          fact('launch and scale', r'launch\s*(?:&|and)\s*scale'),
          fact('21-30 months', r'\b21\s*(?:-|to)\s*30\b')]
FEATURES = [fact('video lessons', r'video\s+(?:lessons?|lectures?)', r'instructional videos'),
            fact('notes/summaries', r'\bnotes?\b', r'\bsummaries\b'),
            fact('tests/quizzes', r'\bquizzes\b', r'test\s+series'),
            fact('question bank/Q&A', r'question\s+banks?', r'Q\s*&\s*A', r'question.answer'),
            fact('adaptive learning', r'adaptive\s+learning', r'personalized.*(?:learning|topic)'),
            fact('doubt forum', r'\bforum\b'),
            fact('progress analytics', r'\banalytics\b', r'progress\s+tracking'),
            fact('gamification', r'\bgamification\b', r'badges.*(?:streaks|leaderboards)'),
            fact('multilingual', r'\bmultilingual\b', r'\bHindi\b', r'regional\s+languages'),
            fact('offline/mobile', r'\boffline\b', r'\bmobile\b')]
GAP = [fact('contract information unavailable', r"couldn.t find.*information",
            r'(?:no|not|does not|do not|doesn.t).*?(?:contract|information|provided|available|specified|listed|contain)',
            r'contract.*?(?:unavailable|not\s+(?:provided|available|specified|listed))')]
CHECKS = {
    'product': {'facts': [fact('AI education portal', r'AI.driven education portal', r'AI.*education portal')] + EXAMS, 'status': ['answered']},
    'estimates': {'facts': [fact('2-3 years', r'\b2\s*(?:-|to)\s*3\s+years?'),
                            fact('10-15 people', r'\b10\s*(?:-|to)\s*15\b'),
                            fact('1M-5M summary budget', r'1\s*(?:M|million).*?5\s*(?:M|million)')], 'status': ['answered']},
    'accessibility': {'facts': ACCESS, 'status': ['answered']},
    'phases': {'facts': PHASES, 'status': ['answered']},
    'risks': {'facts': [fact('human review', r'human.*?(?:review|loop)'),
                       fact('conservative generation', r'conservative'), fact('early feedback', r'feedback'),
                       fact('legal review', r'legal\s+review'), fact('open/public data', r'public.*?open', r'open.*?data'),
                       fact('rephrasing', r'rephras')], 'status': ['answered']},
    'unsupported': {'facts': GAP, 'status': ['abstained'], 'evidence_not_applicable': True, 'citations': False},
    'cross_page': {'facts': [fact('relational database', r'PostgreSQL', r'MySQL'),
                            fact('200K annual cloud', r'200\s*(?:K|thousand).*?(?:year|annual)', r'(?:year|annual).*?200\s*(?:K|thousand)')], 'status': ['answered']},
    'comparison': {'facts': [fact('on-premises option', r'on.?(?:premises|prem)\b', r'on-\s+.*?premises'),
                            fact('public cloud option', r'public\s+(?:\w+\s+){0,8}cloud', r'cloud'),
                            fact('high upfront capital', r'high.*?(?:upfront|initial|hardware|capital)', r'(?:upfront|initial|capital).*?high'),
                            fact('bounded on-prem capacity', r'limited.*?(?:purchased|capacity|scal)', r'(?:purchased|capacity).*?limited'),
                            fact('no upfront public cloud', r'no\s+upfront', r'none', r'avoid.*?CapEx', r'no\s+initial'),
                            fact('cloud scalability', r'virtually\s+(?:\w+\s+){0,4}unlimited', r'elastic', r'auto.scal', r'easier to scale')], 'status': ['answered']},
    'follow_up': {'facts': ACCESS, 'status': ['answered']},
    'conflict': {'facts': [fact('stated three', r'(?:roughly\s+)?(?:3|three)\s+phases?'),
                          fact('listed four', r'(?:4|four)\s+phases?', r'phase\s+4'),
                          fact('disagreement disclosure', r'inconsisten', r'contradict', r'disagree', r'discrepan', r'does not agree', r'do not agree', r'conflict')], 'status': ['conflict'], 'evidence_facts': [fact('stated three', r'(?:roughly\s+)?(?:3|three)\s+phases?'), fact('listed fourth phase', r'phase\s+4')]},
    'explicit_negative': {'facts': [fact('no upfront cost', r'no\s+upfront', r'does not.*?(?:upfront|capital)', r'avoid.*?CapEx', r'no\s+initial'),
                                   fact('ongoing usage cost', r'pay.as.you.go', r'ongoing', r'recurring')], 'status': ['answered'], 'evidence_facts': [fact('explicit no upfront', r'no\s+upfront', r'none', r'avoid.*?CapEx'), fact('usage costs', r'pay.as.you.go', r'ongoing', r'recurring')]},
    'long_section': {'facts': FEATURES, 'status': ['answered']},
    'partial': {'facts': EXAMS + GAP, 'evidence_facts': EXAMS, 'status': ['partial']},
}


def normalized(text):
    return re.sub(r'\s+', ' ', str(text).translate(str.maketrans({'–': '-', '—': '-', '−': '-'}))).strip()


def check_facts(text, facts):
    content = normalized(text)
    return [{'label': item['label'], 'observed': any(re.search(pattern, content, re.I) for pattern in item['alternatives'])}
            for item in facts]


def private_json(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise PermissionError('artifact directory must be private')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2, default=str, allow_nan=False)
        f.write('\n')


def freeze_checks():
    plan = json.loads(PLAN.read_text())
    if set(CHECKS) != {c['id'] for c in plan['cases']}:
        raise ValueError('case set differs from predeclaration')
    data = {'policy': 'development-reliability-source-review-checks/1',
            'predeclared_sha256': hashlib.sha256(PLAN.read_bytes()).hexdigest(),
            'checks': CHECKS,
            'caveat': 'Literal coverage signals plus citation metadata/status checks. Not semantic entailment, full-corpus absence proof, or an LLM judge.'}
    path = ARTIFACTS / 'frozen_fact_checks.json'
    if path.exists():
        if json.loads(path.read_text()) != data:
            raise ValueError('frozen checks differ; refusing to alter observed expectations')
    else:
        private_json(path, data)
    return plan, data


@contextmanager
def guarded_scratch_connections():
    """Verify the actual DB identity before any application data operation."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    original = psycopg.connect
    def guarded(info='', **kwargs):
        parsed = conninfo_to_dict(info)
        parsed.update({k: v for k, v in kwargs.items() if k in ('dbname', 'host')})
        if parsed.get('dbname') != 'rag_test_scratch' or parsed.get('host') not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('only explicit localhost rag_test_scratch may be used')
        conn = original(info, **kwargs)
        try:
            if conn.execute('SELECT current_database()').fetchone()[0] != 'rag_test_scratch':
                raise ValueError('scratch database identity mismatch')
            conn.commit()
        except BaseException:
            conn.close()
            raise
        return conn
    psycopg.connect = guarded
    try:
        yield
    finally:
        psycopg.connect = original


def configure():
    from scripts.v2_scratch import app_url
    os.environ.update(DATABASE_URL=app_url(), RAG_V2='1', RAG_DEVELOPMENT_TRACE='1',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2', GEMINI_FALLBACK_MODELS='')


def source_rows(plan):
    from services.database import get_connection
    from services.tenant_context import tenant_scope
    with tenant_scope(plan['owner']), get_connection() as conn:
        rows = conn.execute('''SELECT id, document_name, page_number, content
            FROM document_chunks WHERE owner_id=%s AND document_id=%s''',
                            (plan['owner'], plan['source_document'])).fetchall()
    if len(rows) != 76:
        raise ValueError('predeclared source changed; expected 76 chunks')
    return {r[0]: r for r in rows}


def two_user_isolation(plan):
    """Read-only RLS checks against two pre-existing scratch document owners."""
    from services.database import get_connection
    from services.tenant_context import tenant_scope
    secondary = '4c4125dc-5f84-4cf5-a6df-82384b03ed7f'
    results = []
    for owner in (plan['owner'], secondary):
        with tenant_scope(owner), get_connection() as conn:
            own_count = conn.execute('SELECT count(*) FROM documents WHERE owner_id=%s', (owner,)).fetchone()[0]
            visible = conn.execute('SELECT id FROM documents WHERE id=%s', (plan['source_document'],)).fetchall()
            chunks = conn.execute('SELECT id FROM document_chunks WHERE document_id=%s', (plan['source_document'],)).fetchall()
        results.append({'owner': owner, 'has_preexisting_owned_documents': own_count > 0,
                        'selected_source_visible': bool(visible), 'selected_chunks_visible': len(chunks)})
    passed = (results[0]['has_preexisting_owned_documents'] and results[0]['selected_source_visible']
              and results[0]['selected_chunks_visible'] == 76
              and results[1]['has_preexisting_owned_documents'] and not results[1]['selected_source_visible']
              and results[1]['selected_chunks_visible'] == 0)
    return {'pass': passed, 'checks': results, 'database_writes': False,
            'secondary_owner_provenance': 'existing v2_evidence/live_smoke_retry1.json resource_ids.owner_ids[0]'}


def sent_sources(snapshot):
    for event in reversed(snapshot.get('events', [])):
        if event['stage'] == 'generation_request':
            return event.get('raw', {}).get('sources', [])
    return []


def metrics_for(case, result, snapshot, rows):
    checks = CHECKS[case['id']]
    sources = sent_sources(snapshot)
    source_text = '\n'.join(s['content'] for s in sources)
    evidence = None if checks.get('evidence_not_applicable') else check_facts(source_text, checks.get('evidence_facts', checks['facts']))
    answer = check_facts(result.get('answer', ''), checks['facts'])
    citations = result.get('citations', [])
    metadata_ok = all(c['chunk_id'] in rows and c['document'] == rows[c['chunk_id']][1]
                      and c['page'] == rows[c['chunk_id']][2] for c in citations)
    citation_presence = bool(citations) == checks.get('citations', True)
    status_ok = result.get('status') in checks['status']
    return {'evidence_coverage': None if evidence is None else all(c['observed'] for c in evidence),
            'evidence_fact_checks': evidence,
            'answer_factual_completeness': all(c['observed'] for c in answer),
            'answer_fact_checks': answer,
            'citation_abstention_correctness': metadata_ok and citation_presence and status_ok,
            'citation_metadata_matches_owned_source': metadata_ok,
            'citation_presence_correct': citation_presence, 'declared_status_correct': status_ok,
            'selected_chunks': [s['chunk_id'] for s in sources],
            'selected_pages': [s['page_number'] for s in sources],
            'selected_characters': sum(len(s['content']) for s in sources),
            'scope_and_budget_ok': len(sources) <= 8 and sum(len(s['content']) for s in sources) <= 12000
                and all(s['document_name'] == next(iter(rows.values()))[1] for s in sources)}


def select_cases(plan, case_ids=None):
    if case_ids is None:
        return list(plan['cases'])
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise ValueError('subset must contain unique predeclared case IDs')
    unknown = set(case_ids) - {c['id'] for c in plan['cases']}
    if unknown:
        raise ValueError('subset contains an undeclared case ID')
    return [case for case in plan['cases'] if case['id'] in case_ids]


def live_run(identity, plan, case_ids=None, max_calls=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}', identity):
        raise ValueError('invalid fresh identity')
    cases = select_cases(plan, case_ids)
    prior_calls = sum(json.loads(path.read_text()).get('provider_calls', 0)
                      for path in ARTIFACTS.glob('*/result.json'))
    remaining = plan['max_provider_calls'] - prior_calls
    call_cap = min(remaining, plan['max_provider_calls'] if max_calls is None else max_calls)
    if call_cap <= 0 or (max_calls is not None and not 0 < max_calls <= remaining):
        raise ValueError('requested provider cap exceeds the remaining aggregate development budget')
    destination = ARTIFACTS / identity
    destination.mkdir(mode=0o700)  # never re-use or overwrite a run
    source_files = ['services/rag_service.py', 'services/hybrid_search_service.py',
                    'services/reranker_service.py', 'services/evidence_trace.py',
                    'services/v2_evidence_recovery.py', 'services/request_coverage.py',
                    'services/answer_service.py', 'services/answer_semantics.py',
                    'services/answer_prompt.py', 'scripts/v2_reliability_check.py']
    source_files.extend(name for name in ['services/source_count_comparison.py'] if (ROOT/name).is_file())
    private_json(destination / 'runtime-sources.json', {
        'sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files},
        'selected_case_ids': [c['id'] for c in cases], 'provider_call_cap': call_cap,
        'prior_provider_calls': prior_calls})
    configure()
    from google.genai.models import Models
    from services.rag_service import ask_question
    from services.request_budget import request_budget
    from services.tenant_context import tenant_scope
    from services.evidence_trace import answer_evidence_trace
    calls = []
    original_generate = Models.generate_content
    def counted(self, *args, **kwargs):
        if len(calls) >= call_cap:
            raise ValueError('predeclared provider-call cap reached')
        record = {'requested_model': kwargs.get('model'),
                  'prompt_sha256': hashlib.sha256(str(kwargs.get('contents')).encode()).hexdigest()}
        calls.append(record)
        started = time.monotonic()
        try:
            response = original_generate(self, *args, **kwargs)
            record.update(response_sha256=hashlib.sha256((response.text or '').encode()).hexdigest(),
                          returned_model=getattr(response, 'model_version', None))
            return response
        except BaseException as exc:
            record['error_type'] = type(exc).__name__
            raise
        finally:
            record['seconds'] = round(time.monotonic() - started, 3)
    Models.generate_content = counted
    results = []
    try:
        with guarded_scratch_connections():
            rows = source_rows(plan)
            isolation = two_user_isolation(plan)
            private_json(destination / 'isolation.json', isolation)
            for case in cases:
                started = time.monotonic(); before = len(calls)
                with answer_evidence_trace(case['question'], [plan['source_document']], include_raw=True) as trace:
                    try:
                        with tenant_scope(plan['owner']), request_budget(seconds=plan['request_budget_seconds'], suppress_output=True), redirect_stdout(io.StringIO()):
                            result = ask_question(case['question'], history=case.get('history', []))
                        entry = {'id': case['id'], 'question': case['question'], 'result': result,
                                 'metrics': metrics_for(case, result, trace.snapshot(), rows)}
                    except Exception as exc:
                        entry = {'id': case['id'], 'question': case['question'], 'error_type': type(exc).__name__,
                                 'metrics': {'evidence_coverage': None if CHECKS[case['id']].get('evidence_not_applicable') else False, 'answer_factual_completeness': False,
                                             'citation_abstention_correctness': False}}
                entry.update(seconds=round(time.monotonic() - started, 3), provider_calls=len(calls)-before)
                trace.write(destination / (case['id'] + '-trace.json'))
                private_json(destination / (case['id'] + '.json'), entry)
                results.append(entry)
                print(json.dumps({k: entry[k] for k in ('id', 'seconds', 'provider_calls')} |
                                 {'metrics': {k: entry['metrics'].get(k) for k in ('evidence_coverage', 'answer_factual_completeness', 'citation_abstention_correctness')}}), flush=True)
            metric_summary = {}
            for key in ('evidence_coverage', 'answer_factual_completeness', 'citation_abstention_correctness'):
                applicable = [r['metrics'][key] for r in results if r['metrics'].get(key) is not None]
                metric_summary[key] = {'passed': sum(applicable), 'total': len(applicable),
                                       'percent': round(100*sum(applicable)/len(applicable), 2) if applicable else None}
            report = {'identity': identity, 'predeclared_sha256': hashlib.sha256(PLAN.read_bytes()).hexdigest(),
                      'frozen_checks_sha256': hashlib.sha256((ARTIFACTS/'frozen_fact_checks.json').read_bytes()).hexdigest(),
                      'metrics': metric_summary, 'provider_calls': len(calls), 'max_provider_calls': call_cap,
                      'selected_case_ids': [c['id'] for c in cases],
                      'aggregate_provider_budget': plan['max_provider_calls'], 'prior_provider_calls': prior_calls,
                      'calls': calls, 'results': results, 'isolation': isolation,
                      'scope': 'development only; no formal acceptance claim', 'database_writes': False,
                      'metric_caveat': 'Literal fact coverage plus citation-page/status checks; manual source comparison still required for entailment.'}
            private_json(destination / 'result.json', report)
    finally:
        Models.generate_content = original_generate
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--identity')
    parser.add_argument('--cases', help='Comma-separated subset of unchanged predeclared case IDs')
    parser.add_argument('--max-provider-calls', type=int)
    args = parser.parse_args()
    plan, _ = freeze_checks()
    if not args.live:
        print('Frozen checks ready; no provider calls or database operations performed.')
        return
    if not args.identity:
        parser.error('--live requires a fresh --identity')
    case_ids = args.cases.split(',') if args.cases else None
    report = live_run(args.identity, plan, case_ids, args.max_provider_calls)
    print(json.dumps({'metrics': report['metrics'], 'provider_calls': report['provider_calls'],
                      'isolation_pass': report['isolation']['pass']}, indent=2))


if __name__ == '__main__':
    main()
