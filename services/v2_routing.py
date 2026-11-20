"""Versioned, tenant-scoped recovery for source overview questions (v2 only)."""
import re
from pathlib import PurePath

OVERVIEW_POLICY='v2-single-source-overview/1'
# Exact broad overview requests only; targeted questions keep their own query.
_OVERVIEW=re.compile(
    r"(?:what(?: is|'s) (?:in|inside|under) (?:that |this |the |my |those |these )?(?:docs?|documents?|pdfs?|files?)"
    r"|what (?:does|do) (?:that |this |the |my |those |these )?(?:docs?|documents?|pdfs?|files?) (?:contain|cover)"
    r"|(?:summarize|summarise|describe|give me an overview of) (?:that |this |the |my )?(?:doc|document|pdf|file))",
    re.I,
)

def is_overview(query):
    return isinstance(query,str) and _OVERVIEW.fullmatch(' '.join(query.strip(' .?!').split())) is not None

def single_source_overview_query(query):
    """Resolve a broad deictic question only when there is one ready owned source.

    Filenames contribute search terms, never factual evidence. With several
    sources no referent is guessed, and no other tenant's inventory is visible.
    """
    if not is_overview(query):return None
    from services.tenant_context import current_owner
    owner=current_owner()
    if owner is None:return None
    from services.database import get_connection
    with get_connection() as conn:
        rows=conn.execute("SELECT filename FROM documents WHERE owner_id=%s AND status='ready' ORDER BY id LIMIT 2",(owner,)).fetchall()
    if len(rows)!=1:return None
    words=' '.join(re.findall(r'\w+',PurePath(rows[0][0]).stem.replace('_',' ')))
    return 'Document overview and summary: '+words

EDUCATION_POLICY='v2-person-education-evidence/2'
_EDUCATION_MARKERS=re.compile(r'\b(?:education|bachelor|master|doctorate|degree|university|college)\b|\b(?:b\.?\s?tech|m\.?\s?tech|ph\.?\s?d)\b',re.I)

def qualification_subject(query):
    """Recognize a person's academic qualification request, not job requirements."""
    if not isinstance(query,str):return None
    text=' '.join(query.strip(' .?!').split())
    if re.search(r'\b(?:professional|skills?|experience|required|requirements?|eligibility)\b',text,re.I):return None
    patterns=[
        r"what (?:is|are) (?:the )?(?:(?:academic|educational) )?qualifications? of (.+)",
        r"what (?:is|are) (.+?)(?:'s|’s) (?:(?:academic|educational) )?qualifications?",
        r"what (?:(?:academic|educational) )?qualifications? (?:does|did) (.+?) (?:have|hold|possess)",
    ]
    for pattern in patterns:
        match=re.fullmatch(pattern,text,re.I)
        if match:
            tokens=re.findall(r'\w+',match.group(1).casefold())
            if tokens and not any(x in {'i','me','my','you','your','he','she','his','her','they','their'} for x in tokens):
                return tokens
    return None

def education_retrieval(question,initial,search_fn,top_k,authorized_scope=None):
    """Anchor the named person first, then search education within that document.

    A degree chunk often lacks the name on a resume's first chunk. Comparing
    both against one name-heavy query favors biography and drops education.
    Never associate a nameless degree with a person across different documents.
    """
    subject=qualification_subject(question)
    explicit_section = (isinstance(question,str) and re.search(
        r"\b(?:under|section|listed|give)\b.*\b(?:education|degree)\b",question,re.I))
    if subject is None and not (explicit_section and authorized_scope and len(authorized_scope)==1):return None
    anchors=set(authorized_scope or []) if subject is None else set()
    for item in initial['results']:
        chunk=item['chunk']
        words=set(re.findall(r'\w+',chunk[3].casefold()))
        if subject and all(token in words for token in subject):anchors.add(chunk[1])
    if len(anchors)!=1:return None
    if authorized_scope is not None and not anchors.issubset(set(authorized_scope)):return None
    from services.evidence_trace import trace_event
    trace_event('education_recovery',metadata={'policy':EDUCATION_POLICY,'documents':sorted(anchors),'explicit_section':bool(explicit_section)})
    result=search_fn('formal education academic degree university college graduation',
                     top_k=top_k,document_names=sorted(anchors))
    # Do not substitute a career summary when no academic evidence is indexed.
    selected=[item for item in result['results'] if _EDUCATION_MARKERS.search(item['chunk'][3])]
    identity=next((item for item in initial['results'] if subject and item['chunk'][1] in anchors
                   and all(token in set(re.findall(r'\w+',item['chunk'][3].casefold())) for token in subject)),None)
    return {**result,'results':selected,'education_identity_anchor':identity}
