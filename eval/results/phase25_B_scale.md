# Phase 2.5 / Workstream B - scale benchmark and index comparison

Scratch database `rag_phase2_scale` only (production `rag_db` never touched). No file under `services/`, `main.py`, `migrations/` or other tests was modified. No Gemini calls. No package installed.

## Reproduction

```
.venv\Scripts\python.exe eval\scale_benchmark.py 500            # ~3,000 chunks
.venv\Scripts\python.exe eval\scale_benchmark.py 2000 --m32     # ~12,000 chunks (+ HNSW m=32/efc=128)
```

Raw output: `eval/results_scale.txt` (both runs, appended, includes full EXPLAIN (ANALYZE, BUFFERS) plans), `eval/results/phase25_B_raw_3000.log`, `eval/results/phase25_B_raw_12000.log`. Optional cleanup: `harness.drop_scratch_database("rag_phase2_scale")` (not done).

## Configuration

- Corpus: the 8 core eval documents + N templated filler documents from `eval.corpus.make_distractors(N, pages_per_doc=3, seed=21)`, chunked with `chunk_page(text, 100, 20, "words")`, embedded with the project's MiniLM (384-d), cosine ops.
- Scale 1: 508 docs, **3,024 chunks** (table 6.7 MB). Scale 2: 2,008 docs, **12,024 chunks** (table 26 MB; real number, no fallback to 8,000 needed). PK + UNIQUE indexes: 224 kB / 960 kB.
- Queries: the 38 evaluation queries that have gold answers. Each query is timed 3x; the per-query median is taken, then the median and p95 are computed across the 38 queries (single-call numbers are marked as such). Vector queries are `ORDER BY embedding <=> $1 LIMIT 10` (no filter).
- Recall@10 = overlap of top-10 ids with the exact (no-index) top-10, mean over the 38 queries.
- IVFFlat lists = round(sqrt(N)) (54 and 109); HNSW m=16/efc=64 (ef_search 40, 100), m=32/efc=128 at the larger scale only.
- Latency loops ran under `eval/results/.bench.lock` (atomic create). Builds, loading and recall computation ran unlocked. The script waited for the other agents' lock for several minutes at each scale.
- Defaults unchanged; all indexes created and dropped inside the scratch DB.

## Results: vector search (top-10)

### N = 3,024 chunks

| Index | median ms | p95 ms | recall@10 | build s | size | plan (EXPLAIN ANALYZE, query 1) |
|---|---|---|---|---|---|---|
| none (exact) | 14.36 | 45.19 | 1.000 | - | - | Seq Scan + top-N sort, 13.6 ms |
| HNSW m16/efc64, ef_search=40 | 1.93 | 2.58 | 0.834 | 4.2 | 6.0 MB | Index Scan chunks_hnsw, 1.2 ms |
| HNSW m16/efc64, ef_search=100 | 3.15 | 4.55 | 0.889 | (same index) | 6.0 MB | Seq Scan + sort, 17.3 ms (see note) |
| IVFFlat lists=54, probes=1 | 0.58 | 0.75 | 0.211 | 0.5 | 5.1 MB | Index Scan chunks_ivf, 0.11 ms |
| IVFFlat lists=54, probes=10 | 1.36 | 1.73 | 0.755 | (same index) | 5.1 MB | Index Scan chunks_ivf, 0.67 ms |

Note: at ef_search=100 the EXPLAIN for query 1 shows the planner flipping to a sequential scan (HNSW cost estimate rises with ef_search and N=3k is near the crossover) although the timing loop median (3.15 ms) indicates the index was mostly used. At this size the planner choice is borderline; it is not a stable operating point.

### N = 12,024 chunks

| Index | median ms | p95 ms | recall@10 | build s | size | plan |
|---|---|---|---|---|---|---|
| none (exact) | 69.00 | 85.93 | 1.000 | - | - | Seq Scan, 72.6 ms |
| HNSW m16/efc64, ef_search=40 | 1.97 | 2.44 | 0.813 | 7.3 | 23 MB | Index Scan, 1.4 ms |
| HNSW m16/efc64, ef_search=100 | 3.42 | 3.98 | 0.871 | (same) | 23 MB | Index Scan, 2.4 ms |
| HNSW m32/efc128, ef_search=40 | 2.94 | 3.57 | 0.842 | 19.7 | 24 MB | Index Scan, 3.1 ms |
| HNSW m32/efc128, ef_search=100 | 5.47 | 7.69 | 0.884 | (same) | 24 MB | Index Scan, 4.2 ms |
| IVFFlat lists=109, probes=1 | 0.78 | 0.91 | 0.242 | 3.0 | 19 MB | Index Scan, 0.32 ms |
| IVFFlat lists=109, probes=10 | 1.88 | 2.18 | 0.779 | (same) | 19 MB | Index Scan, 1.4 ms |

Noise warning: the unindexed 12k number (69 ms median) was measured while other agents were embedding on the same CPU; the same exact query on an already-open connection measured later in the run took 33.6 ms median (connection section below). Treat the exact-scan cost at 12k as roughly 35-70 ms, i.e. about 3-6 ms per 1,000 chunks.

Filtered vector query (`document_name = gold doc`): exact plan is an index (or bitmap) scan on the UNIQUE index followed by a tiny sort, 0.09 ms execution; HNSW ef_search=40 recall vs exact filtered = 1.000. Caveat: this test is weak, because the core documents have only about 3 chunks each, so the filter returns 3 rows. It does not exercise the known pgvector failure mode (index scan returns ef_search candidates, then the WHERE clause removes most of them, returning fewer than k rows). If a vector index is ever added, document-scoped search needs `hnsw.iterative_scan` (pgvector 0.8+) or a planner that prefers the btree filter path; that must be tested before shipping.

Recall reading: absolute recall (0.81-0.89 for HNSW, 0.24/0.78 for IVFFlat) is pessimistic. The filler text is templated, so its embeddings are nearly identical to each other and the 10 nearest neighbours of a query among them are essentially arbitrary ties; ANN recall on real prose is normally higher. Relative ordering (HNSW > IVFFlat at equal latency, recall rises with ef_search/probes, m=32 buys about +0.03 recall for 2.7x build time and 1.5x query time) is the usable conclusion, not the absolute values.

## Results: keyword search (38 queries, top-10)

| Backend | N=3,024 median / p95 ms | N=12,024 median / p95 ms |
|---|---|---|
| BM25 in-memory, first call (SELECT all rows + tokenize + build), single call | 805 | 2,383 |
| BM25 in-memory, cached index, per query (includes fingerprint query) | 156.4 / 255.3 | 279.2 / 348.0 |
| of which fingerprint query (count, max(id), sum(hashtext(content))) | 7.3 / 7.6 | 27.2 / 28.3 |
| BM25 single-document scope (cached; 10 queries, includes one scoped build) | 122.5 / 176.2 | 139.1 / 231.9 |
| BM25 next search after inserting ONE row (full rebuild), single call | 458 | 2,270 |
| BM25 next query after the rebuild, single call | 108 | 176 |
| PostgreSQL FTS, no index | 797.5 / 1155.2 | 1710.5 / 2502.1 |
| PostgreSQL FTS, no index, 1-document scope | 124.2 / 160.7 | 117.4 / 125.9 |
| PostgreSQL FTS, GIN `to_tsvector('english', content)` | 244.6 / 789.4 | 378.9 / 1445.2 |
| PostgreSQL FTS, GIN, 1-document scope | 126.2 / 187.6 | 102.6 / 145.5 |
| GIN build time / size | 0.87 s / 384 kB | 1.51 s / 1.5 MB |

- BM25 memory: resident-memory (RSS) delta after the first build, via psutil: 19.2 MB at 3,024 chunks, 49.4 MB at 12,024 chunks (about 4-6 KB per chunk; includes the cached document text). Roughly 4 MB per 1,000 chunks, per cached scope key (each distinct document/page scope creates another cached index).
- BM25 cached-query cost is the largest retrieval-side cost found: it grows about linearly with N (rank_bm25 `get_scores` is pure Python/NumPy over all documents per query term, then a full Python sort of N items), and the fingerprint query adds a full-table scan on every search (27 ms at 12k). Any corpus change, even one row, costs a full rebuild (2.3 s at 12k) on the next search, which blocks that request.
- FTS with GIN: the plan changes from Seq Scan to Bitmap Heap Scan and median drops 3.3x (797 to 245 ms) and 4.5x (1710 to 379 ms), but absolute time stays high because the OR-query over common words matches a large fraction of the templated filler (613 of 3,024 rows for the 3-term example), and `ts_rank_cd(to_tsvector(...))` is recomputed from text for every matching row. p95 stays bad for the same reason. This is an artefact of the templated vocabulary: real selective queries (identifiers such as ERR-4096) would be far faster, and I did not measure a selective-only subset, so FTS+GIN is shown at its worst case here. The GIN index is used by the service query (timings dropped), confirming the `%s::regconfig` parameter form does not defeat it.
- Do not read FTS-vs-BM25 relevance from these numbers; this workstream measures cost only.

### Document-name filter and the btree question

| | N=3,024 | N=12,024 |
|---|---|---|
| plan using only existing PK + UNIQUE(document_name, page_number, chunk_id) | Index Scan on `document_chunks_document_name_page_number_chunk_id_key`, 0.133 ms | Bitmap Heap Scan via that same UNIQUE index, 0.181 ms |
| plan with extra btree(document_name) | Index Scan on `chunks_docname`, 0.161 ms | Bitmap Heap Scan via `chunks_docname`, 0.178 ms |
| client median, 20x5 repeats | 0.79 ms vs 0.56 ms | 0.57 ms vs 0.34 ms |
| extra index size | 56 kB | 168 kB |

Verified by EXPLAIN: the existing UNIQUE index already serves `document_name = ANY(...)` (leading column). The extra btree is chosen only because it is smaller; execution time is identical (0.13-0.18 ms) and the client-side difference (0.2 ms) is within noise. **No extra document_name index is justified.** The page_number filter alone would not use the UNIQUE index (not a prefix), but pages are always combined with document names in this project and the table is small.

## Results: connection overhead

| | N=3,024 run | N=12,024 run |
|---|---|---|
| new `psycopg.connect` + `register_vector` + close, per call | 123.6 ms median, 228 p95 | 78.9 ms median, 182 p95 |
| reused connection, `SELECT 1` | 0.28 ms | 0.14 ms |
| reused connection, real exact vector query | 15.4 ms (N=3k) | 33.6 ms (N=12k) |
| query embedding (MiniLM, CPU, warm) | 59.8 ms | 20.1 ms |
| psycopg_pool | not installed | not installed |

`psycopg_pool` is not installed in `.venv` (ModuleNotFoundError), so a pool was not measured and nothing was installed. A pool would behave like the reused connection (about 0.1-0.3 ms checkout) apart from `register_vector` configuration done once per connection. Every search currently opens a fresh connection (`semantic_search`, BM25 `_get_index`, FTS), so one hybrid query pays the 80-125 ms connect cost about twice, which exceeds the query embedding time and every database operation measured here at N up to a few thousand. At small N, connection setup is the dominant database-side latency, larger than any index would save.

## Findings by question

- Exact scan scales linearly: about 3-6 ms per 1,000 chunks. Below roughly 3,000 chunks the whole scan is ~10-15 ms.
- HNSW gives about 2-3 ms flat at 3k and 12k (a 7-35x speed-up) but costs 6-23 MB of disk, 4-20 s build, loses exactness (recall 0.81-0.89 on the hard synthetic set) and the planner is unstable near N=3k.
- IVFFlat is smaller/faster to build but recall at probes=1 is unacceptable (0.21-0.24); probes=10 reaches 0.76-0.78, still worse than HNSW ef=40. It also needs rebuilding as data grows and must be built after data load. Not recommended over HNSW.
- Keyword side is the bigger scaling problem than vector side in the current design: cached BM25 costs 156 ms (3k) and 279 ms (12k) per query, more than an exact vector scan at the same size, plus 2.3 s rebuild stalls.

## Limitations

- Single machine, Windows, shared with two other benchmark agents (embedding comparison, A-E re-run). Lock serialised latency loops, but CPU contention from non-latency phases of the other agents (embedding, index builds) was still present; p95 values and the 12k exact-scan median are visibly noisy (see 69 ms vs 33.6 ms for the same query).
- Synthetic, templated filler: 7 sentence templates, ~10 teams/20 topics/10 verbs/10 measures. Embeddings of filler are near-duplicates, which makes ANN recall pessimistic and makes FTS OR-queries match too many rows. BM25/FTS timing depends on query term frequency and is unrepresentative of selective queries.
- Query set is small (38) and 3 repeats each; embedding timing was affected by contention (59.8 ms vs 20.1 ms warm).
- Recall is measured against the exact top-10 of the same synthetic table, not against human relevance.
- Filtered ANN behaviour was only trivially tested (3-row filters).
- Gold documents were also present at both scales, so tiny corpora like production's ~9 chunks are not benchmarked directly; their cost is extrapolated (exact scan well under 1 ms).

## RECOMMENDATION

1. **No vector index now.** Production has ~9 chunks and typical use is stated to be under 10,000. Exact scan costs about 15 ms at 3k and 35-70 ms at 12k; indexes add disk, build time, planner instability and lost exactness for savings of tens of milliseconds, which is small next to the LLM call. A tiny corpus does not need any index: Postgres will not use an ANN index below a few thousand rows anyway (planner picks seq scan), and recall would only drop.
2. **Thresholds at which an index becomes worthwhile** (from these measurements): vector HNSW when the table exceeds roughly 20,000-50,000 chunks (exact scan above ~100 ms) or a latency target below ~30 ms is set. Use HNSW m=16, efc=64, ef_search >= 100 (recall 0.87+ here; re-verify on real data), not IVFFlat. Full-text GIN index when FTS is selected as the backend (`BM25_BACKEND=fts`) and N exceeds about 2,000-3,000 chunks: it removed 3-4.5x of the FTS cost in the worst case measured and costs under 2 MB. No GIN needed while BM25 backend is `memory` (default).
3. **No extra btree on document_name.** The existing UNIQUE (document_name, page_number, chunk_id) is used for document filters (verified in plans).
4. **Connection reuse is the one change justified at any size**: per-call connect costs 80-125 ms versus 0.1-0.3 ms reused, and each search opens one or more connections. Recommended (needs owner approval since it touches `services/database.py` and requirements; `psycopg_pool` is not installed): add `psycopg_pool` to requirements and make `get_connection()` return a pooled connection (`ConnectionPool(DATABASE_URL, min_size=1, max_size=5, configure=register_vector)`), or as a zero-dependency alternative cache one connection per thread. Not applied here.
5. **In-memory BM25 is the next bottleneck before pgvector is**: ~4 MB RAM per 1,000 chunks per scope, 156-279 ms cached query at 3k-12k, 2.3 s full rebuild per corpus change at 12k, plus a full-table fingerprint scan (27 ms at 12k) on every search. Fine below ~3,000 chunks; above that either switch `BM25_BACKEND=fts` with the GIN index below, or keep BM25 but make rebuilds incremental/background. Further evidence is needed before choosing (see below).

### Draft migration for review (not created as a file; do not apply to production without review)

```sql
-- Only when the table passes ~20k chunks. Run outside a long transaction.
-- Vector: HNSW (cosine, matches the "<=>" operator used by semantic_search)
CREATE INDEX CONCURRENTLY IF NOT EXISTS document_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
-- Per-session / per-connection setting, not a migration (set in get_connection after pooling):
--   SET hnsw.ef_search = 100;
--   SET hnsw.iterative_scan = relaxed_order;   -- pgvector >= 0.8, needed for document-scoped queries

-- Keyword: only if BM25_BACKEND=fts is adopted and N > ~3k.
-- Expression must match fts_search exactly: to_tsvector('english', content)
CREATE INDEX CONCURRENTLY IF NOT EXISTS document_chunks_content_fts
    ON document_chunks USING gin (to_tsvector('english', content));

-- NOT recommended: btree(document_name) - duplicates the UNIQUE index prefix.
-- Rollback:
-- DROP INDEX CONCURRENTLY IF EXISTS document_chunks_embedding_hnsw;
-- DROP INDEX CONCURRENTLY IF EXISTS document_chunks_content_fts;
```

### Further evidence needed

- Repeat on a real corpus of 5k-50k chunks (not templated filler) with real queries: ANN recall vs exact on real embeddings, and FTS/BM25 timing on selective vs broad queries.
- Test HNSW with document-scoped queries where the filter is selective but not tiny (e.g. 1% of the table), with and without `hnsw.iterative_scan`, to check that fewer than k rows are not returned.
- Quiet machine (no concurrent benchmarks) to tighten p95 and the exact-scan figures; add a pool measurement after `psycopg_pool` is approved and installed.
- Measure end-to-end request latency (embedding + retrieval + rerank/LLM) to confirm that the database part is a small share; embedding alone is 20-60 ms.
- Measure BM25 with an incremental or per-document index, and FTS ranked via a stored `tsvector` column, since `ts_rank_cd(to_tsvector(...))` recomputation drives the FTS GIN cost.
