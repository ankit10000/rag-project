# Phase 2 — Legacy memory reconciliation rollback plan

**Status:** prepared, **never executed or rehearsed**. Nothing has been applied, so there is currently nothing to roll back.

## 1. What a future reconciliation could affect
The only proposed operation is the quarantine marker (`PHASE2_LEGACY_MEMORY_QUARANTINE_DESIGN.md`). It affects:
- **Proposed schema `004`:** the new table `memory_provenance_quarantine` (created by it).
- **Applying a plan:** rows inserted into that table, one per approved memory.

It does **not** modify `conversation_memories`, `memory_sources` (`link_kind`, `source_role`), `messages`, embeddings, summaries or checkpoints. If a future step proposes anything beyond this, this plan must be extended and re-approved first.

## 2. How original provenance is preserved
- **Untouched:** the original rows are never touched by the proposed operations.
- **Copied into the marker:** each marker copies the evidence it acted on (`source_snapshot`, `issues`, `classification`, text hash).
- **Fingerprinted before and after:** the inventory `fingerprint` (row count + SHA-256 of `conversation_memories(id, conversation_id, source_message_id)` and `memory_sources(memory_id, source_message_id, conversation_id, link_kind, source_role)`) is recorded before any operation. It must match afterwards.
- **Snapshot:** a verified `pg_dump -Fc` snapshot exists before any operation (procedure step 1).

## 3. Restoring quarantined records
- **Normal path, release:** for each memory, set `status='released'`, `released_at=now()`, `release_reason`, `release_approval_ref`. The memory was never changed, so release fully restores normal standing. Release keeps the audit row.
- **Full removal of the mechanism:** export the table, then run `004_memory_provenance_quarantine_down.sql.proposed` (`DROP TABLE`). No other object depends on it, because the design has no FK.

## 4. Recovering from partial failure
- **During apply:** the apply step is one transaction, so any error rolls it back automatically. Verify that the marker count for the plan's `approval_ref` is 0 and that the fingerprints are unchanged.
- **If a non-transactional step was ever used, or the commit state is unclear:**
  - Count the markers with that `approval_ref`.
  - Either release them (as in §3), or `DELETE` the markers with that `approval_ref`. Deleting is acceptable only for markers created in the failed run, and only with approval, because they are new rows with no prior state.
  - Then compare the fingerprints.
- **If the base tables differ from the pre-operation fingerprint**, which should be impossible by design:
  1. Stop.
  2. Do not attempt manual fixes.
  3. Restore the affected database from the verified snapshot into a new clone.
  4. Compare it with the current state.
  5. Restore only after explicit approval.

## 5. Verifying that rollback restored the original state
1. Re-run the read-only inventory against the same database.
2. The `conversation_memories` and `memory_sources` fingerprints must equal the pre-operation values exactly (row counts and SHA-256).
3. The category counts and the per-memory classifications must equal the pre-operation report.
4. The marker table must be absent (after the down script), or contain only `released` rows for the run (after release).
5. Exercise the Phase 1 deletion behaviour on the clone:
   - `delete_message_with_provenance` must still classify support the same way;
   - `delete_memory` and conversation delete must succeed.
6. Record the evidence in a rollback report.

## 6. Rehearsal requirement
Before any production approval, rehearse on an isolated clone, in this order:
1. Forward migration and plan apply.
2. A failure injection during apply, to confirm the transactional rollback.
3. Release.
4. The down script.
5. Re-verification as in §5.

Each step needs the approvals listed in `PHASE2_LEGACY_MEMORY_RECONCILIATION.md` §7.
