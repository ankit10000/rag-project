# A1 report — connect `EMBEDDING_MODEL` to the embedding loader

Date: 2026-11-12. Scope: A1 only (A2 not started). Nothing committed. No Gemini, no network/model downloads (network blocked for unit/integration runs, loader faked in the new test). `rag_db` untouched (scratch DB only via `testsafe`; the runner's read-only fingerprint check only).

## Inspection (before the change)
- `services/retrieval_config.py:58-59`: `EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")`, `EMBEDDING_DIM = _int("EMBEDDING_DIM", 384)` ("must match document_chunks.embedding").
- `services/embedding_service.py`: `model = SentenceTransformer("all-MiniLM-L6-v2")` **hardcoded**, loaded **at import time**; `generate_embeddings(texts)` calls `model.encode(texts, normalize_embeddings=True)`. `EMBEDDING_MODEL` was used nowhere in project code.
- Dimension validation: only in `services/ingestion_service.py:71-75` (`embeddings.shape[1] != cfg.EMBEDDING_DIM` → `ValueError`), plus the vector column width in PostgreSQL. `memory_storage_service`/`memory_search_service`/`search_service` also call `generate_embeddings` but have no explicit width guard (the DB column rejects wrong widths). Not changed.
- Callers of `generate_embeddings`: ingestion, search, memory storage/search, and several `eval/` benchmark scripts. Existing tests patch `generate_embeddings` or use the real default model.

## Change (before / after)
`services/embedding_service.py` only:
```python
from services import retrieval_config as cfg
model = SentenceTransformer(cfg.EMBEDDING_MODEL)
```
- Before: config value ignored; always `all-MiniLM-L6-v2`.
- After: the configured name is loaded. Default unchanged (`all-MiniLM-L6-v2`), still loaded at import, same `encode(..., normalize_embeddings=True)`, same failure behaviour (an unloadable model raises at import; no fallback). The existing ingestion dimension guard is untouched and now checks the configured model's output against `EMBEDDING_DIM`.

## Tests (executed): `test_a1_embedding_model_config.py` — 9 PASS, 0 FAIL (unit, registered in `run_tests.py`)
Uses a recording fake `SentenceTransformer` and private module copies (the real `services.embedding_service` is not reloaded). Covers: default name and dim; env override of `EMBEDDING_MODEL`; loader receives the default name; loader receives a different configured name; unchanged encode/normalise behaviour; a 768-d model rejected by the `EMBEDDING_DIM` guard through `ingest_pdf` (nothing stored); load failure raises `OSError` at import with no silent fallback; module isolation.

**Mutations (executed, repo files untouched):** hardcoded name restored → 2 FAIL (caught); loader errors swallowed with fallback to the default model → 1 FAIL (caught).

## Regression (completed, not killed)
Full default suite `run_tests.py --clean`: **29 / 29 passed, 0 failed** (28 prior + new test), including `test_retrieval_phase2` and P2-01 to P2-04 and `test_p2_05_zero_top_k`. **`rag_db` fingerprint unchanged: True.**

## Model compatibility limitations (documented, not implemented)
- Vectors from different models are **not comparable even at the same dimension**. Changing `EMBEDDING_MODEL` for an existing corpus makes stored `document_chunks`/memory embeddings semantically inconsistent with new query/ingest vectors; retrieval quality silently degrades and no error is raised when dimensions match.
- Nothing stores which model produced a row, so a mismatch cannot be detected. No re-embedding, migration, schema change or automatic switch was implemented.
- A model with a different output width fails the ingestion guard (and the DB column); `EMBEDDING_DIM` and the pgvector column must be changed together, which needs a migration and full re-embed (out of scope).
- Memory/search paths have no explicit width guard (rely on the DB). Not changed.
- Switching models in practice needs: set `EMBEDDING_MODEL` (+ `EMBEDDING_DIM` if needed), re-ingest all documents, and re-embed stored memories. Recommended follow-up: record the model name per row (separate, approved step).

## Files
Modified: `services/embedding_service.py`, `run_tests.py` (registered the test under `unit`). New: `test_a1_embedding_model_config.py`, `docs/remediation/A1_EMBEDDING_MODEL_CONFIG_REPORT.md`. No schema, migration, default or other module changes.
