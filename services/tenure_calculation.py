"""v2-verified-employment-months/1: cited, deterministic closed-date arithmetic.

Only a single unambiguous employer/date range in tenant-owned source text may
produce a calculation. Model-written numbers and dates in questions/history are
never evidence. The ordinary numeric-grounding contract is unchanged.
"""
from dataclasses import dataclass
import calendar
import re

POLICY='v2-verified-employment-months/1'
_MONTHS={name.casefold():i for i in range(1,13) for name in (calendar.month_name[i],calendar.month_abbr[i])}
_MONTHS['sept']=9
_MONTH=r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)'
_RANGE=re.compile(rf'\b(?P<sm>{_MONTH})\.?\s+(?P<sy>\d{{4}})\s*(?:[–—-]|to|through|until)\s*(?P<em>{_MONTH})\.?\s+(?P<ey>\d{{4}})\b',re.I)
_SUFFIXES={'software','pvt','private','ltd','limited','inc','llc','corp','corporation','company','co','technologies','technology','solutions','systems','services','group','labs','lab','industries','consulting'}
_GENERIC={'company','co','corporation','corp','pvt','private','ltd','limited','inc','llc','the','a','an'}
_NON_ENTITY={'years','year','months','month','experience','dates','date','resume','document','documents','duration','tenure','those','these','employment','and','from','to','me'}


def duration_intent(question):
    q=question.casefold() if isinstance(question,str) else ''
    return bool(re.search(r'\b(?:experience|employment|tenure|work(?:ed|ing)?|duration)\b',q)
                and re.search(r'\b(?:years?|months?|duration|tenure|long|calculate|count|compute)\b',q))


def employer_hint(question):
    """Extract an employer, without using any alleged dates or duration values."""
    if not isinstance(question,str):return None
    text=question.strip()
    matches=list(re.finditer(r'\b(?:at|in|with|for)\s+([^?!,;\n]+)',text,re.I))
    matches+=list(re.finditer(r'\b(?:calculate|compute|count)\s+(?:the\s+)?(.+?)\s+(?:employment\s+)?(?:duration|tenure)\b',text,re.I))
    for m in reversed(matches):
        tokens=re.findall(r"[\w'-]+",m.group(1).casefold())
        tokens=[t for t in tokens if t not in _GENERIC]
        if (tokens and len(tokens)<=8 and all(not any(c.isdigit() for c in t) for t in tokens)
                and not any(t in _NON_ENTITY for t in tokens)):
            return tokens
    return None


def resolve_employer(question,history):
    if not duration_intent(question):return None
    hint=employer_hint(question)
    if hint:return hint
    # History resolves a referent only, never supplies arithmetic evidence.
    if not re.search(r'\b(?:those|these|that|same|there|above)\b',question,re.I):return None
    for message in reversed((history or [])[-6:]):
        if message.get('role')=='user':
            hint=employer_hint(message.get('content',''))
            if hint:return hint
    return None


@dataclass(frozen=True)
class Period:
    chunk_id:int
    document:str
    page:int
    content:str
    employer:str
    start:tuple[int,int]
    end:tuple[int,int]


def periods_in_rows(rows,tokens):
    name=re.compile(r'\b'+r'\s+'.join(re.escape(t) for t in tokens)+r'\b',re.I)
    periods=[]
    for cid,document,page,content in rows:
        for entity in name.finditer(content):
            tail=content[entity.end():entity.end()+100]
            date_range=_RANGE.search(tail)
            if not date_range:continue
            bridge=tail[:date_range.start()]
            words=re.findall(r'\w+',bridge.casefold())
            # Only an adjacent company-header suffix may connect name to dates.
            # Never borrow dates from a later employer, role or project paragraph.
            if any(w not in _SUFFIXES for w in words) or re.search(r'[;!?\n]{2}|\d',bridge):continue
            start=(int(date_range['sy']),_MONTHS[date_range['sm'].casefold()])
            end=(int(date_range['ey']),_MONTHS[date_range['em'].casefold()])
            if not 1900<=start[0]<=end[0]<=2199 or end<start:continue
            employer=re.sub(r'\s+',' ',content[entity.start():entity.end()]+bridge).strip(' .:–—-')
            periods.append(Period(cid,str(document),int(page),content,employer,start,end))
    return periods


def _source(period,ref):
    return {'ref':ref,'chunk_id':period.chunk_id,'document_name':period.document,'page_number':period.page,'content':period.content,'retrieval_score':None}


def result_from_rows(rows,tokens):
    from services.citation_service import answer_with_citations,validate_answer_citations
    periods=periods_in_rows(rows,tokens)
    unique={}
    for p in periods:unique.setdefault((p.document,p.employer.casefold(),p.start,p.end),p)
    if not unique:return None
    if len(unique)>1:
        return {'answer':'I found multiple matching employment records. Please specify the person, document or employment period before I calculate the duration.',
                'status':'abstained','sources':[],'citations':[],'issues':['ambiguous_employment_period'],'retrieval_status':'source_lookup','retrieved':[],'routing_policy':POLICY}
    p=next(iter(unique.values()))
    # Reverify the exact range against the original cited content before rendering.
    assert p in periods_in_rows([(p.chunk_id,p.document,p.page,p.content)],tokens)
    months=(p.end[0]-p.start[0])*12+p.end[1]-p.start[1]
    years,remainder=divmod(months,12)
    start=f'{calendar.month_name[p.start[1]]} {p.start[0]}'
    end=f'{calendar.month_name[p.end[1]]} {p.end[0]}'
    parts=[]
    if years:parts.append(f'{years} '+('year' if years==1 else 'years'))
    if remainder:parts.append(f'{remainder} '+('month' if remainder==1 else 'months'))
    duration=' '.join(parts) or '0 months'
    # Avoid treating a company abbreviation as a separate uncited sentence.
    employer=p.employer.replace('.','')
    answer=(f'The resume lists employment at {employer} from {start} to {end} [S1]. '
            f'Calculated from those month/year dates, this is approximately {duration} ({months} months); exact days are not specified [S1].')
    sources=[_source(p,'S1')]
    validation=validate_answer_citations(answer,sources,require_citations=True)
    if not validation['valid']:raise ValueError('calculation citation validation failed')
    checked=answer_with_citations(answer,sources)
    proof={'policy':POLICY,'method':'(end_year-start_year)*12 + end_month-start_month',
           'start':f'{p.start[0]:04d}-{p.start[1]:02d}','end':f'{p.end[0]:04d}-{p.end[1]:02d}',
           'total_months':months,'years':years,'remaining_months':remainder,'precision':'month; approximate elapsed duration',
           'source_ref':'S1','source_chunk_id':p.chunk_id,'source_document':p.document,'source_page':p.page}
    return {'answer':checked['text'],'status':'answered','citations':checked['citations'],
            'sources':[{'document':p.document,'page':p.page,'chunk_id':p.chunk_id,'ref':'S1'}],
            'issues':[],'retrieval_status':'source_lookup','retrieved':[{'ref':'S1','chunk_id':p.chunk_id,'document_name':p.document,'page_number':p.page,'retrieval_score':None}],
            'routing_policy':POLICY,'calculation':proof,'validation':validation,'attempts':0}


def answer_employment_duration(question,history=None):
    tokens=resolve_employer(question,history)
    if tokens is None:return None
    from services.tenant_context import current_owner
    owner=current_owner()
    if owner is None:raise PermissionError('authenticated tenant required')
    from services.database import get_connection
    with get_connection() as conn:
        rows=conn.execute('''SELECT dc.id,dc.document_name,dc.page_number,dc.content
            FROM document_chunks dc JOIN documents d ON d.id=dc.document_id AND d.owner_id=dc.owner_id
            WHERE dc.owner_id=%s AND d.status='ready' AND strpos(lower(dc.content),%s)>0
            ORDER BY dc.document_name,dc.page_number,dc.chunk_id LIMIT 101''',(owner,tokens[0])).fetchall()
    if len(rows)>100:return None
    return result_from_rows(rows,tokens)
