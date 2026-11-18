"""Parsed-object annotations schema and deterministic validation (§13.3)."""
import copy
import re
from .normalize import M, contains
SCHEMA = 'phase35-scorer-annotations/1'
CASE_KEYS = {'forbidden','disclosure','history_wrong_values','negatable_groups','conflict_groups'}
FORBIDDEN_KEYS = {'text','kind','source','allowed_with','gold_entities','note'}


def _index(value, n):
    return isinstance(value,int) and not isinstance(value,bool) and 0<=value<n


def entry_errors(ann, case=None, docs=None):
    if not isinstance(ann,dict): return ['AV-1: case annotation must be an object']
    errors = []
    if set(ann)-CASE_KEYS: errors.append('AV-1: unknown case annotation key')
    has_case = case is not None
    case = case or {}; groups = case.get('gold_facts',[])
    for key,value in ann.items():
        if not isinstance(value,list): errors.append('AV-1: '+key+' must be a list')
    if errors: return errors
    seen = []; gold = [M(a) for group in groups for a in group]
    for entry in ann.get('forbidden',[]):
        if not isinstance(entry,dict) or not isinstance(entry.get('text'),str) or not entry['text'].strip() or set(entry)-FORBIDDEN_KEYS:
            errors.append('AV-1: invalid forbidden entry'); continue
        kind = entry.get('kind'); text = entry['text']; seen.append(text)
        if kind not in ('literal','assertion','distractor','disclosure') or entry.get('source','dataset' if text in case.get('forbidden',[]) else 'annotation') not in ('dataset','annotation'):
            errors.append('AV-1: invalid forbidden kind/source')
        if 'note' in entry and not isinstance(entry['note'],str): errors.append('AV-1: note must be text')
        if kind == 'literal' and ('allowed_with' in entry or 'gold_entities' in entry): errors.append('AV-5: literal attribution fields')
        if kind == 'distractor' and not entry.get('allowed_with'): errors.append('AV-5: distractor requires allowed_with')
        for key in ('allowed_with','gold_entities'):
            if key not in entry: continue
            entities = entry[key]
            if not isinstance(entities,list) or any(not isinstance(e,str) or not e.strip() for e in entities):
                errors.append('AV-5: invalid entities'); continue
            if docs is not None:
                documents = {s['document'] for s in case.get('gold_sources',[])}
                for entity in entities:
                    if not any(contains(M(page),M(entity)) for d in documents for page in docs.get(d,[])):
                        errors.append('AV-5: entity absent from case documents')
        if kind in ('assertion','distractor') and any(contains(M(text),a) or contains(a,M(text)) for a in gold): errors.append('AV-6: required/forbidden overlap')
        if has_case and kind == 'disclosure' and case.get('category') != 'prompt_injection': errors.append('AV-9: disclosure requires prompt_injection')
    if len(seen)!=len(set(seen)): errors.append('AV-10: duplicate forbidden text')
    seen = []
    for value in ann.get('history_wrong_values',[]):
        if isinstance(value,str): entry={'text':value}
        elif isinstance(value,dict): entry=value
        else: errors.append('AV-7: invalid history value'); continue
        if set(entry)-{'text','turn'} or not isinstance(entry.get('text'),str) or not entry['text'].strip():
            errors.append('AV-7: invalid history value'); continue
        text = entry['text']; seen.append(text)
        if any(contains(M(text),a) or contains(a,M(text)) for a in gold): errors.append('AV-6: history/gold overlap')
        if 'turn' in entry and has_case:
            history=case.get('history',[]); turn=entry['turn']
            if not _index(turn,len(history)) or history[turn].get('role')!='assistant' or not contains(M(history[turn].get('content','')),M(text)):
                errors.append('AV-7: history turn mismatch')
    for index in ann.get('negatable_groups',[]):
        if not _index(index,len(groups)) if has_case else not (type(index) is int and index>=0): errors.append('AV-8: invalid negatable group')
    for pair in ann.get('conflict_groups',[]):
        if (has_case and not case.get('expect_conflict')) or not isinstance(pair,list) or len(pair)!=2 or pair[0]==pair[1] or any(not (_index(x,len(groups)) if has_case else type(x) is int and x>=0) for x in pair): errors.append('AV-8: invalid conflict pair')
    for entry in ann.get('disclosure',[]):
        if has_case and case.get('category')!='prompt_injection': errors.append('AV-9: disclosure requires prompt_injection')
        if not isinstance(entry,dict): errors.append('AV-9: invalid disclosure'); continue
        if set(entry)=={'pattern_set'}:
            if entry['pattern_set']!='generic_leak_v1': errors.append('AV-9: unknown pattern set')
        elif set(entry)=={'pattern','refusal_exempt'} and isinstance(entry['pattern'],str) and isinstance(entry['refusal_exempt'],bool):
            try: re.compile(entry['pattern'])
            except re.error: errors.append('AV-9: invalid disclosure regex')
        else: errors.append('AV-9: invalid disclosure fields')
    if len(seen)!=len(set(seen)): errors.append('AV-10: duplicate text')
    return errors


def parse_annotations(obj):
    errors = validate_annotations(obj)
    if errors: raise ValueError('; '.join(errors))
    return copy.deepcopy(obj)


load_annotations = parse_annotations


def validate_annotations(ann, cases=None, docs=None):
    if cases is None:
        if isinstance(ann,dict) and 'schema' not in ann:
            return entry_errors(ann)
        if not isinstance(ann,dict) or set(ann)!={'schema','dataset_version','dataset_sha256','cases'} or ann.get('schema')!=SCHEMA or not isinstance(ann.get('dataset_version'),str) or not isinstance(ann.get('dataset_sha256'),str) or not isinstance(ann.get('cases'),dict):
            return ['AV-1: invalid annotation schema']
        errors=[]
        for entry in ann['cases'].values():
            errors.extend(entry_errors(entry))
        return errors
    errors = validate_annotations(ann)
    if errors: return errors
    from eval.framework.integrity import dataset_hash
    if ann['dataset_sha256']!=dataset_hash(cases): errors.append('AV-2: dataset hash mismatch')
    byid = {c['id']:c for c in cases}
    if set(ann['cases'])!=set(byid): errors.append('AV-3: incomplete or unknown case ids')
    for cid,entry in ann['cases'].items():
        if cid not in byid: continue
        case=byid[cid]; errors.extend(cid+': '+e for e in entry_errors(entry,case,docs))
        if not isinstance(entry,dict): continue
        entries=entry.get('forbidden',[])
        if not isinstance(entries,list): continue
        dataset = case.get('forbidden',[])
        sources = [e.get('text') for e in entries if isinstance(e,dict) and isinstance(e.get('text'),str) and e.get('source','dataset' if e.get('text') in dataset else 'annotation')=='dataset']
        if sorted(sources)!=sorted(dataset) or any(e.get('text') in dataset for e in entries if isinstance(e,dict) and e.get('source')=='annotation'):
            errors.append(cid+': AV-4: dataset forbidden coverage mismatch')
    return errors


def normalize_entry(ann, case):
    ann = copy.deepcopy({} if ann is None else ann)
    errors=entry_errors(ann,case)
    if errors: raise ValueError('; '.join(errors))
    entries=ann.setdefault('forbidden',[])
    for entry in entries:
        entry.setdefault('source','dataset' if entry['text'] in case.get('forbidden',[]) else 'annotation')
    texts={e['text'] for e in entries}
    # Dataset order is stable; annotation-only entries follow it.
    bytext={e['text']:e for e in entries}
    ann['forbidden']=[bytext.get(text,{'text':text,'kind':'literal','source':'dataset'}) for text in case.get('forbidden',[])] + [e for e in entries if e['text'] not in case.get('forbidden',[])]
    return ann
