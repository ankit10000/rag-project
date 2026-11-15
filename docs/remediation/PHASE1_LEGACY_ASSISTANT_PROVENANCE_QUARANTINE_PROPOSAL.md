# Legacy Assistant-Source Provenance Quarantine Proposal

**Status:** Proposal only. No production inventory, quarantine, migration, or historical-data change was run for Phase 1 Task 3. `link_kind='legacy'` is preserved as the link's backfill origin; it is not a message-role label.

## Purpose

Historical `memory_sources` rows can point to assistant messages because the migration retained those rows and recorded their actual role in `source_role`. Such rows are not verified user-origin evidence. This proposal describes how to inventory and safely reconcile them in a separately approved task.

## Identification and classification

Run a read-only inventory on an approved data snapshot. Join `memory_sources` to `messages` on both conversation ID and message ID, and report rows where `source_role` is not `user`, the actual `messages.role` is not `user`, the stored and actual roles disagree, or the source message is missing. Separately inspect non-NULL `conversation_memories.source_message_id` values by joining on the memory's conversation ID and message ID; scalar references whose actual role is `assistant` are assistant-origin references even though the scalar column stores no role.

Classify each memory by the union of both representations:

- **User-supported:** at least one same-conversation source resolves to an actual user message and, for a join row, `source_role='user'`.
- **Assistant-only / unverified:** no valid user source exists and one or more references resolve to assistant messages.
- **Missing or inconsistent:** a reference has no matching message, roles disagree, or the representations cannot be reconciled. Treat as unverified until reviewed.

Do not infer role from `link_kind`. Keep `link_kind='legacy'` unchanged because it describes how the row entered the join table. `source_role` and the actual joined message role are the role evidence.

## Proposed treatment

- For memories supported only by assistant messages, keep the memory and original messages. Mark the provenance outcome as unverified/quarantined in a separately designed, auditable mechanism; do not silently treat the assistant message as a user fact, and do not delete the memory automatically. Until a safe state exists, callers should treat deletion cleanup as incomplete when no valid user source remains.
- For shared memories with at least one valid user source, preserve the memory and every valid user-source link. Retain assistant-origin rows for audit until a reviewed quarantine operation is approved; exclude them from valid-user support calculations. Do not alter or discard the memory because of an invalid extra link.
- For missing or role-inconsistent references, retain the data and route the row for review. Do not guess a replacement source ID.

## Rehearsal and rollback requirements for a future migration

1. Obtain separate authorization and prepare a consistent, access-controlled snapshot. Record row counts and hashes for affected memory IDs, source links, source roles, and referenced messages.
2. Produce a read-only classification report first. Review the assistant-only, shared, missing, and inconsistent groups before designing mutations.
3. Rehearse any proposed quarantine-table or status-field change on an isolated scratch clone only. Verify that valid user-supported memories and links remain unchanged, assistant-only memories remain present and are marked unverified, and all deletion-result classifications remain fail-closed.
4. Make the rehearsal transactional and idempotent. Capture before/after counts and hashes, test foreign-key behavior, and inject a failure to confirm rollback.
5. Define rollback before production approval. Prefer a transaction rollback before commit; for an approved committed change, restore from the captured snapshot or an explicit inverse migration that restores the exact original link and role data. Do not rely on changing `link_kind` to `user`, because that would corrupt its meaning.
6. Do not execute on `rag_db` until the inventory, classification, migration, and rollback plan have each received separate review and approval.

## Current boundary

Phase 1 Task 3 only changes message-deletion accounting and scratch tests. It does not inventory production rows, quarantine historical records, create a migration, or change `link_kind`/`source_role` values.
