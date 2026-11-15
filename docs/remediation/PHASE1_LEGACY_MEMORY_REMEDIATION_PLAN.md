# Phase 1 Legacy Memory Remediation Plan

**Status:** Tasks 1, 2, and 3 were implemented under separate user authorization and are documented in `PHASE1_LEGACY_MEMORY_AUDIT.md`. Task 4 has been **implemented (code and documentation) but NOT yet tested**; testing is deferred until the user reviews and approves the implementation. No production data change, migration, threshold change, or dataset change was authorized or performed by those implementations.

This plan prioritizes deletion safety and provenance integrity. It groups the audit findings into four implementation tasks. Tasks 1 and 2 precede any legacy-data cleanup because incorrect provenance can make deletion falsely appear complete. Existing memory and message data must not be backfilled by guesswork.

## Task 1 — Make source and decision ID handling strict and explicit

**Findings:** PH1-D01, PH1-D02, PH1-L01; related to PH1-C02.

**Scope:** `services/memory_service.py`, `services/memory_storage_service.py`, all memory creation entry points including `services/automatic_memory_service.py` and `add_memory.py`, plus deterministic tests. **Decision implemented:** new memories require explicit valid source IDs; missing or invalid provenance is rejected.

**Implementation requirements:**

- Remove last-user fallback for missing or invalid per-memory source IDs.
- Validate source and one-memory decision ID types before conversion. Booleans and fractional numeric values must not become another valid message or memory ID.
- Keep the existing same-conversation and user-role checks after strict type validation.
- Ensure every new memory writer follows the same policy; `add_memory.py` currently bypasses storage and writes a null source directly.
- Do not fabricate provenance for historical source-less memories.

**Acceptance criteria:**

- A missing, malformed, assistant, foreign-conversation, or unknown source cannot be silently recorded as a valid user source.
- A malformed UPDATE/DELETE decision ID cannot be coerced into a different valid candidate memory.
- A valid multi-source fact retains exactly its asserted contributing user IDs.
- New source-less writes either fail clearly or carry an explicit unknown marker that downstream deletion handles safely.
- Existing memory text, embeddings, similarity thresholds, and retrieval defaults are unchanged by this task.

**Required regressions:**

- Multiple user messages where only an earlier message supports the fact; missing-ID JSON; bullet fallback; malformed/bool/float/string source IDs; valid one- and multi-source output; source list with one invalid ID; malformed/bool/float decision IDs against a real candidate; verify no wrong source link or unintended update/delete.
- Preserve checks for rejection of assistant and foreign-conversation source IDs.
- Update the current fallback assertion in `test_extraction_and_summary_guards.py`; replace it with the new source-integrity contract.

**Database testing:** Scratch-only tests with mocked embeddings and LLM calls. No migration or production backfill is part of this task unless separately approved.

## Task 2 — Make deletion cleanup safe for unknown provenance and summary resets

**Status:** Implemented under the approved Task 2 policy. See the Task 2 implementation evidence in `PHASE1_LEGACY_MEMORY_AUDIT.md`.

**Findings:** PH1-D03, PH1-L01, PH1-L03.

**Scope:** `services/memory_cleanup_service.py`, `services/conversation_service.py`, and deletion-flow tests. `services/memory_service.py` was inspected; its summary and extraction input selectors already enforce checkpoint and exclusion filters, so it did not require code changes. The approved policy is explicit: unknown-provenance cleanup is always reported incomplete, and both pipelines are fenced past current history.

**Implementation requirements:**

- Delete a selected source-less memory while returning an explicit incomplete outcome; never report complete cleanup when relevant history could not be identified.
- Clear the summary and advance both summary and automatic-memory extraction checkpoints monotonically to the conversation's current maximum message ID for unknown provenance.
- On known-provenance rewrite or verification failure, clear the summary and fence both pipelines past current history; never reset a checkpoint to zero.
- Preserve source-message exclusion from history, summaries, and extraction for known sources.
- Keep echo scanning supplemental and bounded; it must not be the sole safety mechanism for old or source-less records.
- Pair only the immediately following message by ID if it is an assistant. An intervening user prevents pairing with any later assistant. Excluded rows still count for adjacency.
- Preserve original conversation messages and avoid broad historical exclusion or source invention.

**Acceptance criteria:**

- For known provenance, result status is `COMPLETE`; every recorded source and only its immediate assistant successor (when applicable) are excluded before rebuild, and user-facing output says cleanup completed.
- For unknown provenance, result status is `INCOMPLETE`, the summary is empty, both checkpoints are at least the current maximum message ID, and user-facing output states that historical cleanup is incomplete.
- A post-cleanup summary rebuild and automatic-extraction selection cannot include pre-cleanup messages after unknown cleanup or a failed known-source rewrite/verification.
- Original messages remain stored; unknown-provenance messages are not broadly marked excluded or deleted.

**Required regressions:**

- Source-less memory with failed echo scan; old source outside the 40-message scan; failed rewrite; failed verification; then run summary rebuilding and inspect summary, history, and extraction inputs.
- Known source with all rewrite/verification failure branches; shared source; assistant reply adjacency; consecutive user messages and explicit pairing contract.
- Verify cleanup remains conversation-scoped and preserves unrelated context according to the approved policy.

**Database testing:** Scratch-only integration tests with all LLM calls mocked. Avoid production history inspection; no source backfill is possible without review.

## Task 3 — Reconcile legacy source representations and assistant links

**Status:** Implemented under separate authorization. Focused regression evidence is recorded in `PHASE1_LEGACY_MEMORY_AUDIT.md`; the historical assistant-link quarantine proposal is in `PHASE1_LEGACY_ASSISTANT_PROVENANCE_QUARANTINE_PROPOSAL.md`.

**Findings:** PH1-D04, PH1-L02.

**Scope:** `services/memory_provenance_service.py`, `services/memory_storage_service.py`, migration design and provenance tests. Treat the legacy scalar `source_message_id`, normalized `memory_sources`, and actual `source_role` as related but distinct evidence.

**Implementation requirements:**

- When deleting a message, calculate affected memories from both `memory_sources` and the legacy scalar column.
- Report orphaned versus still-supported memories after considering all remaining source representations.
- Keep the operation atomic; a database failure must roll back link detachment and message deletion together.
- Preserve the meaning of `link_kind='legacy'` as the origin of a backfilled record. Do not relabel an assistant source as a user source.
- A remaining source counts as verified support only when it resolves within the same conversation to an actual user message; modern links must also record `source_role='user'`.
- Design a reviewed quarantine/reconciliation procedure for historical assistant-role links. Any production migration or data edit requires separate approval.

**Acceptance criteria:**

- A memory whose only source is the legacy scalar is reported as orphaned when that message is deleted.
- A memory with another surviving source is reported as still supported.
- Cross-conversation message deletion remains a no-op; current memory-owner checks stay enforced.
- New writes still reject assistant source messages; historical assistant rows are never silently treated as user evidence.
- Migration rehearsal and data changes, if approved later, run on an isolated scratch clone first and have a rollback plan.

**Required regressions:**

- Legacy-column-only source; join-only source; same source in both representations; shared memory with another source; already missing message; foreign conversation; exception during detach/delete and atomic rollback.
- Assistant legacy row is distinguishable by `source_role`, is not accepted as a new user source, and is handled according to the separately approved quarantine policy.

**Database testing:** Yes, entirely on scratch. Do not query, update, migrate, or backfill `rag_db` as part of the implementation without explicit approval.

## Task 4 — Set contracts for normalization, candidate coverage, and extraction checkpointing

**Findings:** PH1-C01, PH1-C02.

**Scope:** First add characterization tests and document decisions. Change code only where an approved contract shows a defect. Candidate window and normalization changes may alter memory semantics, so they should not be bundled into a deletion-safety fix without approval.

**Implementation requirements:**

- Define whether normalization means trimming only or canonicalizing internal whitespace/case/punctuation. Keep embedding input equal to the text that is persisted.
- Decide whether automatic conflict/update detection must consider memories older than the latest 20.
- Distinguish a successful empty extraction from malformed/unparseable extractor output before advancing the checkpoint.

**Acceptance criteria:**

- Tests pin the selected normalization contract, including punctuation, casing, repeated whitespace, and blank text.
- Candidate recall behavior for a matching memory older than 20 entries is explicitly accepted or changed with a test.
- A malformed extraction result cannot be silently treated as a confirmed empty result if the approved contract requires retry; valid empty output remains a safe no-op.
- No ranking, retrieval defaults, or unrelated memory-decision behavior changes without explicit approval.

**Required regressions:**

- Verify stored text equals the text used for embeddings under the chosen normalization.
- Seed more than 20 memories and place a conflicting target outside the candidate window.
- Compare valid `[]`, malformed JSON with no bullets, valid JSON without IDs, and bullet fallback; assert checkpoint outcome per policy.

**Database testing:** Pure parsing/normalization cases need no database. Candidate-window and checkpoint behavior should use scratch-only fixtures and mocked embeddings/LLM responses.

**Implementation status (2026-11-15): implemented, NOT tested.** The approved contracts:
1. **Normalization is trim-only.**
   - `normalize_memory_text()` returns `text.strip()`; casing, punctuation and internal whitespace are preserved; blank or non-text input is rejected.
   - It is shared by `save_memory`, `update_memory`, `process_memory` (new text and the UPDATE text) and the extraction parser.
   - The persisted text equals the embedding input.
2. **Candidate coverage stays the latest 20.**
   - The window is kept as `AUTOMATIC_CANDIDATE_WINDOW = 20`, with no fallback scan and no ranking or threshold change.
   - Memories older than the window are explicitly not considered for automatic UPDATE.
3. **Extraction has three outcomes:**
   - success with records;
   - success with no memories: exact `NONE`, JSON `[]`, or no user messages;
   - typed failure: `MemoryExtractionError` / `InvalidMemoryProvenanceError`.

   A malformed or ambiguous response is never `[]`. A whole-batch, read-only source check runs before the first write. `main.py` advances the checkpoint only on a normal return.

Full evidence, files and limitations are in `PHASE1_LEGACY_MEMORY_AUDIT.md` (section "Task 4 implementation evidence"). The acceptance criteria and required regressions above remain **open** until the deferred tests are approved and run.

## Recommended sequence and review gates

1. Tasks 1 and 2 are implemented and verified; see `PHASE1_LEGACY_MEMORY_AUDIT.md`. Neither changed historical records.
2. Task 3 is implemented and verified with scratch regressions. Separately review the read-only assistant-source inventory and quarantine proposal before any production inventory, quarantine, or migration is authorized.
3. Task 4: contracts decided by the user (trim-only, latest-20 kept, explicit extraction outcomes) and implemented; testing is deferred until the user approves the implementation.
4. After any future task is separately authorized and reviewed, run only its targeted tests through `testsafe`; preserve an unchanged `rag_db` fingerprint and keep API/model access blocked for deterministic regressions.

## Current audit evidence and boundaries

The original read-only audit ran five focused tests — **5 passed, 0 failed**. Task 1, Task 2, and Task 3 implementation test results and database evidence are recorded in `PHASE1_LEGACY_MEMORY_AUDIT.md`. No production memory inventory was queried, and no Gemini/API call was made.

**Phase 2 reference:** historical-record reconciliation (read-only inventory, deterministic classification, quarantine design, rollback plan) is prepared — implemented as tooling, not executed or tested — in `PHASE2_LEGACY_MEMORY_RECONCILIATION.md`, `PHASE2_LEGACY_MEMORY_QUARANTINE_DESIGN.md` and `PHASE2_LEGACY_MEMORY_ROLLBACK_PLAN.md`.

Tasks 1, 2, and 3 were implemented with separate authorization and their evidence is linked above. Task 4 was implemented with separate authorization but has **not been tested** (deferred by instruction). No schema changes, production data repair, retrieval/ranking changes, or full test run occurred.
