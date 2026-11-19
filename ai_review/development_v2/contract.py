"""Development-only response-behavior checks, not a scorer or entailment judge.

``expected_kind`` is fixed from case/source review before an experiment; never
derive it from model output. This checks status and citation identity only.
Factual correctness and frozen v1 diagnostic scores remain separate checks.
No live evaluation, original-result reinterpretation or formal acceptance occurs.
"""

EXPECTED_STATUSES = {
    'supported_fact': 'answered',
    'explicit_negative_fact': 'answered',
    'missing_information': 'abstained',
    'partial_information': 'partial',
}


def assess_behavior(expected_kind, response, known_sources):
    """Return a diagnostic verdict for a predeclared source-semantic category.

    Valid citations may support a document-omission statement. Their presence
    alone must not force that response to ``answered`` or ``partial``. Known
    facts, including explicit world negatives, still require valid citations.
    """
    if expected_kind not in EXPECTED_STATUSES:
        raise ValueError('unknown predeclared response kind')
    if not isinstance(response, dict):
        raise ValueError('response object required')
    issues = []
    if response.get('status') != EXPECTED_STATUSES[expected_kind]:
        issues.append('status_mismatch')
    if not isinstance(response.get('answer'), str) or not response['answer'].strip():
        issues.append('missing_answer')
    citations = response.get('citations')
    if not isinstance(citations, list):
        issues.append('invalid_citation_shape')
        citations = []
    if expected_kind != 'missing_information' and not citations:
        issues.append('grounded_fact_citation_required')
    source_index = {s['ref']: s for s in known_sources}
    seen = set()
    for citation in citations:
        if not isinstance(citation, dict):
            issues.append('invalid_citation_shape')
            continue
        ref = citation.get('ref')
        source = source_index.get(ref) if isinstance(ref, str) else None
        if source is None or ref in seen:
            issues.append('unknown_or_duplicate_citation')
            continue
        seen.add(ref)
        if (citation.get('document') != source.get('document_name')
                or citation.get('page') != source.get('page_number')
                or citation.get('chunk_id') != source.get('chunk_id')
                or type(citation.get('page')) is not type(source.get('page_number'))
                or type(citation.get('chunk_id')) is not type(source.get('chunk_id'))):
            issues.append('citation_source_mismatch')
    validation = response.get('validation')
    if validation is not None:
        if (not isinstance(validation, dict) or validation.get('valid') is not True
                or validation.get('invalid_refs')):
            issues.append('citation_validation_failed')
    elif citations:
        issues.append('citation_validation_failed')
    return {
        'behavior_contract_pass': not issues,
        'issues': sorted(set(issues)),
        'expected_status': EXPECTED_STATUSES[expected_kind],
        'scope': 'DEVELOPMENT_ONLY',
        'formal_acceptance': False,
        'limitation': 'Status/citation identity only; source semantics and factual correctness need their own verification.',
    }
