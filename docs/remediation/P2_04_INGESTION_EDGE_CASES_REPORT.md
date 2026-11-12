# P2-04 report — ingestion edge-case verification (final, incl. P2-04-F1 fix)

Date: 2026-11-12. Scope: P2-04 only (P2-05 not started). Nothing committed. No Gemini, no network (blocked for every run), no model downloads. `rag_db` untouched (scratch DB `rag_test_scratch` only, via `testsafe`). "Executed" = run in this session; "static" = code inspection.

## Scope and change summary
- P2-04 **began as test-only verification** (new integration test, no application changes).
- It found one reproducible defect (Finding 1: embedder returning fewer vectors than chunks silently stored a partial document). **Finding 1 was subsequently fixed with explicit user approval** (task P2-04-F1). **`services/ingestion_service.py` was therefore modified** (+6 lines, one added check). Nothing else in application code, schemas, migrations, chunking or retrieval defaults changed.
- The other four findings are **not fixed** (section "Findings").

## Ingestion contract discovered
Explicit (code + earlier tests): `ingest_pdf(path)` → `extract_text` (PyMuPDF, blank pages dropped, 1-based `page_number`) → pages with < 10 whitespace words skipped → `chunk_page` (CHUNK_SIZE/OVERLAP/STRATEGY from config) → in-document dedupe (normalised, lower-cased SHA-1) → `ValueError("No usable chunks found in PDF")` if nothing left → `generate_embeddings` → `ValueError` if embedding width ≠ `EMBEDDING_DIM` → **`ValueError` if the number of vectors ≠ number of chunks (added by P2-04-F1)** → one transaction of `INSERT … ON CONFLICT (document_name, page_number, chunk_id) DO UPDATE`. `document_name` = last path component (`/` or `\`).
Incidental (works, not designed): any format PyMuPDF opens (`.txt`, epub…) is accepted; truncated-tail PDFs are repaired silently; error types are whatever PyMuPDF raises.
Undefined: file-type validation, size/page limits, OCR, passwords, languages without spaces, removal of stale chunks on re-ingest. (Embedder row-count validation was undefined before the F1 fix; it is now defined.)

## Test results: `test_p2_04_ingestion_edge_cases.py`
Registered under `integration` in `run_tests.py`.
- **Original run (before the F1 fix):** 48 PASS, 0 FAIL, 5 findings.
- **After the F1 fix (executed):** 0 FAIL, **4 findings** (Finding 1 became two assertions, both PASS). The exact PASS total after the fix was not recorded (the run output was filtered to FAIL/FINDING lines); by construction it is the original 48 plus the 2 new checks.

| Area | Cases and outcome |
|---|---|
| Malformed | `%PDF`+random bytes → `FileDataError`; zero-byte → `EmptyFileError`; text saved as `.pdf` → `FileDataError`; half-truncated PDF and PDF with 200 overwritten bytes → `ValueError("No usable chunks")`; missing file → `FileNotFoundError`; directory → `FileDataError`; password-protected → `ValueError` (encrypted). **Every case stores 0 rows.** Pinned: PDF missing its last 60 bytes is repaired and ingested. |
| Valid, no text | blank pages / whitespace-only / image-only (no OCR) → parser `[]`, `ValueError("No usable chunks")`, 0 rows |
| Short/mixed pages | 9-word page skipped, 10-word page kept (page number preserved); doc of only 9-word pages → error; mixed text/blank/whitespace/9-word pages → real page numbers 1, 4, 6 |
| Unicode | Cyrillic, accented Latin, Devanagari, spaced CJK: extracted and read back from PostgreSQL identical; Unicode file name with spaces stored unchanged; `/` and `\` directory parts stripped |
| Long text | 8 pages × 600 words → 64 chunks, identities and content exactly as chunker output; single 400-word unpunctuated sentence OK under both `words` and `sentences` strategies |
| Duplicates | same file ×3 → identical rows/ids/embeddings (idempotent); same content other filename → independent second document; changed content same name → updated in place, ids kept; more chunks → extras inserted; fewer chunks → surplus old chunks remain (pinned, Finding 4) |
| Failures | parser exception, embedder exception propagate, 0 rows; wrong dimension → `ValueError`, 0 rows; embedder returning list / 1-D array / None → `AttributeError`/`IndexError`, 0 rows; **too few vectors → `ValueError("Embedding count …")`, 0 rows (post-F1)**; **too many vectors → same `ValueError`, 0 rows (post-F1)**; NaN vector in chunk 2 (real DB write failure) → exception and whole document rolled back (0 rows); failing re-ingest leaves previously stored rows untouched |
| Limits | static: no size/page limit anywhere; modest 40-page document ingested completely (no huge file created) |
| Isolation | rows outside `p2_04_*` unchanged; cleanup leaves 0 test rows and removes temp dir |

## Findings
1. **FIXED (P2-04-F1, user-approved) — embedder returning a different number of vectors than chunks.**
   - Reproduction: 3 chunks, embedder returns 2 vectors.
   - Before: `ingest_pdf` succeeded and stored 2 rows (`zip()` truncated); too many vectors were silently ignored. Expected: clear failure, nothing stored.
   - After: `ValueError("Embedding count 2 does not match chunk count 3")`, 0 rows stored; the same for too many vectors.
   - Exact change (`services/ingestion_service.py`, after the dimension check, before the DB transaction):
     ```python
     # One vector per chunk, otherwise zip() below would silently drop chunks.
     if len(embeddings) != len(all_chunks):
         raise ValueError(
             f"Embedding count {len(embeddings)} does not match "
             f"chunk count {len(all_chunks)}"
         )
     ```
   - The real model returns one row per input, so the practical risk was low; the fix is defensive.
2. **NOT FIXED** — gap: no file-type validation (a `.txt` is ingested as page 1). Contract undefined.
3. **NOT FIXED** — limitation: unspaced CJK pages have < 10 whitespace tokens and are skipped (`No usable chunks`). Contract undefined.
4. **NOT FIXED** — known (also P2-01): stale chunks remain after re-ingesting a shorter version of the same file name.
5. **NOT FIXED** — gap: no file-size/page-count/chunk-count limit; all embeddings computed in memory and inserted in one transaction. No limit invented.

## Mutation checks (executed; repo files untouched, modified source loaded in memory)
| Mutation | Result |
|---|---|
| short-page (<10 words) skip removed | caught, 6 FAIL |
| dimension check removed | caught, 4 FAIL |
| `ON CONFLICT DO UPDATE` → `DO NOTHING` | caught, 4 FAIL |
| commit after every chunk (breaks atomicity) | caught, 3 FAIL |
| `document_name` = full path | caught, 23 FAIL |
| "no usable chunks" check removed | caught, 9 FAIL |
| page numbers 0-based | caught, 5 FAIL |
| embedder errors swallowed | caught, 2 FAIL |
| **vector-count check (F1 fix) removed** | **caught, 2 FAIL (the two new count assertions)** |
No survivors. (The first eight ran against the pre-fix test file; the last against the post-fix file.)

## Regression and DB safety (executed, after the F1 fix)
- Focused P2-04 test: 0 FAIL (see above).
- **Full default suite `run_tests.py --clean`, completed after the fix: 27 / 27 passed, 0 failed.** It includes `test_retrieval_phase2`, `test_p2_01_pdf_ingestion`, `test_p2_02_sentence_chunking`, `test_p2_03_metadata_filters` and `test_p2_04_ingestion_edge_cases`, all PASS.
- **`rag_db` fingerprint unchanged: True.** Scratch DB only via `testsafe`, network blocked, no Gemini.
- History note: a full-suite re-run started *before* the F1 fix was killed by Claude Code for low machine memory and produced no result; it is superseded by the completed post-fix run above and is not relied on. The earlier pre-fix 27/27 run is likewise superseded.

## Files
- New: `test_p2_04_ingestion_edge_cases.py`, `docs/remediation/P2_04_INGESTION_EDGE_CASES_REPORT.md`.
- Modified: `run_tests.py` (registered the test under `integration`); **`services/ingestion_service.py`** (+6 lines, the vector-count check).
- No schema, migration, chunking or retrieval-default changes.

## Not covered
Real-model embedding of Unicode text (substitute embedder used); OCR/scanned documents; huge files (deliberately not created); concurrent ingestion of the same file; Windows-only fonts (cases skip if absent); PDFs with embedded forms/attachments.
