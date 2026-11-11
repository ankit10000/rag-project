# P2-03 report — metadata filtering verification

Date: 2026-11-12. Scope: P2-03 only (P2-04 not started). **Test-only change: no application code was modified.** Nothing committed. No Gemini, no network (blocked for every run). `rag_db` untouched. "Executed" = run in this session; "static" = code inspection.

## Existing filter architecture (static inspection, confirmed by the executed tests)
- One shared helper, `search_service.build_scope_filter(document_names, pages)`, returns `(sql_fragment, params)`:
  `document_name = ANY(%s)` and/or `page_number = ANY(%s)`, joined with `AND`. Values are passed as **query parameters** (lists), never interpolated. Falsy filters (`None`, `[]`, `()`) add no clause; pages are cast with `int(p)`.
- Every retriever calls it: `semantic_search` (pgvector `WHERE`), `bm25_search` (`_get_index` loads only the filtered rows and builds a per-filter in-memory BM25 index; cache key includes the filters plus a filter-scoped corpus fingerprint), `fts_search` (`AND {scope}` after the `@@` match).
- `hybrid_search_detailed(query, top_k, document_names=, pages=, use_vector, use_keyword, fusion, rerank, keyword_backend, …)` passes the filters to the vector and keyword retrievers (keyword backend `memory` = BM25 or `fts`). `reciprocal_rank_fusion` and `_interleave` only re-order/de-duplicate the lists they receive, and `rerank_results` only re-scores the fused candidates: **there is no filter step after retrieval, so the filter is enforced entirely at retrieval time and the later stages cannot add chunks** (verified, not assumed — see below).
- Supported per mode: vector ✔ / BM25 ✔ / FTS ✔ / RRF (inherits from inputs) / interleave (inherits) / reranker (inherits) / `hybrid_search` wrapper ✔ (forwards both filters). Page convention: `page_number` is 1-based, as stored by ingestion.

## Test design — `test_p2_03_metadata_filters.py` (integration, registered in `run_tests.py`)
- **Corpus** (real rows inserted into the scratch `document_chunks` table, unique run prefix `p2_03_<hex>_`): `alpha.pdf` (pages 1–3, 2 chunks each), `beta.pdf` (pages 1–2, 2 chunks each), `alpha.pdf.old` (name that starts with `alpha.pdf`), `ALPHA.pdf` (case variant), and a document whose name contains quotes and SQL text (`o'brien; DROP TABLE document_chunks; --.pdf`). Every chunk shares the same text (`quarterly retention policy review`) so **only the filter** separates documents/pages; each chunk also has a unique token that identifies exactly which chunk was returned.
- **Embeddings:** deterministic substitutes (a unit basis vector plus a tiny per-chunk offset; the query maps to the same basis vector via a patched `search_service.generate_embeddings`). The cross-encoder in the "after reranking" checks is the **real local model** (HF offline); a spy records exactly what the reranker receives and returns.
- **Retriever matrix** (each run through the same 20+ checks): vector, BM25, FTS, hybrid vector+BM25 (RRF), hybrid vector+FTS (RRF), hybrid vector-only, hybrid BM25-only, hybrid interleave fusion, hybrid + real reranker.
- Isolation: `testsafe` guard, scratch DB only, only `p2_03_*` rows are deleted (in a `finally`); the check also confirms `document_chunks` still exists after the injection-style values.

## Results (executed)
`test_p2_03_metadata_filters.py`: **190 PASS, 0 FAIL**, no application defect found. Behaviour confirmed per mode (all nine modes, identical results):
| Check | Result |
|---|---|
| document filter | only the requested document, all 6 of its chunks |
| page filter | only that page; every test page-2 chunk present |
| document + page | exactly the intersection (2 chunks) |
| several documents / several pages / cross-product | exactly the cross-product (e.g. 2 docs × pages [1,2] = 8 chunks) |
| no filter | all five test documents eligible |
| nonexistent document / nonexistent page / page 0 / negative page | no results (`[]`) |
| exact matching | `alpha.pdf` does not return `alpha.pdf.old`, `ALPHA.pdf`, or prefix/wildcard/uppercase names (`…alph%`, `…%`) |
| empty filters (`[]`, `()`, `None`) | treated as "no filter" (existing contract); `[""]` is a real filter and matches nothing |
| injection-style values | `x' OR '1'='1`, `'; DROP TABLE …` match nothing; the quoted/SQL-looking real name is found by exact name only; table intact |
| SQL parameterisation (static contract on the helper) | fragment is exactly `document_name = ANY(%s) AND page_number = ANY(%s)`; values only in params |
| RRF | fusing two filtered lists returns only chunks from the filtered inputs (4 of 4 expected, nothing new) |
| hybrid counts | filtered vector/keyword/fused counts equal the filtered population |
| reranking (real cross-encoder) | the reranker **input** contains only filter-satisfying chunks; its output is a subset of its input; a single low-ranked document filter returns only that document |
| `hybrid_search` wrapper | filters forwarded |
| BM25 cache | filtered → unfiltered → filtered gives identical results; inserting a row outside the filter does not change filtered results; the insertion is visible to its own filter |
| FTS vs BM25 | identical filtered populations |
Pinned current behaviour (undefined API, reported not invented): numeric-string page `"2"` and float `2.0` are accepted (int cast); non-numeric page `"abc"` raises `ValueError`; `pages=[True]` would act as page 1 (int cast, not tested); a **bare string** passed as `document_names` is iterated per character and matches nothing (no error).

## Mutation results (executed; repo files not edited, modules loaded from modified source)
| Mutation | Result |
|---|---|
| document filter removed | caught: 130 FAIL |
| page filter removed | caught: 83 FAIL |
| page comparison off by one | caught: 65 FAIL |
| FTS ignores the filter | caught: 38 FAIL |
| BM25 ignores the filter | caught: 100 FAIL |
| vector search ignores the filter | caught: 111 FAIL |
| filter lost before fusion (keyword retriever called unfiltered inside hybrid) | caught: 91 FAIL |
| reranker reintroduces an excluded chunk | caught: 19 FAIL |
| substring/prefix (`LIKE name%`) instead of exact match | caught: 80 FAIL |
| filter interpolated into the SQL text instead of parameterised | caught: 4 FAIL (+ the run aborted on the quote in the name) |
| BM25 cache key ignores the filter | **not caught — equivalent mutant**: the cache entry is also guarded by a filter-scoped corpus fingerprint (`count`, `max(id)`, `sum(hashtext)` computed with the same `WHERE`), so a wrongly shared key is still invalidated; the cache-isolation checks still pass |
"Filter applied before retrieval but lost during fusion" is only testable through the hybrid pipeline, which is what the `filter lost before fusion` mutation does; `reciprocal_rank_fusion` itself has no filter parameter to lose.

## Regression (executed)
- `test_retrieval_phase2.py` PASS, `test_p2_01_pdf_ingestion.py` PASS, `test_p2_02_sentence_chunking.py` PASS, `test_p2_03_metadata_filters.py` PASS (42 s with the real reranker).
- Full default suite (`run_tests.py --clean`): **26 / 26 passed, 0 failed**; application database `rag_db` fingerprint unchanged: **True**.

## Files changed
New: `test_p2_03_metadata_filters.py`, `docs/remediation/P2_03_METADATA_FILTERS_REPORT.md`. Edited: `run_tests.py` (registered the test under `integration`). No application, schema, migration, index or retrieval-default changes.

## Limitations / uncovered
- Filter-value type handling is loose by design of the current API: a bare string for `document_names` silently matches nothing; `pages=[True]`/float values are coerced. Not changed (no new contract invented); worth a decision if the API is ever exposed to untrusted callers.
- Documents are identified only by file name; two uploads with the same name are indistinguishable (ingestion upserts them together).
- Vector scores use deterministic basis vectors; the real embedding model was not used for retrieval ranking in this test (ranking quality is covered by `test_retrieval_phase2.py`).
- `rag_service` / the CLI do not currently expose filters to a user; only the library functions were exercised.
