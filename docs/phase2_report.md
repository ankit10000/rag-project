# Phase 2 (retrieval) and Phase 3 (answer generation) — report

## Phase 2 — what exists and what was measured
Before Phase 2 the repo already had BM25 (rank_bm25, rebuilt on every query), vector search, RRF (k=60) and a cross-encoder reranker. Phase 2 added:
- `services/retrieval_config.py` — all retrieval/answer settings, env-overridable (defaults keep old behaviour).
- Metadata filters (`document_names`, `pages`) in vector, BM25 and FTS retrieval; cached BM25 index (rebuilt only when the corpus changes); Lucene-style positive IDF (stock rank_bm25 IDF is 0 for terms in half the chunks, which dropped matches in small filtered scopes).
- `services/fts_service.py` (PostgreSQL FTS alternative), content de-duplication in RRF, `hybrid_search_detailed` (per-stage timings, switchable stages), sentence-aware chunker, ingestion duplicate prevention and embedding-dimension guard.
- Isolated evaluation in scratch databases (`rag_phase2_*`); `rag_db` was never written.

Measured on 38 answerable queries, 744 chunks (24 real + 720 filler), K=5, from the earlier run (before the Lucene IDF change; not re-run):

| Config | Recall@5 | MRR | nDCG@5 | median ms |
|---|---|---|---|---|
| A vector | 0.842 | 0.785 | 0.776 | 100 |
| B BM25 | 0.921 | 0.908 | 0.888 | 89 |
| C interleave | 0.974 | 0.922 | 0.914 | 213 |
| D RRF | 0.974 | 0.889 | 0.890 | 220 |
| E RRF + rerank (pool 10) | 0.947 | 0.926 | 0.911 | 562 (rerank 316) |
| E, rerank pool 5 | 0.974 | 0.939 | 0.927 | 385 |

Findings: hybrid beats vector alone; reranking improves ordering but costs 300+ ms on CPU and with a pool of 10 it can drop a hit that RRF had in its top 5; PostgreSQL FTS was worse than BM25 (no corpus IDF). Chunking variants (50–200 words, sentence-aware) all landed within one query of the current 100/20, so the setting was left unchanged. A cross-encoder score floor separated 4 no-answer queries from all answerable ones (about -9.5), but 4 queries are too few, so `RERANK_MIN_SCORE` is off by default.

Not done (stopped on request): scale/HNSW/IVFFlat benchmark, alternative-embedding benchmark (scripts are in `eval/`, unrun), re-run after the BM25 IDF fix, stopword-removal evaluation (`BM25_DROP_STOPWORDS`, default off). No migration was applied; the embedding audit found all stored vectors 384-d, unit-norm, same model for documents and queries.

Known limitation: a strong vector-only hit can fall below top 5 after RRF (test documents it stays in the top-10 candidate pool).

## Phase 3 — answer generation
Flow: `ask_question` → classify → rewrite → hybrid search → reranker margin/min-score filter → `assemble_context` (dedupe, budget, `[S#]` refs with chunk id/doc/page/score) → `generate_grounded_answer` (prompt, parse, citation validation, bounded retry, safe fallback) → `{answer, sources (cited only), citations, status, issues, retrieved}`.

New modules: `context_assembly_service.py`, `citation_service.py`, `answer_prompt.py`, `answer_service.py`. `main.py` only changed how sources are printed (ref, missing page). Phase 1 memory code was not touched.

Safeguards: empty retrieval for a document question refuses without calling the LLM; history is clearly marked non-evidence and old `[S#]` markers are stripped from it; delimiter tags in documents/history/question are neutralised; invalid refs or prose-fabricated pages/filenames trigger one regeneration (`ANSWER_MAX_RETRIES`), then repair or an `unverified` fallback.

Tests (mocked Gemini): `test_context_and_citations.py` 62/62, `test_answer_phase3.py` 69/69, `test_answer_scoring.py` pass, `test_retrieval_phase2.py` pass.

Live evaluation (Gemini, 33 hand-written cases, retrieval supplied by the case):

| Metric | Before (old prompt) | After |
|---|---|---|
| Answer correctness | 0.818 | 1.000 |
| Unsupported-claim rate | 0.061 | 0.000 |
| Citation correctness | 0.813 | 1.000 |
| Citation completeness | 0.970 | 1.000 |
| Abstention accuracy | 0.969 | 1.000 |
| Median latency | 2.6 s | 3.0 s |

Old pipeline failed mainly on conflicting sources (0/3), some compound/no-answer/follow-up cases, and cited every retained chunk. Caveat: 33 cases, substring-based scoring, a dataset written alongside the prompt — a perfect score means these cases pass, not that the system is flawless. Token usage is not exposed by `generate_answer`, so it was not measured.

Rollback: restore `services/rag_service.py` from before Phase 3 (the old flow is reproduced in `eval/run_answer_eval.py::run_old`), revert the `main.py` source printing; new modules can stay unused.
