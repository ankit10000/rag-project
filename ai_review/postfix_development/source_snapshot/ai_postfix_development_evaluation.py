"""One-shot, new synthetic post-fix development experiment; never held-out.

Prepare first, then execute exactly once. Neither action edits historical data.
The v2 behavior contract is technical only; frozen v1 scoring is diagnostic.
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
OUT = ROOT/'ai_review/postfix_development'
DATASET_ID = 'ai-lumen-postfix-synthetic-v1'
POLICY_ID = 'ai-lumen-postfix-behavior-policy-v1'
RUN_ID = 'ai-lumen-postfix-live-20261119-v1'
CALL_LIMIT = 12
KINDS = ('supported_fact', 'explicit_negative_fact', 'missing_information', 'partial_information')
CRITERIA = dict(case_count=4, all_behavior_contracts=True, required_fact_recall=1.0,
                fabricated_citations=0, ungrounded_numbers=0, forbidden_hits=0,
                factual_citation_completeness=1.0)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def exclusive_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def build_dataset():
    text = ('SYNTHETIC LUMEN OBSERVATORY VISITOR POLICY. '
            'The Lumen Observatory visitor permit costs 71 tokens. '
            'The visitor permit is valid for 23 days. '
            'The Lumen Observatory does not provide a fax service. '
            'The policy does not provide a telephone number. '
            'The policy does not provide a mailing address.')
    doc = 'synthetic_lumen_observatory.txt'
    chunks = [dict(document=doc, page=1, content=text)]
    source = dict(document=doc, page=1, span=text)
    definitions = [
        ('fee', KINDS[0], 'According to the Lumen Observatory policy, what does a visitor permit cost?', [['71 tokens']]),
        ('fax-service', KINDS[1], 'Does the Lumen Observatory provide a fax service according to its policy?',
         [["does not provide a fax service", "doesn't provide a fax service", 'no fax service',
           'not provide fax', 'not offer fax', 'does not offer a fax service',
           'fax service is not available', 'fax services are unavailable']]),
        ('telephone', KINDS[2], "According to its policy, what is the Lumen Observatory's telephone number?", []),
        ('fee-and-address', KINDS[3], 'According to the Lumen Observatory policy, what does a visitor permit cost and what is the mailing address?', [['71 tokens']]),
    ]
    cases = [dict(id='ai-lumen-postfix-'+suffix, expected_kind=kind, category=suffix,
                  split='new_synthetic_development', tier='answer_only', question=question,
                  history=[], gold_facts=facts, gold_sources=[] if kind==KINDS[2] else [source],
                  tier1_chunks=chunks, forbidden=[], expect_abstain=kind==KINDS[2],
                  expect_partial=kind==KINDS[3], expect_conflict=False)
             for suffix, kind, question, facts in definitions]
    return dict(dataset_id=DATASET_ID, provenance='Wholly new invented non-held-out source and questions', cases=cases)


def validate_inputs(dataset, policy):
    from eval.phase35 import validate
    _, original = validate.load(['data_A', 'data_B', 'data_C', 'data_D'])
    previous = json.loads((ROOT/'ai_review/development/dataset.json').read_text())['cases']
    originals = original+previous
    old_ids = {c['id'] for c in originals}
    old_questions = {' '.join(c['question'].lower().split()) for c in originals}
    cases = dataset['cases']
    if len(cases)!=4 or len({c['id'] for c in cases})!=4 or {c['expected_kind'] for c in cases}!=set(KINDS):
        raise ValueError('four unique cases covering all predeclared kinds required')
    if any(c['id'] in old_ids or ' '.join(c['question'].lower().split()) in old_questions for c in cases):
        raise ValueError('original case/question collision')
    if (dataset['dataset_id']!=DATASET_ID or policy['policy_id']!=POLICY_ID or policy['run_id']!=RUN_ID
            or policy['scope']!='DEVELOPMENT_ONLY' or policy['criteria']!=CRITERIA):
        raise ValueError('wrong independently predeclared scope or criteria')
    if policy['dataset_sha256']!=digest(OUT/'dataset.json'):
        raise ValueError('dataset digest mismatch')
    if policy['behavior_contract_sha256']!=digest(ROOT/'ai_review/development_v2/contract.py'):
        raise ValueError('behavior contract source mismatch')
    if policy['behavior_policy_sha256']!=digest(ROOT/'ai_review/development_v2/policy.json'):
        raise ValueError('behavior policy source mismatch')
    return cases


def prepare():
    if OUT.exists() and any(OUT.iterdir()):
        raise ValueError('predeclared namespace already exists; no overwrite')
    OUT.mkdir(parents=True, exist_ok=True)
    exclusive_json(OUT/'dataset.json', build_dataset())
    exclusive_json(OUT/'policy.json', dict(policy_id=POLICY_ID, version=1, run_id=RUN_ID,
        dataset_id=DATASET_ID, dataset_sha256=digest(OUT/'dataset.json'), created_at=stamp(),
        scope='DEVELOPMENT_ONLY', criteria=CRITERIA,
        behavior_contract_sha256=digest(ROOT/'ai_review/development_v2/contract.py'),
        behavior_policy_sha256=digest(ROOT/'ai_review/development_v2/policy.json'),
        expected_kind='Fixed in each source-reviewed case before provider execution',
        diagnostic_scorer='Unchanged frozen v1 score_generic; its whole-case correct/partial/unsupported flags are reported, not inherited as this policy gate',
        gate_explanation='Existing behavior contract plus required gold fact recall, structural citations and number guards only; not a semantic entailment certificate or acceptance policy',
        maximum_sdk_calls=CALL_LIMIT, request_budget_seconds=45, total_budget_seconds=180,
        acceptance_policy_adoption=False, official_heldout_activation=False, human_review_completed=0))


def evaluate_case(case, result, score, bundle):
    from ai_review.development_v2.contract import assess_behavior
    behavior = assess_behavior(case['expected_kind'], result, bundle['sources'])
    reasons = list(behavior['issues'])
    if score['fact_recall']!=1.0: reasons.append('required_fact_recall')
    if score['fabricated']!=0: reasons.append('fabricated_citation')
    if score['ungrounded_numbers']: reasons.append('ungrounded_numbers')
    if score['forbidden_hits']: reasons.append('forbidden_hits')
    if case['expected_kind']!='missing_information' and score['citation_completeness']!=1.0:
        reasons.append('factual_citation_completeness')
    return dict(policy_pass=not reasons, issues=sorted(set(reasons)), behavior=behavior,
                limitation='Behavior/fact-string/structural guards, not independent semantic judgment or formal acceptance.')


def run():
    if any((OUT/f).exists() for f in ('attempt.json', 'results.jsonl', 'run_evidence.json')):
        raise ValueError('one-shot identity already attempted; no rerun or resume')
    os.environ['DATABASE_URL']='postgresql://invalid:invalid@127.0.0.1:1/rag_test_postfix_unreachable'
    with contextlib.ExitStack() as stack:
        def blocked(*args, **kwargs): raise RuntimeError('database access forbidden in answer-only development run')
        for target in ('connect','Connection.connect','AsyncConnection.connect'):
            stack.enter_context(patch('psycopg.'+target,side_effect=blocked))
        from eval.phase35.run_eval import score_generic, tier1_context
        from services.answer_service import generate_grounded_answer
        from services.context_assembly_service import assemble_context
        from services import llm_service as llm
        from services.request_budget import request_budget
        policy=json.loads((OUT/'policy.json').read_text())
        dataset=json.loads((OUT/'dataset.json').read_text())
        cases=validate_inputs(dataset, policy)
        exclusive_json(OUT/'attempt.json', dict(run_id=RUN_ID, started_at=stamp(), scope='DEVELOPMENT_ONLY'))
        calls=[]; rows=[]; active=None
        code_paths=('scripts/ai_postfix_development_evaluation.py','eval/phase35/run_eval.py','eval/answer_scoring.py',
            'services/answer_service.py','services/citation_service.py','services/answer_semantics.py',
            'services/answer_prompt.py','services/context_assembly_service.py','services/llm_service.py',
            'ai_review/development_v2/contract.py')
        evidence=dict(run_id=RUN_ID, dataset_id=DATASET_ID, policy_id=POLICY_ID, scope='DEVELOPMENT_ONLY',
            started_at=stamp(), policy_sha256=digest(OUT/'policy.json'), dataset_sha256=digest(OUT/'dataset.json'),
            configured_primary=llm.MODEL_NAME, configured_fallbacks=llm.FALLBACK_MODELS,
            code_sha256={p:digest(ROOT/p) for p in code_paths}, database_connections=0,
            database_guard='Unreachable process URL and psycopg sync/async connection tripwires',
            maximum_sdk_calls=CALL_LIMIT, human_review_completed=0,
            official_status='OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING')
        real=llm.get_client().models.generate_content
        def measured(*args, **kwargs):
            if len(calls)>=CALL_LIMIT: raise RuntimeError('aggregate application SDK call cap reached')
            entry=dict(case_id=active, requested_model=kwargs.get('model'), started_at=stamp())
            calls.append(entry); start=time.monotonic()
            try:
                response=real(*args,**kwargs)
                entry.update(outcome='success',returned_model=getattr(response,'model_version',None))
                return response
            except Exception as error:
                entry.update(outcome='error',error_type=type(error).__name__,code=getattr(error,'code',None));raise
            finally:entry['latency_seconds']=round(time.monotonic()-start,4)
        stack.enter_context(patch.object(llm.get_client().models,'generate_content',side_effect=measured))
        start=time.monotonic()
        try:
            with (OUT/'results.jsonl').open('x') as stream, request_budget(180):
                for case in cases:
                    active=case['id']; before=time.monotonic(); first=len(calls)
                    retrieval,pairs,ids=tier1_context(case,{})
                    bundle=assemble_context(retrieval)
                    try:
                        with request_budget(45):
                            result=generate_grounded_answer(case['question'],bundle,'DOCUMENT',llm.generate_answer,[])
                        score=score_generic(case,result,pairs,ids,' '.join(s['content'] for s in bundle['sources']))
                        technical=evaluate_case(case,result,score,bundle)
                        row=dict(id=active,expected_kind=case['expected_kind'],result=result,
                                 frozen_v1_diagnostic=score,technical=technical)
                    except Exception as error:
                        row=dict(id=active,expected_kind=case['expected_kind'],technical=dict(policy_pass=False),error_type=type(error).__name__)
                    row.update(run_id=RUN_ID,latency_seconds=round(time.monotonic()-before,4),sdk_calls=len(calls)-first)
                    stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
                    rows.append(row)
        except Exception as error:
            evidence['error_type']=type(error).__name__
        finally:
            passed=len(rows)==4 and all(r['technical']['policy_pass'] for r in rows)
            evidence.update(finished_at=stamp(),latency_seconds=round(time.monotonic()-start,4),calls=calls,
                total_sdk_calls=len(calls),completed_cases=len(rows),passed_cases=sum(r['technical']['policy_pass'] for r in rows),
                results_sha256=digest(OUT/'results.jsonl') if (OUT/'results.jsonl').exists() else None,
                status='AI_TECHNICAL_EVALUATION_PASS' if passed else 'AI_TECHNICAL_EVALUATION_FAIL')
            exclusive_json(OUT/'run_evidence.json',evidence)
        return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run']); args=parser.parse_args()
    if args.action=='prepare':
        prepare();print('New post-fix development policy/dataset saved; no provider call.')
    else:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):outcome=run()
        print(json.dumps({k:outcome[k] for k in ('run_id','status','completed_cases','passed_cases','total_sdk_calls')}))
        raise SystemExit(0 if outcome['status']=='AI_TECHNICAL_EVALUATION_PASS' else 1)
