from services import retrieval_config as cfg
from services.hybrid_search_service import hybrid_search_detailed
from services.llm_service import generate_answer, rewrite_query
from services.answer_prompt import REFUSAL_MESSAGE
from services.answer_service import generate_grounded_answer
from services.context_assembly_service import assemble_context
from services.local_release_profile import requires_verified_ranking
from services.answer_service import UNVERIFIED_MESSAGE



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
        retrieval = hybrid_search_detailed(search_query, top_k=cfg.FINAL_TOP_K)
        results = retrieval["results"]
        retrieval_status = retrieval["rerank_status"]
        print(f"Retrieval status: {retrieval_status}")

    # Step 3: Filter chunks using adaptive reranker threshold
    if results and "rerank_score" in results[0]:
        best_score = results[0]["rerank_score"]

        # Absolute floor (optional): nothing relevant was retrieved at all.
        if cfg.RERANK_MIN_SCORE is not None and best_score < cfg.RERANK_MIN_SCORE:
            print(f"\nBest reranker score {best_score:.4f} is below "
                  f"RERANK_MIN_SCORE={cfg.RERANK_MIN_SCORE}; no document context.")
            results = []
            best_score = None

    if results and "rerank_score" in results[0]:
        # Threshold based on the best retrieved score
        score_margin = cfg.RERANK_SCORE_MARGIN
        threshold = best_score - score_margin

        results = [
            item for item in results
            if item.get("rerank_score", best_score) >= threshold
        ]

        print(f"\nBest reranker score: {best_score:.4f}")
        print(f"Adaptive threshold: {threshold:.4f}")
        print(f"Relevant chunks retained: {len(results)}")

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

    # Step 4: Assemble context (dedupe, budget, numbered [S#] references).
    # Chunk id, document, page and score travel with every source.
    bundle = assemble_context(results)

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
    return {
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
