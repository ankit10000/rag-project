# A2 report — stale chunk cleanup on PDF re-ingestion

Date: 2026-11-12. Scope: A2 only (A3 not started). Nothing committed. No Gemini, no network/model downloads (deterministic embedder, network blocked). `rag_db` never connected to by any test (scratch DB only via `testsafe`). **Per instruction, the full default suite was NOT run in A2; only focused tests.**

## Inspection (before the change)
- `ingest_pdf` computed all chunks and embeddings in memory (parse → chunk → dedupe → embed → dimension and count checks), then opened ONE `with get_connection() as conn:` block and ran `INSERT … ON CONFLICT (document_name, page_number, chunk_id) DO UPDATE` per chunk. `get_connection()` (`services/database.py`) is a plain `psycopg.connect`; leaving the `with` block commits, an exception rolls back and closes. No autocommit.
- Consequence: rows are keyed by (document, page, chunk). A re-ingest that produced fewer/other keys left the old surplus rows (pinned in P2-01 and P2-04).
- Safest place for cleanup: **the same transaction, after all upserts, as the last statement before commit**. Everything before it (parse, chunk, embed, validations) can still fail without touching the database.

## Change (before / after)
`services/ingestion_service.py` only. After the insert loop, still inside the same cursor/transaction:
```sql
DELETE FROM document_chunks
WHERE document_name = %s
AND NOT EXISTS (
    SELECT 1 FROM unnest(%s::int[], %s::int[]) AS keep(page_number, chunk_id)
    WHERE keep.page_number = document_chunks.page_number
    AND keep.chunk_id = document_chunks.chunk_id
)
```
parameters: the document name and the (page_number, chunk_id) pairs of the current version.
- Before: 4-chunk document re-ingested as 1 chunk → 4 rows (3 obsolete).
- After: exactly 1 row (the current chunk, updated in place, same row id). Unchanged and longer documents behave as before (updated in place / extra rows inserted, ids kept). Other documents are never matched (`document_name = %s` exact).
- Transaction design: validations → upserts → scoped delete → commit. Any exception (parser, embedding, validation before the transaction; insert or delete inside it) leaves the previous document state intact. The keep-list uses the pre-dedupe `chunk_id` actually stored, so dedupe gaps in chunk ids are handled.

## Tests (executed)
New `test_a2_stale_chunk_cleanup.py` (integration, registered in `run_tests.py`): **26 PASS, 0 FAIL** (+ cleanup). Covers: longer (2→4, earlier ids kept), shorter (4→1, row id preserved), multi-page shrink (pages 2–3 removed; text moved to page 2 removes the old page-1 chunk), same count with changed content (same ids, new content/embeddings), repeated identical ingestion (rows/ids/content/embeddings unchanged), and a failed re-ingest that must preserve the previous snapshot exactly for: blank PDF, garbage PDF, parser failure, embedding failure, dimension mismatch, count mismatch, injected failure on the 2nd INSERT, real database error (NaN vector in chunk 2), injected failure on the DELETE (also proving the already-executed upsert of chunk 1 was rolled back), then recovery (the same shorter file ingests and cleans up afterwards). Isolation: another document and a name-prefix sibling (`name.pdf.old`) with identical page/chunk ids stay byte-identical; rows outside `a2_*` unchanged; test rows and temp dir removed.
Database failures are injected by a proxy around the real connection/cursor, so commit/rollback is real PostgreSQL behaviour.
Updated existing pins that encoded the old behaviour: `test_p2_01_pdf_ingestion.py` (shrink now leaves 1 row) and `test_p2_04_ingestion_edge_cases.py` (shrink now leaves 1 row; the stale-chunks finding removed, so that test now reports 3 findings instead of 4).
Focused re-runs after the change: `test_p2_01_pdf_ingestion.py` PASS (0 failed), `test_p2_04_ingestion_edge_cases.py` PASS (0 failed, 3 findings), `test_a2_stale_chunk_cleanup.py` PASS (0 failed).

## Mutation results (executed; repo files untouched, modified source loaded in memory)
| Mutation | Result |
|---|---|
| stale deletion removed | caught, 9 FAIL |
| deletion executed before validation (separate committed delete right after parsing) | caught, 15 FAIL |
| deletion outside the transaction (separate committed connection before the upserts) | caught, 3 FAIL |
| deletion not scoped to `document_name` | caught, 3 FAIL (isolation checks) |
| commit before deletion | caught, 3 FAIL |
| rollback bypassed (delete failure swallowed so inserts still commit) | caught, 3 FAIL |
All six caught. (First attempt at the unscoped mutant crashed on its own SQL typing; fixed the mutant, not the test.)

## Database safety evidence
Scratch DB only (`testsafe.require_scratch_db()` in every new test and mutation run); `rag_db` never connected to. Network blocked via `TESTSAFE_BLOCK_NETWORK=1`, offline HF flags, no Gemini. Test rows are `a2_*` only and removed in `finally`; leftover `a2_%` rows were also purged after each mutation run. The runner's read-only `rag_db` fingerprint check was **not** executed in A2 because the full suite is deferred until A1–A4 are complete (stated limitation).

## Known limitations
- Cleanup is keyed by `document_name`; two different files with the same name share one document (unchanged design). Re-ingesting any file with that name replaces the old document's chunks.
- Documents already containing stale rows from earlier ingestions are only cleaned the next time they are re-ingested.
- Retrieval caches (BM25 index) rely on their existing corpus fingerprint, which changes with the delete; not separately tested here.
- Concurrent re-ingestion of the same name is not serialized (not tested).
- Full-suite regression and `rag_db` fingerprint verification are pending the post-A4 run.

## Files
Modified: `services/ingestion_service.py` (+ cleanup statement), `run_tests.py` (registered `test_a2_stale_chunk_cleanup.py` under `integration`), `test_p2_01_pdf_ingestion.py`, `test_p2_04_ingestion_edge_cases.py` (pins updated). New: `test_a2_stale_chunk_cleanup.py`, `docs/remediation/A2_STALE_CHUNK_CLEANUP_REPORT.md`. No schema, migration, retrieval-default or other module changes.
