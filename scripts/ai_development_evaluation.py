"""New synthetic development-only answer-layer evaluation; never runs held-out inputs.

Policy and dataset are exclusively created before live execution. Results are
exclusive, flushed per case, and cannot be resumed or overwritten by this tool.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'ai_review/development'
DATASET_ID = 'ai-kestrel-synthetic-answer-v1'
POLICY_ID = 'ai-kestrel-development-policy-v1'
RUN_ID = 'ai-kestrel-live-20261119-v1'
CALL_LIMIT = 12
CRITERIA = {'case_count': 4, 'all_correct': True, 'fabricated_total': 0,
            'unsupported_total': 0, 'answered_actual_document_citation': True,
            'proper_abstention': True}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def exclusive_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def build_dataset():
    text = ('SYNTHETIC KEStREL OBSERVATORY VISITOR POLICY. '
            'The Kestrel Observatory visitor permit costs 83 credits. '
            'The visitor permit is valid for 17 days. '
            'The policy does not provide a fax number.')
    document = 'synthetic_kestrel_observatory.txt'
    source = {'document': document, 'page': 1, 'span': text}
    chunks = [{'document': document, 'page': 1, 'content': text}]
    definitions = [
        ('fee', 'According to the Kestrel Observatory policy, what does a visitor permit cost?', [['83 credits']]),
        ('duration', 'According to the Kestrel Observatory policy, how long is a visitor permit valid?', [['17 days']]),
        ('compound', 'According to the Kestrel Observatory policy, what is the visitor permit cost and how long is it valid?', [['83 credits'], ['17 days']]),
        ('unavailable-fax', 'According to the Kestrel Observatory policy, what is its fax number?', []),
    ]
    cases = []
    for suffix, question, facts in definitions:
        abstain = suffix == 'unavailable-fax'
        cases.append(dict(id=f'ai-kestrel-new-v1-{suffix}', category=suffix,
                          split='new_synthetic_development', tier='answer_only',
                          question=question, history=[], gold_facts=facts,
                          gold_sources=[] if abstain else [source], tier1_chunks=chunks,
                          forbidden=[], expect_abstain=abstain,
                          expect_partial=False, expect_conflict=False))
    return dict(dataset_id=DATASET_ID, provenance='New invented synthetic corpus; no original case copied', cases=cases)


def validate_inputs(dataset, policy):
    from eval.phase35 import validate as original
    _, protected = original.load(['data_A', 'data_B', 'data_C', 'data_D'])
    old_ids = {c['id'] for c in protected}
    old_questions = {' '.join(c['question'].lower().split()) for c in protected}
    cases = dataset['cases']
    ids = [c['id'] for c in cases]
    if len(cases) != 4 or len(set(ids)) != 4:
        raise ValueError('exactly four unique synthetic cases required')
    if any(c['id'] in old_ids or ' '.join(c['question'].lower().split()) in old_questions for c in cases):
        raise ValueError('original case/question collision')
    if dataset['dataset_id'] != DATASET_ID or policy['policy_id'] != POLICY_ID:
        raise ValueError('wrong independent identity')
    if policy['criteria'] != CRITERIA or policy['scope'] != 'DEVELOPMENT_ONLY':
        raise ValueError('policy scope or complete criteria mismatch')
    if policy['dataset_sha256'] != digest(OUT / 'dataset.json'):
        raise ValueError('dataset digest mismatch')
    return cases


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    exclusive_json(OUT / 'dataset.json', build_dataset())
    exclusive_json(OUT / 'policy.json', dict(
        policy_id=POLICY_ID, version=1, scope='DEVELOPMENT_ONLY', created_at=stamp(),
        dataset_id=DATASET_ID, dataset_sha256=digest(OUT / 'dataset.json'),
        run_id=RUN_ID, criteria=CRITERIA, maximum_sdk_calls=CALL_LIMIT,
        request_budget_seconds=45, total_budget_seconds=180,
        policy_author='AI', human_review_completed=0,
        limitation='Toy answer-layer technical criteria only; not frozen v1 thresholds or formal acceptance. '
                   'Frozen score_generic is reused without modification. No held-out execution.'))


def evaluate_case(case, result, score, bundle):
    sources = {s['chunk_id']: s for s in bundle['sources']}
    valid_citations = all(c.get('chunk_id') in sources and
        c.get('document') == sources[c['chunk_id']]['document_name'] and
        c.get('page') == sources[c['chunk_id']]['page_number']
        for c in result['citations'])
    behavior = ((result['status'] == 'abstained' and not result['citations'])
                if case['expect_abstain'] else
                (result['status'] == 'answered' and bool(result['citations']) and
                 score['citation_completeness'] == 1 and valid_citations))
    return bool(score['correct'] and score['fabricated'] == 0 and
                not score['unsupported'] and behavior)


def run():
    if any((OUT / f).exists() for f in ('results.jsonl', 'run_evidence.json')):
        raise ValueError('immutable run already exists; rerun refused')
    # Set before dotenv/services imports. A second defense blocks any accidental DB use.
    os.environ['DATABASE_URL'] = 'postgresql://invalid:invalid@127.0.0.1:1/ai_kestrel_unreachable_scratch'
    import psycopg
    def blocked(*args, **kwargs):
        raise RuntimeError('database connection forbidden in synthetic answer-only run')
    with contextlib.ExitStack() as stack:
        for target in ('connect', 'Connection.connect', 'AsyncConnection.connect'):
            stack.enter_context(patch('psycopg.' + target, side_effect=blocked))
        from eval.phase35.run_eval import score_generic, tier1_context
        from services.answer_service import generate_grounded_answer
        from services.context_assembly_service import assemble_context
        from services import llm_service as llm
        from services.request_budget import request_budget
        policy = json.loads((OUT / 'policy.json').read_text())
        dataset = json.loads((OUT / 'dataset.json').read_text())
        cases = validate_inputs(dataset, policy)
        calls, records = [], []
        evidence = dict(run_id=RUN_ID, scope='DEVELOPMENT_ONLY', started_at=stamp(),
                        policy_sha256=digest(OUT / 'policy.json'),
                        dataset_sha256=digest(OUT / 'dataset.json'),
                        configured_primary=llm.MODEL_NAME, configured_fallbacks=llm.FALLBACK_MODELS,
                        maximum_sdk_calls=CALL_LIMIT, database_connections=0,
                        database_guard='unreachable DATABASE_URL and psycopg connection tripwires',
                        human_review_completed=0, official_status='OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING',
                        code_sha256={name: digest(ROOT / name) for name in (
                            'scripts/ai_development_evaluation.py', 'eval/phase35/run_eval.py',
                            'services/answer_service.py', 'services/answer_prompt.py',
                            'services/context_assembly_service.py', 'services/llm_service.py')})
        sdk = llm.get_client()
        real = sdk.models.generate_content
        active = None
        def measured(*args, **kwargs):
            if len(calls) >= CALL_LIMIT:
                raise RuntimeError('aggregate SDK call cap reached')
            entry = dict(case_id=active, requested_model=kwargs.get('model'), started_at=stamp())
            calls.append(entry)
            start = time.monotonic()
            try:
                response = real(*args, **kwargs)
                entry.update(outcome='success', returned_model=getattr(response, 'model_version', None), code=None)
                return response
            except Exception as error:
                entry.update(outcome='error', error_type=type(error).__name__, code=getattr(error, 'code', None))
                raise
            finally:
                entry['latency_seconds'] = round(time.monotonic() - start, 4)
        stack.enter_context(patch.object(sdk.models, 'generate_content', side_effect=measured))
        started = time.monotonic()
        try:
            with (OUT / 'results.jsonl').open('x', encoding='utf-8') as output, request_budget(180):
                for case in cases:
                    active = case['id']
                    retrieval, pairs, ids = tier1_context(case, {})
                    bundle = assemble_context(retrieval)
                    first, before = len(calls), time.monotonic()
                    try:
                        with request_budget(45):
                            result = generate_grounded_answer(case['question'], bundle, 'DOCUMENT', llm.generate_answer, [])
                        score = score_generic(case, result, pairs, ids,
                                              ' '.join(s['content'] for s in bundle['sources']))
                        passed = evaluate_case(case, result, score, bundle)
                        record = dict(id=active, result=result, score=score, policy_pass=passed)
                    except Exception as error:
                        record = dict(id=active, policy_pass=False, error_type=type(error).__name__)
                    record.update(run_id=RUN_ID, dataset_id=DATASET_ID,
                                  latency_seconds=round(time.monotonic()-before, 4),
                                  sdk_calls=len(calls)-first)
                    output.write(json.dumps(record) + '\n')
                    output.flush()
                    os.fsync(output.fileno())
                    records.append(record)
        except Exception as error:
            evidence['error_type'] = type(error).__name__
        finally:
            passed = len(records) == 4 and all(r['policy_pass'] for r in records)
            evidence.update(finished_at=stamp(), latency_seconds=round(time.monotonic()-started, 4),
                            calls=calls, total_sdk_calls=len(calls), completed_cases=len(records),
                            passed_cases=sum(r['policy_pass'] for r in records),
                            results_sha256=digest(OUT / 'results.jsonl'),
                            status='AI_TECHNICAL_EVALUATION_PASS' if passed else 'AI_TECHNICAL_EVALUATION_FAIL')
            exclusive_json(OUT / 'run_evidence.json', evidence)
        return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
        print('New synthetic dataset and DEVELOPMENT_ONLY policy saved before live calls.')
    else:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            evidence = run()
        print(json.dumps({k: evidence[k] for k in ('run_id', 'status', 'total_sdk_calls', 'completed_cases', 'passed_cases')}))
