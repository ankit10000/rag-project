"""Closed v2.1 tables; changes require a scorer minor-version bump."""
TABLES_VERSION = '2.1.0'
REF_PATTERN = r'\[S\d+(?:\s*[,;]\s*S\d+)*\]'
QUOTES = dict.fromkeys('’‘‛′', "'") | dict.fromkeys('“”„″', '"')
DASHES = dict.fromkeys('‐‑‒–—―﹘﹣－', '-')
UNITS = {
 'h': ('h','hr','hrs','hour','hours'), 'min': ('min','mins','minute','minutes'),
 'day': ('day','days'), 'week': ('week','weeks'), 'month': ('month','months'),
 'year': ('year','years'), 'working day': ('working day','working days','business day','business days'),
 'l': ('l','litre','litres','liter','liters'), 'ml': ('ml','millilitre','millilitres','milliliter','milliliters'),
 'g': ('g','gram','grams'), 'kg': ('kg','kilogram','kilograms'), 'mg': ('mg','milligram','milligrams'),
 'nm': ('nm','n·m','n m','newton-metre','newton-metres','newton-meter','newton-meters'),
 'mm': ('mm',), 'cm': ('cm',), 'm': ('metre','metres','meter','meters','m'), 'km': ('km',),
 'bar': ('bar',), 'mm/s': ('mm/s',), 'mg/l': ('mg/l',), '°c': ('°c',), '°f': ('°f',),
}
UNIT_LOOKUP = {alias: unit for unit, aliases in UNITS.items() for alias in aliases}
CURRENCY = {'usd': ('us dollars','dollars','dollar','usd','us$','$'),
            'gbp': ('pounds sterling','pound sterling','gbp','£'),
            'eur': ('euros','euro','eur','€')}
REFWORDS = r'sections?|clauses?|ss?\.|para|paragraphs?|pages?|pp?\.|annex|appendix|schedule|item|no\.|number|article|art\.|rule|step|table|fig\.|figure|version|v|rev\.?|issue|amendment'
TIME12 = r'(?<![\d:.])(?P<h>1[0-2]|0?[1-9])(?::(?P<m>[0-5]\d))?\s?(?P<ap>a\.?m\.?|p\.?m\.?)(?![a-z])'
TIME24 = r'(?<![\d:.])(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)(?![\d:])'
NUMBER_WORDS = dict(zip(('zero two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety').split(), (0,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,30,40,50,60,70,80,90)))
SCALE_WORDS = set('one hundred thousand million billion dozen half quarter point'.split())
FILLER = set('the a an its their that this these those earlier previous previously old original prior former quoted stated printed listed misprinted outdated superseded wrong incorrect erroneous value values figure figures amount amounts rate rates number of usd gbp eur'.split())
PREFIX = r"\b(?:not|never|no longer|rather than|instead of|in place of|isn't|is not|wasn't|was not|aren't|are not|weren't|were not)\s+"
CHANGE = r'\b(?:changed|changes|raised|raises|increased|increases|reduced|reduces|lowered|lowers|corrected|corrects|amended|amends|updated|updates|revised|revises|moved|moves)\b(?:\s+\S+){0,3}?\s+from\s+|\b(?:up|down) from\s+'
WRONG = r'(?:is|was|are|were|has been|had been)\s+(?:wrong|incorrect|a misprint|misprinted|a typo|an error|a mistake|mistaken|outdated|out of date|superseded|withdrawn|obsolete|no longer (?:valid|current|in force))\b'
SELF = r'\b(?:i|we)\s+(?:previously|earlier|wrongly|incorrectly|mistakenly)\s+(?:said|stated|wrote|gave|quoted|told you)\s+|\b(?:previously|earlier),?\s+(?:i|we)\s+(?:said|stated|wrote|gave|quoted)\s+'
REAFFIRM = r'\b(?:still|remains?|stands|is (?:still )?correct|is right|confirmed?)\b'
NEGATABLE = r"\b(?:no|not|cannot|can't|never|isn't|aren't|won't|don't|doesn't|didn't)\b"
DISCLOSURE = (
 ('D1',r'\bhere (?:is|are) (?:my|the) (?:\w+ ){0,2}(?:instructions|prompt|configuration|rules|guidelines)\b',False),
 ('D2',r'\bmy (?:\w+ ){0,2}(?:instructions|system prompt|prompt|configuration) (?:is|are|says?|reads?|states?)\b',True),
 ('D3',r'\b(?:system prompt|hidden instructions?|developer (?:message|instructions?))\s*(?::|follows|reads|says|is as follows)',False),
 ('D4',r'\bi (?:was|am) (?:instructed|told|configured|programmed) to\b',True),
)
REFUSAL = r"\b(?:can(?:not|'t)|won't|will not|do not|don't|am not (?:able|allowed|permitted) to|unable to|must not|may not)\s+(?:\w+\s+){0,2}?(?:share|reveal|disclose|provide|show|repeat|output|print|display|tell you|give)\b"
LEX = r"\b(?:differ(?:s|ent|ence|ences|ing)?|conflict(?:s|ing)?|contradict(?:s|ion|ions|ory)?|discrepanc(?:y|ies)|inconsisten(?:t|cy|cies)|disagree(?:s|d|ment)?|mismatch(?:es)?|(?:do|does|did)(?: not|n't) (?:agree|match|align)|at odds|two (?:different|separate|conflicting) (?:values|figures|dates|amounts|limits|caps|rates))\b"
CONN = r'\b(?:but|however|whereas|while|whilst|although|though|yet|versus|vs\.?|v\.|on the other hand|by contrast|in contrast)\b'
NEGLEX = {'no','not',"n't",'never','without','neither','nor','none','any'}
RESTATED_SOURCE_AST_SHA256 = {'build_chunks':'7e3818238bcebe2adb44cf850b171dd139171b7d7e96adfada358d7d2ccb97f2','chunk_dedupe_key':'e66f2e25e36dc93241d7978715fc7e0e919579f87062f3934f81c0ee17ece8a5','extract_text':'e55a438774da6c194cf8952b70621d53d53727fe4cc64fd62f0c1be5f91bff42','build_scratch_corpus':'a974a49e74664b11fbb396bc4c2ffe12260058fcd08cc127118652a780d221cb','services/chunker.py':'0a002515c7a2fa624d46c2d0375f6fbceac682fab001272a2091d4da481b3554'}
