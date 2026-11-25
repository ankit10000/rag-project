"""Resolve bounded document follow-ups from user requests, independently of evidence.

A resolved question carries a search subject. No date, citation or amount in a
conversation becomes a verified operand, and authorization is checked per turn.
"""
import re
from datetime import date, datetime, timezone

from services.request_coverage import build_request_plan, explicit_field_ids
from services.tenure_calculation import duration_intent, employer_hint, joining_intent


POLICY = 'v2-request-resolution/1'
_CHALLENGE = re.compile(r"(?:are you (?:sure|certain)(?: about (?:it|that|this))?|"
                        r"(?:please )?(?:double[- ]check|recheck|verify)(?: (?:it|that|this|your answer|the calculation))?)"
                        r"(?:[?.,!]?\s+(?:(?:I (?:thought|think) )?(?:it|that) (?:was|is)|"
                        r"shouldn['’]t it be)\s+\d{1,4}\s+(?:months?|years?|weeks?|days?))?", re.I)
_LOCATION = re.compile(r"(?:where (?:is|was) (?:that|this|it) (?:mentioned|stated|written|listed)|"
                       r"(?:on )?(?:which|what) page(?: (?:supports? (?:that|this)|(?:is|was) (?:it|this|that)(?: on)?))?)", re.I)
_DURATION = re.compile(r"(?:(?:and |so )?(?:how many|in) (?:years?|months?)(?: and (?:years?|months?))?|"
                       r"(?:please )?(?:calculate|compute) (?:it|this|that))", re.I)
_JOIN = re.compile(r"when did (?:he|she|they) (?:join|start)(?: (?:there|at (?:this|that) company))?", re.I)
_EDUCATION = re.compile(r"(?:what about|what (?:is|was)|and) (?:his|her|their) (?:education|academic qualifications?)", re.I)
_OTHER = re.compile(r"(?:and |what about )?(?:the )?other (?:company|employer)", re.I)
_SAME = re.compile(r"\b(?:at|in|with|for) (?:this|that|the same) (?:company|employer)\b", re.I)
_NAME = r"([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,3})"
_PERSON = [re.compile(pattern) for pattern in (
    r"\b(?i:did|does|has)\s+" + _NAME + r"\s+(?i:work|join|start|spend|have)\b",
    r"\b" + _NAME + r"(?:['’]s)\s+(?i:education|experience|tenure|qualifications?|employment)\b",
    r"\b(?i:who is|qualifications? of|education of)\s+" + _NAME + r"(?=[?.!,]|$)",
)]


def _history_users(history):
    # Positions are offsets into the bounded, deletion-filtered request history.
    return [(index, item['content']) for index, item in list(enumerate(history or []))[-6:]
            if isinstance(item, dict) and item.get('role') == 'user'
            and isinstance(item.get('content'), str) and item['content'].strip()]


def _subject(question):
    # A person is accepted only in the subject slot of an employment/identity
    # request. Normalize ordinary lower-case questions without turning an
    # employer, a pronoun or a document title into a person's name.
    grammars = (
        r"\b(?:did|does|has)\s+([\w'-]+(?:\s+[\w'-]+){0,3}?)\s+(?:work|join|start|spend|have)\b",
        r"\b(?:when|date)\s+([\w'-]+(?:\s+[\w'-]+){0,3}?)\s+(?:joined|started)\b",
        r"\bexperience\s+(?:to|of)\s+([\w'-]+(?:\s+[\w'-]+){0,3}?)\s+(?:at|in|with)\b",
    )
    for pattern in grammars:
        match = re.search(pattern, question, re.I)
        if match:
            name = match[1]
            if not re.search(r'\b(?:i|me|we|he|she|they|you|the|this|that|company|employee|person)\b', name, re.I):
                return name
    for pattern in _PERSON:
        match = pattern.search(question)
        if match:
            return match[1]
    return None


def employment_subject(question, history=None):
    person = _subject(question)
    if person:
        return person
    if not (re.search(r'\b(?:he|she|they|their|his|her|there|those)\b', question, re.I)
            or re.search(r'^\s*(?:(?:can|could) you )?(?:calculate|compute) (?:the )?(?:exact )?(?:years?|months?)', question, re.I)):
        return None
    for _, older in reversed(_history_users(history)):
        person = _subject(older)
        if person:
            return person
        if not (duration_intent(older) or joining_intent(older) or _DURATION.fullmatch(older.strip(' .?!'))):
            break
    return None


def _intent(query, plan):
    if duration_intent(query):
        return 'calculate'
    if plan['mode'] == 'comparison' or re.search(r'\bcompare\b', query, re.I):
        return 'compare'
    if plan['mode'] == 'enumeration' or re.search(r'\b(?:list|enumerate)\b', query, re.I):
        return 'list'
    if re.search(r'\b(?:summari[sz]e|overview|summary)\b', query, re.I):
        return 'summarize'
    return 'lookup'


def _plan(question, resolved, *, previous=(), scope_question=None, source_location=False,
          clarification=None, deterministic=False, as_of):
    plan = build_request_plan(resolved)
    fields = [*explicit_field_ids(resolved), *(f['id'] for f in plan['facets'])]
    employer = employer_hint(resolved) if duration_intent(resolved) or joining_intent(resolved) else None
    person = _subject(resolved)
    entities = [field for field in (person, ' '.join(employer or [])) if field]
    if plan['mode'] == 'comparison':
        entities = [item['label'] for item in plan['facets']]
    if joining_intent(resolved):
        fields.append('joining_date')
    if duration_intent(resolved):
        fields.append('employment_duration')
    if source_location:
        fields.append('source_page')
    units = re.findall(r'\b(year|month|day|week)s?\b', question, re.I)
    return {
        'policy': POLICY, 'original_question': question, 'resolved_question': resolved,
        'intent': 'clarify' if clarification else _intent(resolved, plan),
        'entities': entities, 'fields': list(dict.fromkeys(fields)),
        'units': list(dict.fromkeys(u.lower() for u in units)),
        'precision': 'exact' if re.search(r'\bexact\w*\b', question, re.I) else None,
        'time_frame': 'as_of_request' if duration_intent(resolved) else None,
        'as_of': as_of.isoformat() if duration_intent(resolved) else None,
        'previous_user_turns': list(previous), 'scope_question': scope_question or question,
        'clarification': clarification, 'deterministic_resolution': deterministic,
        'source_location': source_location,
    }


def build_request_contract(question, history=None, *, as_of=None):
    """Interpret a narrow set of references. Unknown operations use normal routing."""
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    if not isinstance(as_of, date):
        raise TypeError('as_of must be an application date')
    previous = None
    employers = []
    previous_index = None
    for index, text in [*_history_users(history), (None, question)]:
        q = ' '.join(text.strip().rstrip(' .?!').split())
        explicit = bool(re.search(r'\.pdf\b', q, re.I))
        if explicit:
            # Keep the literal question for authorization even when a short
            # reference changes source explicitly, e.g. "Which page in B.pdf?".
            q = re.sub(r'\s+(?:in|from)\s+[^?!]{1,160}\.pdf$', '', q, flags=re.I)
        location = bool(_LOCATION.fullmatch(q))
        challenge = bool(_CHALLENGE.fullmatch(q))
        unit_change = bool(_DURATION.fullmatch(q))
        joining = bool(_JOIN.fullmatch(q))
        education = bool(_EDUCATION.fullmatch(q))
        same = bool(_SAME.search(q) and duration_intent(q))
        other = bool(_OTHER.fullmatch(q))
        if not (location or challenge or unit_change or joining or education or same or other):
            current = _plan(text, text, as_of=as_of)
        else:
            prior_query = previous['resolved_question'] if previous and not previous['clarification'] else ''
            prior_scope = previous['scope_question'] if previous and '.pdf' in previous['scope_question'].lower() else None
            if explicit:
                prior_scope = text
            prior_turns = previous['previous_user_turns'] + [previous_index] if previous else []
            clarification = None
            resolved = text
            if other:
                active = employer_hint(prior_query) if prior_query else None
                alternatives = [name for name in employers if name != active]
                if active and len(alternatives) == 1 and (duration_intent(prior_query) or joining_intent(prior_query)):
                    person = _subject(prior_query) or 'they'
                    alternative = ' '.join(alternatives[0])
                    resolved = (f'When did {person} join {alternative}?' if joining_intent(prior_query) else
                                f'How many months did {person} work at {alternative}?')
                else:
                    clarification = 'Which employer are you referring to?'
            elif not prior_query:
                clarification = 'Which question or source would you like me to check?'
            elif location or challenge:
                resolved = prior_query
            elif education:
                person = _subject(prior_query)
                if person:
                    resolved = f'What are the academic qualifications of {person}?'
                else:
                    clarification = 'Whose academic qualifications would you like me to check?'
            else:
                employer = employer_hint(prior_query) if (duration_intent(prior_query) or joining_intent(prior_query)) else None
                if not employer or re.search(r'\b(?:and|versus|or)\b', ' '.join(employer), re.I):
                    clarification = 'Which employer and person should I use for the employment dates?'
                else:
                    person = _subject(prior_query) or 'they'
                    company = ' '.join(employer)
                    units = ' and '.join(dict.fromkeys(re.findall(r'\b(?:years?|months?)\b', q, re.I))).lower() or 'months'
                    resolved = (f'When did {person} join {company}?' if joining else
                                f'How many {units} did {person} work at {company}?')
            current = _plan(text, resolved, previous=prior_turns, scope_question=prior_scope,
                            source_location=location, clarification=clarification,
                            deterministic=True, as_of=as_of)
        focus = current['resolved_question']
        if duration_intent(focus) or joining_intent(focus):
            named = employer_hint(focus)
            if named and named not in employers:
                employers.append(named)
        else:
            employers.clear()
        previous, previous_index = current, index
    return previous
