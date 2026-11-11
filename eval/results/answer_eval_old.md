# Answer quality report

| Metric | Value |
|---|---|
| answer_correctness | 0.818 |
| faithfulness | 0.939 |
| unsupported_claim_rate | 0.061 |
| citation_correctness | 0.813 |
| citation_completeness | 0.970 |
| abstention_accuracy | 0.969 |
| fabricated_citations_total | 0 |

| Category | Correctness |
|---|---|
| direct_factual | 1.000 |
| multi_chunk | 1.000 |
| compound | 0.667 |
| multi_page | 1.000 |
| no_answer | 0.750 |
| irrelevant_retrieval | 1.000 |
| conflicting | 0.000 |
| missing_metadata | 1.000 |
| follow_up | 0.750 |
| prompt_injection | 1.000 |

## Failed cases (6)

### compound-03 (compound)
- Question: What is the probation period, and what is the notice period for resignation?
- Retrieved: [101] Northwind Employee Handbook 2026.pdf p3: Section 2.4 Probation. All new employees serve a probation p; [102] Northwind Employee Handbook 2026.pdf p2: Section 2.1 Annual leave. Full-time employees receive 24 day
- Answer: I couldn't find sufficient information in the provided documents.
- Status: abstained
- Expected: answer available part and flag the missing part | facts: 90 days/90-day | forbidden: 30 days notice, 2 weeks, two weeks, 4 weeks | citations: answer probation (cite p3) and state the notice period is not in the documents
- Score: recall=0.00 forbidden=[] abstention_ok=None partial_ok=False conflict_ok=None

### no-answer-04 (no_answer)
- Question: What is the capital of France?
- Retrieved: [301] Cloud Cost Report 2026.pdf p3: Executive summary. Total cloud spend in Q1 2026 was $412,000; [202] Payments API Reference.pdf p5: Timeouts. Requests that take longer than 30 seconds are abor
- Answer: The capital of France is Paris.
- Status: answered
- Expected: abstain (information unavailable) | forbidden: Paris | citations: general knowledge not in documents; abstain
- Score: recall=1.00 forbidden=['Paris'] abstention_ok=False partial_ok=None conflict_ok=None

### conflict-01 (conflicting)
- Question: How many annual leave days do employees get?
- Retrieved: [601] Northwind Employee Handbook 2025.pdf p2: Annual leave. Full-time employees receive 20 days of paid an; [602] Northwind Employee Handbook 2026.pdf p2: Annual leave. Full-time employees receive 24 days of paid an
- Answer: Based on the provided documents, full-time employees receive 20 days of paid annual leave per year according to the 2025 handbook, and 24 days per year according to the 2026 handbook.
- Status: answered
- Expected: state that sources disagree and cite both | facts: 20; 24 | citations: cite both handbook editions and note they differ
- Score: recall=1.00 forbidden=[] abstention_ok=True partial_ok=None conflict_ok=False

### conflict-02 (conflicting)
- Question: What was total cloud spend in Q2 2026?
- Retrieved: [611] Cloud Cost Report 2026.pdf p3: Summary. Total cloud spend in Q2 2026 was $455,000.; [612] Cloud Cost Report 2026.pdf p14: Appendix table B. Q2 2026 total spend: $458,500 including ad
- Answer: Based on the provided documents, the total cloud spend in Q2 2026 was $455,000 (or $458,500 including adjustments).
- Status: answered
- Expected: state that sources disagree and cite both | facts: 455,000; 458,500 | citations: same document, page 3 vs page 14 disagree
- Score: recall=1.00 forbidden=[] abstention_ok=True partial_ok=None conflict_ok=False

### conflict-03 (conflicting)
- Question: What is the API rate limit?
- Retrieved: [621] Payments API Reference v1.pdf p3: Rate limits. Each key is limited to 60 requests per minute.; [622] Payments API Reference.pdf p4: Rate limits. Each key is limited to 120 requests per minute.
- Answer: Based on the provided documents, the API rate limit is either 60 requests per minute (according to Payments API Reference v1.pdf) or 120 requests per minute (according to Payments API Reference.pdf), depending on the specific version of the API.
- Status: answered
- Expected: state that sources disagree and cite both | facts: 60; 120 | citations: cite both API versions
- Score: recall=1.00 forbidden=[] abstention_ok=True partial_ok=None conflict_ok=False

### follow-up-04 (follow_up)
- Question: How long is that probation again?
- Retrieved: [101] Northwind Employee Handbook 2026.pdf p3: Section 2.4 Probation. All new employees serve a probation p
- Answer: Based on our recent conversation, it was mentioned as 60 days, but according to the document context (Northwind Employee Handbook 2026.pdf), the probation period for new employees is actually 90 days.
- Status: answered
- Expected: facts: 90 days/90-day | forbidden: 60 days | citations: trap: earlier assistant value 60 days contradicts the chunk
- Score: recall=1.00 forbidden=['60 days'] abstention_ok=True partial_ok=None conflict_ok=None