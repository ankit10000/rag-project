"""Scoped correction spans and polarity (§7)."""
import re
from . import tables as T
from .normalize import M, occurrences
from .signals import clause_abstention


def hedge_veto(text, span, gold_alts):
    a,b = span
    for gold in gold_alts:
        for c,d in occurrences(text,M(gold)):
            if (a,b)==(c,d): continue
            left,right = (b,c) if b<=c else (d,a) if d<=a else (0,0)
            middle = text[left:right]
            if re.search(r'\bor\b|\beither\b|\band/or\b|/',middle) or re.fullmatch(r'\s*-\s*',middle) or (re.search(r'\bbetween\b',text[:min(a,c)]) and re.search(r'\band\b',middle)):
                return True
    return False


def occurrence_family(text, span, gold_alts=(), *, hedge=True):
    a,b = span
    if hedge and hedge_veto(text,span,gold_alts): return None
    before, after = text[:a],text[b:]
    for family,pattern in [('P',T.PREFIX),('F',T.CHANGE),('C',T.SELF)]:
        if family == 'C' and re.search(T.REAFFIRM,text): continue
        for match in re.finditer(pattern,before):
            gap = before[match.end():].split()
            if len(gap)<=4 and all(x in T.FILLER for x in gap): return family
    for m in re.finditer(T.WRONG,after):
        gap = after[:m.start()].split()
        if len(gap)<=3 and all(x in T.FILLER | set('i you we gave said quoted mentioned before cap limit'.split()) for x in gap): return 'S'
    for signal in clause_abstention(text):
        if signal['family'].startswith('A') or signal['family'] in ('B','C'):
            if a>=signal['span'][1]: return 'E'
    return None


def negated_spans(clause, values, gold_alts=()):
    text = M(clause.text if hasattr(clause,'text') else clause)
    out = []
    for value in values:
        for span in occurrences(text,M(value)):
            family = occurrence_family(text,span,gold_alts)
            if family: out.append({'text':value,'family':family,'span':list(span)})
    return out
