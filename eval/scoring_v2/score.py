"""Experimental deterministic v2.1 scorer; never selects acceptance policy."""
import re
from dataclasses import replace
from . import tables as T
from .normalize import M, light, occurrences
from .text_units import split
from .numbers import G, grounded
from .negation import occurrence_family, negated_spans
from .signals import abstention_signals, disagreement_signals
from .history import split_history, history_echo
from .forbidden import evaluate_forbidden
from .annotations import normalize_entry

SCORER_NAME='phase35-scorer'
SCORER_VERSION='2.1.0'


def _validate(case,result,chunk_pair,context_ids,context_text):
    if not isinstance(case,dict) or not isinstance(result,dict): raise ValueError('case and result must be objects')
    if not isinstance(result.get('answer',''),str) and result.get('answer') is not None: raise ValueError('answer must be text or null')
    if result.get('status') is not None and not isinstance(result.get('status'),str): raise ValueError('status must be text or null')
    if context_text is not None and not isinstance(context_text,str): raise ValueError('context must be text or null')
    if not isinstance(chunk_pair,dict) or not isinstance(context_ids,(set,frozenset)): raise ValueError('invalid context mapping')
    if any(type(cid) is not int for cid in context_ids) or any(type(cid) is not int or (pair is not None and (not isinstance(pair,tuple) or len(pair)!=2 or not isinstance(pair[0],str) or type(pair[1]) is not int)) for cid,pair in chunk_pair.items()): raise ValueError('invalid context references')
    if not isinstance(case.get('question',''),str): raise ValueError('question must be text')
    groups=case.get('gold_facts',[])
    if not isinstance(groups,list) or any(not isinstance(g,list) or not g or any(not isinstance(a,str) or not a.strip() for a in g) for g in groups): raise ValueError('invalid gold_facts')
    if not isinstance(case.get('forbidden',[]),list) or any(not isinstance(x,str) or not x.strip() for x in case.get('forbidden',[])): raise ValueError('invalid forbidden')
    sources=case.get('gold_sources',[])
    if not isinstance(sources,list) or any(not isinstance(s,dict) or not isinstance(s.get('document'),str) or type(s.get('page')) is not int for s in sources): raise ValueError('invalid gold sources')
    citations=result.get('citations')
    if citations is None: citations=[]
    if not isinstance(citations,list) or any(not isinstance(c,dict) or type(c.get('chunk_id')) is not int for c in citations): raise ValueError('invalid citations')


def score_case(case, result, chunk_pair, context_ids, context_text, history, annotations):
    _validate(case,result,chunk_pair,context_ids,context_text)
    users,assistant=split_history(history)
    ann=normalize_entry(annotations,case)
    answer=result.get('answer') or ''; status=result.get('status')
    groups=case.get('gold_facts',[]); alts=[a for group in groups for a in group]
    units=split(answer); clauses=[c for s in units for c in s.clauses]
    matched=set(); matched_by_clause={}; neg=[]
    for index,clause in enumerate(clauses):
        c=M(clause.text); found=set()
        neg.extend(dict(span,clause_index=index) for span in negated_spans(clause,alts,alts))
        for group_index,group in enumerate(groups):
            for alternative in group:
                for span in occurrences(c,M(alternative)):
                    if occurrence_family(c,span,alts): continue
                    if group_index in ann.get('negatable_groups',[]) and re.search(T.NEGATABLE,c[:span[0]]): continue
                    found.add(group_index)
        matched_by_clause[index]=found; matched|=found
    recall=len(matched)/len(groups) if groups else 1.0
    wrong=[{'text':x if isinstance(x,str) else x['text'],'kind':'assertion'} for x in ann.get('history_wrong_values',[])]
    hits,excused=evaluate_forbidden(clauses,ann['forbidden'],recall,alts)
    history_hits,history_excused=evaluate_forbidden(clauses,wrong,recall,alts)
    disclosure_hits,disclosure_excused=evaluate_forbidden(clauses,[],recall,alts,ann.get('disclosure',[]))
    hits += ['history:'+x for x in history_hits]+disclosure_hits
    excused += history_excused+disclosure_excused
    allowed=G(context_text or '')+G(case.get('question',''))+users
    tokens=[]; corrected=[]
    for clause in clauses:
        c=M(clause.text); occurrence_counts={}
        for local in G(clause.text):
            tok=replace(local,start=clause.start+local.start,end=clause.start+local.end)
            tokens.append(tok)
            spans=occurrences(c,M(tok.display)) or occurrences(c,M(tok.value))
            occurrence_key=(tok.kind,tok.value,tok.unit)
            occurrence_index=occurrence_counts.get(occurrence_key,0)
            occurrence_counts[occurrence_key]=occurrence_index+1
            spans=spans[occurrence_index:occurrence_index+1]
            if not grounded(tok,allowed) and grounded(tok,assistant) and any(occurrence_family(c,span,alts) in ('P','F','S','C') for span in spans):
                corrected.append(tok)
    echo=history_echo(tokens,allowed,assistant,corrected)
    ungrounded=sorted({t.display for t in tokens if t.kind not in ('ref','code') and t not in corrected and not grounded(t,allowed)}) if context_text is not None else None
    refs=sorted({t.display for t in tokens if t.kind in ('ref','code') and not grounded(t,allowed)}) if context_text is not None else None
    numeric=not ungrounded if context_text is not None else None
    abstention=abstention_signals(answer,alts)
    abstained=status=='abstained' or (status!='error' and bool(abstention))
    partial=None; conflict=None
    if case.get('expect_partial'):
        abstain=None; partial=recall>0 and (status in ('partial','abstained') or bool(abstention)) and numeric is not False
    elif case.get('expect_abstain'):
        abstain=abstained and numeric is not False
    else: abstain=status not in ('abstained','unverified','error')
    gold_pairs={(s['document'],s['page']) for s in case.get('gold_sources',[])}
    cited_ids=[c['chunk_id'] for c in result.get('citations') or []]
    fabricated=sum(1 for cid in cited_ids if cid not in context_ids)
    good=[cid for cid in cited_ids if cid in context_ids and chunk_pair.get(cid) is not None]
    covered={chunk_pair[cid] for cid in good}
    correctness=len(good)/len(cited_ids) if cited_ids else (1.0 if not gold_pairs else 0.0)
    completeness=len(covered)/len(gold_pairs) if gold_pairs else 1.0
    disagreement=disagreement_signals(units,matched_by_clause,ann.get('conflict_groups'))
    if case.get('expect_conflict'): conflict=covered>=gold_pairs and bool(disagreement)
    common=recall==1 and abstain is not False and partial is not False and conflict is not False and not echo
    payload=bool(hits) and len(re.sub(T.REF_PATTERN,'',answer,flags=re.I).strip())<80 and recall<1
    signals={'abstention':abstention,'disagreement':disagreement,'negated_spans':neg,
             'excused':excused,'history_corrections':sorted({t.display for t in corrected}),
             'padded_alternatives':[a for a in alts if a!=a.strip()], 'matched_groups':sorted(matched),
             'status_conflict':status=='conflict','error_row':status=='error','context_unavailable':context_text is None,
             'annotations_applied':bool(annotations)}
    out={'fact_recall':recall,'forbidden_hits':hits,'abstain_ok':abstain,'partial_ok':partial,'conflict_ok':conflict,
         'citation_correctness':correctness,'citation_completeness':completeness,'fabricated':fabricated,
         'ungrounded_numbers':ungrounded,'unsupported':bool(hits) or (bool(case.get('expect_abstain')) and not abstained) or fabricated>0 or bool(ungrounded),
         'correct':common and not hits,'correct_lenient':common and not payload,'status':status,
         'scorer_name':SCORER_NAME,'scorer_version':SCORER_VERSION,'tables_version':T.TABLES_VERSION,
         'numeric_grounded':numeric,'history_echo':echo,'ungrounded_refs':refs,'signals':signals}
    if status=='error':
        out.update(fact_recall=0.0,forbidden_hits=[],abstain_ok=None,partial_ok=None,conflict_ok=None,
                   citation_correctness=0.0,citation_completeness=0.0,fabricated=0,ungrounded_numbers=[],
                   unsupported=False,correct=False,correct_lenient=False,numeric_grounded=None,history_echo=[],ungrounded_refs=[])
    return out


def bind_v1_signature(annotations, *, history_from_case=True):
    if not isinstance(annotations,dict) or not isinstance(annotations.get('cases'),dict): raise ValueError('full annotation set required')
    def bound(case,result,chunk_pair,context_ids,context_text):
        return score_case(case,result,chunk_pair,context_ids,context_text,case.get('history',[]) if history_from_case else [],annotations['cases'][case['id']])
    return bound
