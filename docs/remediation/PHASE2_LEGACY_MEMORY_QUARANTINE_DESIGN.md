# Phase 2 — Legacy memory quarantine design

**Status:** design and plan-builder code only. **No schema created and no quarantine executed.** The proposed SQL is outside `migrations/` and has not been applied anywhere.

## 1. Why quarantine is needed
Some historical memories cannot be verified: they are assistant-only, have no source, or have inconsistent references. Their provenance cannot be repaired without guessing, which is forbidden. Deleting them would destroy data the user may still want. A quarantine **marker** lets a reviewer flag them auditably and reversibly, while every original record stays exactly as it is.

## 2. Principles
- **Non-destructive.**
  - The memory row is not changed: no change to its text, embedding or `source_message_id`.
  - No `memory_sources` row is changed: `link_kind` and `source_role` are untouched.
  - No message is changed.
  - The only effect is inserting a marker row.
- **Explicit.** Only memory IDs that a reviewer explicitly approved are planned. `build_quarantine_plan` refuses IDs that are unknown or `USER_SUPPORTED`, and it requires an `approval_ref`.
- **Evidence-preserving.** Each marker stores:
  - the classification that triggered it;
  - a reason;
  - the verbatim classifier issues;
  - a `source_snapshot` of every link (source id, `link_kind`, `source_role`, actual role) and of the legacy scalar;
  - an optional memory-text SHA-256 for change detection.
- **Reversible.** `status` moves from `quarantined` to `released`, with `released_at`, `release_reason` and `release_approval_ref`. Markers are never deleted by the normal process, so they form the audit history.

## 3. Proposed schema
File: `docs/remediation/proposals/004_memory_provenance_quarantine.sql.proposed`. It adds one table, `memory_provenance_quarantine`:
- **Columns:**
  - `id`, `conversation_id`, `memory_id`
  - `classification` (CHECK: ASSISTANT_ONLY_OR_UNVERIFIED | MISSING_SOURCE | INCONSISTENT_SOURCE)
  - `reason`, `issues` (jsonb), `source_snapshot` (jsonb)
  - `memory_text_sha256`, `approval_ref`
  - `status` (CHECK: quarantined | released), `quarantined_at`
  - `released_at`, `release_reason`, `release_approval_ref`
- **Constraints and indexes:** a CHECK requires `released_at` to be set exactly when the status is released. A partial unique index allows only one **active** marker per memory.
- **No foreign key to `conversation_memories`, by design:**
  - a RESTRICT FK would break conversation deletion (which cascades to memories) and Phase 1's `delete_memory()`;
  - a CASCADE FK would erase the audit record.

  The marker therefore survives as history if the memory is later deleted through the existing, approved paths.

## 4. Effect on existing records
- **None.** Applying the proposed schema only creates an empty table. Inserting markers changes no existing row.
- **Fingerprints:** the inventory fingerprints of `conversation_memories` and `memory_sources` must be identical before and after a quarantine. That is the rehearsal acceptance check.
- **No behaviour change by itself.** Retrieval, memory decisions and deletion are not affected by markers. Making quarantined memories unavailable (e.g. excluding them in `memory_search_service`, `get_recent_memories` and summary inputs) is a **separate application change** that needs its own design review and approval (gate G3). It is not implemented.

## 5. Plan builder (implemented)
`services/legacy_provenance_quarantine.build_quarantine_plan(inventory_records, approved_memory_ids, approval_ref)`:
- **Input:** the `memories` list of an inventory report.
- **Output:** a dict containing `approval_ref`, `planned_count` and `entries`, plus `executed: False`.
  - Each entry has the memory and conversation ids, classification, reason, issues, modern and legacy source ids, text hash, and the proposed action "INSERT quarantine marker row only".
- **Refusals:**
  - an empty approval reference;
  - approved IDs that are not in the inventory;
  - any `USER_SUPPORTED` memory.
- **Pure:** no database access, and there is **no apply function**.

## 6. Proposed future apply step (NOT implemented)
1. Run on an isolated clone first.
2. Use one transaction.
3. For each planned entry, re-read the memory's current provenance read-only.
4. If its classification or fingerprint differs from the plan, abort the whole transaction (stale plan).
5. Insert the marker with the snapshot.
6. Commit only if all entries succeed.
7. Make it idempotent: skip a memory that already has an active marker for the same `approval_ref`.

## 7. Rollback
See `PHASE2_LEGACY_MEMORY_ROLLBACK_PLAN.md`. The proposed down script `004_memory_provenance_quarantine_down.sql.proposed` drops only the marker table, after exporting it.

## 8. Limitations
- The design has not been reviewed or rehearsed.
- No application path honours markers yet.
- Quarantine flags data; it does not resolve unverifiable provenance. The final disposition of each quarantined memory (keep, release or user-approved delete) remains a human decision.
