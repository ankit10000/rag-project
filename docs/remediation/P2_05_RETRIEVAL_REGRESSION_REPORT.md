# P2-05 — Retrieval Regression Verification Report

Date: 2026-11-12  
Scope: verification of the existing retrieval pipeline after P2-01 through P2-04. No application code, schema, migration, ranking logic, or retrieval defaults were changed for P2-05.

## Retrieval architecture inspected

`hybrid_search()` delegates to `hybrid_search_detailed()`. For a query, the pipeline optionally requests vector candidates from `semantic_search()` and keyword candidates from `keyword_search()`. Keyword search defaults to in-memory BM25 (`BM25_BACKEND="memory"`) and can select PostgreSQL full-text search (`"fts"`). Both backend APIs return tuples shaped as `(id, document_name, page_number, content, score)`; the vector score is cosine distance and keyword scores are backend-specific relevance scores.

The shared scope builder adds exact `document_name = ANY(...)` and `page_number = ANY(...)` predicates. BM25 builds a cached index per scope and refreshes it against a corpus fingerprint. FTS uses `to_tsvector`/`to_tsquery` and `ts_rank_cd`. Vector search embeds the query, orders by cosine distance and optionally applies the configured similarity floor.

Fusion receives nonempty keyword and vector lists. RRF sums weighted reciprocal ranks, sorts deterministically, deduplicates IDs and normalized content, and returns chunk plus `rrf_score`. Interleave fusion round-robins the input lists and deduplicates by ID. If enabled, the cross-encoder reranks only fused candidates, adds `rerank_score`, and slices to the final limit. The legacy wrapper returns the `results` list from the detailed response.

Ingestion chunking defaults to word chunks; sentence packing is selectable. The embedding model is loaded in `services/embedding_service.py` as `all-MiniLM-L6-v2`. Although `retrieval_config.EMBEDDING_MODEL` documents an environment-overridable model setting, the current embedding service hardcodes this model name; this was recorded as an implementation fact and not changed.

## Actual defaults

Values read from `services.retrieval_config` in the current environment:

| Setting | Value |
|---|---:|
| `VECTOR_TOP_K` | 10 |
| `BM25_TOP_K` | 10 |
| `BM25_DROP_STOPWORDS` | `False` |
| `BM25_BACKEND` | `memory` |
| `RRF_K` | 60 |
| `RRF_TOP_K` | 10 |
| `RERANK_ENABLED` | `True` |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| `RERANK_TOP_K` | 10 |
| `FINAL_TOP_K` | 5 |
| `SIMILARITY_THRESHOLD` | unset (`None`) |
| `EMBEDDING_MODEL` / actual loader model | `all-MiniLM-L6-v2` / hardcoded `all-MiniLM-L6-v2` |
| `EMBEDDING_DIM` | 384 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 100 / 20 words |
| `CHUNK_STRATEGY` | `words` |

All retrieval defaults above remain unchanged. `test_retrieval_phase2.py` also verifies environment overrides for several settings. The config module parses integer/float values directly, booleans from `1/true/yes/on`, optional floats as `None` when unset, and does not validate ranges or malformed values beyond Python's conversions.

## Test matrix and execution

All focused scripts below were run through `run_tests.py`, targeting `rag_test_scratch`; the runner enabled `testsafe`, blocked outbound network, and set Hugging Face/Transformers offline mode. No test issued a Gemini call.

| Verification area | Evidence | Result |
|---|---|---|
| Vector-only, BM25-only, FTS-only retrieval | P2-03 metadata test exercises the individual backends; P2 retrieval regression uses deterministic corpus and vector mocks | PASS |
| Hybrid vector+BM25 and vector+FTS | P2-03 tests both backends, vector-only, keyword-only, and wrapper forwarding | PASS |
| RRF ranking, weights, tie order, deduplication, top-K | P2 retrieval regression assertions | PASS |
| Interleave fusion | P2-03 exercises interleave with deterministic fixtures | PASS |
| Cross-encoder reranking | P2 retrieval regression uses mocked model for ordering and cached local model; P2-03 checks real local reranker filtering/subset behavior | PASS |
| Metadata document/page filters through pipeline | P2-03 checks all backends and hybrid/reranking; P2 retrieval regression checks scoped corpus and page filters | PASS |
| Duplicate content | P2 retrieval regression checks RRF content dedupe and ingestion duplicate handling | PASS |
| Empty corpus, unknown scope, no-match and similarity floor | P2 retrieval regression checks each; empty corpus yields no results | PASS |
| Positive top-K bounds and result order | Backend/fusion/reranker assertions in P2 regression scripts; deterministic mutation probe below | PASS for tested positive values |
| Config override and defaults | P2 regression subprocess override assertion; defaults read from live config module | PASS |
| P2-04 embedding-count guard | P2-04 asserts too few and too many vectors both raise `ValueError` and store no rows | PASS |

### Focused regression runs

- `test_retrieval_phase2.py`: PASS.
- `test_p2_01_pdf_ingestion.py`: PASS on rerun.
- `test_p2_02_sentence_chunking.py`: PASS.
- `test_p2_03_metadata_filters.py`: PASS.
- `test_p2_04_ingestion_edge_cases.py`: PASS.

The first combined focused invocation hit a Windows `cp1252` encoding exception in the parent runner while it printed Unicode output from the P2-01 child. P2-01 was rerun with `PYTHONIOENCODING=utf-8` and passed. This was a runner-console issue, not a P2-01 test failure.

### Full default suite

Executed `.venv\Scripts\python.exe run_tests.py` with parent `PYTHONIOENCODING=utf-8` so the runner can print Unicode safely. Result: **27 run, 27 passed, 0 failed**. This includes all five requested retrieval/P2 scripts and the embedding-count guard. Two passing suite entries are designated smoke-only by the runner (`test_similarity.py`, `test_memory_storage.py`) and are not assertion-based verification. Live Gemini and manual categories were skipped by the default suite; no live tests were invoked.

## Mutation checks

No repository source or test file was modified for mutation checks. In-memory deterministic probes (network blocked, offline model setting) verified that both RRF and interleave hybrid outputs stayed within the union of their inputs and contained unique IDs; RRF preserved candidate membership/deduplication; reranking returned the expected highest-scored candidate, honored a positive top-K, and introduced no new candidate. These checks validate the invariants on fixtures; they are not a claim that the entire regression suite was rerun against altered application modules.

| Representative fault | Evidence / outcome |
|---|---|
| Vector or keyword candidates ignored | Static regression coverage: retrieval tests assert vector paraphrase hits, BM25 exact identifiers, FTS exact identifiers, and hybrid recovery of a vector/keyword blind spot. Dedicated source-mutant run not performed. |
| FTS branch ignored in hybrid | Static coverage includes hybrid-FTS and direct FTS, but the deterministic overlap in the fixture may not distinguish a hybrid branch substitution in every query. No mutant run performed. |
| RRF rank formula/order broken | Assertions verify exact reciprocal-rank scores, order, weights, deterministic ties, and top-K; static evidence only. |
| RRF deduplication broken | Assertions verify duplicate ID/content collapse; fixture probe confirms unique IDs and input-subset invariant. |
| Reranker bypassed | Regression tests assert score ordering and the real reranker relevance result; P2-03 checks that reranker is called with filtered candidates. No source-mutant run performed. |
| Metadata filter removed | P2-03 has backend- and pipeline-level assertions that fail when returned metadata lies outside the requested scope. |
| Empty retrieval fabricates results | Explicit no-match and empty-corpus tests assert `[]` for each backend/hybrid path. |
| Positive top-K ignored | Positive top-K assertions exist for RRF and reranking; top-K probe passed. |

### Boundary defect found

The additional zero-limit probe found a reproducible edge case: `hybrid_search_detailed("q", top_k=0, rerank=False)` returns one result because `top_k = top_k or cfg.FINAL_TOP_K` replaces zero with the default, and `reciprocal_rank_fusion(..., top_k=0)` also appends one item before checking its limit. This does not affect the configured positive default (`FINAL_TOP_K=5`) or the positive limits exercised by the regression suite, but it violates a literal zero top-K request. No fix was applied. Smallest proposed fix: distinguish `None` from zero in hybrid defaulting and return an empty list from RRF when `top_k <= 0` (with equivalent validation/behavior considered for direct retrievers). Approval is required before changing application code.

### Update — P2-05-F1: zero top-K FIXED (user-approved)

The paragraph above describes the state **before** the fix and is superseded by this section.

**Application changes (two lines of logic):**
- `services/hybrid_search_service.py`: `top_k = top_k or cfg.FINAL_TOP_K` → `top_k = cfg.FINAL_TOP_K if top_k is None else max(0, top_k)` (`None` keeps the default 5; 0 or negative means "no results").
- `services/rrf_service.py`: `reciprocal_rank_fusion` returns `[]` immediately when `top_k <= 0`.

**Before / after:** `hybrid_search_detailed("q", top_k=0, rerank=False)`: before 1 result, after `[]` (also with reranking, interleave fusion and the `hybrid_search` wrapper). `reciprocal_rank_fusion(..., top_k=0)`: before 1 result, after `[]`. Negative `top_k` in hybrid/RRF: now `[]` (before: RRF returned 1 result; hybrid sliced from the end). Positive values and the `None` default are unchanged.

**Direct retrievers (probed on the scratch DB, NOT changed):** `top_k=0` already returns `[]` for vector, BM25 and FTS. Negative `top_k` is inconsistent today: vector and FTS raise a PostgreSQL error (`InvalidRowCountInLimitClause`), BM25 slices off the last item (`ranked[:-1]`). These are not reachable through `hybrid_search_detailed` (it clamps first). Left as a documented limitation; no new semantics invented for them.

**Tests:** new unit test `test_p2_05_zero_top_k.py` (retrievers and reranker faked; no DB/model/network use beyond the shared guard), registered under `unit` in `run_tests.py`: RRF and hybrid for top_k 0, -1/-3, 1, 3, None across rrf/interleave × rerank on/off, plus counts and the wrapper. Result: **0 FAIL**.
**Mutation (executed, repo untouched):** `top_k or default` restored → 9 checks FAIL; RRF guard removed → 2 FAIL; negative clamp removed → 4 FAIL. All caught.
**Regression (completed, not killed):** full default suite `run_tests.py --clean`: **28 / 28 passed, 0 failed** (27 prior + the new test), including `test_retrieval_phase2` and P2-01 to P2-04. `rag_db` fingerprint unchanged: **True**. Scratch DB only, network blocked, no Gemini. A temporary probe row (`p2_05probe.pdf`) was inserted into and deleted from the scratch DB only.

**Files changed for F1:** `services/hybrid_search_service.py`, `services/rrf_service.py`, `run_tests.py` (registration), new `test_p2_05_zero_top_k.py`, this report. Nothing committed. The `EMBEDDING_MODEL` hardcoding is a separate issue and was not touched.

## Database safety and network evidence

The focused and full test runs used the runner's scratch URL for test execution; `testsafe` guards database connections, and tests cleaned their uniquely named rows. The runner performs its documented **read-only** before/after fingerprint connection to `rag_db` for the acceptance check; it reported `application database 'rag_db' fingerprint unchanged : True` for the full default run. No test writes were directed at `rag_db`.

After verification, the 24 rows belonging to the exact synthetic `eval.corpus.DOCS` fixture names left by `test_retrieval_phase2.py` were deleted from `rag_test_scratch` through a `testsafe`-guarded connection; the scratch `document_chunks` count is now 0. Other scratch tables were left untouched.

The default runner blocked outbound network for unit/integration tests and used offline Hugging Face/Transformers flags. Gemini/live tests were not selected. The optional in-memory probe was repeated with Hugging Face offline flags and a socket-level external-network block; the local embedding model loaded cached weights, logged an expected offline Hub-cache notice, and no download or successful network call occurred.

## Defects, limitations, and uncovered cases

- ~~Defect: zero top-K is not respected by hybrid/RRF~~ — **FIXED** by P2-05-F1 (see update above). Remaining: negative `top_k` on the direct retrievers is inconsistent (not fixed).
- `EMBEDDING_MODEL` config does not control the hardcoded loader in `embedding_service.py`.
- Existing tests cover a cached real local cross-encoder, so their result depends on the available local model cache; the offline runs succeeded here.
- Fault injection against every backend-ignored/reranker-bypassed source mutation was not executed. Existing test assertions and invariant probes are reported separately above.
- Live Gemini paths and manual legacy scripts were intentionally not run.
- The runner's `rag_db` fingerprint uses row counts and ordered table-content hashes for its configured table set; it is read-only and is the available safety evidence, not a full physical database snapshot.

## Files created or modified for P2-05

- Created: `docs/remediation/P2_05_RETRIEVAL_REGRESSION_REPORT.md`.
- Modified: none for P2-05.

Pre-existing workspace changes were present before this task: `run_tests.py`, `services/ingestion_service.py`, `test_p2_04_ingestion_edge_cases.py`, and `docs/remediation/P2_04_INGESTION_EDGE_CASES_REPORT.md`. They were preserved and are not attributed to P2-05.

**P2-05 verification stopped after this report.**
