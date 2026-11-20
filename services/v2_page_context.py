"""Bounded same-page continuity for enumerations split across small chunks.

This is a v2 context-selection policy, not a new relevance score. Only pages
already retained by the ordinary rank/filter path can supply adjacent evidence.
"""
import re

POLICY = 'v2-enumeration-page-continuity/1'
_ENUMERATION = re.compile(r'\b(?:list|enumerate)\b|\b(?:all|each|every)\s+(?:\w+\s+){0,2}(?:phases?|steps?|features?|stages?|requirements?|risks?)\b', re.I)


def enumeration_request(question):
    return isinstance(question, str) and bool(_ENUMERATION.search(question))


def expand_page_context(question, results, max_chunks=8):
    """Keep originals; append owned ready same-page passages within the budget.

    At most two anchor pages are read, and each read is limited to budget+1.
    Oversized pages use the nearest chunk positions instead of the page prefix.
    No other tenant, document, page or unranked search result becomes an anchor.
    """
    if not enumeration_request(question) or not results or len(results) >= max_chunks:
        return results
    from services.tenant_context import current_owner
    owner = current_owner()
    if owner is None:
        return results
    from services.database import get_connection
    expanded = list(results)
    seen = {item['chunk'][0] for item in results}
    anchors = []
    for item in results:
        chunk = item['chunk']
        page = (chunk[1], chunk[2])
        if chunk[2] is not None and page not in [a[1:3] for a in anchors]:
            anchors.append(chunk)
    with get_connection() as conn:
        for anchor in anchors[:2]:
            if len(expanded) >= max_chunks:
                break
            rows = conn.execute('''
                SELECT c.id, c.document_name, c.page_number, c.content, c.chunk_id
                FROM document_chunks c
                JOIN documents d ON d.id=c.document_id AND d.owner_id=c.owner_id
                JOIN document_chunks a ON a.id=%s AND a.owner_id=c.owner_id
                    AND a.document_id=c.document_id AND a.page_number=c.page_number
                WHERE c.owner_id=%s AND d.owner_id=%s AND d.status='ready'
                    AND c.document_name=%s AND c.page_number=%s
                ORDER BY abs(c.chunk_id-a.chunk_id), c.chunk_id, c.id
                LIMIT %s
            ''', (anchor[0], owner, owner, anchor[1], anchor[2], max_chunks + 1)).fetchall()
            for cid, doc, page, content, position in rows:
                if cid in seen or not content or not content.strip():
                    continue
                seen.add(cid)
                expanded.append({'chunk': (cid, doc, page, content, None),
                                 'rrf_score': None, 'context_policy': POLICY})
                if len(expanded) >= max_chunks:
                    break
    return expanded
