"""Typed numeric guard, independent of matching rewrites (§5)."""
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import re
from . import tables as T
from .normalize import light, canon_decimal, time_value


@dataclass(frozen=True)
class NumTok:
    kind: str
    value: str
    unit: str = ''
    start: int = 0
    end: int = 0

    @property
    def display(self):
        if self.kind == 'currency': return self.unit+' '+self.value
        if self.kind == 'percent': return self.value+'%'
        if self.kind == 'measure': return self.value+' '+self.unit
        return self.value


_PATTERNS = [
 ('time', re.compile(T.TIME12)), ('time', re.compile(T.TIME24)),
 ('ref', re.compile(r'\b(?:'+T.REFWORDS+r')\s?(?P<v>\d+(?:\.\d+)*)(?!\d)')),
 ('ref', re.compile(r'(?<![\w.])(?P<v>[a-z]{0,3}\.?\d+(?:\.\d+){2,})(?!\d)')),
 ('code', re.compile(r'(?<!\w)(?P<p>[a-z]{1,10})-?(?P<v>\d[\da-z]*(?:-[\da-z]+)*)(?!\w)')),
 ('count', re.compile(r'(?P<sign>(?:^|(?<=[\s(]))[−-](?=\d)|−(?=\d))?(?P<int>\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?P<frac>\.\d+)?(?P<ord>st|nd|rd|th)?(?!\d)')),
]
_UNIT = re.compile(r'(?:\s?|-)(?P<u>'+'|'.join(re.escape(x) for x in sorted(T.UNIT_LOOKUP, key=len, reverse=True))+r')\b')


def _kind(text, tok):
    before, after = text[:tok.start], text[tok.end:]
    for iso, aliases in T.CURRENCY.items():
        prefix = [a for a in aliases if a in ('us$','$','usd','£','gbp','€','eur')]
        suffix = [a for a in aliases if a not in ('us$','$','£','€')]
        if any(re.search(r'(?<!\w)'+re.escape(a)+r'\s?$', before) for a in prefix) or any(re.match(r'\s?'+re.escape(a)+r'\b', after) for a in suffix):
            return replace(tok, kind='currency', unit=iso, value=canon_decimal(tok.value))
    if re.match(r'\s?(?:%|percent\b|per cent\b)', after):
        return replace(tok, kind='percent', unit='%', value=canon_decimal(tok.value))
    m = _UNIT.match(after)
    if m:
        return replace(tok, kind='measure', unit=T.UNIT_LOOKUP[m['u']], value=canon_decimal(tok.value))
    return tok


def G(text):
    text = light(text)
    tokens = []; i = 0
    while i < len(text):
        found = False
        for kind, pattern in _PATTERNS:
            m = pattern.match(text, i)
            if not m: continue
            if kind == 'code' and (m['p'] in T.UNIT_LOOKUP or m['p'] in ('usd','gbp','eur','us','am','pm','st','nd','rd','th') or re.fullmatch(T.REFWORDS, m['p'])):
                continue
            value = time_value(m) if kind == 'time' else m['v'] if kind in ('ref','code') else (m['sign'] or '').replace('−','-')+m['int'].replace(',','')+(m['frac'] or '')
            tok = NumTok(kind, value, '', m.start(), m.end())
            tokens.append(_kind(text,tok) if kind == 'count' else tok)
            i = m.end(); found = True; break
        if not found: i += 1
    # Propagate only through bare coordination/range separators; up to 4 items.
    for end in range(len(tokens)):
        for start in range(max(0,end-3),end):
            group = tokens[start:end+1]
            if any(t.kind not in ('count','measure','currency','percent') for t in group): continue
            if any(not re.fullmatch(r'\s*(?:-|to|and|or|,|,?\s*(?:and|or))\s*', text[a.end:b.start]) for a,b in zip(group,group[1:])): continue
            typed = group[-1] if group[-1].kind != 'count' else group[0]
            if typed.kind == 'count': continue
            for k in range(start,end+1):
                if tokens[k].kind == 'count':
                    tokens[k] = replace(tokens[k],kind=typed.kind,unit=typed.unit,value=canon_decimal(tokens[k].value))
    return tokens


def grounded(tok, allowed):
    for other in allowed:
        if tok.kind in ('ref','code'):
            if tok.value == other.value: return True
        elif tok.kind == 'count' and other.kind != 'time':
            try:
                if tok.value.startswith('-') != other.value.startswith('-'): continue
                if Decimal(tok.value) == Decimal(other.value): return True
            except InvalidOperation:
                if tok.value == other.value: return True
        elif tok.kind == other.kind and tok.value == other.value and tok.unit == other.unit:
            return True
    return False
