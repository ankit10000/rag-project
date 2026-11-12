# A3 report — PDF ingestion resource limits

Date: 2026-11-12. Scope: A3 only (A4 not started). Nothing committed. No Gemini, no network/model downloads (deterministic embedder, network blocked). Scratch DB only via `testsafe`; `rag_db` never connected to by any A3 test. **Per instruction, the full default suite and the final `rag_db` fingerprint check were NOT run in A3** (deferred to after A4).

## Inspection
- `retrieval_config.py` reads every setting from the environment / `.env` through `_int` / `_float` helpers; an invalid value raises `ValueError` at import. No limits existed.
- `ingest_pdf` called `extract_text(path)` first; nothing looked at file size. `extract_text` opened the PDF with PyMuPDF and iterated every page calling `get_text`.
- Safe places: file size from file metadata (`os.path.getsize`, the file is not read) at the very start of `ingest_pdf`; page count via `document.page_count` right after `pymupdf.open`, before the page loop.

## Configuration
| Setting | Env var | Default | Type / convention |
|---|---|---|---|
| `MAX_PDF_SIZE_MB` | `MAX_PDF_SIZE_MB` | 50 | `_float` (fractions allowed); invalid → `ValueError` at import |
| `MAX_PDF_PAGES` | `MAX_PDF_PAGES` | 500 | `_int`; invalid (e.g. `abc`, `1.5`) → `ValueError` at import |
Both limits are inclusive (a file exactly at the limit is accepted). Zero values are used literally (reject everything); no special-casing was invented.

## Validation order (exact)
1. `ingest_pdf`: `os.path.getsize(path)`; if `> MAX_PDF_SIZE_MB × 1024²` → `PDFLimitExceeded("PDF file is X MB, exceeding MAX_PDF_SIZE_MB=…")`. A missing file still raises `FileNotFoundError` (now from `getsize`).
2. `extract_text`: `pymupdf.open(path)` (malformed/encrypted files fail here exactly as before).
3. `extract_text`: if `document.page_count > MAX_PDF_PAGES` → `PDFLimitExceeded("PDF has N pages, exceeding MAX_PDF_PAGES=…")`, before any `get_text`.
4. Unchanged: page text extraction → 10-word page filter → chunking → embedding → dimension and count checks → one transaction (upsert + A2 stale-chunk delete).
`PDFLimitExceeded` is a new `ValueError` subclass in `services/pdf_parser.py`, so existing `except ValueError` callers keep working. Rejections happen before the database is opened, so no rows are created, updated or deleted.

## Tests (executed): `test_a3_ingestion_limits.py` — 33 PASS, 0 FAIL (integration, registered in `run_tests.py`)
Limits are lowered via config so only small PDFs are generated.
| Area | Result |
|---|---|
| defaults 50 MB / 500 pages; env overrides (`12.5`, `30`) | PASS |
| invalid env values (`abc`, `1.5` for pages, empty string) → `ValueError` at import, same as other settings | PASS |
| size: below limit ingested; exactly at limit accepted; 1 byte over rejected (`PDFLimitExceeded`, message names `MAX_PDF_SIZE_MB`) | PASS |
| size rejection: parser and embedder never called; new document creates no rows; existing document rows unchanged | PASS |
| pages: 5 pages with limit 6 ingested; 5 of 5 accepted; 5 of 4 rejected (message names `MAX_PDF_PAGES=4` and `5 pages`) | PASS |
| page check runs before extraction (`Page.get_text` patched to fail → never called) | PASS |
| page rejection: stored document unchanged (ids, content, embeddings), nothing embedded; same-name different-content replacement over the limit leaves old rows intact; with defaults the same replacement updates normally | PASS |
| both limits exceeded → size error reported first | PASS |
| malformed: garbage PDF within limits still `FileDataError`; garbage over size limit → size error before parsing; missing file → `FileNotFoundError`; blank PDF → `No usable chunks`; encrypted → `ValueError` (not a limit error) | PASS |
| zero limits reject everything; defaults leave normal ingestion unchanged; cleanup (rows, temp dir) | PASS |

## Mutation results (executed; repo files untouched, modified source loaded in memory)
| Mutation | Result |
|---|---|
| file-size check removed | caught, 9 FAIL |
| page-count check removed | caught, 5 FAIL |
| size boundary `>` → `>=` | caught, 2 FAIL |
| page boundary `>` → `>=` | caught, 2 FAIL |
| page check moved after text extraction | caught, 3 FAIL |
| size override ignored (hardcoded 50) | caught, 8 FAIL |
| page override ignored (hardcoded 500) | caught, 5 FAIL |
| size rejection after the DB write | caught, 7 FAIL |
All caught.

## Directly affected tests (executed, focused)
`test_p2_01_pdf_ingestion.py` 0 failed; `test_p2_04_ingestion_edge_cases.py` 0 failed (3 findings); `test_a2_stale_chunk_cleanup.py` 0 failed; `test_a1_embedding_model_config.py` 0 failed; `test_p2_02_sentence_chunking.py` and `test_p2_03_metadata_filters.py` 0 failed.
Test adjustments required by the new size check (it reads file metadata, so a path must exist):
- `test_a1_embedding_model_config.py` and `test_p2_04_ingestion_edge_cases.py` (path-separator cases) call `ingest_pdf` with a fake path and a patched parser; they now also patch `os.path.getsize`. The asserted behaviour is unchanged.
- `test_p2_04_ingestion_edge_cases.py`: the static "no limit exists" check (pinned P2-04 Finding 5) now asserts the A3 limits exist; the finding was narrowed to "no total-chunk limit".
- `test_a3_ingestion_limits.py` calls `gc.collect()` before deleting its temp dir, because on Windows a failed `pymupdf.open` keeps the file handle until garbage collection.

## Known limitations
- No total-chunk / total-text limit: a PDF within 50 MB and 500 pages can still yield many chunks, all embedded in one in-memory call and one transaction.
- File size is checked with `getsize` and the page count after the open, so a file can change between the two checks (not a concern for local single-user use).
- PyMuPDF still parses the document structure on open. A malicious file within the size limit could still be expensive to open.
- No file-type/extension/MIME validation (A4).
- The full suite and `rag_db` fingerprint are pending the post-A4 run.

## Files
Modified: `services/retrieval_config.py` (2 settings), `services/pdf_parser.py` (`PDFLimitExceeded`, page-count check), `services/ingestion_service.py` (size check, import), `run_tests.py` (registered the A3 test under `integration`), `test_p2_04_ingestion_edge_cases.py`, `test_a1_embedding_model_config.py`. New: `test_a3_ingestion_limits.py`, `docs/remediation/A3_INGESTION_LIMITS_REPORT.md`. No schema, migration, chunking, embedding, retrieval or 10-word-threshold changes.
