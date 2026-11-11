from services.hybrid_search_service import hybrid_search


def evaluate_retrieval(dataset: list, k: int = 5):

    total_recall = 0
    total_precision = 0
    total_mrr = 0

    for test_case in dataset:

        query = test_case["question"]
        relevant_pages = set(test_case["relevant_pages"])

        # Retrieve results
        results = hybrid_search(query, top_k=k)

        # Extract unique pages in ranking order
        retrieved_pages = []

        for item in results:

            chunk = item["chunk"]
            page = chunk[2]

            if page not in retrieved_pages:
                retrieved_pages.append(page)

        retrieved_pages = retrieved_pages[:k]

        # Calculate relevant retrieved pages
        relevant_retrieved = [
            page for page in retrieved_pages
            if page in relevant_pages
        ]

        # Recall@K
        recall = (
            len(relevant_retrieved) / len(relevant_pages)
            if relevant_pages else 0
        )

        # Precision@K
        precision = len(relevant_retrieved) / k

        # Reciprocal Rank
        reciprocal_rank = 0

        for rank, page in enumerate(retrieved_pages, start=1):

            if page in relevant_pages:
                reciprocal_rank = 1 / rank
                break

        total_recall += recall
        total_precision += precision
        total_mrr += reciprocal_rank

        print(f"\nQuestion: {query}")
        print("Retrieved pages:", retrieved_pages)
        print("Relevant pages:", sorted(relevant_pages))
        print("Recall@K:", round(recall, 3))
        print("Precision@K:", round(precision, 3))
        print("MRR:", round(reciprocal_rank, 3))

    count = len(dataset)

    if count == 0:
        return

    print("\n========== FINAL EVALUATION ==========")
    print("Average Recall:", round(total_recall / count, 3))
    print("Average Precision:", round(total_precision / count, 3))
    print("Average MRR:", round(total_mrr / count, 3))