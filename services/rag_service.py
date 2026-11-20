import os
from services import retrieval_config as cfg
from services.hybrid_search_service import hybrid_search_detailed
from services.llm_service import generate_answer, rewrite_query
from services.answer_prompt import REFUSAL_MESSAGE
from services.answer_service import generate_grounded_answer
from services.context_assembly_service import assemble_context
from services.local_release_profile import requires_verified_ranking
from services.answer_service import UNVERIFIED_MESSAGE
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
def ask_question(
    query: str,
    history: list = None,
    memory_summary: str = ""
) -> dict:

    history = history or []
    trace_event('question', metadata={'history_messages': len(history)}, raw={'question': query})
    if os.getenv("RAG_V2") == "1":
        from services.tenure_calculation import answer_employment_duration
        calculation = answer_employment_duration(query, history)
        if calculation is not None:
            return calculation
        from services.v2_routing import single_source_overview_query, OVERVIEW_POLICY
        overview_query = single_source_overview_query(query)
        if overview_query is not None:
            outcome = _answer_from_route(query, overview_query, "DOCUMENT", history, memory_summary)
            outcome["routing_policy"] = OVERVIEW_POLICY
            return outcome

    # Step 1: Rewrite follow-up question (optional step: on failure search
    # with the user's own words instead of aborting the whole answer).
    try:
        search_query = rewrite_query(
            query=query,
            history=history,
            memory_summary=memory_summary
        )
    except Exception as error:
        print(f"\nQuery rewriting failed ({type(error).__name__}); using the original question.")
        search_query = query

    # Fallback if query rewriting returns an empty result
    if not isinstance(search_query, str) or not search_query.strip():
        search_query = query

    # Step 1b (Stage 8 P3): classify the rewritten standalone query, so a
    # document follow-up ("...after that trip?") is judged with its reference
    # resolved. Without history or memory rewrite_query returns the query
    # unchanged (no LLM call), so standalone questions classify as before.
    # If the provider fails, fall back to DOCUMENT, the strictest type
    # (retrieval runs and citations are required).
    try:
        question_type = classify_question(search_query)
    except Exception as error:
        print(f"\nQuestion classification failed ({type(error).__name__}); using DOCUMENT.")
        question_type = "DOCUMENT"

    print(f"\nQuestion type: {question_type}")
    trace_event('question_category', metadata={'category': question_type},
                raw={'search_query': search_query})

    outcome = _answer_from_route(query, search_query, question_type, history, memory_summary)

    # Versioned v2 recovery only: a classifier label is not proof that the
    # uploaded corpus is irrelevant. Preserve successful memory answers and
    # try the normal grounded document path once after a memory abstention.
    if (os.getenv("RAG_V2") == "1" and question_type == "MEMORY"
            and outcome["status"] == "abstained"):
        recovered = _answer_from_route(query, search_query, "DOCUMENT", history, memory_summary)
        if recovered["retrieved"]:
            recovered["routing_policy"] = "v2-memory-abstention-document-fallback/1"
            return recovered
    return outcome


def _answer_from_route(query, search_query, question_type, history, memory_summary):
    """Run the same retrieval/grounding path for the selected evidence route."""
    # Step 2: Retrieve document chunks
    # Step 2: Retrieve document chunks only when needed
    if question_type == "MEMORY":
        results = []
        retrieval_status = "not_run"
        print("Memory question detected. Skipping document retrieval.")

    else:
        # Stage 6: the detailed call (same arguments and results as the
        # hybrid_search wrapper) also reports the Stage 5 rerank_status:
        # ok | disabled | skipped | failed:<ExceptionType>.
        scope = None
        if os.getenv("RAG_V2") == "1":
            from services.v2_evidence_recovery import explicit_document_scope
            scope = explicit_document_scope(search_query)
        if scope == []:
            # An explicit unavailable/unauthorized filename is not permission
            # to search a different document. Empty SQL filters mean "all".
            retrieval = {'results': [], 'rerank_status': 'skipped'}
        elif scope:
            retrieval = hybrid_search_detailed(search_query, top_k=cfg.FINAL_TOP_K,
                                               document_names=scope)
        else:
            retrieval = hybrid_search_detailed(search_query, top_k=cfg.FINAL_TOP_K)
        if os.getenv("RAG_V2") == "1":
            from services.v2_routing import education_retrieval
            focused = education_retrieval(query, retrieval, hybrid_search_detailed, cfg.FINAL_TOP_K, authorized_scope=scope)
            if focused is not None:
                retrieval = focused
        results = retrieval["results"]
        retrieval_status = retrieval["rerank_status"]
        print(f"Retrieval status: {retrieval_status}")

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
    if os.getenv("RAG_V2") == "1" and results:
        from services.v2_evidence_recovery import recover_complementary_evidence
        recovered = recover_complementary_evidence(
            query, search_query, results, retrieval, hybrid_search_detailed,
            top_k=cfg.FINAL_TOP_K, max_chunks=cfg.CONTEXT_MAX_CHUNKS,
            max_chars=cfg.CONTEXT_MAX_CHARS, document_names=scope)
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
        outcome = generate_grounded_answer(
            question=query,
            bundle=bundle,
            question_type=question_type,
            generate_fn=lambda prompt: generate_answer(prompt),
            history=history,
            memory_summary=memory_summary,
        )

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
    coverage_metadata = result.get('coverage') or {}
    trace_event('answer_result', metadata={'status': result['status'], 'issues': result['issues'],
                'citations': result['citations'],
                'coverage_mode': coverage_metadata.get('mode'),
                'missing_item_ids': [item['id'] for item in coverage_metadata.get('concrete_missing', [])]},
                raw={'answer': result['answer']})
    return result
