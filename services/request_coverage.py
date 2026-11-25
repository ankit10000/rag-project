"""Deterministic, source-bound diagnostics for explicit multi-item requests.

This deliberately measures visible labels and numbered source headings, not
semantic entailment. It never supplies a missing fact, decides that a whole PDF
has no answer, or treats an LLM coverage judgement as proof of correctness.
"""
import re

POLICY = 'v2-explicit-request-coverage/4'
_WORD_NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                 'eleven': 11, 'twelve': 12}
_NUMBER_WORD = '|'.join(_WORD_NUMBERS)
_COUNT = re.compile(r'\b(?P<count>[1-9]\d?|' + _NUMBER_WORD + r')\s+'
                    r'(?:[\w-]+\s+){0,2}(?P<kind>phases?|stages?|steps?)\b', re.I)
_KINDS = re.compile(r'\b(phases?|stages?|steps?)\b', re.I)
_ENUMERATION = re.compile(r'\b(?:list|enumerate)\b|\b(?:all|every|each)\b', re.I)
_CITATIONS = re.compile(r'\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]', re.I)

# These are question/answer vocabulary families, not golden expected answers.
# A field can be called observed only when the submitted context contains one
# of its signals; that is not a claim that every number associated with it is
# correct, or that a mention fully answers the field.
_FIELDS = (
    ('budget', 'budget / cost', r'\b(?:budget|costs?|prices?)\b',
     r'\b(?:budget|costs?|prices?|expenditure)\b|[$€£₹]\s*\d', 'budget cost estimate'),
    ('team', 'team size / staffing', r'\b(?:team|headcount|staffing|staff)\b',
     r'\b(?:team|headcount|staffing|staff|people|members|employees)\b', 'team size staffing people'),
    ('duration', 'development duration / timeline', r'\b(?:duration|timeline|timeframe|how long)\b',
     r'\b(?:duration|timeline|timeframe|years?|months?|weeks?|days?)\b', 'development duration timeline months years'),
    ('languages', 'language support', r'\b(?:multilingual|languages?)\b',
     r'\b(?:multilingual|languages?|Hindi|English|regional)\b', 'multilingual language support'),
    ('offline', 'offline / mobile access', r'\b(?:offline|mobile)\b',
     r'\b(?:offline|mobile|downloads?|downloading)\b', 'offline mobile downloads access'),
    ('database', 'database / account storage', r'\b(?:databases?|account storage)\b',
     r'\b(?:databases?|PostgreSQL|MongoDB|MySQL|SQLite|relational|NoSQL)\b', 'database user accounts storage PostgreSQL relational'),
    ('core_features', 'core / MVP features', r'\b(?:core|MVP)\b(?=.{0,35}\bfeatures?\b)|\bfeatures?\b(?=.{0,35}\b(?:core|MVP)\b)',
     r'\b(?:core|MVP)\b', 'core MVP product features'),
    ('additional_features', 'additional features', r'\b(?:additional|extended|later)\b(?=.{0,35}\bfeatures?\b)|\bfeatures?\b(?=.{0,35}\b(?:additional|extended|later)\b)',
     r'\b(?:additional|extended|later|adaptive|gamification|multilingual|offline)\b', 'additional later extended product features'),
    ('phone', 'phone information', r'\b(?:phone|telephone)\b',
     r'\b(?:phone|telephone)\b', 'phone telephone information'),
    ('fax', 'fax information', r'\bfax\b', r'\bfax\b', 'fax service number'),
    ('email', 'email information', r'\be-?mail\b', r'\be-?mail\b', 'email address'),
)


def _text(value):
    return ' '.join(value.split()) if isinstance(value, str) else ''


def _entity_regex(label):
    # Spaces and hyphens are interchangeable in ordinary entity labels.
    tokens = re.findall(r'\w+', label.casefold())
    return r'(?<!\w)' + r'[\s-]+'.join(re.escape(x) for x in tokens) + r'(?!\w)'


def explicit_field_ids(question):
    """Requested dimensions, including a single field, without decomposing retrieval."""
    return [name for name, _, requested, _, _ in _FIELDS if re.search(requested, question, re.I)]


def _comparison_entities(question):
    # Restrict to explicit comparison syntax. Do not guess pronouns, infer
    # entities from source content, or silently resolve ambiguous references.
    match = re.search(r'\bcompare\s+(.+?)\s+(?:and|with|versus|vs\.?)\s+(.+)', question, re.I)
    if not match:
        return []
    left, right = match.groups()
    right = re.split(r'\s+(?:in terms of|according to|regarding|from the|based on)\b', right, maxsplit=1, flags=re.I)[0]
    right = re.sub(r'\s+(?:in|from)\s+(?:the\s+)?[^?!]+\.pdf[.?!]?(?:\s.*)?$', '', right, flags=re.I)
    right = right.strip(' .?!,:;')
    # Common shared dimensions belong to the query, not the second entity.
    right = re.sub(r'\s+(?:hosting\s+)?(?:costs?|budgets?|benefits?|drawbacks?|options?|models?)$', '', right, flags=re.I)
    # In an explicit deployment comparison, "hosting" is a shared domain
    # qualifier, not part of the conventional on-premises/public-cloud names.
    # Limit this normalization to that recognizable pair; arbitrary entity
    # names ending in "hosting" are left intact.
    if re.fullmatch(r'on[\s-]+premises(?:\s+hosting)?', left.strip(), re.I) and re.fullmatch(r'public\s+cloud\s+hosting', right, re.I):
        left = re.sub(r'\s+hosting$', '', left.strip(), flags=re.I)
        right = re.sub(r'\s+hosting$', '', right, flags=re.I)
    labels = [_text(left).strip(' .?!,:;'), _text(right)]
    if any(not label or len(label.split()) > 8 or label.casefold() in {'it', 'this', 'that', 'them', 'these', 'those', 'a', 'b'} for label in labels):
        return []
    if labels[0].casefold() == labels[1].casefold():
        return []
    return labels


def build_request_plan(question):
    """Return a small, inspectable plan only for explicit bounded requests."""
    question = _text(question)
    result = {'policy': POLICY, 'mode': 'none', 'facets': [], 'enumeration_count': None,
              'caveat': 'Literal presence checks only; not semantic entailment or full-source absence proof.'}
    if not question:
        return result
    count = _COUNT.search(question)
    kind = _KINDS.search(question)
    if kind and _ENUMERATION.search(question):
        kind_name = (count['kind'] if count else kind[1]).lower().rstrip('s')
        expected = None
        if count:
            value = count['count'].lower()
            expected = _WORD_NUMBERS[value] if value in _WORD_NUMBERS else int(value)
            if not 1 <= expected <= 12:
                return result
        result.update(mode='enumeration', enumeration_count=expected, enumeration_kind=kind_name)
        if expected:
            result['facets'] = [
                {'id': f'{kind_name}_{number}', 'label': f'{kind_name.title()} {number}',
                 'pattern': rf'\b{kind_name}\s+{number}\b', 'query_terms': f'{kind_name} {number}'}
                for number in range(1, expected + 1)
            ]
        return result
    entities = _comparison_entities(question)
    if entities:
        result.update(mode='comparison', facets=[
            {'id': f'entity_{i + 1}', 'label': name, 'pattern': _entity_regex(name), 'query_terms': name}
            for i, name in enumerate(entities)
        ])
        return result
    facets = [
        {'id': fid, 'label': label, 'pattern': observed, 'request_pattern': requested, 'query_terms': terms}
        for fid, label, requested, observed, terms in _FIELDS
        if re.search(requested, question, re.I)
    ]
    for facet in facets:
        if facet['id'] != 'additional_features':
            continue
        # "Additional" names a narrative group; it does not establish a
        # later delivery phase. Preserve the user's actual requested group
        # instead of silently merging group identity with MVP prioritization.
        groups = [group for group in ('additional', 'extended', 'later')
                  if re.search(rf'\b{group}\b', question, re.I)]
        facet['label'] = ' and '.join(group + ' features' for group in groups)
        facet['query_terms'] = ' '.join(groups) + ' product features'
        facet['pattern'] = r'\b(?:' + '|'.join(groups) + r')\b'
        if groups == ['additional'] and re.search(r'\bsuggested\s+additional\b', question, re.I):
            facet['label'] = 'suggested additional features'
    if len(facets) >= 2 or (facets and re.search(
            r'\b(?:total|overall|aggregate)(?:\s+(?:project|program|programme))?\s+(?:budget|cost|price)\b', question, re.I)):
        result.update(mode='fields', facets=facets[:6])
    else:
        clauses = re.split(r'\s+and\s+(?=(?:what|which|how|why|when|where|who)\b)', question, flags=re.I)
        if 2 <= len(clauses) <= 3 and all(0 < len(clause) <= 500 for clause in clauses):
            result.update(mode='clauses', decomposition_clauses=clauses)
    return result


def decompose_question(question, max_facets=3):
    """Offer at most three focused retrieval queries, never provider calls.

    Only explicit compound fields/comparisons decompose. Enumeration is best
    recovered from section continuity rather than independent numeral searches.
    Query text is untrusted user data and contributes no factual evidence.
    """
    plan = build_request_plan(question)
    limit = max(0, min(3, int(max_facets)))
    if plan['mode'] not in {'fields', 'comparison', 'clauses'} or limit == 0:
        return []
    # Repeating the complete compound question makes each rerank query favor
    # its dominant part again. Keep each requested clause/entity and any
    # explicit filename preface; the CALLER still enforces document/tenant
    # scope, and must never use these query strings as authorization.
    question = _text(question)
    preface = re.match(r'^(?:according to|from|in)\s+(.+?\.pdf)\b', question, re.I)
    scope_hint = ('According to ' + preface[1] + ': ') if preface else ''
    if plan['mode'] == 'clauses':
        return [scope_hint + (clause.replace(preface[0], '').strip(' ,:') if preface else clause)
                for clause in plan['decomposition_clauses'][:limit]]
    parts = re.split(r'\s*(?:[,;]|\band\b)\s*', question, flags=re.I)
    shared_terms = ' '.join(terms for _, _, requested, _, terms in _FIELDS
                            if re.search(requested, question, re.I))
    queries = []
    for item in plan['facets'][:limit]:
        if plan['mode'] == 'comparison':
            focus = item['label'] + ' ' + shared_terms
        else:
            clause = next((part for part in parts if re.search(item['request_pattern'], part, re.I)), item['label'])
            if preface:
                clause = clause.replace(preface[0], '').strip(' ,:')
            focus = clause + ' ' + item['query_terms']
        queries.append(scope_hint + _text(focus))
    return queries


def _clauses(text):
    return [part for part in re.split(r'(?<=[.!?])\s+|[;\n]+', text) if part.strip()]


def _gap_clause(text):
    from services.answer_semantics import is_insufficiency_clause
    return is_insufficiency_clause(text) or bool(re.search(
        r'\b(?:not (?:stated|provided|specified|mentioned)|'
        r'no (?:information|details|evidence)|not enough|insufficient)\b', text, re.I))


def _enumeration_titles(plan, facet, sources):
    if plan['mode'] != 'enumeration':
        return []
    number = facet['id'].rsplit('_', 1)[-1]
    kind = plan['enumeration_kind']
    pattern = rf'\b{kind}\s+{number}\s*[–—:-]\s*([^\n:;(.]{{2,100}})'
    titles = set()
    for source in sources:
        for match in re.finditer(pattern, source['content'], re.I):
            title = re.split(r'\s+(?=\d)', match[1], maxsplit=1)[0].strip(' –—-')
            if 2 <= len(re.findall(r'\w+', title)) <= 8:
                titles.add(title)
    return sorted(titles)


def _title_pattern(title):
    # Exact source words, accepting only typography variation in '&'/'and'.
    words = [word for word in re.findall(r'\w+', title) if word.casefold() != 'and']
    return r'(?<!\w)' + r'(?:[\W_]+|\s+and\s+)'.join(re.escape(word) for word in words) + r'(?!\w)'


def _title_mentioned(title, text):
    return bool(re.search(_title_pattern(title), text, re.I))


def _feature_heading_facets(question, plan, sources):
    """Track literal feature-list headings only where the context exposes them.

    A bullet on a different section/page is not automatically a requested
    feature. Group-specific lists are handled only when BOTH core and later
    groups are requested; otherwise a missing section boundary is ambiguous.
    """
    if not re.search(r'\b(?:list|enumerate|all|every|each)\b', question, re.I) or not re.search(r'\bfeatures?\b', question, re.I):
        return []
    ids = {facet['id'] for facet in plan['facets']}
    groups = ids & {'core_features', 'additional_features'}
    if len(groups) == 1:
        return []
    pages = {}
    for source in sources:
        key = (source.get('document_name', source.get('document')), source.get('page_number', source.get('page')))
        pages.setdefault(key, []).append(source)
    headings = set()
    for group in pages.values():
        combined = '\n'.join(source['content'] for source in group)
        if not re.search(r'\b(?:core|suggested additional|additional|product)\s+features\b', combined, re.I):
            continue
        for source in group:
            for match in re.finditer(r'(?:^|[•\n])\s*([A-Za-z][\w /&()–—-]{2,65}):', source['content']):
                label = match[1].strip()
                if re.search(r'\bfeatures?\b', label, re.I) or len(label.split()) > 8:
                    continue
                headings.add(label)
    facets = []
    for heading in sorted(headings)[:12]:
        family = _feature_vocabulary_family(heading)
        facets.append({'id': 'heading_' + '_'.join(re.findall(r'\w+', heading.casefold())),
                       'label': heading, 'pattern': _title_pattern(heading), 'query_terms': heading,
                       'literal_titles': [heading], 'answer_pattern': family,
                       'repair_checkable': family is not None,
                       'matching_method': 'source-triggered vocabulary family' if family else 'literal-heading diagnostic only'})
    return facets


def _feature_vocabulary_family(heading):
    """Recognize bounded common vocabulary, not a mandatory output template.

    Source headings select the family; no heading/value is manufactured from a
    question or golden answer. A paraphrase of an unknown heading is uncertain,
    so its absence is diagnostic only and cannot force repair/partial status.
    """
    families = (
        (r'\bvideo\b.*\b(?:lessons?|lectures?)\b',
         r'\bvideo[-\s]+(?:lessons?|lectures?|tutorials?)\b|\b(?:instructional|educational|lecture)\s+videos?\b'),
        (r'\b(?:notes?|summar(?:y|ies))\b', r'\b(?:notes?|summar(?:y|ies))\b'),
        (r'\b(?:tests?|quizzes?|exams?)\b', r'\b(?:tests?|quizzes?|exams?)\b'),
        (r'\bquestion\s+bank|\bQ\s*(?:&|and)\s*A\b',
         r'\bquestion\s+banks?\b|\bQ\s*(?:&|and)\s*A\b|\bquestion[-\s]+answer(?:ing)?\b'),
        (r'\badaptive\b.*\blearning\b',
         r'\badaptive\b.*?\blearning\b|\bpersonali[sz]ed\s+(?:learning|paths?|recommendations?)\b'),
        (r'\bforum\b', r'\bforums?\b|\bdoubt[-\s]+solving\b'),
        (r'\banalytics\b|\bprogress\s+tracking\b', r'\banalytics\b|\bprogress\s+(?:tracking|dashboards?)\b'),
        (r'\bgamification\b', r'\bgamification\b|\bbadges?\b|\bstreaks?\b|\bleaderboards?\b'),
        (r'\bmultilingual\b', r'\bmultilingual\b|\bHindi\b|\bregional\s+languages?\b|\bmultiple\s+languages?\b'),
        (r'\boffline\b|\bmobile\s+app\b', r'\boffline\b|\bdownload(?:ing|s)?\b|\bmobile\s+apps?\b'),
    )
    for source_heading, answer_terms in families:
        if re.search(source_heading, heading, re.I):
            return answer_terms
    return None


_NUM = r'\d+(?:,\d{3})*(?:\.\d+)?'
_RANGE = rf'{_NUM}(?:\s*[-–—]\s*{_NUM})?'
_MONEY = rf'(?:[$€£₹]\s*{_NUM}(?:\s*(?:[kKmMbB]\b|million\b|billion\b|thousand\b))?(?:\s*[-–—]\s*[$€£₹]?\s*{_NUM}(?:\s*(?:[kKmMbB]\b|million\b|billion\b|thousand\b))?)?|{_RANGE}\s+(?:credits?|dollars?|euros?|rupees?|USD|EUR|INR)\b)'
_FIELD_QUANTITIES = {
    'budget': (r'(?:budget|cost|price)', _MONEY),
    'team': (r'(?:team(?:\s+size)?|headcount|staffing)', rf'{_RANGE}(?:\s+(?:people|members?|employees?|engineers?|developers?))?'),
    'duration': (r'(?:duration|timeline|timeframe|development)', rf'{_RANGE}\s+(?:months?|years?|weeks?|days?)'),
}
_QUANTITY_LINK = r'\s*(?:[:=–—-]\s*)?(?:(?:is|was|of|has|had|takes?|lasts?|is estimated at|estimated at|stands at|consists? of|includes?)\s+)?'


def _quantity_key(value, field):
    value = re.sub(r'\s+', ' ', value.strip().casefold()).replace(',', '')
    value = re.sub(r'\s*[-–—]\s*', '-', value)
    if field == 'team':
        return re.match(_RANGE, value)[0]
    return re.sub(r'([$€£₹])\s+', r'\1', value)


def _quantities(field, text, *, require_total=False):
    label, quantity = _FIELD_QUANTITIES[field]
    matches = []
    for match in re.finditer(rf'\b{label}\b{_QUANTITY_LINK}(?P<value>{quantity})(?!\w)', text, re.I):
        prefix = text[max(0, match.start()-50):match.start()]
        if require_total and not re.search(r'\b(?:total|overall|aggregate)(?:\s+(?:project|program|programme))?\s*$', prefix, re.I):
            continue
        # Conditionals, negations, limits and estimates describe different
        # propositions and cannot establish an unqualified exact value.
        clause_prefix = re.split(r'[.!?;\n]', prefix)[-1]
        if re.search(r"\b(?:if|unless|not|never|assume|example|hypothetical)\b", clause_prefix, re.I):
            continue
        matches.append(match)
    return matches


def _typed_field(question, facet, sources, answer):
    from services.citation_service import extract_citation_refs, split_sentences, strip_citations
    field = facet['id']
    require_total = field == 'budget' and bool(re.search(
        r'\b(?:total|overall|aggregate)(?:\s+(?:project|program|programme))?\s+(?:budget|cost|price)\b', question, re.I))
    records = []
    for source in sources:
        if not source.get('ref'):
            continue
        for hit in _quantities(field, source['content'], require_total=require_total):
            qualifier = re.search(r"\b[Pp]roject\s+([A-Z][\w'-]*(?: [A-Z][\w'-]*){0,2})(?:['’]s)?\s+"
                                  r"(?:(?:total|overall)\s+)?$", source['content'][max(0,hit.start()-100):hit.start()])
            records.append({'ref': source['ref'], 'document': source.get('document_name'), 'page': source.get('page_number'),
                            'chunk_id': source.get('chunk_id'), 'span': hit.span('value'), 'value': hit['value'],
                            'entity': qualifier[1].casefold() if qualifier else None})
    values = {_quantity_key(record['value'], field) for record in records}
    if not records:
        return None
    # Different values do not prove a contradiction across unrelated entities
    # or documents. Report the distinct bindings without selecting by rank.
    entities = {r['entity'] for r in records}
    shared_entity = len(entities) == 1 and None not in entities
    state = 'SUPPORTED_DIRECT' if len(values) == 1 else ('CONFLICTING' if shared_entity else 'AMBIGUOUS')
    evidence = {'evidence_state': state, 'evidence_reason': 'explicit field/value binding' if len(values)==1 else 'multiple visible field/value bindings',
                'evidence_records': records, 'supported_values': list(dict.fromkeys(r['value'] for r in records)),
                'evidence_refs': list(dict.fromkeys(r['ref'] for r in records)), 'unsupported_answer_clauses': []}
    if answer is None or len(values) != 1:
        return evidence
    matched = False
    for sentence in split_sentences(answer):
        raw = strip_citations(sentence)
        refs = extract_citation_refs(sentence)
        claims = [hit['value'] for hit in _quantities(field, raw)]
        if not claims:
            # Terse answers may put only a typed value on a line. A number
            # occurring anywhere in an unrelated sentence is not a binding.
            standalone = re.fullmatch(r'\s*(' + _FIELD_QUANTITIES[field][1] + r')\s*[.!]?\s*', raw, re.I)
            if standalone and (field != 'team' or re.search(r'[A-Za-z]', standalone[1])):
                claims = [standalone[1]]
        if not claims or _gap_clause(raw):
            continue
        if all(_quantity_key(value, field) in values for value in claims) and (
                not refs or any(ref in evidence['evidence_refs'] for ref in refs)):
            matched = True
        else:
            evidence['unsupported_answer_clauses'].append(sentence)
    evidence['answer_mentions'] = matched and not evidence['unsupported_answer_clauses']
    return evidence


def request_coverage(question, sources, answer=None):
    """Compare requested labels to actual context and optionally answer text.

    Concrete missing items require BOTH an explicit request facet and a signal
    observed in submitted sources. A source-unobserved facet can motivate
    bounded retrieval recovery, but never fabrication or automatic answering.
    Negative facts count as mentions; existing semantics decides their status.
    """
    plan = build_request_plan(question)
    sources = [s for s in (sources or []) if isinstance(s, dict) and isinstance(s.get('content'), str)]
    answer_text = _CITATIONS.sub('', answer) if isinstance(answer, str) else None
    facets = list(plan['facets'])
    facets.extend(_feature_heading_facets(_text(question), plan, sources))
    if plan['mode'] == 'enumeration' and not facets:
        kind = plan['enumeration_kind']
        observed_numbers = set()
        for source in sources:
            observed_numbers.update(int(n) for n in re.findall(rf'\b{kind}\s+(\d{{1,2}})\b', source['content'], re.I))
        facets = [{'id': f'{kind}_{n}', 'label': f'{kind.title()} {n}',
                   'pattern': rf'\b{kind}\s+{n}\b', 'query_terms': f'{kind} {n}'}
                  for n in sorted(observed_numbers)[:12]]
    output = []
    for facet in facets:
        refs = [source.get('ref') for source in sources
                if source.get('ref') and re.search(facet['pattern'], source['content'], re.I)]
        source_clauses = [clause for source in sources for clause in _clauses(source['content'])
                          if re.search(facet['pattern'], clause, re.I)]
        source_fact_signal = any(not _gap_clause(clause) for clause in source_clauses)
        answer_pattern = facet.get('answer_pattern') or facet['pattern']
        answer_clauses = [clause for clause in _clauses(answer_text or '')
                          if re.search(answer_pattern, clause, re.I)]
        source_titles = facet.get('literal_titles', []) + _enumeration_titles(plan, facet, sources)
        answer_clauses.extend(clause for clause in _clauses(answer_text or '')
                              if any(_title_mentioned(title, clause) for title in source_titles)
                              and clause not in answer_clauses)
        mentions = bool(answer_clauses) if answer_text is not None else None
        # A visible label in an unsupported refusal is not coverage of a
        # concrete source fact. Source-only evidence gaps and explicit negative
        # facts remain valid; this is diagnostic, never an entitlement to fill
        # the answer with an inferred value.
        refused_supported_item = bool(source_fact_signal and answer_clauses
                                      and all(_gap_clause(clause) for clause in answer_clauses))
        if refused_supported_item:
            mentions = False
        details = {'evidence_state': 'AMBIGUOUS' if refs and source_fact_signal else 'NOT_FOUND_IN_SEARCHED_SCOPE',
                   'evidence_reason': 'lexical candidate only' if refs and source_fact_signal else 'no affirmative binding in supplied passages',
                   'supported_values': [], 'unsupported_answer_clauses': []}
        if facet['id'] in _FIELD_QUANTITIES:
            typed = _typed_field(question, facet, sources, answer)
            if typed:
                details.update(typed)
            elif facet['id'] == 'budget' and re.search(r'\b(?:total|overall|aggregate)\s+(?:project\s+)?budget\b', question, re.I):
                components = [s['ref'] for s in sources if s.get('ref') and re.search(
                    r'\b(?:component|department|staffing|hardware|software)\s+budget\b', s['content'], re.I)]
                if components and not any(re.search(r'\b(?:total|overall|aggregate)\b', s['content'], re.I) for s in sources):
                    details.update(evidence_state='NOT_FOUND_IN_SEARCHED_SCOPE', evidence_reason='only component budgets are bound',
                                   observed_in_context=False, evidence_refs=[], source_fact_signal=False)
                    if answer is not None:
                        from services.citation_service import split_sentences
                        details['unsupported_answer_clauses'] = [s for s in split_sentences(answer)
                            if _quantities('budget', s) and not _gap_clause(s) and not re.search(
                                r'\b(?:component|department|staffing|hardware|software)\s+budget\b', s, re.I)]
        output.append({**facet, 'evidence_refs': list(dict.fromkeys(refs)),
                       'observed_in_context': bool(refs), 'answer_mentions': mentions,
                       'source_fact_signal': source_fact_signal,
                       'source_titles': source_titles,
                       'refused_supported_item': refused_supported_item, **details})
    concrete = [{'id': item['id'], 'label': item['label'], 'evidence_refs': item['evidence_refs']}
                for item in output if item['observed_in_context'] and item['answer_mentions'] is False
                and item.get('repair_checkable', True)]
    return {**plan, 'facets': output, 'concrete_missing': concrete,
            'diagnostic_missing': [item['id'] for item in output if item['observed_in_context']
                                   and item['answer_mentions'] is False and not item.get('repair_checkable', True)],
            'context_unobserved': [item['id'] for item in output if not item['observed_in_context']],
            'answer_checked': answer_text is not None}


def coverage_prompt(report):
    """Compact answer contract, not an assertion that the evidence is complete."""
    if not report.get('facets'):
        return ''
    items = '; '.join(item['label'] for item in report['facets'])
    grouping = ''
    if any(item['id'] in {'core_features', 'additional_features'} for item in report['facets']):
        grouping = (' Preserve the author\'s group names: "additional" does not by itself mean '
                    '"later" or "outside the MVP". If the supplied narrative and a table '
                    'assign differing priorities, distinguish those representations and cite '
                    'them; do not silently reconcile them or assert a disagreement without evidence.')
    return ('Requested-item checklist: ' + items + '. Address every requested item separately. '
            'Use only the supplied source evidence; explicitly identify any unavailable item. '
            'Do not infer a missing value from a label, source heading, or this checklist.' + grouping)


def coverage_feedback(report):
    """Repair instruction only for visibly omitted, source-observed labels."""
    missing = report.get('concrete_missing', [])
    if not missing:
        return ''
    items = '; '.join(item['label'] + ' (source references: ' + ', '.join(item['evidence_refs']) + ')'
                      for item in missing)
    return ('The previous answer omitted these explicitly requested items whose labels are present '
            'in the supplied evidence: ' + items + '. Check those passages and address each item '
            'with citations, or clearly state what those passages do not establish. '
            'Do not invent facts or numbers to complete the checklist.')
