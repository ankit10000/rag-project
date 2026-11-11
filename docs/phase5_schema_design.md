# Phase 5 — Stage 2: provenance schema design

Decisions taken (you did not answer the five Stage 1 questions, so the audit's recommendations were used):
1. Evolve the existing `memory_sources` table; no second table. The repository already uses composite `(conversation_id, id)` keys, which give database-level ownership; the handoff's `memory_sources(id, memory_id, message_id)` sketch would be weaker. Names follow existing conventions (`source_message_id`, `memory_id`).
2. Enforce "user messages only" in the database.
3. The 4 assistant-sourced legacy links are kept and labelled `legacy`; new rows cannot be assistant messages.
4. Shared-source policy unchanged and safe: deleting a memory excludes all its source messages even if another memory also uses one (it is documented, tested, and never leaves a forgotten fact in context).
5. `memory_revisions` (update text history) is deferred: it is not needed for deterministic deletion.

## Final table

```
memory_sources
  conversation_id    uuid        NOT NULL
  memory_id          bigint      NOT NULL
  source_message_id  bigint      NOT NULL
  created_at         timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP
  link_kind          text        NOT NULL DEFAULT 'origin'   CHECK IN (origin, update, confirmation, legacy)
  source_role        varchar(20) NOT NULL DEFAULT 'user'     CHECK = 'user'  (NOT VALID: legacy rows tolerated)
  PRIMARY KEY (memory_id, source_message_id)                 -- blocks duplicate links
  FOREIGN KEY (conversation_id, memory_id)                       -> conversation_memories(conversation_id, id) ON DELETE CASCADE
  FOREIGN KEY (conversation_id, source_message_id, source_role)  -> messages(conversation_id, id, role)       NO ACTION
INDEX memory_sources_message_idx (conversation_id, source_message_id)   -- message -> memories
UNIQUE INDEX messages_conversation_id_id_role_uq (conversation_id, id, role)
```

## Delete behaviour (and why)
- Memory deleted → its links go (CASCADE). A link row can never delete a memory: no FK points from `conversation_memories` to `memory_sources`.
- Message deleted directly → refused by the FK (NO ACTION) while links exist. Messages must be removed through the new provenance function, which detaches links and reports which memories lost evidence. Previously the link rows vanished silently.
- Conversation deleted → memories, messages and links disappear in the same statement; NO ACTION is checked at statement end, so this still works (verified in tests). Memories of other conversations are untouched because every key includes `conversation_id`.
- Legacy `conversation_memories.source_message_id` keeps `ON DELETE SET NULL`; it is never read for new decisions except as a fallback union in `get_memory_details`.

## Files
`migrations/003_memory_sources_provenance.sql` (idempotent, one transaction) and `migrations/003_memory_sources_provenance_down.sql`.

## Legacy-data strategy
- Existing links (all from the legacy backfill) are labelled `legacy` and get their message's real `source_role`.
- The 4 assistant-sourced links stay (labelled `legacy`, `source_role='assistant'`); the CHECK is `NOT VALID`, so they are tolerated while any new assistant link is rejected.
- The 34 memories with no source stay valid with zero links; no provenance is invented for them.
- Nothing is deleted or rewritten in `conversation_memories` or `messages`.

## Application behaviour changes (Stages 4-5)
- Extraction may return several contributing user message ids per memory (validated against the batch's user ids); `source_message_id` stays as the primary id for compatibility.
- `save_memory` / `update_memory` accept `source_message_ids` (list) as well as `source_message_id`; all ids are validated (same conversation, role `user`) before any write, and all writes share one transaction.
- A restating message (LLM `DUPLICATE` with a valid memory id, or a ≥0.90 semantic duplicate) is linked to the existing memory with `link_kind='confirmation'`. A `DUPLICATE` without a valid memory id is not linked (no guessing).
- New `services/memory_provenance_service.py`: `get_memory_sources`, `get_memories_for_message`, `detach_message` / `delete_message_with_provenance` (never deletes a memory automatically; returns memories that lost all evidence).

## Risks
See `docs/phase5_audit.md` §7. Additional: the role-aware FK means old application code inserting an assistant id now fails loudly instead of silently succeeding (intended).
