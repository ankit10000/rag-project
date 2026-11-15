# Batch 2, Stage 4: PDF Ingestion Verification and Remediation

**Date:** 2026-11-15.
**Baseline:** `main` at `90568c2`, worktree clean.
**Status:** nothing committed or pushed; Stage 5 not started.

## A. Executive summary

**Already in place and confirmed by source and tests:**
- `services/ingestion_service.ingest_pdf` is the single application entry point. The API upload is its only production caller; the Phase 3.5 evaluation (`eval/phase35/run_eval.py`) also calls it.
- It applies, in order: extension check (A4), file-size limit (A3), page-count limit (A3), PyMuPDF extraction, word or sentence chunking, in-document dedupe, embedding with dimension and count guards, and **one transaction** that upserts and deletes stale chunks (A2).
- The API adds a filename sanitiser, path-traversal and symlink guards, a streaming size limit (413), an empty-file check (422), 409 unless `replace=true`, and restore of the previous file on failure.

**Gaps found and fixed:**
1. **Corrupt input caused HTTP 500 (confirmed).**
   - Zero-byte files, non-PDFs renamed to `.pdf`, random bytes and a `%PDF` header followed by garbage all raised PyMuPDF `FileDataError`/`EmptyFileError`, which are `RuntimeError`s. The API therefore returned 500.
   - Password-protected PDFs returned 422 with a misleading message ("no usable text or invalid embeddings").
   - **Now:** all of these raise `InvalidPDFError` (a `ValueError`), and the API returns **422 `invalid_pdf`**.
2. **Windows file lock after a corrupt upload (found by the new API test).**
   - Chaining the PyMuPDF exception kept the half-opened document, and therefore the file handle, alive. The router's cleanup `os.remove` failed with `WinError 32`, and the request crashed.
   - **Now:** the original error **type** is kept in `cause_type`, and the exception object is released before the new error is raised. A regression test checks that the file can be deleted afterwards.
3. **File swap outside error handling.** `os.replace` of the previous file and the temp file ran outside a `try`. A locked file (Windows) left a temp file behind and a raw 500. **Now:** the swap is undone, the temp file is removed, and the API returns 500 `storage_error` "nothing was changed".
4. **Duplicate ingestion logic in the evaluation harness (confirmed).**
   - `eval/harness.load_corpus` had its own dedupe and its own `INSERT`.
   - **Now:** it uses the same `build_chunks` / `validate_embeddings` / `write_document_chunks` functions as `ingest_pdf`.
   - Its benchmark-specific differences are now explicit parameters.
   - Output was proven byte-identical to the old implementation across 6 configurations.
5. **Safe diagnostics.** Upload rejections and failures are logged with exception **type** names only. Responses contain no path, trace or document text.

**Not changed:**
- Chunking contracts, the embedding model and dimension, the database schema and transaction semantics.
- The 10-word minimum page rule, and document identity (basename).
- Datasets, splits and thresholds; `main.run_turn`; anything Batch 1 introduced.

**Overall result:** **PASS** for Stage 4. Two memory tests that fail are pre-existing; see E and F.

## B. Architecture (source)

### API upload path
`backend/routers/documents.upload_and_ingest` (`POST /api/v1/documents`), in order:
1. `safe_pdf_filename` and the traversal and symlink guards.
2. `ingestion_lock`; existing name → 409 unless `replace=true`.
3. Stream to `.upload-<uuid>.part` (413 over `MAX_PDF_SIZE_MB`; 422 if empty).
4. Swap: previous file → `.previous-<uuid>.pdf.bak`, temp → final.
5. `ingest_pdf(final_path)`. On any failure, `_restore_previous` puts the old file back; the database state is unchanged because the transaction rolled back.
6. Error mapping:

| Error | Response |
|---|---|
| `InvalidPDFError` | 422 `invalid_pdf` |
| limit or type error | 422 `ingestion_rejected` |
| other `ValueError` | 422 `ingestion_failed` |
| other exception | 500 `ingestion_error` |

### `ingest_pdf` (`services/ingestion_service.py`)
1. `document_name` = basename of the path.
2. `.pdf` check → `UnsupportedFileTypeError`.
3. `os.path.getsize` limit → `PDFLimitExceeded`.
4. **Parsing:** `pdf_parser.extract_text`.
   - Opens with `pymupdf.open(path, filetype="pdf")`; open failures → `InvalidPDFError`.
   - `needs_pass` → `InvalidPDFError`.
   - `is_repaired` → a warning only.
   - Page count over `MAX_PDF_PAGES` → `PDFLimitExceeded`.
   - Text per page uses `get_text(sort=True)`. Blank pages are omitted, and 1-based page numbers are kept.
5. **Chunking:** `build_chunks`.
   - Pages under `MIN_PAGE_WORDS=10` are skipped.
   - `chunker.chunk_page(text, CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_STRATEGY)`.
   - `chunk_id` restarts at 1 on every page.
   - SHA-1 dedupe of whitespace-normalised, lower-cased text within the document.
6. No chunks → `ValueError("No usable chunks found in PDF")`.
7. **Embedding:** `embedding_service.generate_embeddings(texts)`. The model is lazy-loaded once, and vectors are normalised.
8. `validate_embeddings`: the dimension must equal `EMBEDDING_DIM` and the count must equal the chunk count.
9. **Persistence:** `with get_connection()`, which commits on exit and rolls back on any exception.
   - `write_document_chunks` runs `INSERT … ON CONFLICT (document_name, page_number, chunk_id) DO UPDATE` per chunk.
   - It then runs `DELETE` on this document's chunks that are absent from the new version.

**Effective configuration (actual, from `retrieval_config` with the current environment):**

| Setting | Value |
|---|---|
| `CHUNK_SIZE` | 100 words |
| `CHUNK_OVERLAP` | 20 words |
| `CHUNK_STRATEGY` | `words` |
| `MAX_PDF_SIZE_MB` | 50 |
| `MAX_PDF_PAGES` | 500 |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` |
| `EMBEDDING_DIM` | 384 |

### Other ingestion code
- **Evaluation harness:** `eval/harness.load_corpus` takes text corpora with pluggable `chunk_fn` and `embed_fn`, and is used by the Phase 2/2.5 benchmarks and `test_retrieval_phase2`. It now runs on the shared functions with `min_words=0`, an unpinned dimension and `TRUNCATE` first. These are the documented benchmark semantics, unchanged.
- **Duplicate document ingestion:**
  - The same name re-ingested is an in-place replacement (identical content keeps the same row ids).
  - Through the API, the same name gives 409 without `replace=true`.
  - On Windows, a name differing only in case also gives 409, because the file system is case-insensitive.

## C. Changed files

| File | Change | Reason |
|---|---|---|
| `services/pdf_parser.py` | `InvalidPDFError(ValueError)` with `cause_type`; `filetype="pdf"`; `needs_pass` check; repaired-file warning; exception not chained | 4.3, 4.12 (corrupt input → 422; no Windows file lock) |
| `services/ingestion_service.py` | Extracted `chunk_dedupe_key`, `build_chunks`, `validate_embeddings`, `write_document_chunks`; `ingest_pdf` uses them; `MIN_PAGE_WORDS` constant | 4.9 (one shared implementation). Behaviour identical (equivalence check in E). |
| `eval/harness.py` | `load_corpus` uses the shared functions; unused `hashlib` import removed | 4.9 |
| `backend/routers/documents.py` | 422 `invalid_pdf` mapping; type-only diagnostic logging; guarded file swap (500 `storage_error`, temp removed, previous file kept) | 4.3, 4.11, 4.12 |
| `test_stage4_ingestion.py` (new) | 63 service-level checks | Section 5 test suite |
| `test_stage4_ingestion_api.py` (new) | 28 API checks | 4.11 |
| `test_a3_ingestion_limits.py`, `test_a4_pdf_file_type_validation.py`, `test_p2_04_ingestion_edge_cases.py` | Expectations `FileDataError`/`EmptyFileError`/plain `ValueError` → `InvalidPDFError` (PyMuPDF type asserted via `cause_type` where pinned) | Intended contract change of 4.3; all other assertions unchanged |
| `run_tests.py` | Registered the two new tests (integration) | Test registry |
| `docs/remediation/proposals/007_document_chunks_embedding_model.sql.proposed` (new) | Proposal only, not applied | 4.10 |
| this report (new) | | 9 |

## D. Database verification

**Database:** `rag_ingestion_test`.
- Created from `template0`; it did not exist before.
- Its name is accepted by `testsafe.is_scratch_name`.
- The connection target was taken from `.env` credentials with the database name replaced; the URL was never printed.

**Migrations:** 000 → 001 → 002 → 003 applied with `ON_ERROR_STOP`. Tables: `conversation_memories`, `conversations`, `document_chunks`, `memory_sources`, `messages`.

**Test records:**
- Created only under the `s4_*`, `s4api_*`, `a2_*`, `a3_*`, `p2_04_*` prefixes (and the other suites' own prefixes); each test removes its own rows.
- The harness check truncates the scratch table by design.

**Final state:** `rag_ingestion_test` has 0 chunks, 0 conversations, 0 messages and 0 memories. The database is kept (empty) for re-runs; drop it with `DROP DATABASE rag_ingestion_test` when no longer needed.

**`rag_db`:**
- Untouched. Every `run_tests.py` run reported "application database 'rag_db' fingerprint unchanged : True" (read-only row-count + md5 per table).
- Row counts equal the Batch 1 snapshot: conv=261, msg=1340, mem=127, links=93, chunks=9.

## E. Test results

All runs used `.venv\Scripts\python.exe run_tests.py --db rag_ingestion_test …`. Unit and integration tests run with the network blocked and Hugging Face offline. The real embedding model came from the local cache; nothing was downloaded.

### Baseline before any change
9/9 PASS: `test_a1`, `test_a2`, `test_a3`, `test_a4`, `test_p2_01`, `test_p2_02`, `test_p2_04`, `test_retrieval_phase2`, `test_batch1_provider_config`.

### New: `test_stage4_ingestion.py` — 63 PASS / 0 FAIL

**Validation:**
- A valid multi-page PDF ingests.
- These five inputs each raise `InvalidPDFError`, store nothing, carry no path in the message, keep the PyMuPDF type in `cause_type`, and leave the file deletable afterwards:
  - zero-byte file
  - non-PDF renamed to `.pdf`
  - random bytes
  - `%PDF` header followed by garbage
  - PDF encrypted with a user password
- An owner-password-only PDF ingests.
- A blank PDF raises `ValueError("No usable chunks")`.
- An oversized file raises `PDFLimitExceeded`.
- Unusual metadata (2,000-character Unicode title, control characters) ingests.

**Extraction:**
- Page order 1..7 is kept and blank pages are skipped.
- Page text belongs to its own page.
- Accented Latin and CJK text survive extraction.
- A truncated PDF is repaired (partial or no text) or rejected; it never crashes. Observed result: no recoverable pages.

**Chunking (100/20/words):**
- A short page gives one chunk.
- Every chunk has at most 100 words and none is empty.
- Consecutive chunks overlap by exactly 20 words.
- No words are lost at chunk boundaries.
- `chunk_id` runs 1..n per page.
- Pages under 10 words are skipped.
- A repeated paragraph is stored once.
- Unicode text is preserved.
- Chunk ids are stable for identical input.

**Embeddings, real model:**
- The model is loaded once.
- Output shape is (n, 384), all values are finite and vectors have L2 norm 1.
- Batch and single encodings agree.
- An empty input gives no vectors.
- The model dimension equals `EMBEDDING_DIM`.

**Persistence, real model:**
- The row count equals the chunker output.
- `vector_dims` is 384.
- Pages, chunk ids and content (md5) match exactly.
- The page under 10 words produces no rows.

**Re-ingestion and failures:**
- An identical re-ingest keeps the same rows **and ids**.
- A shorter version removes stale chunks.
- In each of these failure cases the previous version stays byte-identical:
  - embedding failure;
  - failure after all writes, before commit;
  - database error on the third statement.

**Identity:**
- Same basename from another directory replaces the document (documented contract; the API guards this with 409).
- A renamed copy is stored as a separate document.
- A similar but different file is stored separately, and the original is unchanged.

**Harness:**
- `load_corpus` goes through all three shared functions.
- Benchmark semantics are kept (short pages are not skipped, dedupe applies, ids follow insertion order).
- There is no private `INSERT`.

**Cleanup:** no `s4_*` rows remain.

### New: `test_stage4_ingestion_api.py` — 28 PASS / 0 FAIL

**Successful upload:**
- A valid upload (real model) returns 201 with `indexed`, a chunk count and `replaced=false`.
- The rows are persisted, the file is stored and no temp files remain.
- `GET /documents/{name}` returns 200.

**Rejected uploads:** each case below returns its status, writes no rows, stores no file, leaves no temp files, and leaks no path, trace or text.

| Case | Response |
|---|---|
| `.txt` | 422 `unsupported_file_type` |
| empty | 422 `empty_file` |
| non-PDF renamed | 422 `invalid_pdf` |
| corrupt PDF | 422 `invalid_pdf` |
| PDF without text | 422 `ingestion_failed` |
| oversized | 413 `file_too_large` |

**Replace and duplicates:**
- The same name without `replace` returns 409 and the original is untouched.
- An embedding failure on replace returns 500 `ingestion_error` with no internal text; the previous chunks **and** the previous file are restored, and no temp or backup files remain.
- A corrupt replacement returns 422 and the previous version is kept.
- A valid replace returns 201 with `replaced=true`, and stale chunks are gone.
- A case-variant name returns 409 (case-insensitive file system).

**Auth:** an upload without a token returns 401.

### Equivalence checks (scratch database, deterministic embedder; scripts not kept in the repo)
- **`ingest_pdf`:** the `HEAD` version and the refactored version give identical rows, including content and vectors: `data/documents/sample.pdf` → 9 = 9, and a generated 5-page PDF with repeated headers → 7 = 7.
- **`harness.load_corpus`:** the `HEAD` version and the refactored version give identical rows, including ids, names, pages, chunk ids, content and vectors. Corpus: the Phase 2 corpus plus 30 distractor documents plus a duplicate-page document. Configurations: {words 100/20, sentences 100/20, words 50/10} × dedupe on/off.

| Configuration | Rows (old / new) |
|---|---|
| words 100/20, dedupe on | 206 / 206 |
| words 100/20, dedupe off | 207 / 207 |
| sentences 100/20, dedupe on | 206 / 206 |
| sentences 100/20, dedupe off | 207 / 207 |
| words 50/10, dedupe on | 348 / 348 |
| words 50/10, dedupe off | 350 / 350 |

### Updated existing tests (contract change of 4.3)
`test_a3_ingestion_limits.py`, `test_a4_pdf_file_type_validation.py` and `test_p2_04_ingestion_edge_cases.py`: 3/3 PASS after updating the expected exception type.

### Final full regression (unit + integration, 43 tests)
Command: `.venv\Scripts\python.exe run_tests.py --db rag_ingestion_test`.

| Measure | Result |
|---|---|
| Run / passed / failed | **43 / 41 / 2** |
| Ingestion, Batch 1 and new Stage 4 tests | All pass (19 unit, 22 integration) |
| Smoke-only passes (exit code only) | `test_similarity.py`, `test_memory_storage.py` |
| `rag_db` fingerprint unchanged | True |

The 2 failures are the pre-existing memory tests below.

**Pre-existing failures, not caused by Batch 1 or Stage 4:**
- `test_p1_process_memory.py` (`existing_memories` call assertion) and `test_p1_delete_routing.py` (memory_summary composition and N3 extraction-source checks).
- Both fail identically on a temporary worktree at `bdd8d51` (before Batch 1) and at `4a5e090` (before Phase 6). They are memory-pipeline tests, out of Stage 4 scope.

## F. Remaining technical debt

| Priority | Item |
|---|---|
| High (Stage 6/memory) | The two pre-existing memory test failures. The tests are probably stale against the Phase 1–3 memory changes, or there is a regression. Needs triage in the memory stage. |
| Medium | **Document identity is the file basename.** `ingest_pdf` called with a different file of the same basename (another directory) replaces the stored document. The API prevents this (409 unless `replace=true`), and no other production caller exists. A stable document id or content hash would remove the risk, but that is a schema/contract change; not done. |
| Medium | **Model identity is not stored with vectors.** See G; proposal 007. |
| Medium | **No total-chunk limit** (pinned in `test_p2_04` as a finding). All chunks are embedded in one `encode` call and inserted in one transaction; within the 50 MB / 500 page limits memory is bounded but large. No optimisation without measurements. |
| Low | Pages under 10 whitespace-separated words are skipped, so CJK pages without spaces are skipped silently. The threshold is not configurable. |
| Low | Damaged PDFs that MuPDF repairs are ingested with whatever text was recovered; there is only a console warning. |
| Low | A re-ingest that yields no chunks (`ValueError`) keeps the previous version's chunks. This is intended preservation, but it is undocumented in the API response. |
| Low | `ingestion_lock` is per process; the CLI/eval paths are not serialised with the API (single-user, single-worker design). |
| Low | Upload backups (`.previous-*.pdf.bak`) left by a crash are only reported at startup, never deleted automatically (Phase 7 design). |

## G. Embedding model identity: recommendation

1. **Current behaviour.**
   - `document_chunks` stores `embedding vector(384)` with no model identifier.
   - The model comes from `EMBEDDING_MODEL` (default `all-MiniLM-L6-v2`).
   - The query-embedding cache key is `(EMBEDDING_MODEL, text)`, in memory only.
   - `ingest_pdf` checks only the **dimension** against `EMBEDDING_DIM`.
2. **Risk.** If `EMBEDDING_MODEL` is changed to another 384-dimension model:
   - old and new vectors mix in one table;
   - queries embedded with the new model are compared with documents embedded by the old one;
   - retrieval quality silently degrades, with no error.

   A model with a different dimension is caught: at ingestion by the dimension guard, and by pgvector at query time.
3. **Are current fingerprints sufficient?** No.
   - The in-memory cache key is per process and is not persisted.
   - The BM25 fingerprint covers content only.
   - Nothing ties a stored vector to the model that produced it.
4. **Is metadata or a migration needed?** Yes, before any model change is supported.
   - Proposal `docs/remediation/proposals/007_document_chunks_embedding_model.sql.proposed`: a nullable `embedding_model text` column. **Not applied.**
   - It needs a matching code change: write `cfg.EMBEDDING_MODEL`, then refuse or warn on mismatch at startup or retrieval.
   - It needs an approved backfill decision for existing rows.
   - The same applies to `conversation_memories.embedding`.
5. **Backward compatibility.**
   - The column is nullable, so existing rows are "unknown". The code path is unaffected until the code change is made, and rollback is a `DROP COLUMN`.
   - Until then, the mitigation is operational: do not change `EMBEDDING_MODEL` without re-ingesting all documents and re-embedding memories.

**Recommendation:** review and approve 007 together with the code change in a later stage. Not required for Stage 4 correctness, so not implemented.

## H. Stage readiness

**PASS.** All Stage 4 acceptance criteria are met, with evidence above.

| Criterion | Evidence |
|---|---|
| Valid PDF processed | Service and API tests |
| Invalid/corrupt → appropriate errors (422/413/409) | Service and API tests |
| Page information preserved | Extraction checks |
| Chunking matches contracts | Chunk checks + equivalence |
| Configured model and dimension | Embedding checks |
| Correct persistence in the disposable database | Persistence checks |
| Stale chunks handled transactionally | Re-ingestion checks |
| Failed ingestion preserves valid data | 3 injected failures + API replace failure |
| Duplicate filenames do not silently mix documents | API 409; basename contract documented |
| Harness uses the shared logic | Spy test + equivalence |
| API end to end | API tests |
| Temporary resources cleaned up | Leftover checks + file-release checks |
| `rag_db` unmodified | Fingerprint checks |
| Batch 1 tests passing | Unit suite |
| New tests passing | 63 + 28 |

The two failing memory tests pre-date Batch 1 (verified) and are outside Stage 4 scope. They are recorded in F, not hidden.

## I. Next stage recommendation

Stage 5 (retrieval) can begin. Ingestion now produces verified, consistent chunks through one shared implementation. Suggested Stage 5 prerequisites:
- Reranker failure isolation.
- The `CONTEXT_MAX_CHUNKS` vs `FINAL_TOP_K` mismatch.
- The no-rerank relevance gate.

Decide on proposal 007 before any embedding-model change. Stage 5 was **not** started.
