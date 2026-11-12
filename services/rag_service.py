from services import retrieval_config as cfg
from services.hybrid_search_service import hybrid_search
from services.llm_service import generate_answer, rewrite_query
from services.answer_prompt import REFUSAL_MESSAGE
from services.answer_service import generate_grounded_answer
from services.context_assembly_service import assemble_context



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

    result = generate_answer(prompt).strip().upper()

    if "MIXED" in result:
        return "MIXED"

    if "MEMORY" in result:
        return "MEMORY"

    return "DOCUMENT"
def ask_question(
    query: str,
    history: list = None,
    memory_summary: str = ""
) -> dict:

    history = history or []
    # Step 1: Classify the question. If the provider fails, fall back to
    # DOCUMENT, the strictest type (retrieval runs and citations are required).
    try:
        question_type = classify_question(query)
    except Exception as error:
        print(f"\nQuestion classification failed ({type(error).__name__}); using DOCUMENT.")
        question_type = "DOCUMENT"

    print(f"\nQuestion type: {question_type}")
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
    if not search_query or not search_query.strip():
        search_query = query

    # Step 2: Retrieve document chunks
    # Step 2: Retrieve document chunks only when needed
    if question_type == "MEMORY":
        results = []
        print("Memory question detected. Skipping document retrieval.")

    else:
        results = hybrid_search(search_query, top_k=cfg.FINAL_TOP_K)

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

        print(
            f"Score: {item.get('rerank_score', item['rrf_score']):.4f} | "
            f"Page: {chunk[2]} | "
            f"Content: {chunk[3][:100]}"
        )

    # Step 4: Assemble context (dedupe, budget, numbered [S#] references).
    # Chunk id, document, page and score travel with every source.
    bundle = assemble_context(results)

    if bundle["dropped"]:
        print(f"Context assembly dropped: {bundle['dropped']}")

    # Step 5: Grounded generation + citation validation (bounded retries)
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
        "retrieved": [
            {k: s[k] for k in ("ref", "chunk_id", "document_name", "page_number", "retrieval_score")}
            for s in bundle["sources"]
        ],
    }
