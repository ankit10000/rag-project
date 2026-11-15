# Phase 2 — Legacy memory reconciliation

**Status (2026-11-15):** tooling **implemented, NOT tested, NOT executed**.
- No inventory has been run against any database, `rag_db` was not accessed, and no historical record was changed.
- No quarantine, migration, backfill, rehearsal or rollback was executed.
- **Historical data has NOT been reconciled.**

Related: `PHASE2_LEGACY_MEMORY_QUARANTINE_DESIGN.md`, `PHASE2_LEGACY_MEMORY_ROLLBACK_PLAN.md`, Phase 1 `PHASE1_LEGACY_MEMORY_AUDIT.md`, `PHASE1_LEGACY_MEMORY_REMEDIATION_PLAN.md`, `PHASE1_LEGACY_ASSISTANT_PROVENANCE_QUARANTINE_PROPOSAL.md`.

## 1. Objective
Provide a safe, auditable way to **identify** historical memories whose provenance cannot be verified, and to **prepare** their reconciliation.
- The tooling never guesses a source. It never infers one from text, timestamps, neighbouring messages or similarity.
- It never damages existing records.
- New-write provenance is already enforced by Phase 1. Phase 2 deals only with records written before those rules.

## 2. Existing legacy provenance problems (from Phase 1 and the schema)
- **Two representations of provenance.**
  - The modern join table `memory_sources(conversation_id, memory_id, source_message_id, link_kind, source_role)` is conversation-scoped through composite foreign keys.
  - The legacy scalar `conversation_memories.source_message_id` has a FK on `messages(id)` **only** (`ON DELETE SET NULL`). It is **not** conversation-scoped, so it can in principle point at another conversation's message.
- **Assistant-origin rows.** Migration 002 backfilled the scalars into `memory_sources`. Migration 003 labelled those rows `link_kind='legacy'` and copied the real `messages.role` into `source_role`. The user-role check `memory_sources_user_source_ck` was added `NOT VALID`, so historical rows pointing at assistant messages were tolerated and kept.
- **Source-less memories.** Memories written before strict provenance (Phase 1 Task 1) can have neither a join row nor a scalar.
- **Representation drift.** Normal writes keep the scalar inside the join set: `save_memory` writes `source_message_id = sources[0]` plus links, and `update_memory` sets the scalar to a linked source. A scalar with no matching join row therefore signals drift.
- **Phase 1 deletion is already correct for this.** `delete_message_with_provenance` considers both representations and counts only same-conversation **user** sources as support. Phase 2 does not change it.

## 3. Implemented tooling (code exists; nothing executed)
| File | Responsibility | Writes? |
|---|---|---|
| `services/legacy_provenance_classifier.py` | pure deterministic classifier (facts → category + issues) | no DB, no I/O |
| `services/legacy_provenance_inventory.py` | read-only fact collection, classification and fingerprint | **read-only**; no INSERT/UPDATE/DELETE/DDL statement exists in the module (those words appear only in its docstring) |
| `services/legacy_provenance_quarantine.py` | pure quarantine **plan** builder for explicitly approved IDs | no DB; **no apply function** |
| `legacy_provenance_inventory.py` (CLI) | runs the read-only inventory against an explicitly named database and writes a JSON report | writes only the local report file (refuses to overwrite) |
| `docs/remediation/proposals/004_memory_provenance_quarantine*.sql.proposed` | proposed quarantine schema and its rollback | **not applied**; kept outside `migrations/` |

Phase 1 modules (`memory_provenance_service`, `memory_storage_service`, `automatic_memory_service`, `memory_service`, `main.py`) were **not modified** in Phase 2.

## 4. Inventory: fields and methodology
### Read-only guarantees
1. **Explicit target:** a connection string must be passed (`run_inventory(conninfo, …)`); there is no default target database. The module does not use `services.database.get_connection()`, whose default is the application DB.
2. **Read-only at three levels:** the connection is opened with `default_transaction_read_only=on`; all queries run inside `BEGIN READ ONLY`; the run aborts unless `SHOW transaction_read_only` returns `on`. The transaction is always ended with `ROLLBACK`.
3. **CLI target rules:**
   - `--database` is required and is printed, and the connected `current_database()` must match it.
   - `rag_db`, `postgres`, `template0` and `template1` are refused unless `--allow-protected-database --approval-ref "<ref>"` is given.
   - Credentials come from `.env` and are never printed. An existing output file is never overwritten.

### Columns read
These are only columns confirmed in the repository code and migrations:
- `conversation_memories`: `id`, `conversation_id`, `source_message_id` (plus an optional `sha256(memory)`; the text itself is never read into the report).
- `memory_sources`: `memory_id`, `conversation_id`, `source_message_id`, `link_kind`, `source_role`.
- `messages`: `id`, `conversation_id`, `role`.
- Message content is never read.

### Joins
Messages are joined **by message id only**, for both representations. A foreign-conversation reference therefore remains visible; a conversation-scoped join would hide it.

### Per-memory output (JSON)
- `memory_id`, `conversation_id`, `category`
- `valid_user_source_ids`, `modern_source_ids`, `legacy_source_id`
- `issues[]`, each with `code`, `representation`, `source_message_id` and `detail` (e.g. stored vs actual role)
- optionally `memory_text_sha256`

### Report header
- `database`, `transaction_read_only`, `scope_conversation_id`, `generated_at`, `approval_ref`
- `summary`: counts per category and per issue code, and the number of `USER_SUPPORTED` memories that have recorded issues
- `fingerprint`: row count and SHA-256 over sorted provenance rows of both tables. Used before/after a rehearsal or rollback.

### Not modified by the inventory
Records, provenance, memory text, embeddings, checkpoints, conversations, messages and quarantine state are never modified. Nothing is created.

## 5. Classification (deterministic; `legacy_provenance_classifier.py`)
### Valid user source
- **Modern row:** the message exists, `messages.conversation_id` equals the memory's, `memory_sources.conversation_id` equals the memory's, `messages.role = 'user'` and `source_role = 'user'`.
- **Legacy scalar:** the message exists, it is in the same conversation, and `messages.role = 'user'`. The scalar stores no role, so the actual role is authoritative.
- `link_kind` is never role evidence: `legacy` means migration origin.

### Categories, by precedence
1. **USER_SUPPORTED:** at least one valid user source. One is sufficient.
2. **MISSING_SOURCE:** no `memory_sources` row and a NULL scalar.
3. **INCONSISTENT_SOURCE:** no valid user source, and at least one structural issue:
   - a referenced message that does not exist (`*_SOURCE_MESSAGE_MISSING`);
   - a foreign-conversation message (`*_SOURCE_FOREIGN_CONVERSATION`);
   - a link row with a different conversation (`MODERN_LINK_CONVERSATION_MISMATCH`);
   - a stored role that disagrees with the actual role, or is NULL (`STORED_SOURCE_ROLE_MISMATCH` / `_NULL`);
   - an unknown `link_kind`;
   - a scalar without a matching join row (`LEGACY_SCALAR_WITHOUT_MODERN_LINK`).
4. **ASSISTANT_ONLY_OR_UNVERIFIED:** references exist and are structurally consistent, but none is a valid user source (typically all assistant-role).

### Overlap rule
The brief lists a role disagreement both as an "unverified" example and as an "inconsistent" example. This implementation resolves the overlap deterministically: any structural issue → **INCONSISTENT_SOURCE**, which takes precedence over ASSISTANT_ONLY_OR_UNVERIFIED. A reference whose message no longer exists is also INCONSISTENT_SOURCE, not MISSING_SOURCE, because a reference does exist.

### Mixed valid/invalid sources
A memory with ≥ 1 valid user source stays **USER_SUPPORTED**. Its assistant-origin, foreign, missing or role-mismatched references are recorded as `issues` (counted in `user_supported_with_recorded_issues`) and are **never** grounds for quarantine. A memory without a verified user source is never promoted.

### Determinism
- Links are sorted by `(source_message_id, link_kind)`, issues by `(representation, source_message_id, code)`, and output by `memory_id`.
- There are no timestamps, text, similarity or model calls in the decision.

## 6. Future reconciliation procedure (prepared, NOT executed)
Each numbered step needs the approval named in §7.
1. **Snapshot.** Take an approved snapshot: `pg_dump -Fc` of the database, following the backup conventions in `migrations/README.md`.
2. **Verify the snapshot:** `pg_restore -l` lists the TABLE DATA entries, and table row counts match the source.
3. **Restore to an isolated clone.** Restore the snapshot into a clone, e.g. `rag_db_reconcile_<ts>`, and run the **read-only inventory on that clone**: `legacy_provenance_inventory.py --database rag_db_reconcile_<ts> --output inventory_<ts>.json --include-text-hash`. Running directly on `rag_db` requires the protected-database approval.
4. **Review** the counts, then every non-USER_SUPPORTED record, and the USER_SUPPORTED records that carry issues.
5. **Approve.** Obtain explicit written approval of the exact memory IDs and the operation (quarantine marker only). Then build the plan with `build_quarantine_plan(records, approved_ids, approval_ref)`.
6. **Rehearse on the isolated clone only.** Apply the proposed `004` schema and insert the planned marker rows in one transaction. The apply step is not implemented yet and needs its own approved implementation and review.
7. **Compare** the before/after fingerprints: the `conversation_memories` and `memory_sources` fingerprints must be identical, and only the marker table may change. Compare row counts too.
8. **Validate provenance consistency:** re-run the inventory; categories must be unchanged.
9. **Validate deletion behaviour:** the Phase 1 deletion paths (`delete_message_with_provenance`, `delete_memory`, conversation delete) must still succeed and report the same support classification, since the marker has no FK.
10. **Prepare rollback** (`PHASE2_LEGACY_MEMORY_ROLLBACK_PLAN.md`) and rehearse it on the clone.
11. **Production:** separate approval is required before any production operation.

## 7. Production approval gates (none granted)
| Gate | What needs approval |
|---|---|
| G1 | Running the inventory on `rag_db` or on any snapshot/clone of production data |
| G2 | The reviewed classification results and the exact list of memory IDs to quarantine |
| G3 | Implementing the quarantine apply step and the application read-path change (excluding quarantined memories from use), as code review |
| G4 | Applying the `004` schema (as a real migration file) and the plan on an isolated clone (rehearsal) |
| G5 | Rollback rehearsal results |
| G6 | Any production schema change or marker insert |

## 8. Status: implemented vs proposed vs not executed
- **Implemented (code):** the read-only inventory, the deterministic classifier, the quarantine plan builder, the CLI, and the proposed SQL plus its rollback.
- **Proposed (design only):**
  - the quarantine table;
  - the apply step;
  - the application change so quarantined memories are not used for answers or decisions (no read path filters them today);
  - the reconciliation procedure and the rollback procedure.
- **Not executed:** any inventory run, any database query, quarantine, migration, backfill, rehearsal, rollback, or test.
- **Requires separate authorization:** gates G1–G6.

## 9. Remaining limitations
- **No tests yet.** The tooling is untested. Static review and `py_compile` only.
- **Clones are not machine-protected.** The protected-name check covers only `rag_db`, `postgres` and `template*`. A clone of production data with another name is not machine-protected; gate G1 is procedural.
- **Base DDL is not in the repo.** Column choice relies on code and migrations, and on `docs/phase5_audit.md` for `messages.role` and the scalar FK.
- **Role values:** the classifier treats any `role` other than `user` as non-user. Roles other than `user`/`assistant` are reported as `*_NON_USER_NON_ASSISTANT_ROLE`.
- **Quarantine is not yet enforced.** Even after a future apply, retrieval and memory decisions would still use quarantined memories until the separately approved read-path change exists.
- **Source-less memories stay unverifiable.** They cannot be repaired by design (no fabricated provenance). Quarantine or user-driven review are the only options.
