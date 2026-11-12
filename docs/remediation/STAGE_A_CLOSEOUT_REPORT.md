# Stage A closeout report (A1–A4)

Date: 2026-11-12. Scope: Stage A closeout only. Stages B, C and D were not started. No implementation code was changed during closeout. Nothing was staged, committed or pushed, and no migration was applied.

## 1. A1–A4 completion summary
| Step | Change | Report |
|---|---|---|
| A1 | `EMBEDDING_MODEL` now drives `SentenceTransformer(...)` in `services/embedding_service.py`. The default is unchanged (`all-MiniLM-L6-v2`). | `A1_EMBEDDING_MODEL_CONFIG_REPORT.md` |
| A2 | Re-ingestion removes the document's obsolete chunks in the same transaction, after the upserts, scoped to `document_name`. | `A2_STALE_CHUNK_CLEANUP_REPORT.md` |
| A3 | `MAX_PDF_SIZE_MB=50` is checked before parsing. `MAX_PDF_PAGES=500` is checked after the open and before text extraction. Both raise `PDFLimitExceeded(ValueError)` and are env-configurable. | `A3_INGESTION_LIMITS_REPORT.md` |
| A4 | Only `.pdf` is accepted (case-insensitive), checked first in `ingest_pdf`. Anything else raises `UnsupportedFileTypeError(ValueError)`. | `A4_PDF_FILE_TYPE_VALIDATION_REPORT.md` |
Each step has its own focused test, registered in `run_tests.py`: `test_a1_embedding_model_config.py` (unit), `test_a2_stale_chunk_cleanup.py`, `test_a3_ingestion_limits.py` and `test_a4_pdf_file_type_validation.py` (integration). Each step also had executed mutation checks, and all mutants were caught.

## 2. Pre-flight checks
- **Git:** repository at the project root, HEAD `2a0e06f`. `git diff --cached` was empty, so nothing was staged before closeout.
- **A1–A4 present:** implementation, tests, `run_tests.py` registrations and the four reports were all confirmed.
- **Runner** (`run_tests.py`, default = categories `unit` + `integration`):
  - It builds a scratch URL (`rag_test_scratch`) from the `.env` credentials and refuses any name that is not `rag_*test*`; `testsafe` forbids `rag_db`, `postgres` and `template*`.
  - It checks that every `test_*.py` is classified and calls `testsafe.require_scratch_db()`.
  - It runs each test in its own process with `DATABASE_URL` set to the scratch DB. Unit and integration tests run with `TESTSAFE_BLOCK_NETWORK=1`, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.
  - It fingerprints `rag_db` before and after the run.
- **Established fingerprint procedure, reused unchanged:** `run_tests.fingerprint(url)`. It connects with `options="-c default_transaction_read_only=on"`, and for each of `conversations`, `messages`, `conversation_memories`, `memory_sources` and `document_chunks` it runs `SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') FROM <table> t`. I called this same function directly, through a small helper script outside the repo, for the separate pre- and post-suite captures. It needs no writes.
- **Full-suite command (documented default):** `.venv\Scripts\python.exe run_tests.py --clean`. Here `--clean` empties only the scratch DB at the end, through `testsafe.check_conninfo`.

## 3. Full-suite result (single run)
Command: `.venv/Scripts/python.exe run_tests.py --clean`. It was run exactly once.
- **Run / passed / failed: 32 / 32 / 0.** There were no errors or timeouts, and the exit code was **0**.
  - Unit (13): `test_testsafe`, `test_answer_scoring`, `test_context_and_citations`, `test_answer_phase3`, `test_model_fallback`, `test_similarity`, `test_memory_delete_detector`, `test_p1_decision_parsing`, `test_p1_d3_decision_errors`, `test_p1_d4_delete_decision_errors`, `test_p1_d5_delete_ids`, `test_p2_05_zero_top_k`, `test_a1_embedding_model_config`.
  - Integration (19): `test_memory_sources_regression`, `test_deletion_cleanup`, `test_extraction_and_summary_guards`, `test_retrieval_phase2`, `test_p2_01` … `test_p2_04`, `test_a2_stale_chunk_cleanup`, `test_a3_ingestion_limits`, `test_a4_pdf_file_type_validation`, `test_phase5_provenance`, `test_memory_storage`, `test_p1_process_memory`, `test_p1_memory_update_delete_integration`, `test_p1_delete_routing`, `test_p1_cleanup_failure`, `test_p1_d2_classifier_status`, `test_p1_d7_storage_id_validation`.
- **Smoke-only passes (exit code only, no assertions):** 2, namely `test_similarity.py` and `test_memory_storage.py`.
- **Not run by category (skipped by design, not failures):** 18 scripts, 10 `live` (Gemini) and 8 `manual`. None ran, so there were no Gemini calls, network access or model downloads.
- **Runner's own check:** `application database 'rag_db' fingerprint unchanged : True`.

## 4. `rag_db` fingerprint, before and after (read-only)
| Table | Pre-suite (rows, md5) | Post-suite (rows, md5) | |
|---|---|---|---|
| conversations | 261, `7f4fb6de3077bde3c0b591efcaac70d5` | 261, `7f4fb6de3077bde3c0b591efcaac70d5` | same |
| messages | 1340, `502d43b77c943ab25edcc6c166eb15c8` | 1340, `502d43b77c943ab25edcc6c166eb15c8` | same |
| conversation_memories | 127, `88d8b76aa327ce9d882ee52ef98e0f38` | 127, `88d8b76aa327ce9d882ee52ef98e0f38` | same |
| memory_sources | 93, `7d877c75385fe995aaa9fcbc48096a36` | 93, `7d877c75385fe995aaa9fcbc48096a36` | same |
| document_chunks | 9, `711aa64fa4cb7bd330743dc0f341b5cb` | 9, `711aa64fa4cb7bd330743dc0f341b5cb` | same |
**The fingerprints are identical, and there is no evidence of any `rag_db` modification.** The fingerprint covers row counts and ordered content hashes of these five tables. It is not a physical snapshot of the whole database.

## 5. Final Git status and changed files
- HEAD is still `2a0e06f`. `git diff --cached` is empty: **nothing staged, nothing committed, nothing pushed.**
- **Modified (tracked):** `run_tests.py`, `services/embedding_service.py`, `services/hybrid_search_service.py`, `services/ingestion_service.py`, `services/pdf_parser.py`, `services/retrieval_config.py`, `services/rrf_service.py` and `test_p2_01_pdf_ingestion.py`. Together these are 8 files, +88/−8.
- **Untracked (new):**
  - Reports: `docs/remediation/A1_…`, `A2_…`, `A3_…`, `A4_…`, `P2_04_INGESTION_EDGE_CASES_REPORT.md`, `P2_05_RETRIEVAL_REGRESSION_REPORT.md`, and this report.
  - Tests: `test_a1_embedding_model_config.py`, `test_a2_stale_chunk_cleanup.py`, `test_a3_ingestion_limits.py`, `test_a4_pdf_file_type_validation.py`, `test_p2_04_ingestion_edge_cases.py`, `test_p2_05_zero_top_k.py`.
- **Earlier uncommitted work also in the tree:** the working tree also holds work done before Stage A. That is the P2-04 test and report, P2-04-F1 (the vector-count check in `ingestion_service.py`), and P2-05-F1 (`hybrid_search_service.py` and `rrf_service.py`, zero top-K, plus `test_p2_05_zero_top_k.py`). It is all uncommitted.
- **No closeout changes:** no implementation or test file was changed during closeout. The only new file is this report, plus fingerprint JSON and logs in the job's temp directory outside the repo. No migration was applied.

## 6. Remaining limitations and deferred findings
- **No total-chunk or total-text limit on ingestion.** A file within 50 MB and 500 pages can still produce many chunks. They are all embedded in one in-memory call and written in one transaction. (A3, P2-04)
- **Unspaced CJK pages may be skipped.** The 10-whitespace-word page minimum yields "No usable chunks". (P2-04)
- **Possible flakiness in P2-04.** Its malformed-PDF cases use `os.urandom` bytes after a `%PDF` header, and PyMuPDF's reaction to random bytes could vary between runs. A4's own test uses deterministic invalid content. (A4)
- **Changing the embedding model requires re-embedding.** Vectors from different models are not comparable even at the same dimension. The database does not store which model produced a vector, so a mismatch cannot be detected. Memory and search paths rely on the DB column for width rather than an explicit guard. Changing `EMBEDDING_DIM` needs a schema migration. (A1)
- **A2:**
  - documents name-collide by file name;
  - existing stale rows are cleaned only on the next re-ingest;
  - concurrent re-ingestion of the same name is not serialized;
  - the BM25 cache after a delete was not separately tested.
- **A3:** PyMuPDF still parses the document structure on open, and the size and page checks are not atomic with later reads.
- **A4:**
  - the check is extension-only, with no content sniffing;
  - a file literally named `.pdf` is rejected;
  - `name.PDF` and `name.pdf` are separate documents.
- **Earlier phases, outside Stage A:**
  - negative `top_k` behaves inconsistently on the direct retrievers;
  - the sentence chunker is English-centric;
  - filter value types are loose.
- **Smoke-only tests.** `test_similarity.py` and `test_memory_storage.py` make no assertions.

## 7. Commit and staging
No commit, staging, push or migration was performed at any point in Stage A or this closeout.

## 8. Final Stage A status: **PASS**
- The single full default suite run passed (32/32, exit 0).
- The `rag_db` fingerprint was identical before and after, both by the runner's internal check and by the separate captures.
- All A1–A4 artefacts are present, and the remaining findings are documented and deferred.

Stage B has not been started and is awaiting explicit approval.
