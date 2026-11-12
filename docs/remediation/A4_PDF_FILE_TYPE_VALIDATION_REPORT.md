# A4 report — PDF file-type validation

Date: 2026-11-12. Scope: A4 only (Stage A closeout not started). Nothing committed or staged. No Gemini, no network/model downloads (deterministic embedder, network blocked). Scratch DB only via `testsafe`.

## 1. Finding 2 and the decision preserved
P2-04 report, Finding 2 (original wording): "**NOT FIXED** — gap: no file-type validation (a `.txt` is ingested as page 1). Contract undefined." The test pinned it as "a plain .txt file is accepted and ingested (no file-type validation in ingest_pdf)" and recorded it as a gap, "not asserted as a defect".
No decision conflicted with A4: the report left the contract undefined and recorded no decision to accept other formats. A4 now defines the contract: **only `.pdf` (case-insensitive)**. The P2-04 pin was updated accordingly.

## 2. Implementation and validation order
`services/pdf_parser.py`: new `class UnsupportedFileTypeError(ValueError)`, next to A3's `PDFLimitExceeded(ValueError)`.
`services/ingestion_service.py`, `ingest_pdf`. The order is:
0. `document_name` = last path component (unchanged; `/` and `\`).
1. **A4 (new)**: `extension = os.path.splitext(document_name)[1]`. If `extension.lower() != ".pdf"`, raise `UnsupportedFileTypeError`. This is pure string work, with no filesystem access.
2. A3 size check: `os.path.getsize` → `PDFLimitExceeded`.
3. `extract_text`: `pymupdf.open` (malformed/encrypted errors unchanged) → A3 page-count check → text extraction.
4. Unchanged: chunking → embedding → dimension and count checks → one transaction (upsert + A2 stale delete).

## 3. Exception behaviour
- Non-`.pdf` or no extension → `UnsupportedFileTypeError` (a `ValueError`). Messages: `Unsupported file type '.txt' for 'name.txt': only .pdf files can be ingested`, and `Unsupported file type '(no extension)' for …`.
- Nothing is caught or transformed. Existing `except ValueError` callers still catch it.
- `.pdf`/`.PDF`/`.Pdf` files behave exactly as before:
  - invalid content → PyMuPDF `FileDataError`
  - missing file → `FileNotFoundError`
  - encrypted → `ValueError`
  - blank → `ValueError("No usable chunks…")`
  - over the limits → `PDFLimitExceeded`
- A missing file with a non-PDF extension now reports the type error (it is checked before any filesystem access).

## 4. Focused test results (executed)
`test_a4_pdf_file_type_validation.py` (integration, registered in `run_tests.py`): **37 PASS, 0 FAIL**.
- Accepted: `.pdf`, `.PDF` (the stored `document_name` keeps the case), `.Pdf`, and a multi-dot name ending in `.pdf`.
- Rejected with a descriptive `UnsupportedFileTypeError`, each case containing real PDF bytes so only the name decides: `.txt`, `.docx`, `.png`, no extension, `.pdf.bak`, `.pdfx`, a trailing dot (`.pdf.`), and a missing `.txt`.
- For every rejection, spies show that none of these were called: `os.path.getsize`, `pymupdf.open`, `extract_text`, the embedder, `get_connection`.
- Rejected new files create no rows (all `a4_*` rows identical before and after).
- Rejected "replacements" of an existing document (`stem.txt`, `name.pdf.bak`, `stem.docx`) leave its rows, ids, content and embeddings identical, and create no rows under the rejected names. A same-name replacement cannot have a different type, because the type is part of the name; the meaningful case is a same-stem file.
- Invalid content in a `.pdf` and a `.PDF` gives `FileDataError` after the type and size checks.
- A missing `.pdf` gives `FileNotFoundError`, an encrypted one gives `ValueError` (not a type error), and a blank one gives "No usable chunks".
- A3 still applies:
  - the size limit for `.pdf`
  - the page limit for `.PDF`
  - when a non-PDF also exceeds the size limit, the type error is reported first
  - the stored document is unchanged by the limit rejections.
- Cleanup: no `a4_*` rows left, temp dir removed.

Directly affected tests, updated and re-run:
- `test_p2_04_ingestion_edge_cases.py`: **0 failed, 2 findings** (unspaced CJK; no total-chunk limit).
  - The `.txt`-accepted pin is now "`.txt` rejected with `UnsupportedFileTypeError`, nothing stored". The short-`.txt` case and the "no file-type validation" finding were removed, because both are superseded.
  - "Directory path → FileDataError" is now split in two. A directory without `.pdf` gives `UnsupportedFileTypeError`, and a directory named `*.pdf` still gives `FileDataError`.
- `test_a2_stale_chunk_cleanup.py`: **0 failed**. Its prefix-sibling fixture was renamed from `name.pdf.old` to `name.pdf.old.pdf`; it still starts with the document name, so the isolation intent is unchanged.
- `test_a3_ingestion_limits.py`, `test_p2_01_pdf_ingestion.py`, `test_a1_embedding_model_config.py`: **0 failed**, unchanged.

## 5. Mutation results (executed; repo files untouched, modified source loaded in memory)
| Mutation | Result | Failing checks (examples) |
|---|---|---|
| extension validation removed | caught, 23 FAIL | every `[reject] …` type and "rejected before …" check; replacement checks |
| case-sensitive check (`extension != ".pdf"`) | caught, 5 FAIL | `.PDF` accepted, `.Pdf` accepted, `.PDF` invalid content → FileDataError, A3 page limit for `.PDF` |
| validation moved after PDF parsing | caught, 14 FAIL | every "rejected before getsize, PDF open, text extraction …" check |
| validation moved after the database write | caught, 16 FAIL | "rejected before … DB connection" checks, plus the no-rows and replacement-unchanged checks |
| accidentally rejecting uppercase `.PDF` | caught, 4 FAIL | `.PDF` accepted, `.PDF` invalid content, A3 page limit for `.PDF` |

## 6. Files changed
- Modified:
  - `services/pdf_parser.py` (`UnsupportedFileTypeError`)
  - `services/ingestion_service.py` (extension check as the first step; import)
  - `run_tests.py` (registered the A4 test under `integration`)
  - `test_p2_04_ingestion_edge_cases.py` (Finding 2 pin and directory case)
  - `test_a2_stale_chunk_cleanup.py` (sibling fixture name)
- New: `test_a4_pdf_file_type_validation.py`, `docs/remediation/A4_PDF_FILE_TYPE_VALIDATION_REPORT.md`.
- No chunking, embedding, retrieval, schema, migration or memory changes.

## 7. Limitations and unresolved findings
- Extension only, as specified, with no content sniffing. A non-PDF renamed to `.pdf` is caught later by PyMuPDF if unreadable. A format PyMuPDF can open (e.g. a text file renamed to `.pdf`) still fails as "not a PDF" (`FileDataError`), as the deterministic test shows.
- A file literally named `.pdf` has no extension per `os.path.splitext` and is rejected.
- `name.PDF` and `name.pdf` are different `document_name`s (two documents). This is unchanged and not normalised.
- P2-04's malformed-PDF cases still use `os.urandom` bytes after a `%PDF` header. PyMuPDF's reaction to random bytes could in principle vary between runs. A4's own test uses deterministic invalid content. This is not changed here (out of scope).
- Remaining open P2-04 findings: unspaced CJK pages skipped; no total-chunk limit.

## 8. Not run (by instruction)
The full default suite and the final `rag_db` fingerprint check were **not** run in A4. They are deferred to the Stage A closeout.
