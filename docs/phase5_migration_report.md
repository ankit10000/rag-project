# Phase 5 — Stage 3 migration report

- Files: `migrations/003_memory_sources_provenance.sql`, `migrations/003_memory_sources_provenance_down.sql`.
- Rehearsed on `rag_phase5_mig` (copy of `rag_db`): up / down / up idempotent; memories and messages hashes unchanged.
- Applied to `rag_db` after a backup: 127 memories and 93 links before and after; no memory or message row modified.
- Existing 93 links labelled `legacy` with their message's real role (4 are assistant messages, tolerated by the `NOT VALID` CHECK).
- Message FK changed from cascading to role-aware, non-cascading, `DEFERRABLE INITIALLY DEFERRED` so conversation deletes still work.
- Rollback: run the `_down.sql` (restores the cascade FK; loses `link_kind`/`source_role`).
