# P2-01 report — end-to-end PDF ingestion verification

Date: 2026-11-11. Scope: P2-01 only. **Test-only change: no application code was modified.** Nothing committed. No Gemini, no network (blocked for every run). `rag_db` untouched. "Executed" = run in this session; "static" = code inspection.

## Existing ingestion architecture (static inspection, then confirmed by the executed test)
Entry point: `services.ingestion_service.ingest_pdf(pdf_path)`.
1. `document_name` = base name of the path (splits on `/` and `\`).
2. `services.pdf_parser.extract_text(path)` — PyMuPDF `page.get_text(sort=True)`; returns `[{"page_number": page.number + 1, "text": ...}]` for pages whose text is non-blank (blank pages are skipped, so page numbers are the real PDF page numbers).
3. Pages with fewer than 10 words are skipped by `ingest_pdf`.
4. `chunker.chunk_page(text, cfg.CHUNK_SIZE=100, cfg.CHUNK_OVERLAP=20, cfg.CHUNK_STRATEGY="words")` → word chunks (step 80); `chunk_id` restarts at 1 on every page.
5. In-document duplicate prevention: SHA-1 of the whitespace-normalised, lower-cased chunk text; a repeat inside the same document is skipped (first occurrence wins).
6. No chunks → `ValueError("No usable chunks found in PDF")`.
7. `embedding_service.generate_embeddings(texts)` (SentenceTransformer `all-MiniLM-L6-v2`, normalised); `embeddings.shape[1] != cfg.EMBEDDING_DIM (384)` → `ValueError` before any write.
8. Insert into `document_chunks(document_name, page_number, chunk_id, content, embedding)` with `ON CONFLICT (document_name, page_number, chunk_id) DO UPDATE SET content, embedding` (unique index confirmed in the scratch DB). Connection context commits on exit.
Substitutable boundaries: `ingestion_service.generate_embeddings` (module-level name), `cfg` values, `get_connection`.

## Test design — `test_p2_01_pdf_ingestion.py` (integration, registered in `run_tests.py`)
- **PDF fixture** generated at test time with PyMuPDF in a temp directory: 5 pages — 250 words, 120 words, **blank**, 150 words, 6 words; words are unique tokens (`p1w001…`) so extraction and chunk content can be compared word-for-word. Unique document names `p2_01_<random>.pdf`.
- **Embeddings:** the happy path uses the **REAL** `all-MiniLM-L6-v2` model from the local cache with `HF_HUB_OFFLINE=1` (loaded offline in this session, ≈41 s the first time; no download). **Deterministic substitutes** (a fixed 384-d one-hot vector, and a 3-d zero matrix) are used only for: proving DO UPDATE on conflict, in-document dedupe, shrink re-ingest, and the dimension-mismatch failure; each such check is labelled `DETERMINISTIC embedder`.
- **Expectations are computed independently** with `chunker.chunk_text` on the fixture words, not copied from ingestion output.
- **Isolation/cleanup:** guard `testsafe.require_scratch_db()`, scratch DB only; all rows match prefix `p2_01_`; cleanup in `finally` removes only those; the rest of `document_chunks` is fingerprinted (count + md5) before/after and compared; temp PDFs removed.

## Database assertions (executed, real rows)
Exactly 7 rows for the document; `(page, chunk_id)` = (1,1),(1,2),(1,3),(2,1),(2,2),(4,1),(4,2) (blank page 3 and 6-word page 5 absent); stored `content` equals the expected chunks; `vector_dims(embedding) = 384` for every row; norm = 1.0 ± 1e-3; stored vectors match a fresh real-model encoding of the stored content (cos > 0.999); vectors differ per chunk; `document_name` equals the file base name; other documents' rows unchanged.

## Duplicate ingestion (existing behaviour, preserved — executed)
- Re-ingesting the same PDF: still 7 rows, **same row ids**, same identities and content (upsert).
- Conflict path **updates** the existing rows' embedding (proved with the deterministic embedder), row count and ids unchanged.
- Identical text on two pages of one document: stored once, from page 1 only.
- **Pinned existing behaviour / limitation:** re-ingesting a *shorter* version under the same name updates chunk 1 but **leaves the old extra chunks** (stale rows are never deleted). Not changed or fixed here; reported only.

## Failure cases (executed)
| Case | Result |
|---|---|
| all pages blank | parser returns `[]`; `ingest_pdf` → `ValueError("No usable chunks found in PDF")`, no rows |
| page with < 10 words | skipped → same `ValueError`, no rows |
| multi-page PDF with a blank page | covered by the happy path (page numbers 1, 2, 4 kept) |
| embeddings of wrong dimension (3) | `ValueError` mentioning `EMBEDDING_DIM`, nothing written |
| text file named `.pdf` | `pymupdf.FileDataError` raised (propagates), no rows |
| missing file | `FileNotFoundError` raised, no rows |
Undefined by the current contract (reported, not invented): ingestion has no transaction wrapping all rows beyond the connection context (a mid-insert failure would roll back the whole connection context, not tested); parser exceptions are not wrapped in a project-specific error type; malformed/encrypted/huge-PDF security handling is out of scope.

## Results (executed)
- `test_p2_01_pdf_ingestion.py`: **30 PASS, 0 FAIL** (14 s inside the runner with network blocked; real model loaded from cache).
- `test_retrieval_phase2.py`: PASS (unchanged).
- Full default suite (`run_tests.py --clean`): **24 / 24 passed, 0 failed**; `rag_db` fingerprint unchanged: **True**.
- Mutation checks (modules loaded in memory from modified source; repo untouched), all against the new test:
  | Mutation | Result |
  |---|---|
  | no dimension check | caught: 2 FAIL |
  | `ON CONFLICT DO NOTHING` instead of `DO UPDATE` | caught: 3 FAIL |
  | page number off by one in the parser | caught: 1 FAIL (then the run aborted on the missing page) |
  | short-page skip removed | caught: 9 FAIL |
  | in-document digest dedupe removed | caught: 2 FAIL |
  | `chunk_id` zero-based | caught: 3 FAIL |
  | empty-chunks check removed | caught: 3 FAIL |

## Files changed
- New: `test_p2_01_pdf_ingestion.py`, `docs/remediation/P2_01_PDF_INGESTION_REPORT.md`.
- Edited: `run_tests.py` (registered the new test under `integration`).
- No application files, schema, migrations or retrieval settings changed.

## Limitations
- Fixture PDFs are text-only generated PDFs; scanned/image-only PDFs, tables, multi-column layouts and non-Latin text are not exercised.
- Only the default `words` chunking strategy is asserted (sentence chunking is a later task).
- The real-model check depends on the cached model being present; if the cache is missing the test fails (it never downloads).
- Stale chunks after a shrinking re-ingest remain (pinned, not fixed).
