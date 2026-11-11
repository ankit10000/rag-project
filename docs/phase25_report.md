# Phase 2.5 — Retrieval verification (combined report)

Scope: verify the Phase 2 retrieval code after the BM25 IDF fix, without changing any default.
Detailed reports: `eval/results/phase25_AD_E.md`, `phase25_B_scale.md`, `phase25_C_embeddings.md`.
All runs used scratch databases (`rag_phase2_eval`, `_scale`, `_emb`); `rag_db` still holds 9 chunks and was not written.
No file under `services/` or any default in `services/retrieval_config.py` changed in Phase 2.5.

## Completion gate: reproducible benchmarks + documented recommendation — MET
Every script is in `eval/` with its command in the corresponding report. Corpus: 24 real + 720 filler chunks, 38 answerable queries, K=5.

## Findings
| Workstream | Result |
|---|---|
| A. A–E re-run after IDF fix | Matches the historical (pre-fix) numbers to 3 decimals; same ordering on a second distractor seed. Only two differences are statistically solid: vector < RRF, and PostgreSQL FTS < BM25. Everything else overlaps within the 95% bootstrap CIs. RRF k (10–100) changes no query. |
| A. Rerank pool 5 vs 10 | Pool 5: recall 0.974 / MRR 0.939; pool 10 (default): 0.947 / 0.926. A 1–2 query difference, not significant. |
| D. Stopword removal | Never helped; sign flips between seeds. Keep `BM25_DROP_STOPWORDS=False`. |
| E. Vector hits lost from RRF top 5 | Almost absent (1 query, vector rank 6, outside the rerank pool). The other miss ("callback…platform") is caused by the reranker at pool 10, not by RRF. Weighted RRF breaks exact-ID/abbreviation queries (recall 0.974 → 0.842). Keyword-score filtering at 0.7× best is an untested lead only. |
| B. Scale / indexes | No index needed at the current size (9 chunks; exact scan ≈15 ms at 3k, 35–70 ms at 12k chunks). HNSW (m=16, efc=64, ef_search≥100) only above ~20–50k chunks or for a <30 ms target; IVFFlat recall was poor. In-memory BM25 becomes the first bottleneck (156 ms/query at 3k, 279 ms at 12k; full rebuild after any insert). GIN on `to_tsvector` only if the FTS backend is adopted. No extra document_name index needed. New connection per query costs 79–124 ms vs <0.3 ms reused. |
| C. Embedding models (six 384-d models) | No alternative is significantly better than all-MiniLM-L6-v2; BM25 in the hybrid absorbs the vector-only gains of e5/gte/bge. Reranking helps more (+0.04–0.09 MRR) than any model swap. 12-layer models embed ~3x slower; L12 truncates 32 chunks at 128 tokens. |

## Recommendation (no default changed)
- Keep: `RRF_K=60`, equal RRF weights, `BM25_DROP_STOPWORDS=False`, in-memory BM25, `all-MiniLM-L6-v2`, `RERANK_TOP_K=10`.
- `RERANK_TOP_K=5` is the only candidate change, and only after confirmation on a larger query set.
- Worth doing regardless of corpus size (needs approval; touches `services/database.py`): reuse database connections instead of opening one per query.
- Add no index until the corpus passes roughly 20k chunks; revisit BM25 caching/backend before that.

## Evidence still required before changing any default
1. At least 150 labelled queries with a held-out split, ideally on real documents (current corpus is templated and favours BM25).
2. Latency re-measured with exclusive CPU (the machine was shared; numbers are coarse).
3. A filtered-ANN test with large documents, and an end-to-end answer-quality check for any embedding change.

## Housekeeping
Scratch databases `rag_phase2_eval`, `rag_phase2_test`, `rag_phase2_emb`, `rag_phase2_scale` (~65 MB total) are still present; drop them with `harness.drop_scratch_database(name)` when no longer needed.
