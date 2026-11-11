# Database migrations

Plain SQL files, applied by hand with `psql`, in numeric order.

| File | Purpose | Rollback |
|---|---|---|
| `001_add_messages_context_excluded.sql` | `messages.context_excluded` flag | none (additive column; leave in place) |
| `002_add_memory_sources.sql` | `memory_sources` join table + backfill from legacy `source_message_id` | `002_add_memory_sources_down.sql` |

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

## 5. Restore from a backup (last resort, replaces current data)

```powershell
& $psql -U postgres -h localhost -d postgres -c "DROP DATABASE rag_db"      # destroys current data
& $psql -U postgres -h localhost -d postgres -c "CREATE DATABASE rag_db"
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -U postgres -h localhost -d rag_db backups\rag_db_<timestamp>.dump
```
The `vector` extension is restored from the dump; if `pg_restore` reports it missing, run
`CREATE EXTENSION vector;` in `rag_db` first.
