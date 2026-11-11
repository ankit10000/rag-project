# Phase 5 — Deterministic Memory Source Attribution: final report

Status: **PASS** (with the documented limits below).

## What changed
| Stage | Result |
|---|---|
| 1 Audit | `docs/phase5_audit.md` |
| 2 Schema | `docs/phase5_schema_design.md` — evolve `memory_sources` (no second table) |
| 3 Migration | `migrations/003_memory_sources_provenance.sql` (+ `_down.sql`) applied to `rag_db`; 127 memories / 93 links before and after; no memory or message rewritten |
| 4 Creation/update | `memory_storage_service`, `automatic_memory_service`, `memory_service` |
| 5 Deletion/cleanup | `memory_provenance_service.py`; cleanup already consumed `source_message_ids`, now fed from all links |
| 6 Tests | `test_phase5_provenance.py` (25 checks, scratch DB only) |
| 7 Regression | see below |

## Behaviour now
- A memory can have many source user messages. Link kinds: `origin`, `update`, `confirmation`, `legacy`.
- Extraction asks for `source_message_ids` (all contributing user messages); ids are filtered to the batch's user messages. Old single-id shape still parsed.
- `save_memory` / `update_memory` validate **every** source (same conversation, role `user`) before any write, in one transaction; one bad id rejects everything.
- Restatements are linked, not lost: a >=0.90 semantic duplicate or an LLM `DUPLICATE` with a valid memory id adds a `confirmation` link. `DUPLICATE` with no valid id links nothing (no guessing).
- The database itself enforces user-only sources for new rows (role-aware composite FK + CHECK) and refuses to delete a still-linked message.
- Deleting a memory removes its links (cascade); links never delete memories. Forgetting excludes all linked source messages + their positional paired assistant replies + the deletion turn, using links only; echo scan stays a best-effort extra.
- `delete_message_with_provenance` detaches links, deletes the message, and reports `orphaned` / `still_supported` memories; it never deletes a memory.
- Conversation delete cascades cleanly; other conversations are untouched (tested).

## Tests (all against scratch DB `rag_phase5_test`, never `rag_db`)
- Phase 5 suite: 25/25 PASS.
- Regression, all PASS: `test_memory_sources_regression`, `test_deletion_cleanup`, `test_extraction_and_summary_guards`, `test_deleted_facts_regression`, `test_deletion_scenarios`, `test_answer_scoring`, `test_answer_phase3` (69/69), `test_context_and_citations` (62/62), `test_retrieval_phase2`; `test_memory_storage` ran without error.
- Not run on purpose: `test_automatic_memory`, `test_duplicate_memory`, `test_memory_search`, `test_memory_update` (hard-coded conversation ids).
- Live-Gemini Phase 1 evaluation was not re-run (quota); the logic it exercises (cleanup, deletion, extraction guards) is covered by the mocked tests above.
- `rag_db` after all work: still 127 memories, 93 links.

## Known limits
1. 34 legacy memories have no source and cannot be repaired; forgetting them still relies on the echo scan.
2. 4 legacy links point at assistant messages; tolerated (`NOT VALID` CHECK, labelled `legacy`), no new ones possible.
3. If extraction returns no valid id, the last user message of the batch is used as a fallback source (existing behaviour, can over-attribute).
4. A shared source message is excluded when any memory using it is deleted (safe direction; sibling memory loses that context).
5. User→assistant pairing is positional (next message id).
6. Rollback drops `link_kind` / `source_role` labels.
7. `memory_revisions` (text history on update) deferred.
8. Message-delete helper reports orphaned memories but does not delete them.

## Housekeeping
Scratch DBs still present (not dropped without approval): `rag_phase2_*`, `rag_phase35_eval`, `rag_phase5_mig`, `rag_phase5_test`. Phase 3.5 eval dev run finished; its results have not been reviewed yet.
