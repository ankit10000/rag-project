# Database migrations

Plain SQL files, applied by hand with `psql`, in numeric order. **All four are required**
by the current application code: 000 → 001 → 002 → 003.

| File | Purpose | Rollback |
|---|---|---|
| `000_base_schema.sql` | Base tables `conversations`, `messages`, `conversation_memories`, `document_chunks`, their keys/indexes and the `vector` extension (Batch 1) | none (base schema). No-op on an existing database. |
| `001_add_messages_context_excluded.sql` | `messages.context_excluded` flag | none (additive column; leave in place) |
| `002_add_memory_sources.sql` | `memory_sources` join table + backfill from legacy `source_message_id` | `002_add_memory_sources_down.sql` (breaks memory writes, see §4) |
| `003_memory_sources_provenance.sql` | `memory_sources.link_kind` / `source_role`, CHECK constraints (`user_source_ck` is NOT VALID: legacy rows tolerated), role-aware deferrable message FK, `memory_sources_message_idx` | `003_memory_sources_provenance_down.sql` — **breaks the current code**, see §4b |

Proposals 004–006 in `docs/remediation/proposals/` are NOT migrations and are not applied.

## 0. Fresh database from version control (no dump needed)

Prerequisites: PostgreSQL 18 with the pgvector extension installed on the server
(the Python `pgvector` package does NOT install it; check with
`SELECT * FROM pg_available_extensions WHERE name = 'vector'`), and a role allowed to
`CREATE EXTENSION` (the database owner). Verified in Batch 1 (2026-11-15) on PostgreSQL 18.6 /
pgvector 0.8.7 in a disposable database: all four scripts applied cleanly twice (idempotent)
and the resulting schema was identical to the application database (excluding the unused
`vector_test` table).

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
& $psql -U postgres -h localhost -d postgres -c "CREATE DATABASE rag_db TEMPLATE template0"
foreach ($f in "000_base_schema","001_add_messages_context_excluded","002_add_memory_sources","003_memory_sources_provenance") {
    & $psql -U postgres -h localhost -d rag_db -v ON_ERROR_STOP=1 -f "migrations\$f.sql"
    if ($LASTEXITCODE -ne 0) { throw "$f failed" }
}
```

Expected schema: tables `conversations`, `messages` (with `context_excluded`),
`conversation_memories` (`embedding vector(384)`), `memory_sources` (with `link_kind`,
`source_role`), `document_chunks` (`embedding vector(384)`, UNIQUE
`(document_name, page_number, chunk_id)`). There are no ANN (HNSW/IVFFlat) or GIN/full-text
indexes: vector search and `BM25_BACKEND=fts` are sequential scans (fine at the current
size; add indexes only after measuring real queries). `vector(384)` must match `EMBEDDING_DIM`.

Conventions: `NNN_name.sql` for the change, `NNN_name_down.sql` for the
rollback. Every script is idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`)
and wrapped in a transaction where it touches more than one object.
Migrations never delete or rewrite rows in `conversation_memories` or `messages`.
The legacy `conversation_memories.source_message_id` column is kept and still written.

Connection used below (adjust user/host/port): `-U postgres -h localhost -p 5432`, database `rag_db`.
PowerShell: `$env:PGPASSWORD = "<password>"` first. psql lives in `C:\Program Files\PostgreSQL\18\bin`.

## 1. Back up BEFORE any migration

```powershell
mkdir backups -ErrorAction SilentlyContinue
$ts = Get-Date -Format yyyyMMdd_HHmmss
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -U postgres -h localhost -p 5432 -Fc -f "backups\rag_db_$ts.dump" rag_db
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -l "backups\rag_db_$ts.dump"   # must list TABLE DATA entries
```

## 2. Rehearse on a throw-away copy (recommended)

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
& $psql -U postgres -h localhost -d postgres -c "CREATE DATABASE rag_db_migtest TEMPLATE rag_db"
& $psql -U postgres -h localhost -d rag_db_migtest -v ON_ERROR_STOP=1 -f migrations\002_add_memory_sources.sql
& $psql -U postgres -h localhost -d rag_db_migtest -c "SELECT count(*) FROM memory_sources"
& $psql -U postgres -h localhost -d postgres -c "DROP DATABASE rag_db_migtest"
```
(`CREATE DATABASE ... TEMPLATE` needs no other session connected to `rag_db`.)

## 3. Apply

```powershell
& $psql -U postgres -h localhost -d rag_db -v ON_ERROR_STOP=1 -f migrations\002_add_memory_sources.sql
```

Verify:

```sql
SELECT count(*) FROM memory_sources;                         -- = memories whose legacy source_message_id is not NULL
SELECT count(*) FROM conversation_memories cm
 WHERE cm.source_message_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM memory_sources ms
                    WHERE ms.memory_id = cm.id AND ms.source_message_id = cm.source_message_id);  -- must be 0
```

## 4. Roll back

```powershell
& $psql -U postgres -h localhost -d rag_db -v ON_ERROR_STOP=1 -f migrations\002_add_memory_sources_down.sql
```

This drops `memory_sources` and the two helper unique indexes. Memories, messages and the
legacy `source_message_id` column are untouched. Links recorded only in `memory_sources`
(for example sources added by later UPDATEs) are lost, so take a backup first. After a
rollback the application still works: `get_memory_details` falls back to the legacy
column, but `save_memory`/`update_memory` will fail until the table exists again, so
roll the code back (or re-apply 002) as well.

## 4b. Rolling back 003 (not recommended)

```powershell
& $psql -U postgres -h localhost -d rag_db -v ON_ERROR_STOP=1 -f migrations\003_memory_sources_provenance_down.sql
```

This drops `link_kind`, `source_role`, both CHECK constraints, the lookup index and the
role-aware FK (the old cascading FK is restored). **The current application code then
fails**: `save_memory` / `update_memory` / `confirm_memory` write `link_kind`, and the
memory-context and provenance services read `source_role`. Only roll back 003 together
with a code rollback to before Phase 5, and back up first: the labels are lost.

## 5. Restore from a backup (last resort, replaces current data)

```powershell
& $psql -U postgres -h localhost -d postgres -c "DROP DATABASE rag_db"      # destroys current data
& $psql -U postgres -h localhost -d postgres -c "CREATE DATABASE rag_db"
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -U postgres -h localhost -d rag_db backups\rag_db_<timestamp>.dump
```
The `vector` extension is restored from the dump; if `pg_restore` reports it missing, run
`CREATE EXTENSION vector;` in `rag_db` first.
