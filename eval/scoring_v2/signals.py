"""Finite abstention and disagreement signals (§10–11)."""
import re
from .normalize import M, contains
from .text_units import split
from . import tables as T

DOC_SUBJ = r'(?:the |these |this |those )?(?:provided |retrieved |available |supplied |attached )?(?:documents?|sources?|context|texts?|excerpts?|passages?|materials?|records?|information (?:provided|available|given)|provided information)'
INSTR_SUBJ = r'(?:the |this |that )?(?:policy|policies|report|manual|guide|agreement|contract|handbook|call|sop|price list|bylaw|study|schedule|notice|memo|card|leaflet|brochure|warranty|terms)'
NEG = r"(?:(?:do|does|did)(?: not|n't)|(?:is|are|was|were)(?: not|n't))"
EPI = r'say|state|specify|mention|list|record|indicate|detail|explain|discuss|describe|set out|refer to|address|give|provide'
ANCHOR = r'\b(?:in|by|from|within)\s+(?:the\s+)?(?:'+DOC_SUBJ+'|'+INSTR_SUBJ+r')\b'
PAST = r'recorded|stated|specified|mentioned|listed|documented|published|disclosed|reported|indicated|set out'
_BSTART = r"\b(?:(?:is|are|was|were|has|have)\s+(?:not|n't)(?:\s+been)?|isn't|aren't|wasn't|weren't)\s+"
_PATTERNS = [
 ('A1',r'\b'+DOC_SUBJ+r'\b(?:\s+\S+){0,6}?\s+'+NEG+r'\s+(?:\S+\s+)?(?:'+EPI+r'|include|cover|contain|show)\b'),
 ('A2',r'\b'+INSTR_SUBJ+r'\b(?:\s+\S+){0,6}?\s+'+NEG+r'\s+(?:\S+\s+)?(?:'+EPI+r')\b'),
 ('A3',r'\b(?:'+DOC_SUBJ+'|'+INSTR_SUBJ+r')\b(?:\s+\S+){0,6}?\s+(?:(?:is|are) silent|makes? no (?:mention|reference))\b'),
 ('B',_BSTART+'(?:'+PAST+r')\b'),
 ('B_anchor',_BSTART+r'(?:included|covered|provided|available|given)\b'),
 ('C',r"\b(?:could not|couldn't|cannot|can't|can not|unable to|(?:am|is|are|was|were) not able to|(?:isn't|aren't|wasn't|weren't) able to)\s+(?:find|locate|determine|confirm|answer|see|identify|tell|verify)\b"),
 ('D',r"\bno (?:information|mention|details?|records?|data|figures?|reference|indication)\b|\b(?:not enough|insufficient) information\b|\b(?:the|that|this|such) (?:information|details?|data|figures?) (?:is|are) (?:not|n't) (?:available|provided|given|included)\b"),
]
_STRONG = ("couldn't find",'could not find',"can't find",'cannot find','not enough information','insufficient information','no information','cannot answer',"can't answer",'unable to answer','no mention')


def clause_abstention(text):
    text = M(text); out = []
    for family,pattern in _PATTERNS:
        if family == 'B_anchor' and not re.search(ANCHOR,text): continue
        for match in re.finditer(pattern,text):
            out.append({'family': 'B' if family == 'B_anchor' else family,'span':[match.start(),match.end()]})
    from eval.answer_scoring import INSUFFICIENCY_PHRASES
    for phrase in INSUFFICIENCY_PHRASES:
        if phrase in text and (out or phrase in _STRONG):
            start = text.find(phrase)
            out.append({'family':'E','span':[start,start+len(phrase)]})
    return out


def abstention_signals(answer, gold_alts):
    out = []; index = 0
    for sentence in split(answer):
        for clause in sentence.clauses:
            text = M(clause.text)
            if not any(contains(text,M(a)) for a in gold_alts):
                out.extend(dict(signal,clause_index=index) for signal in clause_abstention(text))
            index += 1
    return out


def disagreement_signals(units, matched_by_clause, conflict_groups=None):
    out = []; clause_offset = 0; indices = []
    for sentence in units:
        indices.append(set().union(*(matched_by_clause.get(clause_offset+i,set()) for i in range(len(sentence.clauses)))))
        clause_offset += len(sentence.clauses)
    for index,sentence in enumerate(units):
        scope = [sentence]; groups = set(indices[index]); j = index+1
        if sentence.list_intro:
            while j < len(units) and units[j].bullet:
                scope.append(units[j]); groups |= indices[j]
                if getattr(units[j],'_blank_after',False): break
                j += 1
        if len(groups)<2 or (conflict_groups and not any(set(pair)<=groups for pair in conflict_groups)): continue
        text = M(' '.join(s.text for s in scope)); lex = []
        for m in re.finditer(T.LEX,text):
            before = re.findall(r"\w+(?:'\w+)?|n't",text[:m.start()])[-3:]
            if not any(w in T.NEGLEX or w.endswith("n't") for w in before): lex.append(m.group())
        if lex or (len(scope)==1 and re.search(T.CONN,text)):
            out.append({'sentence_index':index,'groups':sorted(groups),'lexicon':lex,'list_scope':len(scope)>1})
    return out
