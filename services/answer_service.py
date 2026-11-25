"""
Grounded answer generation: prompt -> Gemini -> parse -> citation validation
-> bounded regeneration -> safe fallback. Citations are kept as structured
data next to the prose so they can be validated against the retrieval result.
"""
import os
import re

from services import retrieval_config as cfg
from services.answer_prompt import REFUSAL_MESSAGE, build_answer_prompt
from services.citation_service import (
    ABSTAIN_PHRASES,
    answer_with_citations,
    drop_uncited_claims,
    evidence_profile,
    extract_citation_refs,
    remove_invalid_refs,
    split_sentences,
    strip_citations,
    uncited_claim_sentences,
    validate_answer_citations,
)
from services.context_assembly_service import source_index
from services.grounding_service import drop_unsupported_number_sentences, unsupported_numbers
from services.request_budget import RequestDeadlineExceeded, check_deadline

UNVERIFIED_MESSAGE = (
    "I found related passages in your documents, but I couldn't produce an "
    "answer I can verify against them, so I won't guess. Please rephrase or "
    "ask about a more specific part."
)

ERROR_MESSAGE = (
    "I couldn't generate a reliable answer right now. Please try again."
)
BOUNDED_REFUSAL = "I couldn't establish that from the available evidence."

_TAG_RE = re.compile(r"^\s*\[(DOCUMENT|MEMORY|MIXED)\]\s*", re.I)

_ABSTAIN_PHRASES = ABSTAIN_PHRASES      # single shared list (citation_service)
_CONFLICT_PHRASES = ("disagree", "conflict", "differ", "inconsistent", "contradict")
_EMPLOYMENT = re.compile(r'\b(?:employ(?:ed|ment)|work(?:ed|ing)?|tenure|experience)\b', re.I)
_DURATION_VALUE = re.compile(
    r'\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)'
    r'\s*[- ]\s*(?:months?|years?|weeks?|days?)\b', re.I)
_SOURCE_DISAGREEMENT = re.compile(
    r'\b(?:sources?|passages?|documents?|reports?|roadmap|sections?|header|list)\b'
    r'[^.!?]{0,100}\b(?:disagree|conflict|contradict|(?:is|are|appears?|seems?)\s+(?:internally\s+)?inconsistent)\b'
    r'|\b(?:contradiction|inconsistency|conflict|disagreement)\s+(?:between|in|within)\s+'
    r'[^.!?]{0,60}\b(?:sources?|passages?|documents?|reports?|roadmap|sections?|header|list|'
    r'(?:stated|reported|documented)\s+(?:\w+\s+){0,2}(?:count|number|total))\b',
    re.I,
)


def has_abstention_language(text: str) -> bool:
    return evidence_profile(text)[0] > 0


def classify_status(answer: str, cited_docs: set, has_citations: bool, sources=None) -> str:
    """Report pure insufficiency separately from cited negative facts and partials."""
    missing, facts = evidence_profile(answer, sources)

    lowered = answer.lower()

    if (os.getenv('RAG_V2') != '1' and has_citations and len(cited_docs) >= 2
            and any(p in lowered for p in _CONFLICT_PHRASES)):
        return "conflict"
    if (os.getenv('RAG_V2') == '1' and has_citations and not missing
            and _SOURCE_DISAGREEMENT.search(answer)
            and not re.search(r"\b(?:no|not|never|doesn't|don't)\s+(?:\w+\s+){0,2}(?:conflict|disagree|contradict|inconsistent)", lowered)
            ):
        # One PDF may contradict itself within a single passage or between
        # sections. This reports explicitly disclosed source disagreement;
        # neither this label nor citation syntax establishes entailment.
        return "conflict"
    if missing:
        return "partial" if facts else "abstained"
    return "answered"


def _result(answer, status, tag=None, citations=None, validation=None,
            attempts=0, issues=None):
    citations = citations or []
    result = {
        "answer": answer,
        "status": status,
        "tag": tag,
        "citations": citations,
        # backward compatible shape used by main.py: document + page (+ extras)
        "sources": [
            {"document": c["document"], "page": c["page"],
             "chunk_id": c["chunk_id"], "ref": c["ref"]}
            for c in citations
        ],
        "validation": validation,
        "attempts": attempts,
        "issues": issues or [],
    }
    from services.evidence_trace import trace_event
    trace_event('answer_result', {
        'status': status, 'tag': tag, 'attempts': attempts,
        'issues': result['issues'], 'citations': citations,
        'validation': validation,
    }, raw={'answer': answer})
    return result


def _coverage(question, sources, body):
    if os.getenv('RAG_V2') != '1' or not sources:
        return None
    from services.request_coverage import request_coverage
    report = request_coverage(question, sources, body)
    from services.source_count_comparison import source_count_comparison
    comparison = source_count_comparison(question, sources)
    if comparison is not None:
        report['source_count_comparison'] = comparison
        if has_abstention_language(body) and not evidence_profile(body, sources)[1]:
            # An explicit source-bound count comparison exists. A model's
            # refusal cannot establish source absence after a citation repair.
            report['concrete_missing'] = report['concrete_missing'] + [{
                'id': 'source_phase_count_comparison',
                'label': 'the stated phase count versus the explicitly listed phase headings',
                'evidence_refs': comparison['evidence_refs'],
            }]
    return report


def _count_comparison_fallback(question, sources, attempts, last_issues):
    if os.getenv('RAG_V2') != '1':
        return None
    from services.source_count_comparison import source_count_comparison, comparison_answer
    proof = source_count_comparison(question, sources)
    if proof is None:
        return None
    answer = comparison_answer(proof)
    validation = validate_answer_citations(answer, sources, require_citations=True)
    if not validation['valid'] or unsupported_numbers(answer, sources, question, check_uncited=True):
        return None
    checked = answer_with_citations(answer, sources)
    from services.evidence_trace import trace_event
    trace_event('source_count_comparison_fallback', {
        'policy': proof['policy'], 'attempts': attempts,
        'previous_issues': last_issues, 'evidence_refs': proof['evidence_refs'],
        'stated_count': proof['stated_count'],
        'observed_consecutive_headings': proof['observed_consecutive_headings'],
    }, raw={'proof': proof, 'answer': answer})
    return _result(checked['text'], 'conflict', 'DOCUMENT', checked['citations'],
                   validation, attempts, ['source_bound_count_comparison_fallback'])


def _with_coverage(result, question, sources):
    """Never report a mechanically known incomplete repair as complete."""
    report = _coverage(question, sources, result['answer'])
    if report is None:
        return result
    result['coverage'] = report
    if report.get('concrete_missing'):
        missing = ['missing_requested_item:' + item['id'] for item in report['concrete_missing']]
        result['issues'] = list(dict.fromkeys(result['issues'] + missing))
        if result['status'] == 'answered':
            result['status'] = 'partial'
        elif result['status'] == 'abstained':
            # Evidence exists for a requested item; do not present a failed
            # bounded generation as proof that the information is absent.
            result['answer'] = UNVERIFIED_MESSAGE
            result['status'] = 'unverified'
            result['citations'] = []
            result['sources'] = []
    if result['status'] in {'answered', 'partial'}:
        # An absent requested field can be disclosed without spending a
        # provider retry. The statement applies only to the selected evidence.
        unresolved = [item for item in report['facets']
                      if item['answer_mentions'] is False and not item.get('refused_supported_item')
                      and report['mode'] in {'fields', 'comparison'}
                      and (item['id'] in report['context_unobserved']
                           or any(item['id'] == missing['id'] for missing in report['concrete_missing']))]
        if unresolved:
            labels = ', '.join(item['label'] for item in unresolved)
            result['answer'] += (
                " I couldn't establish the following requested information from "
                f"the available evidence: {labels}."
            )
            result['status'] = 'partial'
            result['issues'] += ['unresolved_requested_item:' + item['id'] for item in unresolved]
    from services.evidence_trace import trace_event
    trace_event('answer_coverage', {
        'mode': report.get('mode'), 'status': result['status'],
        'missing_item_ids': [item['id'] for item in report.get('concrete_missing', [])],
        'caveat': report.get('caveat'),
    }, raw={'coverage': report, 'answer': result['answer']})
    return result


def with_source_locations(result):
    """Render only identities validated on the current, freshly resolved turn."""
    if result.get('status') not in {'answered', 'partial', 'conflict'}:
        return result
    citations = result.get('citations') or []
    refs = set(extract_citation_refs(result.get('answer', '')))
    locations = []
    for citation in citations:
        page, ref = citation.get('page'), citation.get('ref')
        if type(page) is not int or page < 1 or ref not in refs:
            continue
        # Keep two independent source identities even for the same page number.
        if (ref, page) not in locations:
            locations.append((ref, page))
    if not locations:
        return result
    text = ', '.join(f'page {page} [{ref}]' for ref, page in locations)
    return {**result, 'answer': result['answer'] + ' Source location: ' + text + '.'}


def _parse(raw):
    """Return (tag, body) or (None, '') for empty/malformed model output."""
    if not isinstance(raw, str) or not raw.strip():
        return None, ""

    text = raw.strip()
    match = _TAG_RE.match(text)

    if match:
        return match.group(1).upper(), text[match.end():].strip()

    return None, text


def _render_verified_duration(body, calculation, sources):
    """Only the deterministic renderer may add derived numbers, never the model."""
    if calculation is None:
        return body
    kept=[]
    for sentence in split_sentences(body):
        missing,facts=evidence_profile(sentence,sources)
        duration_gap=(missing and not facts
                      and re.search(r'\b(?:calculation|calculate[ds]?|duration|tenure|how long)\b',sentence,re.I)
                      and not re.search(r'\b(?:degree|education|institution|phone|telephone|salary|fax|budget|email|project|milestone|position|skills|team|cost)\b',sentence,re.I))
        if not duration_gap:
            kept.append(sentence)
    return ' '.join(kept+[calculation['answer']])


def _employment_claim(sentence):
    if _EMPLOYMENT.search(sentence) or re.search(r'\b(?:spent|duration|lasted|joined|start date)\b', sentence, re.I):
        return True
    timing = re.sub(r'^(?:it (?:is|was) |approximately |about )+', '',
                    strip_citations(sentence).strip(' .'), flags=re.I)
    return bool(_DURATION_VALUE.fullmatch(timing))


def _unsupported_employment_sentences(body, question, sources, calculation, incompatible_refs):
    """A model cannot turn a digit elsewhere in a passage into a work duration."""
    from services.tenure_calculation import duration_intent, joining_intent, employer_hint
    if not ((duration_intent(question) and _EMPLOYMENT.search(question)) or joining_intent(question)):
        return []
    by_ref = source_index(sources)
    employer = ' '.join(employer_hint(question) or [])
    bad = []
    for sentence in split_sentences(body):
        refs = set(extract_citation_refs(sentence))
        if not _employment_claim(sentence):
            continue
        if refs & incompatible_refs:
            bad.append(sentence)
            continue
        quantities = _DURATION_VALUE.findall(sentence)
        if not quantities:
            continue
        if calculation is not None:
            # The model was asked for the other fields only. Render all such
            # quantities through the verified calculator, including when the
            # same digit incidentally occurs in the source for another fact.
            bad.append(sentence)
            continue
        cited = [clause for ref in refs if ref in by_ref
                 for clause in re.split(r'(?<=[.!?])\s+|[;\n]+', by_ref[ref]['content'])
                 if (_EMPLOYMENT.search(clause) or (employer and employer in clause.casefold()))
                 and (not employer or employer in clause.casefold())]
        if not all(any(quantity.casefold() in passage.casefold() for passage in cited)
                   for quantity in quantities):
            bad.append(sentence)
    return bad


def _complete_document_task(result, question, sources, calculation):
    from services.tenure_calculation import duration_intent, has_additional_requests
    if (os.getenv('RAG_V2') == '1' and result['status'] in {'answered', 'partial'}
            and calculation is None and duration_intent(question) and _EMPLOYMENT.search(question)
            and not any(_DURATION_VALUE.search(sentence) and _employment_claim(sentence)
                        for sentence in split_sentences(result['answer']))):
        # A verified sourcing of dates is useful to a multi-part question,
        # but those operands do not by themselves fulfill a duration request.
        asks_other = has_additional_requests(question) or bool(re.search(
            r'\b(?:when|start and end dates?|start date|joining date)\b', question, re.I))
        if asks_other:
            result['status'] = 'partial'
            if not has_abstention_language(result['answer']):
                result['answer'] += " I couldn't establish the employment duration from the available evidence."
        else:
            result = _result(BOUNDED_REFUSAL, 'abstained', 'DOCUMENT', attempts=result['attempts'],
                             issues=result['issues'] + ['requested_duration_not_established'])
    return _with_coverage(result, question, sources)


def _with_verified_duration(result, calculation, sources, question):
    if calculation is None or result['status'] in {'error','unverified'}:
        return result
    body=_render_verified_duration(result['answer'],calculation,sources)
    validation=validate_answer_citations(body,sources,require_citations=True)
    if not validation['valid']:
        return result
    checked=answer_with_citations(body,sources)
    # Month precision is a disclosed calculation limit, not an unanswered part
    # of a question that requested years/months. Other evidence gaps still count.
    status_calculation=calculation
    if not re.search(r'\bdays?\b',question,re.I):
        status_calculation={**calculation,'answer':calculation['answer'].replace('; exact days are not specified','')}
    status_body=_render_verified_duration(result['answer'],status_calculation,sources)
    return {**result,'answer':checked['text'],'citations':checked['citations'],
            'sources':[{'document':c['document'],'page':c['page'],'chunk_id':c['chunk_id'],'ref':c['ref']}
                       for c in checked['citations']],
            'status':classify_status(status_body,{c['document'] for c in checked['citations']},True,sources),
            'validation':validation,'calculation':calculation['calculation']}


def generate_grounded_answer(
    question: str,
    bundle: dict,
    question_type: str,
    generate_fn,
    history: list | None = None,
    memory_summary: str = "",
    *,
    as_of=None,
) -> dict:
    check_deadline()
    sources = bundle.get("sources", [])
    context_text = bundle.get("context_text", "")
    calculation=None
    incompatible_refs = set()
    v2_grounded = os.getenv('RAG_V2') == '1' and question_type != 'MEMORY'
    grounding_question = '' if v2_grounded else question
    if v2_grounded:
        from services.tenure_calculation import calculation_from_sources, incompatible_employment_refs
        calculation = calculation_from_sources(question, sources, history, as_of=as_of)
        incompatible_refs = set(incompatible_employment_refs(question, sources, history))

    # Nothing retrieved for a document question: never ask the model to
    # "answer anyway" (that is where general knowledge leaks in).
    if question_type == "DOCUMENT" and not sources:
        return _result(BOUNDED_REFUSAL if v2_grounded else REFUSAL_MESSAGE, "abstained", tag="DOCUMENT")
    if v2_grounded:
        from services.explicit_source_update import current_amount_answer
        update = current_amount_answer(question, sources)
        if update:
            checked = answer_with_citations(update, sources)
            if checked['validation']['valid'] and not unsupported_numbers(update, sources):
                return _result(update, 'answered', 'DOCUMENT', checked['citations'],
                               checked['validation'], issues=['explicit_source_update'])

    retries = max(0, cfg.ANSWER_MAX_RETRIES)
    attempts = 1 + (min(1, retries) if v2_grounded else retries)
    feedback = None
    last_issues = []
    last_body, last_tag = "", None

    for attempt in range(1, attempts + 1):
        check_deadline()
        prompt = build_answer_prompt(
            question, sources, context_text, history, memory_summary, feedback,
            calculation_managed=calculation is not None,
        )
        from services.evidence_trace import trace_event
        trace_event('generation_request', {
            'attempt': attempt, 'question_type': question_type,
            'source_refs': [s['ref'] for s in sources],
            'context_characters': len(context_text),
        }, raw={'prompt': prompt, 'context_text': context_text, 'sources': sources})

        try:
            raw = generate_fn(prompt)
            check_deadline()
        except RequestDeadlineExceeded:
            raise
        except Exception as error:   # retry/fallback already happened inside generate_answer
            last_issues = [f"generation_error: {type(error).__name__}"]
            if v2_grounded:
                return _result(ERROR_MESSAGE, "error", None, [], None, attempt, last_issues)
            feedback = None
            continue
        trace_event('answer_generated', {'attempt': attempt}, raw={'answer': raw})

        tag, body = _parse(raw)

        if not body:
            last_issues = ["empty_answer"]
            feedback = "Your previous reply was empty. Reply with a tag and an answer."
            continue

        last_tag, last_body = tag, body
        is_refusal = body.strip() == REFUSAL_MESSAGE or (v2_grounded and body.strip() == BOUNDED_REFUSAL)
        # A DOCUMENT/MIXED question with retrieved sources needs citations,
        # whatever tag the model chose (a [MEMORY] tag must not bypass grounding).
        needs_citations = bool(sources) and question_type != "MEMORY" and not is_refusal

        # Nothing was retrieved, yet the reply claims document facts: reject.
        if (not sources and tag == "DOCUMENT" and not is_refusal
                and not (has_abstention_language(body) and not uncited_claim_sentences(body))):
            last_issues = ["document_claim_without_sources"]
            feedback = (
                "Problems found: document_claim_without_sources. No document passages "
                "were retrieved, so you cannot state document facts. Answer only from "
                "memory/conversation with the [MEMORY] tag, or say the documents do not "
                "contain the answer."
            )
            continue

        checked = answer_with_citations(body, sources)
        # Numbers are checked whenever document grounding applies, including in
        # an abstention that the next rule exempts from needing a citation.
        check_uncited_numbers = needs_citations

        # A pure abstention / insufficiency statement needs no citation.
        # Only when EVERY sentence is an insufficiency statement; a factual
        # sentence that merely contains "not available" still needs a citation.
        if (needs_citations and not checked["citations"]
                and has_abstention_language(body)
                and validate_answer_citations(body, sources, require_citations=False)["uncited_sentences"] == 0):
            needs_citations = False

        validation = validate_answer_citations(body, sources, require_citations=needs_citations)

        # Stage 6: every number must be written in the passage it cites (or in the question).
        # For document answers an assertion in the question is never numerical
        # evidence. Application-derived values are added only after this check.
        ungrounded = unsupported_numbers(body, sources, grounding_question, check_uncited=check_uncited_numbers)
        if ungrounded:
            validation = {**validation, "valid": False,
                          "issues": validation["issues"] + ["unsupported_number"]}
        bad_duration = (_unsupported_employment_sentences(body, question, sources, calculation, incompatible_refs)
                        if v2_grounded else [])
        if bad_duration:
            validation = {**validation, 'valid': False,
                          'issues': validation['issues'] + ['unverified_employment_duration']}

        coverage = _coverage(question, sources, _render_verified_duration(body,calculation,sources)) if question_type != 'MEMORY' else None
        coverage_missing = coverage.get('concrete_missing', []) if coverage else []
        invalid_fields = [item['id'] for item in (coverage or {}).get('facets', [])
                          if item.get('unsupported_answer_clauses')]
        if invalid_fields:
            validation = {**validation, 'valid': False, 'issues': validation['issues'] +
                          ['unsupported_requested_value:' + field for field in invalid_fields]}
        if coverage_missing:
            validation = {**validation, 'valid': False,
                          'issues': validation['issues'] + ['missing_requested_item:' + item['id'] for item in coverage_missing]}
        trace_event('answer_validation', {
            'attempt': attempt, 'valid': validation['valid'],
            'issues': validation['issues'],
            'missing_item_ids': [item['id'] for item in coverage_missing],
        }, raw={'coverage': coverage, 'answer': body})

        if validation["valid"]:
            cited_docs = {c["document"] for c in checked["citations"]}
            status = classify_status(body, cited_docs, bool(checked["citations"]), sources)
            final_tag = tag or ("DOCUMENT" if checked["citations"] else "MEMORY")
            result = _result(checked["text"], status, final_tag,
                             checked["citations"], validation, attempt)
            result = _with_verified_duration(result,calculation,sources,question)
            return _complete_document_task(result, question, sources, calculation) if question_type != 'MEMORY' else result

        last_issues = validation["issues"]
        feedback = (
            "Problems found: " + ", ".join(validation["issues"]) +
            f". Cite only these references: {', '.join(s['ref'] for s in sources) or 'none'}. "
            "Do not write page numbers or filenames. If the passages do not "
            "contain the answer, say so instead of guessing."
        )
        if coverage_missing:
            from services.request_coverage import coverage_feedback
            feedback += ' ' + coverage_feedback(coverage)
        if bad_duration:
            feedback += (' State work duration only when directly given with its units in the cited '
                         'passage. When the application has verified an employment calculation, '
                         'leave the duration to the application and answer the other requested parts.')
        if invalid_fields:
            feedback += (' Check the cited value and units for ' + ', '.join(invalid_fields) +
                         '. A component or an unrelated amount cannot establish the requested value.')
        if ungrounded:
            numbers = sorted({n for _, missing in ungrounded for n in missing})
            feedback += (
                f" These numbers are not written in the passages you cited: {', '.join(numbers)}. "
                "Use only numbers that appear in the cited passage; do not calculate, "
                "estimate or carry over numbers from elsewhere."
            )

    # ---- bounded retries exhausted: safe fallback ---------------------------
    check_deadline()
    if last_body:
        if (question_type != 'MEMORY' and (
                has_abstention_language(last_body) or 'uncited_claim' in last_issues)):
            comparison = _count_comparison_fallback(question, sources, attempts, last_issues)
            if comparison is not None:
                return _with_coverage(comparison, question, sources)
        rejected_sentences = set(_unsupported_employment_sentences(last_body, question, sources, calculation, incompatible_refs)
                                 if v2_grounded else [])
        if v2_grounded:
            rejected_sentences.update(clause for item in (_coverage(question, sources, last_body) or {}).get('facets', [])
                                      for clause in item.get('unsupported_answer_clauses', []))
        if rejected_sentences:
            last_body = ' '.join(s for s in split_sentences(last_body) if s not in rejected_sentences)
        if not last_body and calculation is not None:
            from services.tenure_calculation import has_additional_requests
            result = _with_verified_duration(_result('', 'answered', 'DOCUMENT', attempts=attempts,
                                                      issues=last_issues), calculation, sources, question)
            if has_additional_requests(question):
                result['answer'] += " I couldn't establish the remaining requested details from the available evidence."
                result['status'] = 'partial'
            return _with_coverage(result, question, sources)
        result = _fallback(last_body, last_tag, last_issues, sources, grounding_question, attempts)
        result = _with_verified_duration(result,calculation,sources,question)
        return _complete_document_task(result, question, sources, calculation) if question_type != 'MEMORY' else result

    return _result(ERROR_MESSAGE, "error", None, [], None, attempts, last_issues)


def _fallback(last_body, last_tag, last_issues, sources, question, attempts):
    """Repair the last reply, accept a pure abstention, or return UNVERIFIED."""
    # Repair: drop invalid refs, then drop every sentence left without a
    # citation (including a claim whose only citation was fabricated) and
    # every sentence with a number its evidence does not contain. Keep the
    # answer only if valid citations remain and nothing fabricated was
    # written in prose.
    without_bad_refs = remove_invalid_refs(last_body, set(source_index(sources)))
    dropped = uncited_claim_sentences(without_bad_refs)
    repaired = drop_uncited_claims(without_bad_refs) if dropped else without_bad_refs
    number_dropped = unsupported_numbers(repaired, sources, question)
    if number_dropped:
        repaired = drop_unsupported_number_sentences(repaired, sources, question)
    v = validate_answer_citations(repaired, sources, require_citations=True)
    issues_blocking = [i for i in v["issues"] if i != "invalid_ref"]

    if v["valid"] and not issues_blocking:
        checked = answer_with_citations(repaired, sources)
        cited_docs = {c["document"] for c in checked["citations"]}
        repair_issues = ["repaired:" + ",".join(last_issues)]
        if dropped:
            repair_issues.append(f"dropped_uncited_sentences:{len(dropped)}")
        if number_dropped:
            repair_issues.append(f"dropped_unsupported_number_sentences:{len(number_dropped)}")
        return _result(checked["text"],
                       classify_status(repaired, cited_docs, True, sources),
                       last_tag or "DOCUMENT", checked["citations"], v,
                       attempts, issues=repair_issues)

    if has_abstention_language(last_body) and not any(
        i.startswith(("unknown_", "invalid")) for i in last_issues
    ) and validate_answer_citations(
        last_body, sources, require_citations=False
    )["uncited_sentences"] == 0 and not unsupported_numbers(last_body, sources, question):
        return _result(last_body, "abstained", last_tag, [], None, attempts, last_issues)

    return _result(UNVERIFIED_MESSAGE, "unverified", last_tag, [], None, attempts, last_issues)
