import os
import re
from services import retrieval_config as cfg
from services.hybrid_search_service import hybrid_search_detailed
from services.llm_service import generate_answer, rewrite_query
from services.answer_prompt import REFUSAL_MESSAGE
from services.answer_service import generate_grounded_answer
from services.context_assembly_service import assemble_context
from services.local_release_profile import requires_verified_ranking
from services.answer_service import ERROR_MESSAGE, UNVERIFIED_MESSAGE
from services.request_budget import RequestDeadlineExceeded, check_deadline
from services.evidence_trace import trace_candidates, trace_event



def classify_question(query: str) -> str:
    """
    Classify the question as:
    MEMORY, DOCUMENT, or MIXED.
    """

    prompt = f"""
Classify the user's question into exactly one category:

MEMORY:
Questions about the user's project, preferences,
previous conversations, personal details, or past decisions.

DOCUMENT:
Questions asking about information contained in uploaded documents.

MIXED:
Questions requiring both user memory and document information.

Return only one label: MEMORY, DOCUMENT, or MIXED.

Question:
{query}
"""

    raw = generate_answer(prompt)
    result = raw.strip().upper() if isinstance(raw, str) else ""
    # Only the requested exact enum may suppress document retrieval. A
    # malformed reply such as "NOT MEMORY" follows the existing safe fallback.
    return result if result in ("DOCUMENT", "MEMORY", "MIXED") else "DOCUMENT"


def _keeps_entities(rewritten, entities):
    normalized = ' ' + ' '.join(re.findall(r'\w+', rewritten.casefold())) + ' '
    for entity in entities:
        name = ' '.join(re.findall(r'\w+', entity.casefold()))
        if name and f' {name} ' not in normalized:
            return False
    return True


def ask_question(
    query: str,
    history: list = None,
    memory_summary: str = ""
) -> dict:

    history = history or []
    trace_event('question', metadata={'history_messages': len(history)}, raw={'question': query})
    v2 = os.getenv("RAG_V2") == "1"
    contract = None
    scope = None
    as_of = None
    document_operation = False
    routing_error = False
    if v2:
        from services.tenure_calculation import _as_of_date, answer_employment_duration, has_additional_requests
        from services.v2_evidence_recovery import explicit_document_scope
        from services.v2_request_contract import build_request_contract
        as_of = _as_of_date()
        contract = build_request_contract(query, history, as_of=as_of)
        query = contract['resolved_question']
        document_operation = contract['source_location'] or (
            bool(contract['entities']) and
            any(field in {'employment_duration', 'joining_date'} for field in contract['fields'])
        )
        scope = explicit_document_scope(contract['scope_question'])
        trace_event('request_contract', metadata={
            'intent': contract['intent'], 'units': contract['units'],
            'inherited_user_turns': contract['previous_user_turns'],
            'scope': scope, 'field_count': len(contract['fields']),
            'source_location': contract['source_location'],
        }, raw={'contract': contract})
        if contract['clarification']:
            return dict(answer=contract['clarification'], status='abstained', issues=['ambiguous_reference'],
                        sources=[], citations=[], retrieved=[], retrieval_status='not_run')
        if scope == []:
            return _answer_from_route(query, query, 'DOCUMENT', [], '', scope=scope, as_of=as_of)
        check_deadline()
        if not has_additional_requests(query):
            calculation = answer_employment_duration(query, history, scope=scope, as_of=as_of)
            if calculation is not None:
                trace_event('verified_lookup', metadata={
                    'status': calculation['status'], 'scope': scope,
                    'citations': calculation.get('citations', []),
                    'evidence_state': ('SUPPORTED_DERIVED' if calculation.get('calculation') else
                                       'SUPPORTED_DIRECT' if calculation['status'] == 'answered' else
                                       'AMBIGUOUS' if 'ambiguous_employment_period' in calculation.get('issues', []) else
                                       'NOT_FOUND_IN_SEARCHED_SCOPE'),
                }, raw={'calculation': calculation.get('calculation')})
                return _finish_request(calculation, contract)
        from services.v2_routing import single_source_overview_query, OVERVIEW_POLICY
        overview_query = single_source_overview_query(query) if scope is None else None
        if overview_query is not None:
            outcome = _answer_from_route(query, overview_query, 'DOCUMENT', history, memory_summary,
                                         scope=scope, as_of=as_of)
            outcome['routing_policy'] = OVERVIEW_POLICY
            return _finish_request(outcome, contract)

    # Pin the original user's source selection before interpreting rewritten text.
    fixed = bool(contract and (contract['deterministic_resolution'] or scope is not None))
    search_query = query
    if not fixed:
        try:
            user_history = [turn for turn in history if turn.get('role') == 'user'] if v2 else history
            rewritten = rewrite_query(query=query, history=user_history, memory_summary=memory_summary)
            if isinstance(rewritten, str) and rewritten.strip():
                if _keeps_entities(rewritten, (contract or {}).get('entities', [])):
                    search_query = rewritten
        except RequestDeadlineExceeded:
            raise
        except Exception as error:
            routing_error = True
            print(f"Query rewriting failed ({type(error).__name__}); using the original question.")

    check_deadline()
    question_type = 'DOCUMENT'
    if scope is None and not document_operation:
        try:
            question_type = classify_question(search_query)
        except RequestDeadlineExceeded:
            raise
        except Exception as error:
            routing_error = True
            print(f"Question classification failed ({type(error).__name__}); using DOCUMENT.")

    trace_event('question_category', metadata={'category': question_type},
                raw={'search_query': search_query})
    route_options = {'scope': scope, 'as_of': as_of} if v2 else {}
    outcome = _answer_from_route(query, search_query, question_type, history, memory_summary, **route_options)
    if v2 and question_type == 'MEMORY' and outcome['status'] == 'abstained':
        check_deadline()
        recovered = _answer_from_route(query, search_query, 'DOCUMENT', history, memory_summary, **route_options)
        if recovered['retrieved'] or recovered['status'] == 'error':
            recovered['routing_policy'] = 'v2-memory-abstention-document-fallback/1'
            outcome = recovered
    if v2 and routing_error and outcome['status'] == 'abstained':
        outcome = {**outcome, 'answer': ERROR_MESSAGE, 'status': 'error', 'issues': ['routing_unavailable'],
                   'sources': [], 'citations': []}
    return _finish_request(outcome, contract)


def _finish_request(outcome, contract):
    if contract and contract['source_location']:
        from services.answer_service import with_source_locations
        outcome = with_source_locations(outcome)
    check_deadline()
    return outcome


_SCOPE_UNSET = object()


def _document_search(query, **options):
    check_deadline()
    try:
        result = hybrid_search_detailed(query, **options)
    except Exception as error:
        trace_event('search_failure', metadata={'evidence_state': 'NOT_VERIFIED_DUE_TO_ERROR',
                    'error': type(error).__name__, 'scope': options.get('document_names')})
        raise
    check_deadline()
    return result


def _answer_from_route(query, search_query, question_type, history, memory_summary, *,
                       scope=_SCOPE_UNSET, as_of=None):
    """Run the same retrieval/grounding path for the selected evidence route."""
    # Step 2: Retrieve document chunks
    # Step 2: Retrieve document chunks only when needed
    ranking_failed = False
    if question_type == "MEMORY":
        results = []
        retrieval_status = "not_run"
        print("Memory question detected. Skipping document retrieval.")

    else:
        # Stage 6: the detailed call (same arguments and results as the
        # hybrid_search wrapper) also reports the Stage 5 rerank_status:
        # ok | disabled | skipped | failed:<ExceptionType>.
        check_deadline()
        if scope is _SCOPE_UNSET:
            from services.v2_evidence_recovery import explicit_document_scope
            scope = explicit_document_scope(query) if os.getenv("RAG_V2") == "1" else None
        if scope == []:
            # An explicit unavailable/unauthorized filename is not permission
            # to search a different document. Empty SQL filters mean "all".
            retrieval = {'results': [], 'rerank_status': 'skipped'}
        elif scope:
            retrieval = _document_search(search_query, top_k=cfg.FINAL_TOP_K, document_names=scope)
        else:
            retrieval = _document_search(search_query, top_k=cfg.FINAL_TOP_K)
        ranking_failed = retrieval['rerank_status'].startswith('failed:')
        if os.getenv("RAG_V2") == "1":
            from services.v2_routing import education_retrieval
            focused = education_retrieval(query, retrieval, _document_search, cfg.FINAL_TOP_K, authorized_scope=scope)
            if focused is not None:
                retrieval = focused
        results = retrieval["results"]
        retrieval_status = retrieval["rerank_status"]
        print(f"Retrieval status: {retrieval_status}")

    ranking_failed |= retrieval_status.startswith("failed:")
    unfiltered = list(results)
    removals = []

    # Step 3: Filter chunks using adaptive reranker threshold
    if results and "rerank_score" in results[0]:
        best_score = results[0]["rerank_score"]

        # Absolute floor (optional): nothing relevant was retrieved at all.
        if cfg.RERANK_MIN_SCORE is not None and best_score < cfg.RERANK_MIN_SCORE:
            removals.extend({'chunk_id': item['chunk'][0], 'reason': 'below_absolute_rerank_floor',
                             'score': item.get('rerank_score'), 'threshold': cfg.RERANK_MIN_SCORE}
                            for item in results)
            print(f"\nBest reranker score {best_score:.4f} is below "
                  f"RERANK_MIN_SCORE={cfg.RERANK_MIN_SCORE}; no document context.")
            results = []
            best_score = None

    if results and "rerank_score" in results[0]:
        # Threshold based on the best retrieved score
        score_margin = cfg.RERANK_SCORE_MARGIN
        threshold = best_score - score_margin

        removals.extend({'chunk_id': item['chunk'][0], 'reason': 'below_adaptive_rerank_margin',
                         'score': item.get('rerank_score'), 'threshold': threshold}
                        for item in results if item.get('rerank_score', best_score) < threshold)

        results = [
            item for item in results
            if item.get("rerank_score", best_score) >= threshold
        ]

        print(f"\nBest reranker score: {best_score:.4f}")
        print(f"Adaptive threshold: {threshold:.4f}")
        print(f"Relevant chunks retained: {len(results)}")

    trace_event('adaptive_filter', metadata={'removals': removals,
                'input_ids': [item['chunk'][0] for item in unfiltered],
                'selected_ids': [item['chunk'][0] for item in results]})
    trace_candidates('after_adaptive_filter', results)

    # Debugging: Display retained reranker scores
    print("\n--- Reranker Scores ---")

    for item in results:
        chunk = item["chunk"]

        # Phase 7 privacy: identifiers and scores only, no document text in logs.
        print(
            f"Score: {item.get('rerank_score', item['rrf_score']):.4f} | "
            f"Chunk: {chunk[0]} | "
            f"Page: {chunk[2]}"
        )

    # V2 enumerations can span multiple small chunks on a relevant page.
    # Expand after ranking/filtering so neighboring list entries are not lost
    # merely because they omit the section heading used by the search query.
    if os.getenv("RAG_V2") == "1" and question_type != "MEMORY" and (results or scope):
        from services.v2_evidence_recovery import recover_complementary_evidence
        recovered = recover_complementary_evidence(
            query, search_query, results, retrieval, _document_search,
            top_k=cfg.FINAL_TOP_K, max_chunks=cfg.CONTEXT_MAX_CHUNKS,
            max_chars=cfg.CONTEXT_MAX_CHARS, document_names=scope)
        ranking_failed |= any(status.startswith('failed:') for status in recovered.get('facet_rerank_statuses', []))
        results = recovered['results']
        retrieval_status = recovered.get('rerank_status', retrieval_status)
        from services.v2_page_context import expand_page_context
        before_ids = {item['chunk'][0] for item in results}
        results = expand_page_context(query, results, cfg.CONTEXT_MAX_CHUNKS)
        trace_event('page_continuity', metadata={
            'recovered_ids': [item['chunk'][0] for item in results if item['chunk'][0] not in before_ids]})
        trace_candidates('after_page_continuity', results)

    if question_type != 'MEMORY' and results:
        anchor = retrieval.get('education_identity_anchor')
        if (anchor and any(item['chunk'][1] == anchor['chunk'][1] for item in results)
                and all(item['chunk'][0] != anchor['chunk'][0] for item in results)):
            # Preserve the actual same-document identity proof alongside the
            # nameless degree; final packing still enforces all original caps.
            results = results + [anchor]
            trace_event('education_identity_continuity',metadata={'chunk_id':anchor['chunk'][0],
                'document':anchor['chunk'][1],'page':anchor['chunk'][2]})

    # Step 4: Assemble context (dedupe, budget, numbered [S#] references).
    # Chunk id, document, page and score travel with every source.
    bundle = assemble_context(results)
    if os.getenv('RAG_V2') == '1':
        from services.v2_source_labels import label_owned_sources
        bundle = label_owned_sources(bundle)
    trace_candidates('final_context', [dict(chunk=(s['chunk_id'], s['document_name'],
                    s['page_number'], s['content']), rrf_score=s['rrf_score'],
                    rerank_score=s['rerank_score']) for s in bundle['sources']])
    trace_event('context_packing', metadata={'total_chars': bundle['total_chars'],
        'max_chars': cfg.CONTEXT_MAX_CHARS, 'max_chunks': cfg.CONTEXT_MAX_CHUNKS,
        'dropped': bundle['dropped'], 'truncated': bundle['truncated']},
        raw={'context_text': bundle['context_text']})

    if bundle["dropped"]:
        print(f"Context assembly dropped: {bundle['dropped']}")

    # Step 5: Grounded generation + citation validation (bounded retries)
    if requires_verified_ranking(question_type, results, retrieval_status):
        outcome = dict(answer=UNVERIFIED_MESSAGE, status="unverified", sources=[],
                       citations=[], attempts=0, issues=["local_v1_rerank_required"])
    else:
        check_deadline()
        outcome = generate_grounded_answer(
            question=query,
            bundle=bundle,
            question_type=question_type,
            generate_fn=lambda prompt: generate_answer(prompt),
            history=history,
            memory_summary=memory_summary,
            **({'as_of': as_of} if as_of is not None else {}),
        )
    if os.getenv('RAG_V2') == '1' and ranking_failed and outcome['status'] in {'abstained', 'partial', 'unverified'}:
        outcome = dict(answer=ERROR_MESSAGE, status='error', sources=[], citations=[],
                       attempts=outcome['attempts'], issues=['evidence_not_verified_due_to_rerank_error'])

    print(
        f"Answer status: {outcome['status']} | "
        f"citations: {[c['ref'] for c in outcome['citations']]} | "
        f"attempts: {outcome['attempts']}"
    )

    # Step 6: Return. 'sources' holds only chunks the answer actually cites.
    result = {
        "answer": outcome["answer"],
        "sources": outcome["sources"],
        "citations": outcome["citations"],
        "status": outcome["status"],
        "issues": outcome["issues"],
        # Stage 6: how retrieval ran; "not_run" when no retrieval was needed.
        # Existing defaults keep H.1 behavior; explicit local-v1.0 requires
        # verified reranking for nonempty document retrieval above.
        "retrieval_status": retrieval_status,
        "retrieved": [
            {k: s[k] for k in ("ref", "chunk_id", "document_name", "page_number", "retrieval_score")}
            for s in bundle["sources"]
        ],
    }
    if 'coverage' in outcome:
        result['coverage'] = outcome['coverage']
    if 'calculation' in outcome:
        result['calculation'] = outcome['calculation']
    coverage_metadata = result.get('coverage') or {}
    trace_event('answer_result', metadata={'status': result['status'], 'issues': result['issues'],
                'citations': result['citations'],
                'coverage_mode': coverage_metadata.get('mode'),
                'missing_item_ids': [item['id'] for item in coverage_metadata.get('concrete_missing', [])]},
                raw={'answer': result['answer']})
    return result
