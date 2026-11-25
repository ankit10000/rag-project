"""v2-verified-employment-months/3: cited, deterministic date arithmetic.

Only a single unambiguous employer/date range in tenant-owned source text may
produce a calculation. Model-written numbers and dates in questions/history are
never evidence. The ordinary numeric-grounding contract is unchanged.
"""
from dataclasses import dataclass
import calendar
from datetime import date,datetime,timezone
import re

POLICY='v2-verified-employment-months/3'
_MONTHS={name.casefold():i for i in range(1,13) for name in (calendar.month_name[i],calendar.month_abbr[i])}
_MONTHS['sept']=9
_MONTH=r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)'
_RANGE=re.compile(rf'\b(?P<sm>{_MONTH})\.?\s+(?P<sy>\d{{4}})\s*(?:[–—-]|to|through|until)\s*(?P<em>{_MONTH})\.?\s+(?P<ey>\d{{4}})\b',re.I)
_CURRENT_RANGE=re.compile(rf'\b(?P<sm>{_MONTH})\.?\s+(?P<sy>\d{{4}})\s*(?:[–—-]|to|through|until)\s*(?:Present|Current)\b',re.I)
_SUFFIXES={'software','pvt','private','ltd','limited','inc','llc','corp','corporation','company','co','technologies','technology','solutions','systems','services','group','labs','lab','industries','consulting'}
_GENERIC={'company','co','corporation','corp','pvt','private','ltd','limited','inc','llc','the','a','an'}
_NON_ENTITY={'years','year','months','month','days','day','experience','dates','date','resume','document','documents','duration','tenure','those','these','employment','and','from','to','me','exact','there'}


def _as_of_date():
    """Application clock only; neither questions nor model replies set 'Present'."""
    return datetime.now(timezone.utc).date()


def _bare_duration_followup(question):
    text=' '.join(question.strip(' .?!').split())
    return bool(re.fullmatch(r'(?:(?:can|could|would) you\s+)?(?:please\s+)?'
                             r'(?:calculate|compute|count)\s+(?:the\s+)?(?:exact\s+)?'
                             r'(?:years?(?:\s+and\s+months?)?|months?(?:\s+and\s+years?)?)',text,re.I))


def joining_intent(question):
    return isinstance(question,str) and bool(
        re.search(r'\b(?:when|joining date|start date|what date)\b',question,re.I)
        and re.search(r'\b(?:join(?:ed)?|start(?:ed)?|hired)\b',question,re.I))


def duration_intent(question):
    q=question.casefold() if isinstance(question,str) else ''
    return bool(_bare_duration_followup(q) or (
                re.search(r'\b(?:experience|employment|tenure|work(?:ed|ing)?|duration|spent|spend(?:ed|ing)?)\b',q)
                and re.search(r'\b(?:years?|months?|duration|tenure|long|calculate|count|compute)\b|\bhow much\b',q)))


def has_additional_requests(question):
    """Keep compound requests on normal retrieval instead of returning only tenure."""
    return bool(re.search(r'\b(?:degree|education|academic|institution|university|college|'
                          r'qualifications?|skills?|projects?|milestones?|budget|salary|'
                          r'phone|telephone|fax|email|position|job title)\b', question, re.I))


def employer_hint(question):
    """Extract an employer, without using any alleged dates or duration values."""
    if not isinstance(question,str):return None
    text=question.strip()
    matches=list(re.finditer(r'\b(?:at|in|with|for)\s+([^?!,;\n]+)',text,re.I))
    matches+=list(re.finditer(r'\bjoin(?:ed)?\s+(?:the\s+)?([^?!,;\n]+)',text,re.I))
    matches+=list(re.finditer(r'\b(?:calculate|compute|count)\s+(?:the\s+)?(.+?)\s+(?:employment\s+)?(?:duration|tenure)\b',text,re.I))
    for m in reversed(matches):
        tokens=re.findall(r"[\w'-]+",m.group(1).casefold())
        tokens=[t for t in tokens if t not in _GENERIC]
        if (tokens and len(tokens)<=8 and all(not any(c.isdigit() for c in t) for t in tokens)
                and not any(t in _NON_ENTITY for t in tokens)):
            return tokens
    return None


def _one_edit_apart(left,right):
    if left==right or abs(len(left)-len(right))>1:return False
    if len(left)==len(right):return sum(a!=b for a,b in zip(left,right))==1
    shorter,longer=sorted((left,right),key=len)
    return any(longer[:i]+longer[i+1:]==shorter for i in range(len(longer)))


def _literal_employer(question,history):
    hint=employer_hint(question)
    if hint:return hint
    for message in reversed((history or [])[-6:]):
        if message.get('role')=='user':
            hint=employer_hint(message.get('content',''))
            if hint:return hint
    return None


def resolve_employer(question,history):
    if not (duration_intent(question) or joining_intent(question)):return None
    hint=employer_hint(question)
    recent=[]
    for message in reversed((history or [])[-6:]):
        if message.get('role')=='user':
            candidate=employer_hint(message.get('content',''))
            if candidate and candidate not in recent:recent.append(candidate)
    if hint:
        # A pronoun follow-up may contain a single-character acronym typo.
        # Require the remaining employer words and one unique recent USER hint;
        # the corrected full employer must still match actual owned source text.
        if len(hint)>1 and len(hint[0])>=2 and re.search(r'\b(?:he|she|they|his|her|their)\b',question,re.I):
            matches=[candidate for candidate in recent if len(candidate)==len(hint)
                     and candidate[1:]==hint[1:] and _one_edit_apart(candidate[0],hint[0])]
            if len(matches)>1:return hint
            if matches:return matches[0]
        return hint
    # History resolves a referent only, never supplies arithmetic evidence.
    if not (_bare_duration_followup(question) or re.search(r'\b(?:those|these|that|same|there|above)\b',question,re.I)):return None
    if not recent:return None
    focus=recent[0]
    previous=next((m.get('content','') for m in reversed((history or [])[-6:])
                   if m.get('role')=='user' and employer_hint(m.get('content',''))==focus),'')
    if len(focus)>1 and len(focus[0])>=2 and re.search(r'\b(?:he|she|they|his|her|their)\b',previous,re.I):
        matches=[candidate for candidate in recent[1:] if len(candidate)==len(focus)
                 and candidate[1:]==focus[1:] and _one_edit_apart(candidate[0],focus[0])]
        if len(matches)==1:return matches[0]
    return focus


@dataclass(frozen=True)
class Period:
    chunk_id:int
    document:str
    page:int
    content:str
    employer:str
    start:tuple[int,int]
    end:tuple[int,int]
    date_span:tuple[int,int]
    is_current:bool=False


def periods_in_rows(rows,tokens,as_of=None):
    name=re.compile(r'\b'+r'\s+'.join(re.escape(t) for t in tokens)+r'\b',re.I)
    periods=[]
    for cid,document,page,content in rows:
        for entity in name.finditer(content):
            tail=content[entity.end():entity.end()+100]
            date_range=_RANGE.search(tail)
            is_current=False
            if date_range is None and as_of is not None:
                date_range=_CURRENT_RANGE.search(tail)
                is_current=date_range is not None
            if not date_range:continue
            bridge=tail[:date_range.start()]
            header_bridge=bridge
            labeled=re.fullmatch(r'(?P<header>.*?)\bEmployment(?:\s+(?:dates|period))?\s*:\s*',bridge,re.I|re.S)
            if labeled:
                # A directly adjacent, explicit field is still this employer's
                # period. Do not cross blank sections, employees or other fields.
                if re.search(r'\n\s*\n|[;!?]',bridge):continue
                header_bridge=labeled['header']
            words=re.findall(r'\w+',header_bridge.casefold())
            # Only an adjacent company-header suffix may connect name to dates.
            # Never borrow dates from a later employer, role or project paragraph.
            if any(w not in _SUFFIXES for w in words) or re.search(r'[;!?\n]{2}|\d',bridge):continue
            start=(int(date_range['sy']),_MONTHS[date_range['sm'].casefold()])
            end=(as_of.year,as_of.month) if is_current else (int(date_range['ey']),_MONTHS[date_range['em'].casefold()])
            if not 1900<=start[0]<=end[0]<=2199 or end<start:continue
            employer=re.sub(r'\s+',' ',content[entity.start():entity.end()]+header_bridge).strip(' .:–—-|·')
            date_span=(entity.end()+date_range.start(),entity.end()+date_range.end())
            periods.append(Period(cid,str(document),int(page),content,employer,start,end,date_span,is_current))
    return periods


def _source(period,ref):
    return {'ref':ref,'chunk_id':period.chunk_id,'document_name':period.document,'page_number':period.page,'content':period.content,'retrieval_score':None}


_PERSON_LABEL = re.compile(r'\b(?:employee|candidate|name)\s*:\s*([^.:;|,\n]{2,65}?)(?=\s+(?:employer|position|role)\s*:|[.:;|,\n]|$)', re.I)


def _name_matches(person, name):
    requested = re.findall(r"[\w'-]+", person.casefold())
    words = re.findall(r"[\w'-]+", name.casefold())
    return bool(requested and words[:len(requested)] == requested)


def _personal_heading(person, row):
    if row[2] != 1:
        return False
    start = re.sub(r'^\s*(?:(?:curriculum vitae|r[eé]sum[eé]|CV)\s*[:|–—-]?\s*)?', '', row[3], flags=re.I)
    match = re.match(r"([\w'-]+(?: [\w'-]+){0,3}?)\s*(?:\n|[|·]|[–—]\s+|\s+(?=Full Stack|Software Engineer|Email:))", start)
    return bool(match and _name_matches(person, match[1]))


def _person_rows(rows, person, headers):
    """Bind employment rows to a labeled person or their resume heading."""
    labels = {}
    for row in [*headers, *rows]:
        labels.setdefault(str(row[1]), set()).update(m[1].strip().casefold() for m in _PERSON_LABEL.finditer(row[3]))
    result, anchors = [], {}
    for row in rows:
        doc = str(row[1])
        # Multiple named people make a document-level binding unsafe.
        if len(labels[doc]) > 1 or any(not _name_matches(person, label) for label in labels[doc]):
            continue
        candidates = [row, *(h for h in headers if str(h[1]) == doc)]
        for candidate in candidates:
            if (any(_name_matches(person, m[1]) for m in _PERSON_LABEL.finditer(candidate[3]))
                    or _personal_heading(person, candidate)):
                result.append(row)
                anchors[row[0]] = candidate
                break
    return result, anchors


def incompatible_employment_refs(question, sources, history=None):
    """Refs with an explicitly different employee for a requested employment fact."""
    if not (duration_intent(question) or joining_intent(question)):
        return []
    from services.v2_request_contract import employment_subject
    person=employment_subject(question,history)
    if not person:return []
    return [s['ref'] for s in sources if s.get('ref') and
            any(not _name_matches(person,m[1]) for m in _PERSON_LABEL.finditer(s.get('content','')))]


def _result_for_employer(rows,tokens,question,*,as_of,start_only=False,history=None,headers=()):
    from services.v2_request_contract import employment_subject
    person = employment_subject(question,history)
    anchors = {}
    if person and rows:
        rows, anchors = _person_rows(rows,person,headers)
        if not rows:
            return {'answer':"I couldn't establish this person's employment at the requested employer from the available evidence.",
                    'status':'abstained','sources':[],'citations':[],'issues':['employment_person_not_verified'],
                    'retrieval_status':'source_lookup','retrieved':[],'routing_policy':POLICY}
    requested=_literal_employer(question,history)
    if requested and requested!=tokens:
        exact=re.compile(r'\b'+r'\s+'.join(re.escape(t) for t in requested)+r'\b',re.I)
        if any(exact.search(row[3]) for row in rows):
            # A literal employer always wins, even if its dates are missing.
            # Never overwrite a real GO Productions record with a GOC guess.
            tokens=requested
    result=result_from_rows(rows,tokens,as_of=as_of,start_only=start_only)
    if result and requested and requested!=tokens and 'calculation' in result:
        result['calculation']['requested_employer_hint']=' '.join(requested)
        result['calculation']['resolved_employer_hint']=' '.join(tokens)
    if result and result.get('citations') and person:
        citation=result['citations'][0]
        anchor=anchors[citation['chunk_id']]
        ref=citation['ref']
        if anchor[0]!=citation['chunk_id']:
            ref='S2'
            source={'ref':ref,'chunk_id':anchor[0],'document':str(anchor[1]),'page':anchor[2]}
            result['answer']+=f' The résumé identifies {person} [{ref}].'
            result['citations'].append(source)
            result['sources'].append(source.copy())
            result['retrieved'].append({'ref':ref,'chunk_id':anchor[0],'document_name':str(anchor[1]),
                                        'page_number':anchor[2],'retrieval_score':None})
            from services.citation_service import validate_answer_citations
            result['validation']=validate_answer_citations(result['answer'],result['retrieved'],require_citations=True)
            if not result['validation']['valid']:
                raise ValueError('employment identity citation validation failed')
        if 'calculation' in result:
            result['calculation']['person_evidence']={'ref':ref,'document':str(anchor[1]),'page':anchor[2],'chunk_id':anchor[0]}
    return result


def result_from_rows(rows,tokens,*,as_of=None,start_only=False):
    from services.citation_service import answer_with_citations,validate_answer_citations
    if as_of is not None and not isinstance(as_of,date):raise TypeError('trusted as_of must be a date')
    periods=periods_in_rows(rows,tokens,as_of)
    unique={}
    for p in periods:unique.setdefault((p.document,p.employer.casefold(),p.start,p.end,p.is_current),p)
    if not unique:return None
    if len(unique)>1:
        return {'answer':'I found multiple matching employment records. Please specify the person, document or employment period before I calculate the duration.',
                'status':'abstained','sources':[],'citations':[],'issues':['ambiguous_employment_period'],'retrieval_status':'source_lookup','retrieved':[],'routing_policy':POLICY}
    p=next(iter(unique.values()))
    # Reverify the exact range against the original cited content before rendering.
    if p not in periods_in_rows([(p.chunk_id,p.document,p.page,p.content)],tokens,as_of):
        raise ValueError('employment source range did not revalidate')
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
    if p.is_current:
        as_of_label=f'{as_of.day} {calendar.month_name[as_of.month]} {as_of.year}'
        answer=(f'The resume lists employment at {employer} from {start} to Present [S1]. '
                f'Treating "Present" as {as_of_label}, this is approximately {duration} ({months} months); exact days are not specified [S1].')
    if start_only:
        answer=f'The resume lists the employment start at {employer} as {start} [S1]. The exact joining day is not specified [S1].'
    sources=[_source(p,'S1')]
    validation=validate_answer_citations(answer,sources,require_citations=True)
    if not validation['valid']:raise ValueError('calculation citation validation failed')
    checked=answer_with_citations(answer,sources)
    proof={'policy':POLICY,'method':'(end_year-start_year)*12 + end_month-start_month',
           'start':f'{p.start[0]:04d}-{p.start[1]:02d}','end':f'{p.end[0]:04d}-{p.end[1]:02d}',
           'total_months':months,'years':years,'remaining_months':remainder,'precision':'month; approximate elapsed duration',
           'source_ref':'S1','source_chunk_id':p.chunk_id,'source_document':p.document,'source_page':p.page,
           'date_span_in_analyzed_chunk':list(p.date_span)}
    if p.is_current:proof.update(as_of=as_of.isoformat(),end_source='application_clock_for_explicit_present',source_end='Present')
    result={'answer':checked['text'],'status':'answered','citations':checked['citations'],
            'sources':[{'document':p.document,'page':p.page,'chunk_id':p.chunk_id,'ref':'S1'}],
            'issues':[],'retrieval_status':'source_lookup','retrieved':[{'ref':'S1','chunk_id':p.chunk_id,'document_name':p.document,'page_number':p.page,'retrieval_score':None}],
            'routing_policy':POLICY,'calculation':proof,'validation':validation,'attempts':0}
    if start_only:result.pop('calculation')
    return result


def calculation_from_sources(question,sources,history=None,*,as_of=None):
    """Derive only from final selected context, retaining its original reference."""
    if not duration_intent(question):return None
    tokens=resolve_employer(question,history)
    if tokens is None:return None
    rows=[(s['chunk_id'],s['document_name'],s['page_number'],s['content']) for s in sources]
    result=_result_for_employer(rows,tokens,question,as_of=as_of or _as_of_date(),history=history,headers=rows)
    if not result or 'calculation' not in result:return None
    proof=result['calculation']
    source=next(s for s in sources if s['chunk_id']==proof['source_chunk_id']
                and s['document_name']==proof['source_document'] and s['page_number']==proof['source_page'])
    # Remap all refs simultaneously: the identity anchor can itself be S1.
    remap = {citation['ref']: next(s['ref'] for s in sources if s['chunk_id']==citation['chunk_id']
             and s['document_name']==citation['document'] and s['page_number']==citation['page'])
             for citation in result['citations']}
    result['answer']=re.sub(r'\[(S\d+)\]',lambda m:f'[{remap[m[1]]}]',result['answer'])
    if 'person_evidence' in proof:proof['person_evidence']['ref']=remap[proof['person_evidence']['ref']]
    proof['source_ref']=source['ref']
    for collection in ('citations','sources','retrieved'):
        result[collection]=[{**item,'ref':remap[item['ref']]} for item in result[collection]]
    from services.citation_service import validate_answer_citations
    result['validation']=validate_answer_citations(result['answer'],sources,require_citations=True)
    if not result['validation']['valid']:raise ValueError('selected employment citation validation failed')
    return result


def answer_employment_duration(question,history=None,*,scope=None,as_of=None):
    tokens=resolve_employer(question,history)
    if tokens is None:return None
    from services.tenant_context import current_owner
    owner=current_owner()
    if owner is None:raise PermissionError('authenticated tenant required')
    from services.v2_evidence_recovery import explicit_document_scope
    if scope is None:scope=explicit_document_scope(question)
    if scope==[]:return None
    from services.database import get_connection
    from services.v2_request_contract import employment_subject
    person=employment_subject(question,history)
    headers=[]
    with get_connection() as conn:
        scope_sql=' AND dc.document_name=ANY(%s)' if scope else ''
        requested=_literal_employer(question,history)
        prefixes=list(dict.fromkeys([requested[0],tokens[0]] if requested else [tokens[0]]))
        prefix_sql=' OR '.join('strpos(lower(dc.content),%s)>0' for _ in prefixes)
        params=(owner,*prefixes,scope) if scope else (owner,*prefixes)
        rows=conn.execute('''SELECT dc.id,dc.document_name,dc.page_number,dc.content
            FROM document_chunks dc JOIN documents d ON d.id=dc.document_id AND d.owner_id=dc.owner_id
            WHERE dc.owner_id=%s AND d.status='ready' AND ('''+prefix_sql+')'+scope_sql+'''
            ORDER BY dc.document_name,dc.page_number,dc.chunk_id LIMIT 101''',params).fetchall()
        if (person and 0<len(rows)<=100 and
                any(not _PERSON_LABEL.search(row[3]) and not _personal_heading(person,row) for row in rows)):
            ids=list(dict.fromkeys(row[1] for row in rows))
            if len(ids)<=3:
                headers=conn.execute('''SELECT DISTINCT ON (dc.document_name)
                    dc.id,dc.document_name,dc.page_number,dc.content
                    FROM document_chunks dc JOIN documents d ON d.id=dc.document_id AND d.owner_id=dc.owner_id
                    WHERE dc.owner_id=%s AND d.status='ready' AND dc.document_name=ANY(%s) AND dc.page_number=1
                    ORDER BY dc.document_name,dc.chunk_id''',(owner,ids)).fetchall()
    if len(rows)>100:return None
    return _result_for_employer(rows,tokens,question,as_of=as_of or _as_of_date(),start_only=joining_intent(question) and not duration_intent(question),history=history,headers=headers)
