"""Protected sentence and clause splitter (§6), with source offsets."""
from dataclasses import dataclass, field
import re
from .normalize import light


@dataclass
class Clause:
    text: str
    start: int
    end: int
    paren: bool = False


@dataclass
class Sentence:
    text: str
    start: int
    end: int
    clauses: list = field(default_factory=list)
    list_intro: bool = False
    bullet: bool = False


def _protected(text):
    mask = set()
    patterns = [r'https?://[^\s<>\"]+[^\s<>\".,;:)\]]', r'www\.[^\s<>\"]+[^\s<>\".,;:)\]]',
                r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', r'\d[.,:]\d',
                r'\b[a-z]{0,3}\.?\d+(?:\.\d+)+\b',
                r'\b(?:vs|v|no|nos|s|ss|cl|para|paras|p|pp|fig|figs|approx|incl|e\.g|i\.e|etc|cf|mr|mrs|ms|dr|st|art|sec|ch|dept|est|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.',
                r'\b\d{1,2}\s?[ap]\.m\.']
    for pattern in patterns:
        for m in re.finditer(pattern,text,re.I):
            if m.group().lower() == 'etc.' and re.match(r'\s+[A-Z]',text[m.end():]): continue
            mask.update(range(m.start(),m.end()))
    return mask


def _clauses(text, offset):
    mask = _protected(text); parens = list(re.finditer(r'\([^()]*\)', text))
    result = [Clause(m.group()[1:-1].strip(),offset+m.start()+1,offset+m.end()-1,True) for m in parens if m.group()[1:-1].strip()]
    outer = list(text)
    for m in parens:
        outer[m.start():m.end()] = ' '*(m.end()-m.start())
    outer = ''.join(outer); start = 0
    for m in re.finditer(r'[;:]|\s-\s',outer):
        if m.start() in mask: continue
        if m.group().strip() == '-' and re.search(r'\d\s*$',outer[:m.start()]) and re.match(r'\s*\d',outer[m.end():]): continue
        part = outer[start:m.start()]
        if part.strip(): result.append(Clause(re.sub(r'\s+',' ',part).strip().rstrip('.!?'),offset+start,offset+m.start()))
        start = m.end()
    if outer[start:].strip(): result.append(Clause(re.sub(r'\s+',' ',outer[start:]).strip().rstrip('.!?'),offset+start,offset+len(text)))
    return sorted(result,key=lambda c:c.start)


def split(text):
    text = light(text,casefold=False)
    result = []; offset = 0; prior_blank = False
    for line in text.splitlines(keepends=True):
        if not line.strip():
            if result: result[-1]._blank_after = True
            offset += len(line); continue
        marker = re.match(r'^\s*(?:[-*•·]|\d{1,2}[.)])\s+',line)
        start = marker.end() if marker else 0
        mask = _protected(line)
        boundaries = [m.end() for m in re.finditer(r'[.!?]+["\')\]]*(?=\s|$)',line) if not any(i in mask for i in range(m.start(),m.end()))]+[len(line)]
        for end in boundaries:
            if end <= start: continue
            piece = line[start:end]
            if piece.strip():
                lead = len(piece)-len(piece.lstrip()); clean = piece.strip()
                result.append(Sentence(clean,offset+start+lead,offset+end,_clauses(clean,offset+start+lead),False,bool(marker)))
            start = end
        offset += len(line)
    for i,s in enumerate(result[:-1]):
        s.list_intro = s.text.rstrip().endswith(':') and result[i+1].bullet and not getattr(s,'_blank_after',False)
    return result
