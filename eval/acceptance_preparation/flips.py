"""Pure, dev-only scorer-flip evidence validation; no adoption or review decisions.

Caller supplies raw artifacts and independently reconstructed row evidence. The
module never reads files, loads data revisions, executes scorers or writes outputs.
Older scorer hashes are retained and explicitly cannot claim current-code replay.
"""
import copy
import hashlib
import json
import re
from eval.framework.hashing import portable_sha256
from eval.framework.integrity import split_of

REVIEW_STATUS = 'PENDING_INDEPENDENT_REVIEW'
_HEX = re.compile(r'[0-9a-f]{64}')


def raw_hash(data):
    if not isinstance(data, bytes): raise ValueError('artifact inputs must be bytes')
    return hashlib.sha256(data).hexdigest()


def _object(data):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError('duplicate JSON key')
            out[key] = value
        return out
    try:
        return json.loads(data, object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ValueError('malformed artifact JSON') from exc


def _rows(data):
    raw_hash(data)
    try:
        rows = [_object(line) for line in data.decode('utf-8').splitlines() if line.strip()]
    except UnicodeError as exc:
        raise ValueError('malformed artifact encoding') from exc
    if not rows or any(not isinstance(row,dict) for row in rows):
        raise ValueError('artifact requires nonempty object rows')
    keys=[]
    for row in rows:
        if (not isinstance(row.get('id'),str) or not row['id'] or type(row.get('tier')) is not int
                or row['tier'] not in (1,2) or row.get('split')!='dev'
                or split_of(row['id'])!='dev'):
            raise ValueError('only correctly labelled development rows are allowed')
        keys.append((row['tier'], row['id']))
    if len(keys)!=len(set(keys)): raise ValueError('duplicate artifact row')
    return rows


def _digest(value):
    return isinstance(value,str) and _HEX.fullmatch(value) is not None


def _score(value):
    if not isinstance(value,dict) or type(value.get('correct')) is not bool:
        raise ValueError('missing or malformed scorer result')
    return value


def _scorer(identity):
    required={'name','version','tables_version','sha256','module_sha256','annotations_sha256','annotation_schema'}
    if not isinstance(identity,dict) or set(identity)!=required or identity['name']!='phase35-scorer' or identity['version']!='2.1.0' or identity['tables_version']!='2.1.0' or identity['annotation_schema']!='phase35-scorer-annotations/1':
        raise ValueError('invalid scorer identity')
    modules=identity['module_sha256']
    if not isinstance(modules,dict) or not modules or any(not isinstance(path,str) or not re.fullmatch(r'eval/scoring_v2/[a-z_]+\.py',path) or not _digest(value) for path,value in modules.items()) or not _digest(identity['annotations_sha256']):
        raise ValueError('invalid scorer module or annotation hashes')
    records=dict(modules, **{'eval/scoring_v2/annotations.json':identity['annotations_sha256']})
    expected=hashlib.sha256(''.join(f'{p}\t{h}\n' for p,h in sorted(records.items())).encode()).hexdigest()
    if identity['sha256']!=expected: raise ValueError('scorer aggregate hash mismatch')


def validate_comparison(comparison_bytes, sidecar_bytes, source_bytes, annotations_bytes,
                        *, current_identity, reconstructed_rows):
    """Return verified parsed evidence, or raise ValueError; never infer a proof.

    ``reconstructed_rows[(tier,id)]`` must contain exact context SHA, independently
    computed v1 score, question, answer, gold facts/sources and annotation. For a
    matching scorer identity it additionally supplies the exact replayed v2 score.
    The caller must use the sidecar-pinned dataset and unchanged WP6 reconstruction.
    """
    for data in (comparison_bytes,sidecar_bytes,source_bytes,annotations_bytes): raw_hash(data)
    sidecar=_object(sidecar_bytes); annotations=_object(annotations_bytes)
    if not isinstance(sidecar,dict) or sidecar.get('sidecar_format')!='phase35-scoring-sidecar/1':
        raise ValueError('invalid scoring sidecar')
    identity=sidecar.get('scorer'); _scorer(identity); _scorer(current_identity)
    if portable_sha256(annotations_bytes,'text')!=identity['annotations_sha256']:
        raise ValueError('annotation hash mismatch')
    if not isinstance(annotations,dict) or annotations.get('schema')!=identity['annotation_schema'] or not isinstance(annotations.get('cases'),dict) or not _digest(annotations.get('dataset_sha256')) or not isinstance(annotations.get('dataset_version'),str) or not annotations['dataset_version']:
        raise ValueError('missing annotation provenance')
    dataset=sidecar.get('dataset')
    if not isinstance(dataset,dict): raise ValueError('missing dataset provenance')
    pin=dataset.get('run_time',{})
    if (not isinstance(pin,dict) or pin.get('pin_source') not in ('operator_git_rev','run_header')
            or not isinstance(pin.get('git_rev'),str) or not re.fullmatch(r'[0-9a-f]{40}',pin['git_rev'])
            or not isinstance(pin.get('dataset_version'),str) or not pin['dataset_version']
            or not isinstance(pin.get('file_sha256'),dict)
            or set(pin['file_sha256'])!={f'eval/phase35/data_{x}.py' for x in 'ABCD'}
            or not all(_digest(v) for v in pin['file_sha256'].values())
            or not (_digest(pin.get('manifest_content_sha256')) or (pin.get('manifest_content_sha256') is None and pin['pin_source']=='operator_git_rev'))):
        raise ValueError('missing dataset pin')
    source=sidecar.get('source_results',{})
    if not isinstance(source,dict) or source.get('sha256')!=raw_hash(source_bytes) or not isinstance(source.get('path'),str) or not source['path'] or type(source.get('rows')) is not int:
        raise ValueError('source artifact hash mismatch')
    rows=_rows(comparison_bytes); originals=_rows(source_bytes)
    keys=[(r['tier'],r['id']) for r in rows]
    if keys!=[(r['tier'],r['id']) for r in originals] or source.get('rows')!=len(rows):
        raise ValueError('source/comparison row order or coverage mismatch')
    meta=sidecar.get('rows')
    if not isinstance(meta,list) or len(meta)!=len(keys) or any(not isinstance(r,dict) or type(r.get('tier')) is not int for r in meta) or [(r.get('tier'),r.get('id')) for r in meta]!=keys:
        raise ValueError('sidecar row coverage mismatch')
    if not isinstance(reconstructed_rows,dict) or set(reconstructed_rows)!=set(keys):
        raise ValueError('missing independent reconstruction evidence')
    exact_identity=identity==current_identity
    for row,original,record in zip(rows,originals,meta):
        key=(row['tier'],row['id']); rebuilt=reconstructed_rows[key]
        if not isinstance(rebuilt,dict) or rebuilt.get('reconstruction_status')!='exact':
            raise ValueError('independent context reconstruction is not exact')
        if not isinstance(row.get('context_mode'),str) or not isinstance(record.get('context_mode'),str):
            raise ValueError('context mode must be an explicit string')
        if row.get('reconstruction_status')!='exact' or record.get('reconstruction_status')!='exact' or row.get('context_mode')!=record.get('context_mode') or 'NON_ACCEPTANCE' in row.get('context_mode',''):
            raise ValueError('comparison context is unavailable or fallback')
        if not _digest(rebuilt.get('context_sha256')) or rebuilt['context_sha256']!=record.get('context_sha256'):
            raise ValueError('context hash mismatch')
        if row['id'] not in annotations['cases'] or rebuilt.get('annotation')!=annotations['cases'][row['id']]:
            raise ValueError('annotation-to-case linkage mismatch')
        if rebuilt.get('question')!=original.get('question') or rebuilt.get('answer')!=original.get('answer'):
            raise ValueError('reconstructed input differs from source')
        if (_score(row.get('v1_stored'))!=_score(original.get('score'))
                or _score(row.get('v1_current'))!=_score(rebuilt.get('v1'))
                or row['v1_stored']!=row['v1_current']):
            raise ValueError('v1 source, reconstruction, or stored/current drift')
        v2=_score(row.get('v2'))
        if any(v2.get(k)!=identity[v] for k,v in [('scorer_name','name'),('scorer_version','version'),('tables_version','tables_version')]):
            raise ValueError('row scorer identity differs from sidecar')
        if exact_identity and v2!=_score(rebuilt.get('v2')):
            raise ValueError('current-identity v2 replay mismatch')
        if not isinstance(row.get('rule_codes'),list) or any(not isinstance(code,str) or not code for code in row['rule_codes']):
            raise ValueError('missing rule codes')
        if row['v1_current']['correct']!=v2['correct'] and not row['rule_codes']:
            raise ValueError('flip lacks explanatory rule codes')
    counts=sidecar.get('counts',{})
    expected={'exact':len(rows),'mismatch':0,'fallback':0,'error_row':0,'drift':0,
              'v2_flips':sum(r['v1_current']['correct']!=r['v2']['correct'] for r in rows)}
    if not isinstance(counts,dict) or any(type(v) is not int for v in counts.values()) or counts!=expected: raise ValueError('sidecar counts do not reproduce')
    if sidecar.get('acceptance_eligible') is not False:
        raise ValueError('development comparison must remain non-acceptance')
    return {'rows':rows,'source_rows':originals,'sidecar':sidecar,
            'identity_match':exact_identity,'reconstructed_rows':reconstructed_rows}


def analyze_artifact(comparison_bytes,sidecar_bytes,source_bytes,annotations_bytes,
                     *, artifact_path,current_identity,reconstructed_rows):
    """Preserve every flip occurrence and its recorded scorer/source identities."""
    verified=validate_comparison(comparison_bytes,sidecar_bytes,source_bytes,annotations_bytes,
        current_identity=current_identity,reconstructed_rows=reconstructed_rows)
    if not isinstance(artifact_path,str) or not artifact_path: raise ValueError('artifact path is required')
    sidecar=verified['sidecar']; identity=sidecar['scorer']; occurrences=[]
    for number,row in enumerate(verified['rows'],1):
        if row['v1_current']['correct']==row['v2']['correct']: continue
        rebuilt=reconstructed_rows[(row['tier'],row['id'])]
        unique=f"tier{row['tier']}:{row['id']}:{sidecar['source_results']['sha256']}"
        occurrences.append({'unique_flip_id':unique,'case_id':row['id'],'tier':row['tier'],
            'artifact_path':artifact_path,'artifact_line':number,'artifact_sha256':raw_hash(comparison_bytes),
            'sidecar_sha256':raw_hash(sidecar_bytes),'source_results_path':sidecar['source_results']['path'],
            'source_results_sha256':sidecar['source_results']['sha256'],
            'annotations_raw_sha256':raw_hash(annotations_bytes),'annotations_sha256':identity['annotations_sha256'],
            'dataset_pin':copy.deepcopy(sidecar['dataset']['run_time']),
            'scorer_sha256':identity['sha256'],'scorer_version':identity['version'],
            'context_sha256':rebuilt['context_sha256'],'reconstruction_status':'exact',
            'v1_reproduction':'EXACT','v2_replay':'EXACT_CURRENT_IDENTITY' if verified['identity_match'] else 'NOT_REPLAYED_OLD_SCORER_IDENTITY',
            'v1_correct':row['v1_current']['correct'],'v2_correct':row['v2']['correct'],
            'v1_score':copy.deepcopy(row['v1_current']),'v2_score':copy.deepcopy(row['v2']),
            'rule_codes':list(row['rule_codes']),'question':rebuilt['question'],'answer':rebuilt['answer'],
            'gold_facts':copy.deepcopy(rebuilt.get('gold_facts',[])),
            'gold_sources':copy.deepcopy(rebuilt.get('gold_sources',[])),
            'context_evidence':copy.deepcopy(rebuilt.get('context_evidence',[])),
            'annotation':copy.deepcopy(rebuilt['annotation']),'review_status':REVIEW_STATUS,
            'human_approved':False})
    return {'artifact_path':artifact_path,'artifact_sha256':raw_hash(comparison_bytes),
            'row_count':len(verified['rows']),'scorer_sha256':identity['sha256'],
            'identity_match':verified['identity_match'],'flip_occurrences':occurrences}


def group_occurrences(analyses):
    groups={}; seen=set()
    for analysis in analyses:
        for row in analysis['flip_occurrences']:
            occurrence=(row['artifact_path'],row['artifact_sha256'],row['artifact_line'])
            if occurrence in seen: raise ValueError('same artifact occurrence supplied twice')
            seen.add(occurrence)
            groups.setdefault(row['unique_flip_id'],[]).append(copy.deepcopy(row))
    return [{'unique_flip_id':key,'occurrences':value,'review_status':REVIEW_STATUS,
             'human_approved':False} for key,value in sorted(groups.items())]


ASSESSMENT_FIELDS = ('explanation','rule_support','error_category','input_quality',
    'impact','severity','likely_cause','confidence','potential_false_positive',
    'potential_false_negative','recommended_disposition')


def ledger_rows(analyses, assessments=None):
    """Flatten evidence reproducibly, keeping supplied engineering judgments separate.

    Assessments are proposed engineering interpretations, never review sign-offs.
    No caller can override provenance, pending status, or the approval flag here.
    Nested evidence is canonical JSON suitable for a CSV cell.
    """
    assessments=assessments or {}
    group_occurrences(analyses)  # Reject accidental repeated ingestion.
    output=[]
    for analysis in analyses:
        for occurrence in analysis['flip_occurrences']:
            row=copy.deepcopy(occurrence)
            assessment=assessments.get(row['unique_flip_id'],{})
            if not isinstance(assessment,dict) or set(assessment)-set(ASSESSMENT_FIELDS):
                raise ValueError('unknown assessment field; review approval cannot be supplied')
            row['judgment_type']='ENGINEERING_ASSESSMENT_NOT_INDEPENDENT_REVIEW'
            for name in ASSESSMENT_FIELDS:
                value=assessment.get(name,'NOT_ASSESSED')
                if not isinstance(value,str): raise ValueError('assessment values must be text')
                row['proposed_'+name]=value
            for key,value in list(row.items()):
                if isinstance(value,(dict,list)):
                    row[key]=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
            output.append(row)
    return output
