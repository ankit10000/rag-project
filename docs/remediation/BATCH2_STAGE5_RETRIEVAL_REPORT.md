# Batch 2, Stage 5: Retrieval Pipeline

**Date:** 2026-11-16. **Scope:** retrieval only.
**Not done:**
- No answer generation, memory, ingestion, schema or model changes.
- Nothing committed or pushed.
- Stage 6 not started.

## A. Baseline

### Git and environment

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD | `358b8b2` "Add SQL proposal for embedding model tracking and implement ingestion tests" (2026-11-16, by `ankit10000`) |
| Stage 4 commit | Separate: 12 files, exactly the Stage 4 set (`documents.py`, `harness.py`, `run_tests.py`, `ingestion_service.py`, `pdf_parser.py`, 3 updated tests, 2 new tests, report, proposal 007) |
| Worktree | Clean |
| Remote | `origin/main` = `358b8b2`, in sync |
| Python | 3.14.10 |
| PostgreSQL | 18.6, pgvector 0.8.7 |

### Database target
- `rag_ingestion_test`, the Stage 4 disposable database.
  - `current_database()` confirmed it.
  - It was empty at preflight: chunks, conversations, messages, memories and links all 0.
  - Credentials come from `.env` with the database name replaced; the URL is never printed.
- `rag_db` was only read:
  - Read-only fingerprint (row count + md5 per table): conversations 261, messages 1340, conversation_memories 127, memory_sources 93, document_chunks 9.
  - A schema-only dump was also taken.

### Baseline tests (before any change)
- **How:** a temporary git worktree at `HEAD`, running `run_tests.py --db rag_ingestion_test`.
- **Tests:** `test_retrieval_phase2`, `test_p2_03_metadata_filters`, `test_p2_05_zero_top_k`, `test_context_and_citations`, `test_p2_02_sentence_chunking`, `test_answer_phase3`.
- **Result:** **6/6 PASS**, `rag_db` fingerprint unchanged.
- **Procedural note:** the baseline was recorded right after the first source edits. Running it on an untouched `HEAD` worktree makes it equivalent to a pre-change baseline.

## B. Architecture audit

### Call sequence (the only retrieval path; shared by the CLI and the API)
1. `main.run_turn` calls `rag_service.ask_question`.
   - `classify_question` runs (LLM). A `MEMORY` result skips retrieval.
   - `rewrite_query` runs (LLM; falls back to the original query).
2. `hybrid_search(search_query, top_k=FINAL_TOP_K)` calls `hybrid_search_detailed`.
   - `search_service.semantic_search(query, VECTOR_TOP_K=10)`:
     - `embedding_service.generate_embeddings([query])` (same lazily loaded `EMBEDDING_MODEL` as ingestion);
     - pgvector `ORDER BY embedding <=> q LIMIT k` (cosine distance);
     - optional `SIMILARITY_THRESHOLD` floor (unset by default).
   - `keyword_search(query, BM25_TOP_K=10)`. With the default `BM25_BACKEND=memory` this is `bm25_service.bm25_search`:
     - `LuceneBM25` over a cached in-memory index;
     - each scope's cache entry is validated per query by the fingerprint `count, max(id), sum(hashtext(content))`;
     - only scores > 0 are returned.
   - With `BM25_BACKEND=fts`, `fts_service.fts_search` runs instead (PostgreSQL `ts_rank_cd`).
   - `rrf_service.reciprocal_rank_fusion([keyword, vector], RRF_K=60, top_k=RRF_TOP_K=10)`:
     - score = Σ 1/(k+rank);
     - merged by chunk id, de-duplicated by normalised content;
     - ties broken by first-seen order.
   - If `RERANK_ENABLED` (default true): `reranker_service.rerank_results(q, fused[:RERANK_TOP_K=10], top_k=FINAL_TOP_K)`. This is a lazily loaded `CrossEncoder(RERANK_MODEL)`, and results are sorted by score.
   - Otherwise: `fused[:FINAL_TOP_K]`.
3. Back in `rag_service`, the relevance gate applies **only if `rerank_score` is present**:
   - `RERANK_MIN_SCORE` floor (unset by default);
   - margin rule: keep scores ≥ best − `RERANK_SCORE_MARGIN` (2.0).
4. `context_assembly_service.assemble_context` (`CONTEXT_MAX_CHUNKS=8`, `CONTEXT_MAX_CHARS=12000`):
   - drops empty chunks, duplicate ids and duplicate content;
   - applies the chunk cap and the character budget in rank order;
   - assigns `[S#]` references.
5. `answer_service` (Stage 6, untouched).

### Confirmed defects

| # | Defect | Evidence |
|---|---|---|
| D1 | **No reranker failure isolation.** A `CrossEncoder` load error (for example offline with no cache) or a `predict` error propagated through `hybrid_search` → `ask_question` → `run_turn`. The whole turn failed although valid RRF results existed. | `rerank_results` / `hybrid_search_detailed` had no exception handling; `main.py:199` calls `ask_question` without try. |
| D2 | **Reranker output was not validated.** Fewer scores than candidates were silently dropped by `zip`; NaN scores gave an undefined sort order. | `reranker_service.py` |
| D3 | **A blank query returned arbitrary chunks.** `semantic_search("")` embedded the empty string and returned the k nearest chunks, i.e. fabricated relevance. A `None` query failed inside the model. | `search_service.py` |
| D4 | **Query-embedding dimension not validated before the database call** (pgvector would fail later with a DataException). | `search_service.py` |
| D5 | **BM25 cache key used unnormalised page values.** `[2]` and `["2"]` made two entries; a mixed `[2, "1"]` raised `TypeError` in `sorted()` although the SQL filter `int()`-normalises. | `bm25_service._get_index` |
| D6 | **RRF `weights` shorter than the lists silently dropped lists** (`zip`). | `rrf_service.py` |
| D7 | **Reranker model loaded even when `top_k=0`.** | `hybrid_search_detailed` |

### Not defects (verified)
- **RRF:** arithmetic, de-duplication, tie-breaking and metadata are all correct. `test_retrieval_phase2` and the new tests cover them.
- **BM25 fingerprint invalidation:** works after both ingestion and deletion. Preserved unchanged.
- **Context assembly:** limits are correct, and it does not mutate its input.
- **`FINAL_TOP_K` / `CONTEXT_MAX_CHUNKS`:** not a conflict; see E7.

### Coverage gaps before Stage 5
None of these had a test:
- reranker failure;
- invalid reranker output;
- hybrid failure modes;
- blank query;
- dimension check;
- mixed-type page cache key;
- the `FINAL_TOP_K` > `CONTEXT_MAX_CHUNKS` interplay;
- the no-rerank gate policy.

## C. Changes implemented

| File | Change | Why | Tests |
|---|---|---|---|
| `services/hybrid_search_service.py` | Reranker call wrapped: on any exception, keep `fused[:top_k]` (the RRF order, identical to rerank-disabled) and print a type-only line. New `rerank_status` in the detailed result: `ok` / `disabled` / `skipped` / `failed:<Type>`. Reranker skipped when `top_k==0` or there are no candidates. Blank query → empty result without calling anything; non-string query → `TypeError`. Retriever exceptions still propagate (documented). | D1, D3, D7 | `test_stage5_retrieval` [fallback]/[hybrid]/[rerank]; integration [fallback] |
| `services/reranker_service.py` | Scores converted to float and validated: count must equal the candidate count, and all must be finite; otherwise `ValueError` (handled as a reranker failure) | D2 | [rerank] predict raise / short / nan; [fallback] NaN |
| `services/search_service.py` | `TypeError` for a non-string query; `[]` for a blank query; query-vector dimension checked against `EMBEDDING_DIM` before `get_connection` | D3, D4 | integration [vector] blank / dimension mismatch |
| `services/bm25_service.py` | Cache key pages normalised with `int()` (same as `build_scope_filter`). The fingerprint logic is unchanged. | D5 | integration [bm25] int/str share entry; mixed no `TypeError` |
| `services/rrf_service.py` | `ValueError` if `len(weights) != len(result_lists)` | D6 | [rrf] weights mismatch |
| `test_stage5_retrieval.py` (new, unit) | 47 checks (fakes only) | §5 coverage | |
| `test_stage5_retrieval_integration.py` (new, integration) | 33 checks (scratch database, real models offline) | §5 coverage | |
| `run_tests.py` | Registered the two tests | Registry | |
| this report (new) | | §10 | |

## D. Test evidence

All commands were run from the project root, against database `rag_ingestion_test`. Unit and integration tests run with the network blocked and Hugging Face offline. There are no skip mechanisms; "skipped" in `run_tests` means "not selected".

### Focused unit test: 47 passed / 0 failed / 0 skipped
- **Command:** `test_stage5_retrieval.py` (direct run, same environment as `run_tests`).
- **Configuration recorded:** `FINAL_TOP_K=5 CONTEXT_MAX_CHUNKS=8 CONTEXT_MAX_CHARS=12000 RRF_TOP_K=10 RERANK_TOP_K=10`.
- **RRF (12 checks):**
  - manual example `A=[1,2,3]`, `B=[3,1,4]`, k=60 → order 1, 3, 2, 4 with exact scores (1/61+1/62, 1/63+1/61, 1/62, 1/63);
  - duplicates merged; first-list metadata kept; k applied (k=10 → 1/11+1/12);
  - ties deterministic over 3 runs; content dedupe (and its opt-out);
  - one empty list; no lists; weights mismatch; `top_k`.
- **Reranker (10 checks):**
  - lazy loading: no load on an empty list; loaded once with `RERANK_MODEL`;
  - ordering and `top_k`; chunk and rrf preserved; input not mutated;
  - load failure raises and is not cached;
  - predict raise / short / NaN → exception.
- **Hybrid (12 checks):**
  - both succeed → `[12, 10, 13, 11]` (hand-computed);
  - same query passed to both retrievers;
  - vector empty; keyword empty; both empty;
  - vector / keyword / both raising → the exception propagates;
  - blank query → no calls; non-string → `TypeError`.
- **Fallback (3 checks):**
  - reranker `OSError` → results **identical** to rerank-disabled, status `failed:OSError`;
  - printed diagnostic has the type only (the path and message are absent);
  - NaN output → same fallback.
- **Gate (3 checks):**
  - margin gate keeps [1, 2] for scores 5/4/2.5/−3 with margin 2.0;
  - `RERANK_MIN_SCORE=6` → no context;
  - unreranked results → no gate (documented gap).
- **Context (7 checks):**
  - default path gives 5 sources in rank order;
  - 12 candidates with cap 8 → first 8, the rest dropped as `max_chunks`;
  - `FINAL_TOP_K=10` > cap 8 → the 8 best kept;
  - duplicate id / duplicate content / empty excluded with reasons;
  - metadata preserved; empty → valid empty context;
  - character budget enforced; no mutation.

### Focused integration test: 33 passed / 0 failed / 0 skipped
- **Command:** `test_stage5_retrieval_integration.py`.
- **Fixtures:** three generated synthetic PDFs ingested through `ingest_pdf` with the real all-MiniLM-L6-v2 model.
- **Vector (10 checks):**
  - a paraphrase query finds the leave-policy chunk first;
  - distances ascend; `top_k`; metadata equals the stored row;
  - blank → `[]`; unknown filter → `[]`; document filter applied;
  - `SIMILARITY_THRESHOLD=0.99` → `[]`;
  - a 768-dimension query vector → `ValueError` with **no database call**;
  - `OperationalError` propagates.
- **BM25 and FTS (13 checks):**
  - `ERR-7781` → API chunk first; positive descending scores; no duplicates;
  - empty / punctuation-only / no-match → `[]`;
  - int and str page filter give equal results; mixed type works;
  - **invalidation:** a new document is found after ingestion and disappears after deletion, without clearing the cache;
  - FTS finds the identifier; FTS empty → `[]`.
- **Hybrid with the real cross-encoder (6 checks):**
  - status ok; relevant chunk first; scores descending; metadata intact;
  - **`CrossEncoder` load failure → results identical to rerank-disabled**, and still the relevant chunk;
  - no stored rows modified; no candidates → empty.
- **Context (2 checks):**
  - at most min(5, 8) sources, in retrieval order, within 12,000 characters;
  - document and page match the database.
- **Cleanup:** no `s5_*` rows left.

### Regression: `.venv\Scripts\python.exe run_tests.py --db rag_ingestion_test` (unit + integration)

| Measure | Result |
|---|---|
| Run | **45** |
| Passed | **43** |
| Failed | **2** (pre-existing; below) |
| Smoke-only passes (exit code only) | `test_similarity`, `test_memory_storage` |
| `rag_db` fingerprint unchanged | True |

All retrieval-related suites passed: `test_retrieval_phase2`, `test_p2_03_metadata_filters`, `test_p2_05_zero_top_k`, `test_context_and_citations`, `test_answer_phase3`, `test_b3_answer_reliability`, both Stage 5 tests. All Stage 4 and Batch 1 tests passed too.

### Pre-existing failures, reported separately (not Stage 5 regressions)
- `test_p1_process_memory.py`: `existing_memories` call assertion.
- `test_p1_delete_routing.py`: N2 `memory_summary` composition (2 checks) and N3 extraction source.
- Same failures as before Batch 1, verified at `bdd8d51` and `4a5e090` in Stage 4. Stage 5 touched no memory code. They were not modified.

## E. Critical issue results

1. **Vector retrieval is correct.**
   - Same configured model as ingestion: one lazily loaded `embedding_service` model, and the cache key is `(EMBEDDING_MODEL, text)`.
   - Cosine-distance order, `top_k`, filters, threshold and metadata are verified against the database.
   - Blank queries and dimension errors are now handled before the database.
   - Database errors propagate.
2. **Keyword retrieval is correct.**
   - Tokenisation is `[a-z0-9]+`, lower-cased; stopwords are kept by default.
   - Lucene IDF, only scores > 0, no duplicates.
   - Fingerprint invalidation verified after ingestion and deletion.
   - FTS backend verified.
3. **Hybrid failure behaviour:**

   | Case | Behaviour |
   |---|---|
   | Both succeed | RRF of both |
   | Vector empty | Keyword-only ranking |
   | Keyword empty | Vector-only ranking |
   | Both empty | Valid empty result |
   | One retriever fails | Exception propagates (not a silent partial result) |
   | Both fail | Exception propagates |
   | Reranker fails | Exact RRF order kept, `rerank_status="failed:<Type>"` |

   A total retrieval failure is **never** reported as an empty success. Today the exception reaches `run_turn`; turning it into a user-facing message is Stage 6 / API territory.
4. **RRF is correct.** Hand-computed example, k, duplicates, ties, missing lists, metadata, weights validation.
5. **Reranker failure isolation: FIXED.** Load errors, `predict` errors and invalid output all keep the valid RRF results unchanged, with a type-only diagnostic.
6. **No-rerank relevance gate: GAP, documented and not invented.**
   - When reranking is disabled or has failed, `rag_service` applies no score gate. Its gate keys on `rerank_score`, and RRF scores have no approved threshold.
   - The only existing knob is `SIMILARITY_THRESHOLD`, a vector cosine floor. It is unset by default, and when set it filters only vector candidates.
   - BM25 can still add chunks that share any token. Stopwords are kept by default, so a common word such as "the" matches.
   - The policy is now explicit and tested: margin and floor gates for reranked results; no score gate otherwise.
   - The downstream grounding and citation validation (Stage 6) remains the safety net.
   - **Decision needed** (see H).
7. **`FINAL_TOP_K` / `CONTEXT_MAX_CHUNKS`: not a conflict.**
   - `FINAL_TOP_K` (5) is applied in `hybrid_search_detailed` after reranking (or to the RRF list when there is no reranking).
   - `CONTEXT_MAX_CHUNKS` (8) is a hard cap in `assemble_context`.
   - The effective limit is min(5, 8) = 5. The cap only binds if `FINAL_TOP_K` is raised above 8; it then drops the lowest-ranked chunks, so ranking is never reordered.
   - The context cannot exceed either limit.
   - Truncation happens after reranking: `RRF_TOP_K` (10) and `RERANK_TOP_K` (10) bound the reranker input, then `FINAL_TOP_K` bounds the output.
   - No correction needed; behaviour is tested both ways. The earlier audit's "can never take effect" holds at the defaults; by design it is a safety cap.
8. **Context assembly limits are enforced.**
   - Chunk cap and character budget.
   - Empty, duplicate-id and duplicate-content chunks excluded with reasons.
   - Rank order kept; metadata preserved; empty input → empty context; no input mutation.

## F. Database safety

- **`rag_db` was not modified.**
  - The fingerprint taken at preflight is **identical** to the one after all tests: 261 / 1340 / 127 / 93 / 9, with the same md5 per table.
  - Every `run_tests.py` run also reported "fingerprint unchanged : True".
- **Writes to `rag_ingestion_test` only:**
  - Stage 5 integration test: inserts of three `s5_*` documents plus `s5_new_doc.pdf` via `ingest_pdf`; one `DELETE` of `s5_new_doc.pdf` (invalidation check); a final `DELETE` of `s5_*`.
  - Regression suite: each existing suite writes and cleans its own prefixed rows.
  - `test_retrieval_phase2` `TRUNCATE`s `document_chunks` and loads the synthetic `eval/corpus.py` corpus. During the baseline run it left 24 synthetic rows behind; the full suite's ordering removed them again.
- **Final state of `rag_ingestion_test`:** empty (0 chunks, conversations, messages and memories). No database was created or dropped in Stage 5.

## G. Frozen contract verification

`git diff --quiet HEAD -- <paths>` reported no changes for each of these:

| Contract | Path checked | Unchanged |
|---|---|---|
| Evaluation datasets and splits | `eval/phase35`, `data/` | Yes |
| Evaluation thresholds | `eval/framework/safety.py` `FROZEN_THRESHOLDS`, `HELDOUT_THRESHOLD_FREEZE.md` | Yes |
| BM25 fingerprint invalidation | `_fingerprint` untouched; only the cache-key normalisation changed; invalidation re-verified | Yes |
| `main.run_turn` | `main.py` | Yes |
| Stage 4 ingestion | `services/ingestion_service.py`, `pdf_parser.py`, `embedding_service.py`; Stage 4 tests pass | Yes |
| Migrations 000–003 | `migrations/` | Yes |
| Auth and API configuration | `backend/` | Yes |

The held-out evaluation was not run; no parameters were tuned; no migration or proposal was applied; `EMBEDDING_MODEL` is unchanged.

## H. Remaining risks and proposals

### Unresolved (decision needed)
1. **No-rerank relevance gate.**
   - Today, when the reranker is disabled or failed, candidates reach the context with no score gate.
   - **Options for approval:**
     - **(a)** Measure and set `SIMILARITY_THRESHOLD` on the **dev** set only, then in no-rerank mode require vector support above it for keyword-only candidates. This is a code change plus a calibrated value.
     - **(b)** Enable `BM25_DROP_STOPWORDS` to stop stopword-only BM25 matches. This changes keyword results, so measure on dev first.
     - **(c)** Fail closed: when the reranker fails and no threshold is configured, return no document context.
   - **Recommendation:** (a) with (b) measured together on dev. Not implemented, because no approved threshold exists.
2. **Retriever failure handling in the turn.** A database or embedding failure raises through `run_turn`; the API turns it into a 500 `internal_error`. Whether to degrade to the surviving retriever, or show a user message, is a Stage 6 / product decision. The current behaviour is safe (never silently empty).

### Limitations (non-blocking)
- **Full-scan cost:** the BM25 fingerprint scans the scope on every query; vector and FTS are sequential scans (no ANN/GIN indexes). Fine at the current size; indexes only with measurements and approval.
- **FTS backend:** uses English stemming and ignores `BM25_DROP_STOPWORDS`. It is not the default.
- **No backfill after content dedupe:** if context assembly drops a duplicate, nothing from deeper candidates replaces it (RRF already removes content duplicates, so this is rare).
- **Reranker load retries:** a failed load is retried on every query. That costs time while the model is missing, but the results are correct.
- **Test hygiene:** `test_retrieval_phase2` leaves the synthetic corpus in the scratch table when run alone (pre-existing).

### Proposals pending from earlier stages
007 (embedding model identity), 004–006. None was applied.

## I. Final status

**PASS WITH KNOWN ISSUES.**

### What passed
- Vector, keyword, hybrid, RRF and reranker failure isolation are validated with real models and controlled fixtures.
- Context limits and `FINAL_TOP_K`/`CONTEXT_MAX_CHUNKS` are understood and tested.
- Focused tests pass (47 + 33). Regression is 43/45, with the 2 pre-existing memory failures reported separately.
- `rag_db` unchanged; frozen contracts unchanged.

### Known issue
The no-rerank relevance gate has an **explicit, tested policy** (no score gate without an approved threshold) but no threshold. It needs the decision in H.1; it was not invented here.

### Stage 6 readiness
**Ready**, on the condition that H.1 is decided before relying on no-rerank mode in production. With the default (reranking enabled and the model cached), the gate is active, and a reranker failure now degrades to the RRF order instead of failing the turn. Stage 6 was not started.

---

## H.1 — Development-Only Relevance Gate Evaluation

**Date:** 2026-11-16 (follow-up, after Stage 5 was committed as `09e6007`). **Scope:** measurement only.
The original Stage 5 sections above are unchanged.
**Not done:**
- No application code, default, threshold, dataset, split or schema changed. `SIMILARITY_THRESHOLD` stays unset and `BM25_DROP_STOPWORDS` stays `False`.
- No held-out case was retrieved or scored, no LLM was called, and nothing was committed or pushed.

### H.1.1 Environment and database target

| Item | Value |
|---|---|
| Machine | macOS (Apple silicon). This is the first run on this machine; earlier sections ran on Windows 11 |
| HEAD | `09e6007`, `main` = `origin/main`. Untracked before this work: `.vscode/` only |
| Python | 3.14.5 (`.venv`); the Windows runs used 3.14.10 |
| PostgreSQL | 18.7 (Homebrew), pgvector 0.8.7 |
| Evaluation database | `rag_phase35_eval`, the existing Tier 2 scratch name, created new and empty by `eval/harness.use_scratch_database`. The script asserts `current_database() = 'rag_phase35_eval'` and `harness.assert_scratch()` before any work |
| `rag_db` on this machine | A **fresh, empty** schema (migrations 000–003) created on 2026-11-16. It is **not** the Windows application database. Its read-only fingerprint (`run_tests.fingerprint`) was identical before and after (all 5 tables: 0 rows) |

**Database writes:** only `rag_phase35_eval`, which got 12 synthetic PDFs from the evaluation corpus and 135 chunks through the real `ingest_pdf`, using `run_eval.build_scratch_corpus` (unchanged). No other database was written.

### H.1.2 Dataset and method

- **Dataset:** `eval/phase35` data A–D (160 cases, 12 documents, 56 pages). `build_manifest` reports it valid, and the split rule matches the runner.
  - Dataset hash: `dataset_sha256 5c58796a…a7d6a1`.
  - Split hash: `split_sha256 a185fa1c…44244`.
- **Cases used:** the **dev** split, Tier 2 cases (`tier == "both"`): **42 cases**. 38 have gold pages; 4 are `no_answer` (`A-noanswer-03`, `B-none-01`, `D-no_answer-01`, `D-no_answer-03`).
  - Held-out cases are loaded only for dataset validation (`run_eval.load_all`) and are never retrieved.
- **Queries:** the raw case question. The production path first rewrites the query with Gemini, and earlier Tier 2 results do not store the rewritten text. This affects the 2 `follow_up` cases.
- **Path under test:** the **no-rerank** path. This is where the H.1 gap is: `rag_service`'s margin/min-score gate needs a `rerank_score`.
  - Simulation: RRF over `[keyword, vector]`, then the first `FINAL_TOP_K`, then `assemble_context`.
  - Check: at T = none, the simulated top-5 equals `hybrid_search_detailed(rerank=False)` chunk-for-chunk in **42/42 cases under both stopword settings** (0 mismatches).
- **Settings:** the defaults, unchanged:
  - `VECTOR_TOP_K = BM25_TOP_K = 10`, `RRF_K = 60`, `RRF_TOP_K = 10`, `FINAL_TOP_K = 5`, `CONTEXT_MAX_CHUNKS = 8`.
  - `BM25_BACKEND = memory`, `EMBEDDING_MODEL = all-MiniLM-L6-v2`.
  - Every option is passed as an explicit argument; no environment variable was changed.
- **Configurations:**
  - **E (existing):** no threshold, stopwords kept.
  - **(a):** cosine floor T. The vector list is filtered at T, which is the existing `SIMILARITY_THRESHOLD` semantics, and *every* fused candidate, keyword-only ones included, needs cosine similarity ≥ T ("vector support"). Two variants:
    - **with refill:** gate the RRF pool of 10, then keep 5.
    - **without refill:** keep 5, then gate. This is how the existing margin gate works.
  - **(b):** `drop_stopwords=True`, the existing BM25 path.
  - **(a)+(b):** both together.
- **Calibration for (a):**
  - Grid: T = 0.00, 0.05, …, 0.70.
  - Rule, **fixed before looking at the results:** take the largest T at which no answerable case loses all of its gold pages and no case's page recall falls below its T = none value.
  - Stability: recomputed with each answerable case left out in turn (leave-one-out).

### H.1.3 Metrics

The existing metrics come from `eval/framework/retrieval_metrics.case_metrics`. The unit is the (document, page) pair: a chunk counts as relevant when its page is a gold page. Those metrics are page recall, precision@5 (a fixed K, so missing slots count as misses), MRR and nDCG@5, averaged over the 38 answerable cases.

The framework has no "relevant / irrelevant retrieval rate", so these are defined here:
- **Relevant retrieval rate:** the share of the 38 answerable cases whose final context contains at least one gold-page chunk.
- **Irrelevant retrieval rate:** non-gold chunks divided by all chunks returned, over all 42 cases. A chunk returned for a no-answer case always counts as irrelevant.
- **No-answer leakage:** the number of no-answer cases that still get any context, and how many chunks they get.
- **Keyword-only candidate:** a chunk in the final context that is not in the vector top-10. "Removed" and "relevant lost" are counted against the T = none context of the same stopword setting.

### H.1.4 Command

```
.venv/bin/python -m eval.h1_relevance_gate --output eval/results/h1_relevance_gate_dev.json             # run 1: ingest + measure
.venv/bin/python -m eval.h1_relevance_gate --output eval/results/h1_relevance_gate_dev.json --no-ingest # run 2: adds the no-refill variant
```

- The script is `eval/h1_relevance_gate.py` (new, untracked).
- Raw results are in `eval/results/h1_relevance_gate_dev.json` (new, untracked; the file is opened in mode `x`, so it is never overwritten).
- Run 1's output was kept outside the repository. Its with-refill summaries and per-case contexts are **identical** to run 2, so the retrieval is deterministic.

### H.1.5 Results

**Reference: the default reranked path** (cross-encoder plus `rag_service`'s margin gate, `rerank_status = ok` in 42/42 cases):
- Relevant rate **0.921**, irrelevant rate **0.359** (28 of 78 chunks).
- Page recall 0.842, MRR 0.833, nDCG@5 0.800.
- No-answer leakage: 4 of 4 cases, 5 chunks. Median latency 58.0 ms.

**Table 1: no-rerank, gate *without* refill** (matches the existing gate style):

| Configuration | Rel. rate | Irrel. rate (chunks) | Page recall | P@5 | MRR | nDCG@5 | No-answer leakage | KW-only returned / removed / relevant lost | Contexts changed vs E |
|---|---|---|---|---|---|---|---|---|---|
| **E** existing | 0.947 | 0.652 (137/210) | 0.934 | 0.253 | 0.882 | 0.892 | 4/4 cases, 20 chunks | 23 / – / – | – |
| (a) T=0.10 | 0.947 | 0.647 (132/204) | 0.934 | 0.253 | 0.868 | 0.882 | 4/4, 19 | 17 / 6 / 1 | 5 |
| **(a) T=0.15** (calibrated) | 0.947 | 0.636 (126/198) | 0.934 | 0.253 | 0.868 | 0.882 | 4/4, 18 | 11 / 12 / 1 | 10 |
| (a) T=0.20 | **0.921** | 0.628 (120/191) | 0.908 | 0.247 | 0.855 | 0.866 | 4/4, 18 | 4 / 19 / 2 | 13 |
| (a) T=0.30 | 0.895 | 0.609 (109/179) | 0.868 | 0.237 | 0.842 | 0.839 | 4/4, 16 | 3 / 20 / 2 | 18 |
| (a) T=0.40 | 0.842 | 0.544 (74/136) | 0.776 | 0.205 | 0.803 | 0.766 | 4/4, 13 | 0 / 23 / 2 | 34 |
| (a) T=0.50 | 0.658 | 0.471 (33/70) | 0.579 | 0.142 | 0.632 | 0.577 | 3/4, 6 | 0 / 23 / 2 | 41 |
| **(b)** stopwords | 0.947 | 0.648 (136/210) | 0.934 | 0.253 | 0.890 | 0.894 | 4/4, 20 | 18 / – / – | 29 (25 with a different chunk set) |
| **(a)+(b)** T=0.15 | 0.947 | 0.633 (126/199) | 0.934 | 0.253 | 0.890 | 0.894 | 4/4, 18 | 7 / 11 / 1 | 9 vs (b) |

At T ≥ 0.55, at least 17 answerable cases get no context at all, and at T = 0.70 relevant retrieval falls to 0.105. Every T value is in the JSON.

**Table 2: no-rerank, gate *with* refill** (gate the pool of 10, then keep 5):

| Configuration | Rel. rate | Irrel. rate (chunks) | Page recall | MRR | nDCG@5 | No-answer leakage | KW-only removed / relevant lost |
|---|---|---|---|---|---|---|---|
| E | 0.947 | 0.652 (137/210) | 0.934 | 0.882 | 0.892 | 4/4, 20 | – |
| (a) T=0.15 | 0.947 | 0.652 (137/210) | 0.934 | 0.868 | 0.882 | 4/4, 20 | 12 / 1 |
| (a)+(b) T=0.15 | 0.947 | 0.652 (137/210) | 0.934 | 0.890 | 0.894 | 4/4, 20 | 11 / 1 |

With refill, every removed keyword-only chunk is replaced by another non-gold chunk from deeper in the pool. The irrelevant rate does not move at the calibrated T, so the refill variant gives no benefit and is not considered further.

**Calibration evidence for (a)**, identical for both stopword settings:
- **Calibrated T = 0.15.** Leave-one-out gives T between 0.15 and 0.20: dropping **one** case, `B-follow-03`, raises T to 0.20.
  - `B-follow-03` is a follow-up question evaluated **without** the production query rewrite. The calibrated value is therefore set by a case whose query is not what production would search with.
- **Cases that lose relevance as T rises:**

  | T | Cases losing relevance |
  |---|---|
  | 0.20 | `B-follow-03` |
  | 0.25 | + `D-direct-05` |
  | 0.30 | + `D-multi_page-04` |
  | 0.40 | 7–8 cases |
  | 0.50 | 16 cases |

- **Cosine similarity of every candidate** in the vector and keyword top-10 lists, with stopwords kept:

  | Candidates | n | min | p10 | median | p90 | max |
  |---|---|---|---|---|---|---|
  | On a gold page | 97 | 0.094 | 0.311 | 0.482 | 0.627 | 0.796 |
  | Other | 541 | −0.093 | 0.096 | 0.311 | 0.482 | 0.639 |

  The two groups overlap heavily: the 10th percentile of gold candidates equals the median of the others, and the best non-gold candidate (0.639) scores above 90% of gold candidates. No single cosine value separates relevant from irrelevant chunks on this corpus.

**Effect of stopword removal (b):**
- The keyword top-10 changed order in **42/42** cases and changed membership in **38/42**.
- The final context changed in 29/42 cases (25 with a different chunk set).
- The first gold rank improved in 1 case and got worse in 1.
- The relevance metrics barely move:

  | Metric | Before | After | Change |
  |---|---|---|---|
  | Irrelevant chunks | 137 | 136 | −1 |
  | MRR | 0.882 | 0.890 | +0.008 |
  | nDCG@5 | 0.892 | 0.894 | +0.002 |
  | Keyword-only chunks in context | 23 | 18 | −5 |

- No-answer leakage did not change. The FTS backend ignores this setting (see H, Limitations).

**Latency** (medians per query, run 2, warm caches):

| Measurement | Median |
|---|---|
| BM25 search, stopwords kept | 6.1 ms |
| BM25 search, stopwords removed | 6.0 ms |
| Full no-rerank retrieval (either setting) | 13.1 ms |
| Similarity lookup for the gate (an extra query, ~10–20 candidate ids) | 6.4 ms |

- Run-to-run variation was about 1 ms (run 1: 5.4, 5.5, 11.8 and 5.8 ms in the same order).
- Neither option has a meaningful latency cost. The gate's lookup could be folded into the vector query if it were ever implemented.

### H.1.6 Trade-offs

- **(a) at the only threshold that loses nothing on dev (0.15, without refill):**
  - Removes 11 of 137 irrelevant chunks (irrelevant rate 0.652 → 0.636).
  - Stops **0 of 4** no-answer cases from receiving context (20 → 18 chunks).
  - Still drops one relevant keyword-only chunk: MRR −0.014, nDCG@5 −0.010, one case's first gold rank gets worse.
  - Each higher grid value loses whole answerable cases before it removes much irrelevant content.
  - Keeping no-answer cases out would need T ≥ 0.5–0.65, which cuts relevant retrieval to 0.66–0.16.
  - The calibrated value rests on 38 answerable cases, its binding case is an unrewritten follow-up, and the similarity distributions overlap. **The dev set cannot support a reliable threshold.**
- **(b):** neutral on every relevance metric (changes of 1 chunk or less, or 0.01 or less) but reorders most contexts. There is no measured benefit to justify the churn, and it would also change the default reranked path's candidate pool, which was not part of this measurement.
- **(a)+(b):** the same small irrelevant-chunk reduction as (a), and (b) happens to avoid (a)'s MRR loss on this set. That is a single-case difference and not a basis for a default.
- **The real gap:**
  - Even the best variant leaves the no-rerank path at an irrelevant rate of about 0.63, against **0.359** with the reranker plus margin gate.
  - What actually filters irrelevant content in this pipeline is the cross-encoder plus margin gate, not a cosine or stopword tweak.
  - No configuration tested here, including the reranked path, stops the 4 no-answer cases from receiving some context. Abstaining on those is left to the answer layer, as in the Stage B dev run.
- **Limits of this measurement:**
  - Relevance is judged at page level: a chunk on a gold page counts as relevant even if it lacks the fact.
  - Raw questions were used (no query rewrite).
  - The corpus is small (135 chunks).
  - Setting `SIMILARITY_THRESHOLD` would also filter the vector list in the *reranked* path; that was not measured, because neither option is recommended.

### H.1.7 Recommendation

**Adopt neither.**
- **(a): insufficient evidence for calibration.** The only safe dev value (0.15) brings a negligible benefit and depends on one unrepresentative case. No threshold is proposed, and `SIMILARITY_THRESHOLD` remains unset.
- **(b): no measurable benefit.** It is neutral on relevance and causes large ranking churn.

H.1 stays **open** as a policy decision rather than a tuning task. These options need separate approval and are not implemented:
1. **(c) Fail closed:** when the reranker is disabled or fails, return no document context (or a user-visible "degraded retrieval" status) instead of ungated RRF results.
2. **Keep the reranker as a hard dependency** of document answers, and add a startup check that the model is cached locally.
3. Repeat (a) only on a larger dev set, with the rewritten queries stored, so any threshold rests on more than ~40 cases.

No production default was changed.

**Stage 5 status:** unchanged, **PASS WITH KNOWN ISSUES**. The known issue (no-rerank relevance gate) is now measured, not just described.
