"""Bounded v2 source/facet recovery for demonstrated complementary-evidence loss.

No provider calls, new global thresholds or new facts. Independent facet ranks
are never compared numerically: a useful answer to the second requested field
must not lose to the first field's unrelated higher reranker score.
"""
import re

from services.evidence_trace import trace_candidates, trace_event

POLICY = 'v2-bounded-complementary-evidence/2'
_STOP = {'the', 'and', 'for', 'from', 'with', 'what', 'which', 'all', 'each', 'every',
         'list', 'give', 'according', 'document', 'pdf', 'does', 'are', 'this', 'that',
         'proposed', 'its', 'their', 'please', 'both', 'also', 'about', 'how', 'would',
         'could', 'should', 'requested', 'information', 'summary', 'executive'}


def explicit_document_scope(question):
    """Resolve actual ready owned filenames, never turn a filename into facts.

    Only a literal filename mention selects scope. Ambiguous overlarge source
    lists are left unresolved; the caller must not guess a cross-document link.
    """
    from services.tenant_context import current_owner
    owner = current_owner()
    if owner is None or not isinstance(question, str) or '.pdf' not in question.casefold():
        return None
    from services.database import get_connection
    with get_connection() as conn:
        rows = conn.execute('''SELECT id FROM documents
            WHERE owner_id=%s AND status='ready'
                AND strpos(lower(%s), lower(filename)) > 0
            ORDER BY id LIMIT 5''', (owner, question)).fetchall()
    if not rows or len(rows) > 3:
        # An explicit file reference that cannot be authorized is a closed
        # scope, not permission to search every other document in the account.
        return []
    return [str(row[0]) for row in rows]


def _terms(text):
    return {word.rstrip('s') for word in re.findall(r'[a-z]{3,}', text.casefold())
            if word not in _STOP}


def _structural_count_request(question):
    return (bool(re.search(r'\b(?:phases?|stages?|steps?)\b', question, re.I))
            and bool(re.search(r'\b(?:count|number|how many)\b', question, re.I))
            and bool(re.search(r'\b(?:agree|match|inconsisten\w*|conflict\w*|listed|list)\b', question, re.I)))


def _capital_expenditure_subject(question):
    """A narrow terminology bridge, not a positive/negative answer rule."""
    if not re.search(r'\b(?:capex|capital\s+expenditure|upfront\s+capital)\b', question, re.I):
        return None
    match = re.search(r'\b(?:(?:public|private|hybrid)\s+)?cloud\b', question, re.I)
    return match.group(0) if match else None


def _capital_prose_candidates(subject, candidates, scope):
    """Keep source prose about the requested cost attribute; reject table labels.

    Both positive and negative source relations qualify. Selection is not a
    finding that a claim is true; ordinary generation/grounding still decides.
    A row saying only "Public Cloud / None" is deliberately insufficient here.
    """
    chosen, seen = [], set()
    requested = re.match(r'(public|private|hybrid)\s+cloud', subject, re.I)
    for item in candidates:
        chunk = item['chunk']; content = chunk[3]
        if chunk[0] in seen or chunk[1] not in scope or not re.search(r'\bcloud\b', content, re.I):
            continue
        qualifiers = set(re.findall(r'\b(public|private|hybrid)\s+cloud\b', content.casefold()))
        if requested and qualifiers and requested[1].casefold() not in qualifiers:
            continue
        relation = re.search(r'\b(?:avoids?|requires?|needs?|without|no)\b[^.!?;]{0,50}'
                             r'\b(?:capex|capital\s+expenditure|upfront)\b', content, re.I)
        if relation:
            chosen.append(item); seen.add(chunk[0])
        if len(chosen) == 2:
            break
    return chosen


def _matching_section_candidates(question, candidates, scope):
    """Prefer actual requested headings over summaries merely naming a section.

    Flattened PDF text retains many colon-terminated headings even when line
    breaks disappear. Matching uses only declared question terms and the actual
    candidate text; no document-specific titles or golden facts are embedded.
    """
    terms = _terms(question)
    matches, seen = [], set()
    for index, item in enumerate(candidates):
        chunk = item['chunk']
        if chunk[1] not in scope or chunk[0] in seen:
            continue
        seen.add(chunk[0])
        best = None
        for heading in re.findall(r'(?<!\w)([A-Z][A-Za-z0-9 &/()–-]{2,100}):', chunk[3]):
            heading_terms = _terms(heading)
            shared = len(terms & heading_terms)
            fraction = shared / len(heading_terms) if heading_terms else 0
            if shared >= 2 and fraction >= 2 / 3:
                score = (shared, fraction)
                if best is None or score > best:
                    best = score
        if best is not None:
            matches.append((best, index, item))
    matches.sort(key=lambda row: (-row[0][0], -row[0][1], row[1]))
    return [item for _, _, item in matches[:2]]


def _facet_retained(retrieval, margin, minimum):
    rows = retrieval['results']
    if not rows or 'rerank_score' not in rows[0]:
        return rows[:2]
    best = rows[0]['rerank_score']
    if minimum is not None and best < minimum:
        return []
    return [item for item in rows if item.get('rerank_score', best) >= best - margin][:2]


def _adjacent_chunks(anchor, scope, owner):
    """At most one preceding and one following chunk in the same owned source."""
    from services.database import get_connection
    rows = []
    with get_connection() as conn:
        for comparator, order in (('<', 'DESC'), ('>', 'ASC')):
            rows.extend(conn.execute(f'''
                SELECT c.id, c.document_name, c.page_number, c.content
                FROM document_chunks c
                JOIN document_chunks a ON a.id=%s AND a.owner_id=c.owner_id
                    AND a.document_id=c.document_id
                JOIN documents d ON d.id=c.document_id AND d.owner_id=c.owner_id
                WHERE c.owner_id=%s AND d.owner_id=%s AND d.status='ready'
                    AND c.document_name=ANY(%s)
                    AND (c.page_number,c.chunk_id,c.id) {comparator}
                        (a.page_number,a.chunk_id,a.id)
                ORDER BY c.page_number {order}, c.chunk_id {order}, c.id {order}
                LIMIT 1
            ''', (anchor[0], owner, owner, scope)).fetchall())
    return rows


def _pack(results, max_chunks, max_chars):
    chosen, seen_ids, seen_content, used, dropped = [], set(), set(), 0, []
    for item in results:
        chunk = item['chunk']
        content = chunk[3].strip()
        normalized = ' '.join(content.casefold().split())
        if chunk[0] in seen_ids or normalized in seen_content or not content:
            continue
        seen_ids.add(chunk[0]); seen_content.add(normalized)
        if len(chosen) >= max_chunks:
            dropped.append({'chunk_id': chunk[0], 'reason': 'max_chunks'})
            continue
        if chosen and used + len(content) > max_chars:
            dropped.append({'chunk_id': chunk[0], 'reason': 'character_budget'})
            continue
        # Preserve the original strongest anchor if it alone exceeds budget;
        # existing context assembly performs its established safe truncation.
        chosen.append(item)
        used += len(content)
    return chosen, dropped


def recover_complementary_evidence(question, search_query, retained, initial,
                                   search_fn, *, top_k=5, max_chunks=8,
                                   max_chars=12000, document_names=None):
    """Recover only explicit compound/comparison/enumeration requests.

    Result includes policy diagnostics. Tenant scope is required; every new
    search is restricted to explicitly named documents or the sole retained
    source. Keep the original top anchor, one anchor per facet, then relevant
    adjacent section chunks before additional redundant same-page passages.
    """
    from services.tenant_context import current_owner
    from services.request_coverage import decompose_question
    from services.v2_page_context import enumeration_request
    from services import retrieval_config as cfg
    from services.request_budget import check_deadline
    owner = current_owner()
    unchanged = {'results': retained, 'policy': POLICY, 'changed': False, 'facet_queries': 0}
    if owner is None or not retained or max_chunks <= 0:
        return unchanged
    facets = decompose_question(search_query or question, max_facets=3)
    structural_count = _structural_count_request(question)
    enumeration = enumeration_request(question) or structural_count
    capital_subject = _capital_expenditure_subject(search_query or question)
    if not facets and not enumeration and not capital_subject:
        return unchanged
    scope = document_names if document_names is not None else explicit_document_scope(search_query or question)
    if scope == []:
        return {**unchanged, 'results': [], 'changed': bool(retained), 'reason': 'explicit_source_unavailable'}
    if scope is None:
        sources = {item['chunk'][1] for item in retained}
        if len(sources) != 1:
            trace_event('evidence_recovery', {'policy': POLICY, 'reason': 'ambiguous_source'})
            return unchanged
        scope = sorted(sources)
    scope = list(scope)
    originals = [item for item in retained if item['chunk'][1] in scope]
    if not originals:
        return unchanged
    primary, secondary, statuses, facet_status_by_id, facet_candidates = [], [], [], {}, []
    capital_matches = (_capital_prose_candidates(capital_subject, initial.get('results', []), scope)
                       if capital_subject else [])
    # Prefer evidence already retrieved and merely removed by the combined
    # query's score margin. Only an actual unresolved terminology gap permits
    # one extra local search, within the existing three-query recovery cap.
    capital_probe = None
    if capital_subject and not capital_matches and len(facets) < 3:
        capital_probe = f'{capital_subject} hosting CapEx upfront costs capital expenditure'
        facets.append(capital_probe)
    for index, facet in enumerate(facets):
        check_deadline()
        retrieval = search_fn(facet, top_k=min(3, max(1, top_k)), document_names=scope)
        facet_rows = [item for item in _facet_retained(retrieval, cfg.RERANK_SCORE_MARGIN, cfg.RERANK_MIN_SCORE)
                      if item['chunk'][1] in scope]
        statuses.append(retrieval['rerank_status'])
        facet_candidates.extend(retrieval['results'])
        for item in retrieval['results']:
            facet_status_by_id[item['chunk'][0]] = retrieval['rerank_status']
        if facet == capital_probe:
            # Expanded vocabulary supplies no answer: require actual positive
            # or negative source prose rather than accepting a weak table.
            facet_rows = _capital_prose_candidates(capital_subject, retrieval['results'], scope)
            capital_matches.extend(facet_rows)
        trace_candidates('facet_retained', facet_rows)
        if facet_rows:
            primary.append(facet_rows[0]); secondary.extend(facet_rows[1:])
    # Original ranks apply to the combined query, not each requested facet.
    # Reserve their first anchor and then interleave independent facet anchors.
    section_matches = (_matching_section_candidates(question, initial.get('results', []) + facet_candidates, scope)
                       if enumeration else [])
    trace_candidates('section_identity_recovery', section_matches)
    trace_candidates('capital_prose_recovery', capital_matches)
    anchors, _ = _pack(originals[:1] + capital_matches + section_matches + primary, max_chunks, max_chars)
    neighbours = []
    if enumeration:
        query_terms = _terms(question)
        seen_anchor = set()
        queue = [(item, 0) for item in anchors[:2]]
        examined = 0
        while queue and examined < (4 if structural_count else 2):
            item, depth = queue.pop(0)
            anchor = item['chunk']
            if anchor[0] in seen_anchor:
                continue
            seen_anchor.add(anchor[0]); examined += 1; check_deadline()
            for cid, doc, page, content in _adjacent_chunks(anchor, scope, owner):
                if content and query_terms & _terms(content):
                    neighbour = {'chunk': (cid, doc, page, content, None),
                                 'rrf_score': None, 'context_policy': POLICY}
                    neighbours.append(neighbour)
                    if structural_count and depth < 1 and cid not in seen_anchor:
                        queue.append((neighbour, depth + 1))
    chosen, dropped = _pack(anchors + neighbours + originals[1:] + secondary, max_chunks, max_chars)
    trace_candidates('complementary_recovery', chosen)
    trace_event('evidence_recovery', {'policy': POLICY, 'scope': scope,
                'before_ids': [x['chunk'][0] for x in retained],
                'after_ids': [x['chunk'][0] for x in chosen],
                'facet_queries': len(facets), 'facet_rerank_statuses': statuses,
                'budget_dropped': dropped})
    # Do not label newly admitted unranked facet evidence as verified ranking.
    original_ids = {item['chunk'][0] for item in retained}
    admitted_statuses = [facet_status_by_id[item['chunk'][0]] for item in chosen
                         if item['chunk'][0] not in original_ids and item['chunk'][0] in facet_status_by_id]
    merged_status = initial.get('rerank_status', 'skipped')
    degraded = [status for status in admitted_statuses if status != 'ok']
    if degraded:
        merged_status = next((status for status in degraded if status.startswith('failed:')), degraded[0])
    return {'results': chosen, 'policy': POLICY, 'changed': chosen != retained,
            'facet_queries': len(facets), 'facet_rerank_statuses': statuses,
            'rerank_status': merged_status}
