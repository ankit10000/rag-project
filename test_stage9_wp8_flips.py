"""Deterministic WP8 flip ledger validation and actual dev-only reconstruction."""
import testsafe
testsafe.require_scratch_db()
import copy
import csv
import hashlib
import json
from pathlib import Path
import unittest
from eval.acceptance_preparation import flips as F
from eval.scoring_v2.rescore_meta import scorer_identity


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def synthetic():
    ann=encoded({'schema':'phase35-scorer-annotations/1','dataset_sha256':'a'*64,
                 'dataset_version':'synthetic','cases':{'B-comp-04':{}}})
    identity=scorer_identity({'eval/scoring_v2/score.py':b'synthetic'},ann)
    v1={'correct':False,'partial_ok':False}
    v2={'correct':True,'partial_ok':True,'scorer_name':identity['name'],
        'scorer_version':identity['version'],'tables_version':identity['tables_version']}
    source=[{'id':'B-comp-04','tier':1,'split':'dev','question':'Question?',
             'answer':'Answer.','score':v1}]
    comparison=[dict(id='B-comp-04',tier=1,split='dev',v1_stored=v1,v1_current=v1,v2=v2,
        context_mode='tier1_reconstructed_exact',reconstruction_status='exact',rule_codes=['§10.3-partial'])]
    original=encoded(source[0])+b'\n'
    sidecar={'sidecar_format':'phase35-scoring-sidecar/1','scorer':identity,
        'dataset':{'run_time':{'pin_source':'operator_git_rev','git_rev':'b'*40,'dataset_version':'synthetic',
            'manifest_content_sha256':None,'file_sha256':{f'eval/phase35/data_{x}.py':'c'*64 for x in 'ABCD'}}},
        'source_results':{'path':'synthetic_dev.jsonl','sha256':F.raw_hash(original),'rows':1},
        'rows':[{'id':'B-comp-04','tier':1,'context_mode':'tier1_reconstructed_exact',
                 'reconstruction_status':'exact','context_sha256':'d'*64}],
        'counts':{'exact':1,'mismatch':0,'error_row':0,'fallback':0,'drift':0,'v2_flips':1},
        'acceptance_eligible':False}
    rebuilt={(1,'B-comp-04'):{'question':'Question?','answer':'Answer.','annotation':{},
        'context_sha256':'d'*64,'reconstruction_status':'exact','v1':v1,'v2':v2}}
    return comparison,sidecar,original,ann,identity,rebuilt


def analyze_fixture(data=None, path='synthetic.v2.jsonl'):
    rows,sidecar,source,ann,identity,rebuilt=data or synthetic()
    return F.analyze_artifact(b'\n'.join(encoded(r) for r in rows),encoded(sidecar),source,ann,
        artifact_path=path,current_identity=identity,reconstructed_rows=rebuilt)


EVIDENCE_ROOT=Path(__file__).resolve().parent/'docs/remediation/phase_e2_engineering/wp8_evidence/flip_inputs'
ARTIFACT_DIRS=(EVIDENCE_ROOT/'initial',EVIDENCE_ROOT/'final')


def actual_analyses():
    """Reproduce every available comparison using pinned WP6 functions, no writes."""
    from eval.scoring_v2 import context, score_case, validate_annotations
    from eval.scoring_v2.rescore import ROOT, load_pinned_dataset, read_rows, render_pages, pipeline_metadata
    from eval.phase35.run_eval import score_generic
    from eval.framework.integrity import dataset_hash
    from services.chunker import chunk_page
    index=json.loads((EVIDENCE_ROOT/'index.json').read_bytes())
    if index.get('format')!='wp8-flip-input-snapshots/1' or len(index.get('artifacts',[]))!=4:
        raise AssertionError('missing archived comparison inventory')
    for item in index['artifacts']:
        for path_key,hash_key in [('archive_path','artifact_sha256'),('sidecar_path','sidecar_sha256'),('annotations_path','annotations_raw_sha256'),('diff_path','diff_sha256')]:
            if F.raw_hash((ROOT/item[path_key]).read_bytes())!=item[hash_key]:
                raise AssertionError('archived input hash mismatch')
    docs,cases,pin=load_pinned_dataset(ROOT,'c1bbcae')
    pipeline_metadata(ROOT)
    table=context.build_tier2_chunks(render_pages(docs),(100,20,'words'),chunk_page)
    modules={p.relative_to(ROOT).as_posix():p.read_bytes() for p in sorted((ROOT/'eval/scoring_v2').glob('*.py'))}
    results=[]
    for directory in ARTIFACT_DIRS:
        annotations=(directory/'literal-annotations.c1bbcae.json').read_bytes(); ann=json.loads(annotations)
        if validate_annotations(ann,cases,docs) or ann['dataset_sha256']!=dataset_hash(cases):
            raise AssertionError('historical annotations failed pinned validation')
        current=scorer_identity(modules,annotations)
        for tier in (1,2):
            artifact=directory/f'tier{tier}_dev.v2.jsonl'; raw=artifact.read_bytes()
            sidecar_bytes=Path(str(artifact)+'.scoring.json').read_bytes(); sidecar=json.loads(sidecar_bytes)
            if sidecar['dataset']['run_time']['git_rev']!=pin['git_rev'] or sidecar['dataset']['run_time']['file_sha256']!=pin['file_sha256']:
                raise AssertionError('sidecar dataset pin differs from independent git load')
            source=(ROOT/sidecar['source_results']['path']).read_bytes()
            rows,byid=read_rows(source,tier,cases); rebuilt={}
            if tier==2 and (sidecar['context_config']['tier2']['chunk_count']!=len(table) or sidecar['context_config']['tier2']['chunk_table_sha256']!=context.chunk_table_sha256(table)):
                raise AssertionError('Tier2 chunk count/table hash mismatch')
            for row in rows:
                case=byid[row['id']]
                pair,ids,text,status,mode=(context.verify_tier1(row,case,docs) if tier==1 else context.verify_tier2(row,table,case))
                if status!='exact': raise AssertionError('reconstruction mismatch')
                v1=score_generic(case,row,pair,ids,text)
                if tier==2:
                    gold={(s['document'],s['page']) for s in case['gold_sources']}
                    refs=[(r['document_name'],r['page_number']) for r in row['retrieved']]
                    v1.update(retrieval_page_recall=len(gold&set(refs))/len(gold) if gold else None,
                        retrieval_first_gold_rank=next((i for i,r in enumerate(refs,1) if r in gold),None))
                record={'question':row['question'],'answer':row['answer'],'annotation':ann['cases'][row['id']],
                    'context_sha256':context.text_sha256(text),'reconstruction_status':status,'v1':v1,
                    'gold_facts':case['gold_facts'],'gold_sources':case['gold_sources'],
                    'context_evidence':[{'document':s['document'],'page':s['page'],'span':s['span']} for s in case['gold_sources']]}
                if current==sidecar['scorer']:
                    record['v2']=score_case(case,row,pair,ids,text,case['history'],ann['cases'][row['id']])
                rebuilt[(tier,row['id'])]=record
            inventory=next(x for x in index['artifacts'] if ROOT/x['archive_path']==artifact)
            result=F.analyze_artifact(raw,sidecar_bytes,source,annotations,artifact_path=inventory['original_path'],
                current_identity=current,reconstructed_rows=rebuilt)
            result['archive_path']=inventory['archive_path']
            for occurrence in result['flip_occurrences']:
                occurrence['archive_path']=inventory['archive_path']
                occurrence['archived_sidecar_path']=inventory['sidecar_path']
                occurrence['archived_annotations_path']=inventory['annotations_path']
            result['sidecar_path']=str(artifact)+'.scoring.json'
            result['sidecar_sha256']=F.raw_hash(sidecar_bytes)
            diff=artifact.with_suffix('.diff.md'); result['diff_path']=str(diff); result['diff_sha256']=F.raw_hash(diff.read_bytes())
            results.append(result)
    return results


class FlipTests(unittest.TestCase):
    def test_valid_current_identity_and_no_input_mutation(self):
        fixture=synthetic(); before=copy.deepcopy(fixture); result=analyze_fixture(fixture)
        self.assertEqual(fixture,before); row=result['flip_occurrences'][0]
        self.assertEqual(row['v2_replay'],'EXACT_CURRENT_IDENTITY')
        self.assertEqual(row['review_status'],'PENDING_INDEPENDENT_REVIEW'); self.assertFalse(row['human_approved'])

    def test_old_identity_is_retained_without_claiming_replay(self):
        f=list(synthetic()); f[4]=scorer_identity({'eval/scoring_v2/score.py':b'new implementation'},f[3])
        del f[5][(1,'B-comp-04')]['v2']
        result=analyze_fixture(f)
        self.assertFalse(result['identity_match'])
        self.assertEqual(result['flip_occurrences'][0]['v2_replay'],'NOT_REPLAYED_OLD_SCORER_IDENTITY')

    def test_grouping_retains_occurrences_and_rejects_double_ingestion(self):
        one=analyze_fixture(path='one'); two=analyze_fixture(path='two')
        groups=F.group_occurrences([one,two]); self.assertEqual(len(groups),1)
        self.assertEqual(len(groups[0]['occurrences']),2)
        with self.assertRaises(ValueError): F.group_occurrences([one,one])

    def test_malformed_json_duplicate_keys_and_nonfinite_rejected(self):
        for payload in (b'[]',b'{',b'{"x":1,"x":2}',b'{"x":NaN}'):
            f=synthetic()
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                F.analyze_artifact(payload,encoded(f[1]),f[2],f[3],artifact_path='x',current_identity=f[4],reconstructed_rows=f[5])

    def test_source_annotation_and_scorer_hash_mismatches_rejected(self):
        for mode in ('source','annotation','aggregate','module','counts'):
            f=list(synthetic())
            if mode=='source': f[2]+=b' '
            elif mode=='annotation': f[3]+=b' '
            elif mode=='aggregate': f[1]['scorer']['sha256']='0'*64
            elif mode=='module': f[1]['scorer']['module_sha256']['eval/scoring_v2/score.py']='0'*64
            else: f[1]['counts']['v2_flips']=0
            with self.subTest(mode=mode),self.assertRaises(ValueError): analyze_fixture(f)

    def test_missing_duplicate_inconsistent_and_nondevelopment_rows_rejected(self):
        for mode in ('heldout','tier','duplicate','metadata','pin','context','question','annotation','v1','v2','rules'):
            f=list(synthetic())
            if mode=='heldout': f[0][0]['split']='heldout'
            elif mode=='tier': f[0][0]['tier']=True
            elif mode=='duplicate': f[0].append(copy.deepcopy(f[0][0]))
            elif mode=='metadata': f[1]['rows']=[]
            elif mode=='pin': del f[1]['dataset']['run_time']['file_sha256']
            elif mode=='context': f[5][(1,'B-comp-04')]['context_sha256']='0'*64
            elif mode=='question': f[5][(1,'B-comp-04')]['question']='different'
            elif mode=='annotation': f[5][(1,'B-comp-04')]['annotation']={'negatable_groups':[0]}
            elif mode=='v1': f[5][(1,'B-comp-04')]['v1']={'correct':True}
            elif mode=='v2': f[5][(1,'B-comp-04')]['v2']={'correct':False}
            else: f[0][0]['rule_codes']=[]
            with self.subTest(mode=mode),self.assertRaises(ValueError): analyze_fixture(f)

    def test_ledger_replays_mechanical_evidence_without_review_approval(self):
        path=Path(__file__).resolve().parent/'docs/remediation/phase_e2_engineering/WP8_SCORER_FLIP_LEDGER.csv'
        with path.open(newline='',encoding='utf-8') as source:
            stored=list(csv.DictReader(source))
        assessments={}
        for row in stored:
            assessment={key:row['proposed_'+key] for key in F.ASSESSMENT_FIELDS}
            old=assessments.setdefault(row['unique_flip_id'],assessment)
            self.assertEqual(old,assessment)
        expected=F.ledger_rows(actual_analyses(),assessments)
        # The preserved ledger records replay at its original review time. Source
        # hardening legitimately changes current identity, not historical evidence.
        omit_replay=lambda row:{key:str(value) for key,value in row.items() if key!='v2_replay'}
        self.assertEqual([omit_replay(row) for row in stored],[omit_replay(row) for row in expected])
        self.assertTrue(all(row['v2_replay'] in ('EXACT_CURRENT_IDENTITY',
            'NOT_REPLAYED_OLD_SCORER_IDENTITY') for row in stored))
        self.assertEqual(len(stored),8)
        self.assertTrue(all(r['review_status']==F.REVIEW_STATUS and r['human_approved']=='False' for r in stored))
        with self.assertRaises(ValueError):
            F.ledger_rows([analyze_fixture()],{analyze_fixture()['flip_occurrences'][0]['unique_flip_id']:{'human_approved':True}})

    def test_extra_metadata_boolean_count_and_malformed_modes_rejected(self):
        for mode in ('extra','boolean_count','missing_count','boolean_tier','null_mode','list_mode'):
            f=list(synthetic())
            if mode=='extra': f[1]['rows'].append(None)
            elif mode=='boolean_count': f[1]['source_results']['rows']=True
            elif mode=='missing_count': del f[1]['source_results']['rows']
            elif mode=='boolean_tier': f[1]['rows'][0]['tier']=True
            else:
                value=None if mode=='null_mode' else []
                f[0][0]['context_mode']=value; f[1]['rows'][0]['context_mode']=value
            with self.subTest(mode=mode),self.assertRaises(ValueError): analyze_fixture(f)

    def test_actual_four_artifacts_reconstruct_all_development_rows(self):
        before={p:F.raw_hash(p.read_bytes()) for d in ARTIFACT_DIRS for p in d.iterdir()}
        analyses=actual_analyses(); groups=F.group_occurrences(analyses)
        self.assertEqual(len(analyses),4); self.assertEqual(sum(a['row_count'] for a in analyses),178)
        self.assertEqual(sum(len(a['flip_occurrences']) for a in analyses),8); self.assertEqual(len(groups),4)
        # Replay claims follow source identity; historical score archives are immutable.
        for analysis in analyses:
            expected_replay=('EXACT_CURRENT_IDENTITY' if analysis['identity_match']
                else 'NOT_REPLAYED_OLD_SCORER_IDENTITY')
            self.assertTrue(all(row['v2_replay']==expected_replay for row in analysis['flip_occurrences']))
        self.assertEqual([len(a['flip_occurrences']) for a in analyses],[3,1,3,1])
        self.assertEqual(before,{p:F.raw_hash(p.read_bytes()) for p in before})


if __name__=='__main__': unittest.main()
