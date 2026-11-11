# Phase 5 — Stage 1 audit: memory source attribution (read only)

Scope of this stage: inspection only. No application code, schema, dependency, configuration or data was changed.
The database was queried with SELECT/`\d` statements only (`rag_db`, PostgreSQL 18.6, pgvector 0.8.7).
Statistics below are a snapshot taken during this audit and will drift.

## 1. Current schema (live `rag_db`)

| Table | Relevant columns / constraints |
|---|---|
| `conversations` | `id uuid PK`, `summary`, `summary_up_to_message_id`, `memory_extraction_up_to_message_id` |
| `messages` | `id bigserial PK`, `conversation_id uuid NOT NULL → conversations(id) ON DELETE CASCADE`, `role varchar(20) NOT NULL` (no CHECK), `content`, `created_at`, `context_excluded bool NOT NULL DEFAULT false`; `UNIQUE (conversation_id, id)` (added by migration 002); index `(conversation_id, created_at)` |
| `conversation_memories` | `id bigserial PK`, `conversation_id uuid NOT NULL → conversations(id) ON DELETE CASCADE`, `memory text`, `embedding vector(384)`, `source_message_id bigint NULL → messages(id) ON DELETE SET NULL` (legacy, single source, **FK is on `id` only, not `(conversation_id, id)`**), `created_at`; `UNIQUE (conversation_id, id)` |
| `memory_sources` (migration 002) | `conversation_id uuid`, `memory_id bigint`, `source_message_id bigint`, `created_at`; **PK `(memory_id, source_message_id)`**; FK `(conversation_id, memory_id) → conversation_memories(conversation_id, id) ON DELETE CASCADE`; FK `(conversation_id, source_message_id) → messages(conversation_id, id) ON DELETE CASCADE` |

Indexes on these tables: only the PKs, the two `(conversation_id, id)` unique indexes, `idx_conversation_memories(conversation_id)` and `idx_messages_conversation(conversation_id, created_at)`. **There is no index that serves "which memories does message M source?"** (the PK leads with `memory_id`).

Migration conventions: plain SQL in `migrations/NNN_name.sql` (+ `NNN_name_down.sql` when rollback exists), applied by hand with `psql`, idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), documented in `migrations/README.md`. Only `001` (messages.context_excluded, no down script) and `002` exist. **The base table DDL is not in the repo** (no `schema.sql`), so a scratch database must be created from `pg_dump --schema-only` of `rag_db` (read-only operation).

## 2. Data snapshot

| Fact | Value |
|---|---|
| memories | 127 across 46 conversations (max 6 per conversation) |
| memories with a legacy `source_message_id` | 93 (all have a matching `memory_sources` row) |
| memories with **no source at all** | 34 (22 are in conversations that have no messages at all; 12 are in conversations that do have messages) |
| `memory_sources` rows | 93; memories with more than one source: 0 |
| `memory_sources` rows whose source message is an **assistant** message | 4 (migration 002 backfill did not check role) |
| legacy source pointing at another conversation's message | 0 |
| sources that are `context_excluded` | 0 |
| messages that are the source of more than one memory | 1 (up to 3 memories share one message) |
| messages / excluded messages / conversations | 1340 / 281 / 261 |

## 3. Code paths

**Creation** — `main.py` (~279-310) fetches un-extracted user messages in batches of `MEMORY_EXTRACTION_THRESHOLD=4` and calls `extract_and_save_memories` (`services/memory_service.py:258`). `extract_memories` (`:154`) shows only user messages tagged `[id=N]` and asks the LLM for `{"memory","source_message_id"}` — **exactly one source id per memory**; `_parse_json_memories` (`:109`) discards ids not among the batch's user ids; a memory without a valid id falls back to the batch's last user message. `process_memory` (`services/automatic_memory_service.py:67`) then decides NEW / DUPLICATE / UPDATE / DELETE (DELETE is blocked in automatic mode), and NEW calls `save_memory` (`services/memory_storage_service.py:10`), which validates the source (`_validate_source_message`, `:137`: must exist in the same conversation and be role `user`), inserts the row, and calls `_link_memory_source` (`:149`, `INSERT … ON CONFLICT (memory_id, source_message_id) DO NOTHING`) in the same transaction.

**Update** — `process_memory` UPDATE branch (`:168`) calls `update_memory` (`memory_storage_service.py:242`): validates the source, `UPDATE … SET memory=…, embedding=…, source_message_id=COALESCE(%s, source_message_id)`, then links the new source if the row was updated — one transaction. Old rows in `memory_sources` are kept; the legacy column is overwritten with the latest source. The previous text and embedding are overwritten and not recorded anywhere.

**Duplicates** — LLM `DUPLICATE` (`:163`) returns `SKIPPED` without any link; `save_memory` returns `False` on a ≥0.90 cosine duplicate (`:54-60`) before linking. A later user message that restates an existing memory is therefore **not** recorded as a source.

**Deletion** — `main.py` (~88-160): explicit-delete detector → `delete_matching_memories` (`automatic_memory_service.py:203`) reads **all** of the conversation's memories (not the 20 most recent), asks the LLM for IDs, filters them against the conversation's own IDs, captures `get_memory_details` (text + `source_message_ids`, union of `memory_sources` and the legacy column) **before** calling `delete_memory` (`memory_storage_service.py:162`, ownership check + `DELETE … AND conversation_id`). Then `apply_deletion_cleanup` (`services/memory_cleanup_service.py:283`) deterministically excludes every recorded source, its positional assistant reply and the deletion-turn messages (`mark_messages_excluded`, `conversation_service.py:55`, conversation-scoped), runs the best-effort LLM echo scan, and rewrites/verifies/resets the summary.

**Message / conversation deletion** — no application code deletes messages or conversations (the only `DELETE FROM` in the code base is `conversation_memories` in `delete_memory`). Behaviour exists only through database FK actions (answers 5-6).

## 4. Answers to the ten audit questions

1. **One source or many?** Both, inconsistently. `memory_sources` can hold many; the legacy column holds one. Extraction supplies **one** id per memory, so a memory built from several messages in a batch records only the LLM-chosen one.
2. **Previous sources preserved on update?** Yes in `memory_sources` (rows are only added). The legacy column is replaced with the latest id, and the previous memory text/embedding is lost.
3. **Cross-conversation references?** Not possible in `memory_sources` (composite FKs). Possible in the legacy column (its FK targets `messages(id)` only, and `save_memory`/`update_memory` check the conversation only in application code). 0 such rows exist today.
4. **Assistant pairing?** Positional: `get_paired_assistant_ids` (`conversation_service.py:85`) takes the next message by `id` in the same conversation and accepts it only if it is an assistant message and the origin is a user message. There is no stored link between a user message and its reply, so pairing relies on ids being adjacent (true for `main.py`, which saves user then assistant).
5. **Contributing message deleted?** `memory_sources` rows are removed silently (`ON DELETE CASCADE`), the legacy column becomes NULL (`ON DELETE SET NULL`), the memory stays, nothing is re-evaluated, and the information about which memories lost evidence is gone. No application path triggers this today.
6. **Conversation deleted?** Everything cascades (`conversation_memories`, `messages`, `memory_sources`). Because memory and message belong to the same conversation, no memory outlives its supporting messages. No application path triggers this today.
7. **Legacy memories without a valid source?** Yes: 34 have none (22 in conversations with no messages, so unrecoverable; 12 in conversations with messages, but no reliable evidence of which message produced them). 4 sources are assistant messages.
8. **Ownership enforced?** In `memory_sources`: at database level for conversation (composite FKs) and at application level for role. In the legacy column: application level only. The database does **not** enforce that a source is a `user` message.
9. **Duplicate relationships?** Blocked by the PK `(memory_id, source_message_id)` and by `ON CONFLICT DO NOTHING`.
10. **FKs and indexes that affect the design:** see section 1. Notably: both composite unique indexes already exist; the message→memories direction has no index; the legacy FK uses `SET NULL`, the new ones `CASCADE`.

## 5. Identified defects (the provenance gap)

| # | Defect | Effect |
|---|---|---|
| G1 | Extraction yields one source id per memory; the extractor sees up to 4 messages | A memory combined from several messages keeps one source; the others stay live after deletion (only the best-effort echo scan may catch them). |
| G2 | Restating messages are never linked (`DUPLICATE` decision and `save_memory` semantic-duplicate skip) | The restating message survives the deletion of the memory it restates. |
| G3 | UPDATE records only the single id passed in; update text history is not kept | Cannot audit what each message contributed; the superseded text can still sit in a retained message. |
| G4 | 34 memories have no source, 4 sources are assistant messages | Not deterministically cleanable; assistant evidence violates the "never evidence" rule and is not blocked by the database. |
| G5 | Shared sources: one message can source several memories (seen: 3) | Deleting memory A excludes the message from history/extraction even when memories B and C also derive from it (safe direction, but it hides legitimate context). |
| G6 | `ON DELETE CASCADE` on the message FK of `memory_sources` | Removing a message erases the evidence trail instead of flagging the affected memories for re-evaluation. |
| G7 | No index for message → memories lookup | Needed by deletion, shared-source checks and re-evaluation; currently a scan. |
| G8 | Legacy FK lacks the conversation component; `role` has no CHECK | Cross-conversation or assistant provenance cannot be prevented by the database. |
| G9 | Pair detection is positional | Correct today, fragile if message ids stop being adjacent (concurrent writers, retries). |
| G10 | Base schema DDL is not versioned | Test databases must be cloned from `pg_dump --schema-only`. |

Phase 1 behaviours that must stay intact: owner/conversation scoping on every delete, `valid_ids` filtering of LLM-selected ids, DELETE blocked during automatic extraction, deterministic exclusion before any LLM step, summary rewrite + verification + reset, user-only extraction, `delete_matching_memories` reading all of a conversation's memories.

## 6. Proposed schema (for Stage 2 approval; nothing applied)

Evolve the existing `memory_sources` rather than create a second table (a new table would duplicate 93 rows and the repo's composite-FK design already enforces ownership better than the handoff's sketch).

1. Keep PK `(memory_id, source_message_id)`; no surrogate `id` is needed for correctness (add one only if you want a stable link identifier — your call).
2. Add `link_kind text NOT NULL DEFAULT 'origin'` with `CHECK (link_kind IN ('origin','update','confirmation','legacy'))` so provenance is auditable and backfilled links are labelled.
3. Enforce user-only evidence in the database: unique index `messages(conversation_id, id, role)`, add `source_role text NOT NULL DEFAULT 'user' CHECK (source_role = 'user')` and a composite FK `(conversation_id, source_message_id, source_role) → messages(conversation_id, id, role)`. Added `NOT VALID` first so existing rows are not touched.
4. Add index `memory_sources(conversation_id, source_message_id)` for message → memories lookups.
5. Change the message FK action from `CASCADE` to `NO ACTION` so a message cannot vanish without its dependent links being handled first, while a conversation delete still works (memories and their links are removed in the same statement). Memory FK stays `CASCADE` (deleting a memory removes only its own links; no cascade can delete a memory).
6. Optional, to answer G3: a `memory_revisions(memory_id, revision, memory_text, created_at, source ids)` history table. Not required for deterministic deletion; recommended only if you want update audit.
7. Legacy data: keep the legacy `source_message_id` column untouched; backfill is already present; the 4 assistant-sourced rows are labelled `link_kind='legacy'` and quarantined from the constraint (or moved to a side table) rather than deleted; the 34 sourceless memories remain valid with zero links and are never given invented provenance.

Behavioural changes proposed for later stages: extraction returns a **list** of contributing ids per memory (validated against the batch's user ids); DUPLICATE decisions and semantic-duplicate skips link the restating message (`link_kind='confirmation'`) to the memory they restate; UPDATE links all contributing ids in the same transaction; message deletion goes through one function that lists affected memories via the new index and re-evaluates instead of cascading.

## 7. Migration risks

- **Assistant-sourced rows (4)** violate the new role constraint; add it `NOT VALID`, quarantine/label them, validate after.
- **Lock/impact:** tables are small (1,340 messages, 127 memories); all DDL is brief. Index creation uses plain `CREATE INDEX` inside a maintenance window or `CONCURRENTLY` outside a transaction.
- **Changing the message FK action** requires drop-and-recreate of one constraint; do it in a single transaction.
- **Rollback loses** links added after migration beyond the legacy column (multi-source links, `link_kind`); take `pg_dump` before applying (backup procedure exists in `migrations/README.md`).
- **No baseline DDL** in the repo, so rehearsal needs `pg_dump --schema-only` into a scratch database; never rehearse on `rag_db`.
- **Data drift:** the 34 sourceless memories cannot be repaired; any heuristic attribution would be fabricated provenance and is excluded by the rules.
- **Application risk:** code writing the new columns must ship with the migration (defaults make old code keep working: `link_kind` defaults to `'origin'`, `source_role` to `'user'`).

## 8. Test plan (isolated scratch database, fresh fixtures, no hard-coded conversations)

Scratch DB `rag_phase5_test` built from `pg_dump --schema-only rag_db` + the migrations; embeddings mocked (numpy zeros) so tests are fast; every test creates its own conversation and removes it in `finally`.

- **Creation:** one message → one memory with one link; several messages → every id linked; duplicate ids deduplicated; assistant id rejected (app **and** DB constraint); source from another conversation rejected (app and DB).
- **Update:** old links preserved; new link appended; several new ids appended; repeated update creates no duplicate; update + link atomic (force a failure after the UPDATE and assert neither the new text nor the new link persists).
- **Restatement:** a DUPLICATE decision and a semantic-duplicate skip each add a `confirmation` link, and a later deletion excludes that message.
- **Deletion:** all sources + positional assistant replies excluded; unrelated memories untouched; shared-source message behaviour documented and asserted (excluded, other memory still retrievable); cross-conversation and cross-owner deletion rejected; `valid_ids` filtering unchanged.
- **Message deletion (new function):** one of several sources removed → memory kept with remaining links and flagged for re-evaluation; last source removed → existing cleanup path, no silent retention; conversation delete leaves other conversations' memories alone.
- **Legacy:** one-source memory backfilled and deletes correctly; sourceless memory valid and deletable; invalid/NULL legacy source never deletes its memory; assistant-sourced legacy row handled without error.
- **Integrity:** duplicate link blocked; invalid FK blocked; rollback leaves no partial provenance; migration up, down and up again is idempotent (checksum of `conversation_memories` unchanged).
- **Regression:** the existing Phase 1 suite (`test_memory_delete_detector.py`, `test_deletion_cleanup.py`, `test_extraction_and_summary_guards.py`, `test_memory_sources_regression.py`, `test_model_fallback.py`; live: `test_deletion_scenarios.py`, `test_deleted_facts_regression.py`) plus `test_retrieval_phase2.py`, `test_answer_phase3.py`, `test_context_and_citations.py`. **Not to be run:** `test_automatic_memory.py`, `test_duplicate_memory.py`, `test_memory_update.py` (hard-coded real conversation `991c4838-…`).

## 9. Decisions needed from you before Stage 2

1. Evolve `memory_sources` (recommended) vs. create a new table with a surrogate `id`.
2. Enforce user-only evidence in the database (item 3) — yes/no.
3. Quarantine the 4 assistant-sourced links as `legacy` (recommended) vs. remove them.
4. Shared-source policy: keep the safe behaviour (exclude the shared message, accepting lost context for the other memories) — recommended — or exclude only when no surviving memory shares it.
5. Add `memory_revisions` for update audit now, or defer.
6. Message-deletion function: implement in Stage 5 as a library function only (no UI/CLI exists).
