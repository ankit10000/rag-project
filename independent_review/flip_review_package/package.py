"""Build a staged, dev-only independent-review evidence package, without decisions."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess

PIN='c1bbcae9a21e389c16c3f1587de5acc1b5209e37'
EXPECTED_SCORER='0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf'
STATUS='PENDING_INDEPENDENT_REVIEW'
TARGETS=((1,'D-conflicting-01'),(1,'B-comp-04'),(1,'B-conf-04'),(2,'B-conf-04'))
ARCHIVE='docs/remediation/phase_e2_engineering/wp8_evidence/flip_inputs'
SPEC='docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md'
README='''# Independent flip-review package — development only

**No independent review has occurred.** All decisions, rationales and reviewer fields are blank.
Four case/tier records and eight historical artifact occurrences are distinct; none is an approved golden list.
V1 remains official. V2.1 remains experimental. Acceptance and re-freezing are not authorized here.

## Stage A: record your own judgment before AI analysis

The existing anti-anchoring policy is preserved: see `docs/remediation/dev_review/README.md`
“How to review” and `docs/remediation/phase_e2_engineering/PHASE_E2_REMAINING_DECISIONS.md`
§1 S-2. The owner must designate an independent reviewer. This package does not designate one.

1. Open only each `records/<case-tier>/stage_a_blind.json`: question, raw answer,
   citations, full reconstructed scoring context and relevant source pages/passages.
   These files intentionally omit scorer outcomes, gold labels, AI recommendations and mechanics.
2. Record an independent judgment and rationale in a **working copy** of
   `reviewer_decisions.csv`; keep the supplied template and evidence immutable.
   Record reviewer name, date and any prior exposure; do not backfill a sign-off.
3. A human review coordinator verifies that independent judgments have been recorded
   before providing the Stage B files. No review has been recorded by this builder.

## Stage B: compare the mechanics after the independent judgment

Only after Stage A is recorded, open `records/<case-tier>/after_independent_judgment.json`.
It contains full v1/v2 results, source/scorer hashes, applicable specification excerpts,
neutral mechanical explanations and both historical occurrences. It offers no recommended outcome.
Keep the original independent judgment, then separately record any post-analysis comment/change.
Do not open the historical WP8 AI flip ledger/analysis before Stage A.

This staging is an exposure instruction, **not filesystem access control or an authenticated
approval gate**. Do not treat editing a CSV cell as proof of independence or adoption authority.
The review-status index reports preparation state only; source identity is not a truth judgment.
D-conflicting-01 is listed first as the handoff's review-priority item; no judgment is suggested.

## Provenance and limits

Current scorer identity is pinned in each Stage B record. Historical ebc9/af81 identities
remain distinct from the hardened current identity; equal result dictionaries mean behavioral
parity, not execution of an unavailable old implementation. Contexts follow the historical
WP6 scoring-context contract. Historical original runtime configuration, row order and exact
prompt bytes are not proven by reconstruction. The seven unavailable `(1)` uploads are not
represented as byte-verified uploads; repository-retained snapshots are named explicitly.

No held-out case is scored. No provider, database, ingestion, adoption or official gate is invoked.
Use `package.build_payloads(repo_root)` and `test_phase_e2_flip_review.py` to verify deterministic
records, full contexts, source/scorer hashes and blank review state. Regeneration writes exclusively
to a new directory; existing packages must never be overwritten or silently marked reviewed.
'''


def digest(data): return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()


def _read_rows(path): return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _spec_sections(root,sections):
    text=(root/SPEC).read_text(); result=[]
    for title,next_title in sections:
        start=text.index(title); end=text.index(next_title,start)
        result.append({'path':SPEC,'source_sha256':digest((root/SPEC).read_bytes()),
            'start_line':text[:start].count('\n')+1,'section':title.lstrip('# '),'text':text[start:end].rstrip()})
    return result


def build_payloads(root):
    """Reconstruct exactly four dev cases, returning new package payloads in memory."""
    from eval.scoring_v2 import context,score_case,validate_annotations
    from eval.scoring_v2.rescore import load_pinned_dataset,render_pages
    from eval.scoring_v2.rescore_meta import scorer_identity
    from eval.phase35.run_eval import score_generic
    from eval.framework.integrity import split_of
    root=Path(root).resolve(); archive=root/ARCHIVE
    annotations_bytes=(archive/'final/literal-annotations.c1bbcae.json').read_bytes()
    annotations=json.loads(annotations_bytes)
    modules={p.relative_to(root).as_posix():p.read_bytes() for p in sorted((root/'eval/scoring_v2').glob('*.py'))}
    identity=scorer_identity(modules,annotations_bytes)
    if identity['sha256']!=EXPECTED_SCORER: raise ValueError('current scorer identity changed; prepare a new identified package')
    docs,cases,pin=load_pinned_dataset(root,PIN); byid={c['id']:c for c in cases}
    if validate_annotations(annotations,cases,docs): raise ValueError('pinned annotations failed validation')
    chunk_source=subprocess.check_output(['git','show',f'{PIN}:services/chunker.py'],cwd=root)
    namespace={};exec(compile(chunk_source,'pinned-pure-chunker','exec'),namespace)
    table=context.build_tier2_chunks(render_pages(docs),(100,20,'words'),namespace['chunk_page'])
    historical_index=json.loads((archive/'index.json').read_bytes())['artifacts']
    for item in historical_index:
        for p,h in [('archive_path','artifact_sha256'),('sidecar_path','sidecar_sha256'),('annotations_path','annotations_raw_sha256')]:
            if digest((root/item[p]).read_bytes())!=item[h]: raise ValueError('historical snapshot hash mismatch')
    source_rows={t:{r['id']:r for r in _read_rows(root/f'eval/phase35/results/tier{t}_dev.jsonl')} for t in (1,2)}
    payloads={'README.md':README.encode()}; index=[]; decisions=[]
    for tier,cid in TARGETS:
        if split_of(cid)!='dev': raise ValueError('only development cases may enter this package')
        case=byid[cid]; row=source_rows[tier][cid]; key=f'tier{tier}_{cid}'; prefix=f'records/{key}'
        if tier==1:
            pair,ids,text,status,mode=context.verify_tier1(row,case,docs)
            items,_,_,_,_=context.tier1_items(case,docs)
            chunks=[{'chunk_id':i['chunk'][0],'document':i['chunk'][1],'page':i['chunk'][2],'text':i['chunk'][3].strip()} for i in items]
        else:
            pair,ids,text,status,mode=context.verify_tier2(row,table,case)
            chunks=[{'chunk_id':r['chunk_id'],'document':table[r['chunk_id']-1]['document'],
                'page':table[r['chunk_id']-1]['page'],'text':table[r['chunk_id']-1]['content']} for r in row['retrieved']]
        if status!='exact' or ' '.join(c['text'] for c in chunks)!=text: raise ValueError('exact scoring context missing')
        for chunk in chunks: chunk['text_sha256']=context.text_sha256(chunk['text'])
        pairs=list(dict.fromkeys((c['document'],c['page']) for c in chunks))
        pages=[{'document':d,'page':p,'text':docs[d][p-1],'text_sha256':context.text_sha256(docs[d][p-1])} for d,p in pairs]
        passages=[{'document':s['document'],'page':s['page'],'text':s['span']} for s in case['gold_sources']]
        v1=score_generic(case,row,pair,ids,text)
        if tier==2:
            gold={(s['document'],s['page']) for s in case['gold_sources']}; refs=[(r['document_name'],r['page_number']) for r in row['retrieved']]
            v1.update(retrieval_page_recall=len(gold&set(refs))/len(gold) if gold else None,
                retrieval_first_gold_rank=next((i for i,r in enumerate(refs,1) if r in gold),None))
        v2=score_case(case,row,pair,ids,text,case['history'],annotations['cases'][cid])
        if v1!=row['score'] or v1['correct']==v2['correct']: raise ValueError('source score drift or expected review item absent')
        occurrences=[]
        for item in historical_index:
            if item['tier']!=tier: continue
            archived=next((r for r in _read_rows(root/item['archive_path']) if r['id']==cid),None)
            side=json.loads((root/item['sidecar_path']).read_bytes()); meta=next(r for r in side['rows'] if r['id']==cid)
            if archived is None or archived['v1_current']!=v1 or archived['v2']!=v2 or meta['context_sha256']!=context.text_sha256(text):
                raise ValueError('historical comparison behavior/context differs')
            occurrences.append({'original_path':item['original_path'],'archive_path':item['archive_path'],
                'artifact_sha256':item['artifact_sha256'],'sidecar_path':item['sidecar_path'],'sidecar_sha256':item['sidecar_sha256'],
                'recorded_scorer':side['scorer'],'recorded_comparison':archived,
                'recorded_source_results':side['source_results'],'recorded_dataset_pin':side['dataset']['run_time'],
                'context_sha256':meta['context_sha256'],'shared_raw_answer_and_full_context':'stage_a_blind.json',
                'identity_relation':'HISTORICAL_DISTINCT_IDENTITY_BEHAVIORAL_PARITY_ONLY'})
        if len(occurrences)!=2: raise ValueError('historical occurrence coverage differs')
        citations=[dict(c,context_present=c['chunk_id'] in ids,
            context_reference=next(({'document':x['document'],'page':x['page']} for x in chunks if x['chunk_id']==c['chunk_id']),None)) for c in row['citations']]
        blind={'schema':'phase-e2-flip-blind-evidence/1','record_id':key,'tier':tier,'case_id':cid,'split':'dev',
            'question':row['question'],'raw_answer':row['answer'],'history':case['history'],
            'ordered_scoring_context':chunks,'scoring_context_text':text,'context_sha256':context.text_sha256(text),
            'source_pages':pages,'relevant_source_passages':passages,'citations':citations,
            'review_status':STATUS,'reviewer_judgment':'','reviewer_rationale':''}
        if cid=='B-comp-04':
            mechanics='The available-fact group matches. Eligible clauses produce A1 and A2 missing-part signals; partial_ok changes False to True. Citation correctness remains 0.5 in both results.'
            sections=[('### 10.1 Eligible clauses','### 10.2'),('### 10.2 Signal families','### 10.3'),('### 10.3 Status rules','### 10.4')]
        else:
            mechanics=('Both duration groups occur in one sentence with the connective '+('Although' if tier==1 else 'though')+'. Both required pages are cited; conflict_ok changes False to True.' if cid=='B-conf-04' else 'The 750-hour group and 500-hour group occur in separate sentences. V1 has a global However signal; v2 has no single qualifying two-group sentence/list scope. conflict_ok changes True to False.')
            sections=[('## 11. Disagreement','### 11.1 Tests')]
        source_path=f'eval/phase35/results/tier{tier}_dev.jsonl'
        after={'schema':'phase-e2-flip-mechanics/1','record_id':key,'review_status':STATUS,'human_approved':False,
            'scorer':identity,'source_revision_role':'Working-tree HEAD context only; uncommitted scorer identity is bound by module hashes',
            'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip(),
            'dataset_pin':pin,'annotation_path':f'{ARCHIVE}/final/literal-annotations.c1bbcae.json',
            'annotation_raw_sha256':digest(annotations_bytes),'annotation':annotations['cases'][cid],
            'source_results':{'path':source_path,'raw_sha256':digest((root/source_path).read_bytes())},
            'context_sha256':context.text_sha256(text),'reconstruction_status':status,'context_mode':mode,
            'gold_facts':case['gold_facts'],'gold_sources':case['gold_sources'],'expected_case_flags':{k:case[k] for k in ('expect_partial','expect_conflict','expect_abstain')},
            'v1':v1,'v2':v2,'specification_clauses':_spec_sections(root,sections),
            'neutral_mechanical_explanation':mechanics,'historical_occurrences':occurrences,
            'reviewer_judgment':'','reviewer_rationale':'','recommended_outcome':None}
        payloads[prefix+'/stage_a_blind.json']=encoded(blind)
        payloads[prefix+'/after_independent_judgment.json']=encoded(after)
        index.append({'record_id':key,'case_id':cid,'tier':tier,'blind_evidence':prefix+'/stage_a_blind.json',
            'stage_b_after_judgment':prefix+'/after_independent_judgment.json','historical_occurrence_count':2,
            'review_status':STATUS,'reviewer_judgment':'','reviewer_rationale':'','human_approved':False})
        decisions.append({'record_id':key,'review_status':STATUS,'reviewer_name':'','review_date':'','prior_exposure':'',
            'reviewer_judgment':'','reviewer_rationale':'','independent_judgment_recorded_at':'','stage_b_viewed_at':'','post_analysis_comment':''})
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=list(decisions[0]));writer.writeheader();writer.writerows(decisions)
    payloads['reviewer_decisions.csv']=output.getvalue().encode()
    payloads['review_status_index.json']=encoded({'schema':'phase-e2-flip-review-status/1','state':STATUS,
        'unique_case_tier_records':4,'historical_occurrences':8,'review_completed':False,'acceptance_approved':False,
        'current_scorer_sha256':identity['sha256'],'records':index})
    payloads['package_manifest.json']=encoded({'schema':'phase-e2-flip-review-package/1','review_status':STATUS,
        'generator_sha256':digest(Path(__file__).read_bytes()),'files':{p:digest(b) for p,b in sorted(payloads.items())}})
    return payloads


def write_package(root,output):
    payloads=build_payloads(root);output=Path(output)
    if any((output/p).exists() or (output/p).is_symlink() for p in payloads): raise FileExistsError('review evidence already exists')
    for name,data in payloads.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as file: file.write(data)
    return output


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();write_package(args.root,args.output)
