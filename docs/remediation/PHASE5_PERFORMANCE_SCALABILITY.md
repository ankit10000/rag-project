# Phase 5 — Performance and Scalability

**Status (2026-11-15):** source-level optimizations and instrumentation implemented. **Nothing was measured.**
- No test, benchmark, profiler, load test or model call was executed.
- No database was accessed.
- Every impact statement below is an **estimate from code reading**, not a measurement.

## 1. Architecture inventory (per request turn and per ingestion)
| Stage | Where | Cost driver (from source) | Measurable today? |
|---|---|---|---|
| Ingestion: text extraction | `pdf_parser.extract_text` | PyMuPDF per page; A3 size/page limits first | no (needs instrumentation) |
| Chunking + dedupe | `chunker.chunk_page`, `ingest_pdf` | linear in words; SHA-1 per chunk | no |
| Embedding (ingestion) | `embedding_service.generate_embeddings(texts)` | one batched `encode` per document | **yes** (`embedding.encode`, batch size) |
| Vector insertion | `ingest_pdf` | one transaction, one `INSERT … ON CONFLICT` per chunk, plus the A2 delete | no |
| Query embedding | `semantic_search`, `search_memories`, `save_memory`/`update_memory` | one `encode` per call; the same text is often embedded twice per turn | **yes** (cache hit/miss counters) |
| Vector retrieval | `search_service.semantic_search` | pgvector `ORDER BY embedding <=> q LIMIT k`, new connection | no |
| BM25 | `bm25_service` | fingerprint query on every call; full-scope load and index build on a miss | **yes** (hit/miss, build time and size) |
| FTS | `fts_service` | one SQL query | no |
| RRF / interleave | `rrf_service`, `hybrid_search_service._interleave` | small lists (≤ 10 + 10), negligible | partly (`timings_ms` already in `hybrid_search_detailed`) |
| Cross-encoder | `reranker_service` | lazy model load once; `predict` on ≤ 10 pairs | **yes** (`reranker.model_init`, `reranker.predict` with candidate count) |
| Context assembly | `context_assembly_service` | linear in sources | no |
| LLM request | `llm_service.generate_answer` | network-bound; per-model retry and fallback; 120 s timeout | tokens via `usage_log` (existing) |
| Classify + rewrite + answer | `rag_service.ask_question` | 2–3 sequential LLM calls per turn | per-call usage (existing) |
| Memory retrieval | `memory_search_service.search_memories` | one embed + one vector query | embed counters |
| Memory context | `memory_context_service` | 2 read queries for provenance of ≤ 5 memories | **yes** (`memory_context.provenance`) |
| Memory extraction | `memory_service`, `automatic_memory_service` | 1 LLM call per batch; per memory: candidate query, LLM decision, write | no |
| DB connections | `database.get_connection` | **new connection plus `register_vector` type lookup on every call** | no |

### Identified bottlenecks and risks (source inspection)
1. **No connection reuse.** Every `get_connection()` opens a TCP/auth session and runs `register_vector`. One answer turn opens several: BM25 fingerprint, vector search, memory search, memory provenance, history, summary, saves. This is the largest avoidable overhead, but fixing it is not a safe drop-in (see §10).
2. **Duplicate query embedding.** The user query is embedded by the memory search and again by the document vector search when the rewrite returns the same text (always, when there is no history).
3. **Unbounded BM25 cache.** Each distinct document/page filter scope kept a full copy of its rows plus a BM25 index forever.
4. **Full sort for top-k in BM25.** `sorted()` ran over every chunk's score to keep 10.
5. **BM25 fingerprint per call.** `count/max/sum(hashtext)` over the scope on every keyword search. It is needed for correctness (staleness), so it was kept.
6. **Logging of personal content.** Every extraction printed all candidate memory texts and the model's replacement text; deletion printed the memory text.
7. **Per-memory candidate re-query during extraction.** `process_memory` re-reads the latest-20 candidates for every extracted memory. This is kept on purpose: later memories must see earlier writes in the same batch.
8. **Sequential LLM calls.** Classification and rewrite are independent of each other but run sequentially; see §9.

## 2. Implemented optimizations
| # | Change | File | Behaviour preserved because |
|---|---|---|---|
| O1 | **Bounded LRU cache for single-text embeddings.** Key `(EMBEDDING_MODEL, exact text)`, values copied in and out, `EMBEDDING_QUERY_CACHE_SIZE` (default 256; 0 disables). | `services/embedding_service.py` | The model is deterministic for a given text and the model name is part of the key, so a hit returns what `encode` returns. Batches (ingestion) are not cached. |
| O2 | **BM25 index cache bounded** to `BM25_CACHE_MAX_ENTRIES` (default 8) filter scopes, LRU. | `services/bm25_service.py` | Eviction only forces a rebuild; the corpus-fingerprint check still guards staleness. |
| O3 | **BM25 top-k with `heapq.nlargest`** instead of a full sort. | `services/bm25_service.py` | Python documents `nlargest(n, it, key)` as equivalent to `sorted(it, key=key, reverse=True)[:n]` (same ties order). The `score > 0` filter is unchanged. Non-standard `top_k` values (e.g. negative) keep the exact previous slicing path. |
| O4 | **Opt-in instrumentation** `services/perf_metrics.py` (`RAG_PERF_METRICS=1`): bounded timings and counters, ints and names only. Hooks: model init, encode and batch size, query-cache hit/miss, BM25 cache hit/miss and build size, reranker init and predict with candidate count, memory-context provenance with candidate count. | `perf_metrics.py`, `embedding_service.py`, `bm25_service.py`, `reranker_service.py`, `memory_context_service.py` | Disabled by default, so each hook is a cheap no-op. When enabled it only records, never alters values or exceptions. |
| O5 | **Logs no longer print memory content:** candidate list → count and ids; model decision → action, id and replacement length; delete → memory length; semantic-duplicate skip → existing id. | `automatic_memory_service.py`, `memory_storage_service.py` | Only `print` output changed; no decision, write or deletion logic changed. |
| O6 | **New config knobs:** `EMBEDDING_QUERY_CACHE_SIZE`, `BM25_CACHE_MAX_ENTRIES`, `RAG_PERF_METRICS`. | `services/retrieval_config.py` | No retrieval default, threshold or limit changed. |

**Estimated impact (estimates, not measured):**
- **O1:** one fewer `encode` call per turn when the search query equals the user query, and repeated identical queries avoid encoding. Memory cost is about 256 × 384 floats (~0.4 MB).
- **O2:** the memory held by BM25 is bounded to at most 8 scope copies.
- **O3:** top-k selection drops from O(n log n) to O(n log k) for large corpora. It is negligible for small ones.
- **O4/O5:** negligible.

## 3. Behaviour changes
- **None to retrieval results, rankings, thresholds, limits, answer generation, memory decisions, provenance, deletion or checkpoints.**
- **Observable log text changed** (O5). Any external tooling or test that parsed those `print` lines (memory texts) would see ids and counts instead.

## 4. Cache design and invalidation
| Cache | Key | Value | Invalidation | Bound | Persistence | Concurrency |
|---|---|---|---|---|---|---|
| Embedding (O1) | `(EMBEDDING_MODEL, exact text)` | normalized vector (copy) | process restart; `clear_embedding_cache()`; a model change changes the key | `EMBEDDING_QUERY_CACHE_SIZE` entries, LRU | in-process only | `threading.Lock` |
| BM25 index (existing, now bounded) | `(document filter, page filter, drop_stopwords)` | rows + BM25 index + fingerprint | per-call fingerprint (count, max id, sum of `hashtext`) mismatch → rebuild; `clear_bm25_cache()` | `BM25_CACHE_MAX_ENTRIES` scopes, LRU | in-process | `threading.Lock` |
| Reranker model (existing) | — | CrossEncoder instance | process restart | 1 | in-process | lock on lazy init |

**Isolation:**
- The embedding cache holds no conversation-specific *results*; it maps text to a vector.
- No retrieval results, memory selections, provenance verdicts or LLM answers are cached. Provenance filtering therefore runs on every turn, and an unsupported memory cannot enter the context through a cache.
- Memory text embedded for storage is cached like any other single text. That is safe, because the embedding of a text never depends on the conversation.

**Not cached, by decision:**
- final answers;
- retrieval result lists, which would need document-update invalidation across vector, BM25 and FTS;
- memory search results, which are conversation-scoped and change with every write.

No external cache service was introduced.

## 5. Resource lifecycle decisions
- **Embedding model:** loaded once at import (unchanged); init time is instrumented.
- **Cross-encoder:** lazily loaded once behind a lock (unchanged); instrumented.
- **No new model or downloads:** no model initialization was added and nothing is downloaded. Embedding dimension validation in ingestion is unchanged.
- **Connections:** still opened and closed per operation by the `with` blocks, so connections are not leaked. Pooling is deferred (§10).

## 6. Concurrency decisions
- **Single-user CLI:** no parallelism was introduced. The order of memory writes, checkpoint advancement, provenance validation, ingestion transactions and provider fallback is unchanged.
- **Shared mutable state:** new state is behind locks (embedding cache, BM25 cache, perf metrics). Existing shared state (`llm_service.usage_log`, quota cooldown dict) is unchanged and is single-threaded in practice.
- **Model thread-safety:** `SentenceTransformer` and `CrossEncoder` instances are shared. Concurrent `encode`/`predict` calls are not serialized. This is acceptable for the single-user CLI; any future multi-threaded server must review it (§11).

## 7. Database
- **No schema change, migration or index creation**, and no database was accessed.
- **Existing indexes:** from migrations and `docs/phase5_audit.md`, the extraction-checkpoint query and the memory lookups are served by existing indexes: `(conversation_id, id)` uniques and `memory_sources_message_idx`.
- **Deferred (§10):** an ANN index (HNSW/IVFFlat) on `document_chunks.embedding` would make vector search **approximate** and could change results. It is not proposed as a migration here and needs a separate, benchmarked approval.

## 8. Observability
- **Enable** with `RAG_PERF_METRICS=1`; read with `services.perf_metrics.snapshot()`.
- **What is recorded:** names and integers only, with at most 200 distinct names.
- **Not recorded:** document text, memory text, prompts, queries, keys or credentials.
- **Remaining content in logs:** `rag_service` still prints a 100-character snippet of each retained chunk in its reranker debug output. That is retrieval behaviour-adjacent and was left unchanged. Removing it is a deferred item.

## 9. Deferred optimization opportunities (not implemented)
| Opportunity | Why deferred |
|---|---|
| Connection pooling (`psycopg_pool`) or a per-request connection | Changes transaction and commit semantics of every `with get_connection()` block (commit on exit, close). It also needs a dependency check and a careful rollout. Highest expected gain. |
| Cache `register_vector` type info per process | Depends on psycopg/pgvector internals; correctness must be verified. |
| Run classification and rewrite concurrently | Changes provider call ordering, fallback cooldown and quota interaction. Explicitly out of scope. |
| Batch provenance queries across turns / cache provenance | Would risk serving stale provenance after deletions. |
| Cache the BM25 fingerprint between calls | Would allow stale results after ingestion or deletion. |
| ANN vector index | Approximate search can change rankings; needs benchmark and approval. |
| Single extraction-batch candidate read | Later memories must see earlier writes; would change decisions. |
| Remove chunk snippets from the reranker debug print | Behaviour-adjacent logging in the retrieval path; separate approval. |
| Async I/O | No concurrency need in a single-user CLI; would add complexity without demonstrated benefit. |

## 10. Risks and limitations
- **Nothing measured:** no performance claim is measured; the estimates above are qualitative.
- **Embedding cache test risk.** A test that patches `embedding_service.model` (instead of `generate_embeddings`) could receive a cached real vector for a text embedded earlier in the same process. Existing tests patch `generate_embeddings` at the call sites or load fresh module copies (A1), so this is expected not to matter. Unverified.
- **BM25 eviction:** a deployment that alternates among more than 8 filter scopes rebuilds indexes more often (slower, never wrong). The limit is tunable.
- **O3 equivalence** relies on the documented `heapq.nlargest` contract; not verified by execution.
- **Log changes** may affect any external log parsing.

## 11. Future profiling and benchmarking plan (requires authorization)
1. Enable `RAG_PERF_METRICS=1` on a scratch database with a fixed corpus (e.g. the Phase 2 eval corpus). Run a fixed set of offline queries with the LLM mocked, then capture `snapshot()`: encode calls and batch sizes, cache hit rates, BM25 builds, reranker latency, provenance query time.
2. Add connection-count instrumentation (wrap `get_connection`) to quantify §1-1 before choosing a pooling design.
3. Compare retrieval outputs before and after O1–O3 on the same queries; they must be identical. Run retrieval-quality checks with the Phase 4 framework on development data only.
4. Benchmark candidate deferred items (pooling, ANN) on scratch clones, with explicit approval and frozen comparison criteria.

## 12. Files
- **New:** `services/perf_metrics.py`, this document.
- **Modified:** `services/embedding_service.py`, `services/bm25_service.py`, `services/reranker_service.py`, `services/memory_context_service.py`, `services/automatic_memory_service.py` (log lines only), `services/memory_storage_service.py` (log lines only), `services/retrieval_config.py` (3 knobs).

**TESTING AND BENCHMARKING NOT RUN — strictly prohibited by user instruction. No unit tests, integration tests, smoke tests, regression tests, evaluations, benchmarks, load tests, stress tests, live model calls, or evaluation scripts were executed. Only source inspection, static review, and optional syntax compilation were performed.**
