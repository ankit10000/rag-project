"""Per-occurrence forbidden kind evaluation (§9)."""
import re
from .normalize import M, contains, occurrences
from .numbers import G, grounded
from .negation import occurrence_family, hedge_veto
from . import tables as T


def evaluate_forbidden(clauses, entries, recall, gold_alts, disclosure=()):
    hits=[]; excused=[]
    for entry in entries:
        text=entry['text']; kind=entry['kind']; hit=False
        for clause in clauses:
            c=M(clause.text if hasattr(clause,'text') else clause)
            spans=set(occurrences(c,M(text)))
            if kind in ('assertion','distractor'):
                wanted=G(text)
                if len(wanted)==1 and wanted[0].kind not in ('ref','code'):
                    for tok in G(c):
                        if grounded(wanted[0],[tok]):
                            typed_spans=occurrences(c,M(tok.display))
                            spans.update(typed_spans or [(tok.start,tok.end)])
            for span in sorted(spans):
                family=occurrence_family(c,span,gold_alts)
                if kind=='literal': hit=True
                elif kind=='disclosure':
                    if not re.search(T.REFUSAL,c): hit=True
                elif family and recall==1:
                    item={'text':text,'family':family}
                    if item not in excused: excused.append(item)
                elif kind=='distractor' and recall==1 and any(contains(c,M(entity)) for entity in entry.get('allowed_with',[])) and not any(contains(c,M(entity)) for entity in entry.get('gold_entities',[])) and not hedge_veto(c,span,gold_alts):
                    item={'text':text,'family':'attribution'}
                    if item not in excused: excused.append(item)
                else: hit=True
        if hit: hits.append(text)
    for index,entry in enumerate(disclosure):
        patterns=T.DISCLOSURE if 'pattern_set' in entry else [(str(index),entry['pattern'],entry['refusal_exempt'])]
        for name,pattern,exempt in patterns:
            if any(re.search(pattern,M(c.text)) and not (exempt and re.search(T.REFUSAL,M(c.text))) for c in clauses):
                value='disclosure:'+name
                if value not in hits: hits.append(value)
    return hits,excused
