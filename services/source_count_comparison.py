"""Narrow source-bound phase-count comparisons; no model or database calls.

This proves only that a stated count is exceeded by explicitly observed,
consecutive numbered headings on one source page. It does not prove that a
retrieval bundle contains every section, or interpret arbitrary contradictions.
"""
import re

POLICY = 'v2-source-bound-phase-count-comparison/1'
_REQUEST = re.compile(r'\b(?:phase\s+count|number\s+of\s+phases)\b', re.I)
_COMPARE = re.compile(r'\b(?:agree|consistent|inconsisten\w*|disagree\w*|contradict\w*|match|compare)\b', re.I)
_LISTED = re.compile(r'\b(?:list(?:ed)?|enumerat\w*|actual)\b', re.I)
_EXTRA_REQUEST = re.compile(r'\b(?:also|additionally|as\s+well\s+as|and\s+(?:what|who|where|how|give|list|show|provide))\b', re.I)
_DECLARED = re.compile(r'(?P<qualifier>roughly\s+|approximately\s+|about\s+|~\s*)?(?P<count>\d{1,2})\s+phases\b', re.I)
_HEADING = re.compile(r'(?:^|[\n•;])\s*Phase\s+(?P<number>\d{1,2})\s*[–—:-]\s*(?P<title>[^\n•;:(]{2,90})(?=[(:])', re.I)
_NEGATION = re.compile(r'\b(?:not|no|never|without|rather\s+than|instead\s+of|at\s+least|at\s+most|more\s+than|fewer\s+than)\b', re.I)


def source_count_comparison(question, sources):
    """Return provenance-bearing proof only for a uniquely bound disagreement.

    Count equality is deliberately not a proof of agreement: more headings may
    exist outside this bounded context. Different documents/pages, duplicate
    ordinals with different titles, gaps and negated/count-range declarations
    are ambiguous and produce no proof.
    """
    if (not isinstance(question, str) or _EXTRA_REQUEST.search(question)
            or not (_REQUEST.search(question) and _COMPARE.search(question) and _LISTED.search(question))):
        return None
    groups = {}
    for source in sources or []:
        content = source.get('content', '')
        if not isinstance(content, str) or not source.get('ref') or not source.get('document_name') or source.get('page_number') is None:
            continue
        groups.setdefault((source['document_name'], source['page_number']), []).append(source)
    proofs = []
    for (document, page), items in groups.items():
        declarations, headings = [], {}
        ambiguous = False
        for source in items:
            text = source['content']
            for match in _DECLARED.finditer(text):
                before = text[max(0, match.start() - 35):match.start()]
                # Do not reinterpret a range, alternative, exclusion or lower
                # bound as a single positively asserted count.
                if _NEGATION.search(before) or re.search(r'(?:\d\s*[–—/-]|\b(?:or|to))\s*$', before, re.I):
                    ambiguous = True
                    continue
                declarations.append((int(match['count']), (match['qualifier'] or '').strip(), source['ref']))
            for match in _HEADING.finditer(text):
                number = int(match['number'])
                title = ' '.join(match['title'].strip().casefold().split())
                headings.setdefault(number, {}).setdefault(title, set()).add(source['ref'])
        if ambiguous or not declarations or not headings or any(len(titles) != 1 for titles in headings.values()):
            continue
        counts = {item[0] for item in declarations}
        if len(counts) != 1:
            continue
        declared = next(iter(counts))
        last = max(headings)
        if not 1 <= declared < last <= 20 or set(headings) != set(range(1, last + 1)):
            continue
        # Distinct passages may overlap; duplicate identical headings count
        # once. Their original reference provenance remains intact.
        ordered_refs = [source['ref'] for source in items]
        heading_refs = set().union(*(next(iter(titles.values())) for titles in headings.values()))
        refs = [ref for ref in ordered_refs if ref in heading_refs]
        stated_refs = [ref for ref in ordered_refs if ref in {item[2] for item in declarations}]
        qualifiers = {item[1] for item in declarations}
        if len(qualifiers) != 1:
            continue
        proofs.append({'policy': POLICY, 'document_name': document, 'page_number': page,
                       'stated_count': declared, 'qualifier': next(iter(qualifiers)),
                       'observed_consecutive_headings': list(range(1, last + 1)),
                       'stated_refs': stated_refs, 'heading_refs': refs,
                       'evidence_refs': list(dict.fromkeys(stated_refs + refs)),
                       'scope': 'observed source headings exceed stated count; not exhaustive section discovery'})
    return proofs[0] if len(proofs) == 1 else None


def comparison_answer(proof):
    """Use only numbers copied from the count and actual numbered headings."""
    qualifier = proof['qualifier'] + ' ' if proof['qualifier'] else ''
    stated = ''.join('[' + ref + ']' for ref in proof['stated_refs'])
    headings = ''.join('[' + ref + ']' for ref in proof['heading_refs'])
    all_refs = ''.join('[' + ref + ']' for ref in proof['evidence_refs'])
    last = proof['observed_consecutive_headings'][-1]
    return (f"The source states {qualifier}{proof['stated_count']} phases {stated}. "
            f"The retrieved passages explicitly list consecutive headings from Phase 1 through Phase {last} {headings}. "
            f"This presents an inconsistency between the stated phase count and the listed phase headings {all_refs}.")
