# Phase 3 — Conversational Memory Intelligence

**Status (2026-11-15):** implemented as application code. **NOT tested**: testing is disabled by user instruction. Only static review and `py_compile` were done.
- No database was accessed and no historical record was changed.
- No migration, backfill or quarantine was executed. The schema proposal below is not applied.

## 1. Architecture and data flow
```
user message ──► main.py
  ├─ answer context:  memory_context_service.assemble_memory_context()
  │     search_memories (existing vector search, same conversation, thr 0.35, top_k 5)
  │     → future-quarantine exclusion hook (exclude_memory_ids)
  │     → provenance filter (Phase 2 pure classifier: USER_SUPPORTED only)
  │     → deterministic category (memory_classification_service)
  │     → bounded, grouped text  +  internal metadata (ids, source ids)
  │     ──► rag_service.ask_question(memory_summary = summary + memory context)
  └─ extraction (every N messages, unchanged checkpointing):
        memory_service.extract_and_save_memories()          [Phase 1 contract]
          → automatic_memory_service.process_memory()
               exact-duplicate pre-check  (memory_consolidation_service)
               → decide_memory_action (LLM: NEW/DUPLICATE/UPDATE/UNCERTAIN)
               → detail-preserving DUPLICATE guard
               → conservative UPDATE guard (analyze_relation, detail check)
               → memory_storage_service.save_memory / update_memory / confirm_memory
                    (semantic-duplicate check now also requires preserved details)
```

New modules:
| Module | Purity | Responsibility |
|---|---|---|
| `services/memory_classification_service.py` | pure | category model, deterministic classifier, temporary-statement detector |
| `services/memory_consolidation_service.py` | pure | duplicate key, material-detail extraction, memory comparison, relation (conflict) analysis |
| `services/memory_context_service.py` | read-only DB | relevance, provenance filtering, categorized bounded context |

Document retrieval (vector, BM25, RRF, reranker, answer generation, citations) is untouched and stays separate from memory retrieval.

## 2. Memory category model (Work Area A)
- **Categories:** `profile`, `preferences`, `goals`, `projects`, `skills`, `relationships`, `routines`, `other`.
- **Classification:** `classify_memory_text()` uses ordered word-boundary phrase rules. Precedence: relationships → routines → goals → preferences → projects → skills → profile, otherwise `other`. It is deterministic: no model and no similarity.
- **Not persisted:** the schema has no category column. Categories are computed at runtime. A persistence proposal is in §9.

**Extraction.** The JSON format and the whole Phase 1 contract are unchanged: explicit source IDs, batch validation, `[]`/`NONE`, typed errors and checkpointing. The prompt now also tells the model to:
- extract only facts useful in future conversations, one fact per memory, and skip temporary states and one-off details;
- never infer sensitive attributes;
- keep numbers, amounts, dates, versions and status words exactly;
- never treat assistant suggestions as user facts.

Assistant messages were already never shown to the extractor (Phase 1).

## 3. Deduplication and consolidation (Work Area B)
- **Exact duplicates (new).** `duplicate_key` = casefold, collapse whitespace, drop trailing `.!?`. It is used for **comparison only**: it is never stored or embedded, so the Phase 1 trim-only normalization contract is unchanged.
  - An exact restatement of a candidate is linked as a `confirmation` source of the existing memory, without a model call, and nothing is saved.
- **Material details.** `material_details()` extracts numbers, amounts, %, times, ISO dates, years and versions.
- **LLM DUPLICATE guard.** If the new statement has a material detail that the chosen existing memory lacks, it is **not** discarded. It is stored as its own memory with its own sources.
- **Storage semantic-duplicate guard (`save_memory`).** Similarity ≥ 0.90 (threshold unchanged) still skips a restatement, **unless** the new text has details the nearest memory lacks, in which case it is stored.
- **What is never done:** memories are never merged across conversations. All candidates and the storage nearest-neighbour query are conversation-scoped. No memory is deleted or rewritten by deduplication. Where merging could lose information, both facts are kept.

## 4. Update detection (Work Area C)
- **Decisions:** NEW / DUPLICATE / UPDATE / UNCERTAIN from the decision model. Its prompt now states that UPDATE needs a clearly stated change, that a temporary state or a different time period is not an update, that a bare contradiction is NEW (both kept), and that the replacement must keep every detail of the new statement.
- **Code guard before any replacement:** `analyze_relation(existing, new)` gives the evidence (§5). The replacement is applied **only if** the relation is not `TEMPORARY_STATE` or `TIME_DEPENDENT` **and** the replacement keeps all material details of the new statement. Otherwise the existing memory is left unchanged and the new statement is stored separately.
- **Provenance:**
  - `update_memory` still appends the updating message as an `update` link and keeps all previous links.
  - A separately stored statement carries only its own validated sources.
  - Confirmations add `confirmation` links.
- **Candidate window:** unchanged, the latest 20 (`AUTOMATIC_CANDIDATE_WINDOW`).

## 5. Conflict resolution (Work Area D)
`analyze_relation()` returns one of the following. Precedence is top to bottom, and the result is logged for every UPDATE as `Update relation evidence: …`, which makes it auditable.

| Relation | Meaning | Effect on an UPDATE decision |
|---|---|---|
| `TEMPORARY_STATE` | new text is a short-lived state ("today", "right now", …) | not applied; stored separately |
| `EXPLICIT_UPDATE` | new text states a change ("no longer", "switched to", "now works", …) | allowed (detail check still applies) |
| `TIME_DEPENDENT` | both statements carry different years/dates, so both may be true | not applied; stored separately |
| `DETAIL_CHANGE` | material details differ | allowed (detail check still applies) |
| `UNRESOLVED` | no deterministic evidence | the model's judgement stands (prompt requires a clearly stated change) |

- **Newer is not automatically correct:** a bare contradiction is NEW (both kept), not an overwrite.
- **Assistant text is excluded:** it is never part of the evidence, because the extractor only sees user messages.
- **No new numeric confidence thresholds** were introduced.
- **Not deleted:** old facts are never deleted by conflict handling.
- **Why kept facts are stored as separate memories:** the decision UNCERTAIN already exists and still makes extraction raise (Phase 1). Contradictions are therefore steered to NEW, which retains both, rather than UNCERTAIN, which would block the checkpoint forever.

## 6. Relevance and context assembly (Work Areas E, F)
`assemble_memory_context(conversation_id, query, top_k=5, exclude_memory_ids=None, …)`:
1. **Candidates:** the existing `search_memories` (same conversation, threshold 0.35, top_k 5, as before), so no new ranking or threshold.
2. **Exclusions:** IDs in `exclude_memory_ids` are dropped. This is the **future quarantine integration point**; nothing is passed today because no quarantine status exists.
3. **Provenance:** only memories classified `USER_SUPPORTED` by the Phase 2 pure classifier are used. Unsupported, assistant-only, source-less or inconsistent memories are excluded, and their IDs are returned in `excluded.unverified_provenance`. The read uses messages joined by id, so foreign-conversation references do not count as support.
4. **Organisation:** grouped in a fixed category order, newest first within a group, under a header telling the model to ask the user when facts disagree.
5. **Output:**
   - `text` contains the memory sentences only, with no IDs;
   - `memories` holds internal metadata (ids, category, similarity, valid user source ids) for debugging and future citations;
   - `excluded` lists what was left out.

`main.py` now uses this block in place of the raw search list. The conversation summary is still prepended unchanged. The answer prompt still treats memory as context, never as document evidence.

## 7. Lifecycle and deletion integration (Work Area G)
| State | How it is represented today |
|---|---|
| Active | a row in `conversation_memories` |
| Updated | same row, new text and embedding, plus an `update` link (old links kept) |
| Duplicate | no new row; a `confirmation` link on the existing memory |
| Uncertain | the decision UNCERTAIN; extraction raises and the checkpoint is not advanced (Phase 1) |
| Deleted | row removed through the existing ownership-checked deletion paths |
| Excluded source messages | Phase 1 context exclusion and checkpoint fencing (unchanged) |
| Unsupported historical | kept in the DB, **excluded from answer context** (new) |
| Quarantined (future) | hook `exclude_memory_ids`; no schema assumed |

- **Deletion paths and checkpoints:** unchanged (`delete_matching_memories`, `delete_memory`, `delete_message_with_provenance`, cleanup and summary rewrite).
- **No reappearance:** a deleted memory cannot reappear in the context because it no longer exists. Summary safety is the Phase 1 mechanism.
- **Lost support:** a memory whose only user source was deleted is classified non-supported and therefore dropped from context.

## 8. Provenance and safety summary
- **Phase 1 rules kept:** explicit, batch-validated, same-conversation user sources, and no fallback attribution.
- **No guessing:** nothing infers provenance, and no candidate crosses a conversation.
- **Read-only role checks:** user-role validation reuses the Phase 2 classifier, which is not modified; the context service reads facts only.

## 9. Schema limitations and migration proposals (not applied)
- **No category column.** Proposal: `docs/remediation/proposals/005_memory_category.sql.proposed` adds a nullable `category` with a CHECK, no backfill. Rollback: `005_memory_category_down.sql.proposed`. Affected table: `conversation_memories`. Kept outside `migrations/`.
- **No status column** (uncertain/conflicted/superseded): there is no persisted "held for review" state, so conflicts are kept as separate memories. A lifecycle-status column is a possible future proposal and was not drafted, to avoid inventing a model before a decision.
- **Quarantine:** the Phase 2 proposal `004` is still not applied. Context integration exists only as a hook.

## 10. Files
- **New:**
  - `services/memory_classification_service.py`
  - `services/memory_consolidation_service.py`
  - `services/memory_context_service.py`
  - `docs/remediation/proposals/005_memory_category.sql.proposed`
  - `docs/remediation/proposals/005_memory_category_down.sql.proposed`
  - `test_p3_memory_intelligence.py` (**written, not executed**; registered under `unit` in `run_tests.py`)
  - this document
- **Modified:**
  - `services/automatic_memory_service.py`: exact-duplicate pre-check, DUPLICATE and UPDATE guards, `_save_new_retaining_existing`
  - `services/memory_storage_service.py`: detail check in the semantic-duplicate skip
  - `services/memory_service.py`: extraction prompt rules only
  - `services/memory_decision_service.py`: decision prompt rules only
  - `main.py`: uses `assemble_memory_context`
  - `run_tests.py`: registration

## 11. Unresolved assumptions and limitations
- **Heuristics:** category rules, temporary markers, change markers and material details are deterministic phrase heuristics. They can misclassify; for example, "today I started a new job" counts as temporary, so it is stored separately rather than replacing the old job.
- **Duplicate-looking separate facts:** keeping both facts can leave near-duplicate or contradictory memories. They are shown newest first with an instruction to ask the user. There is no automatic pairwise conflict flag, because a deterministic one without new thresholds would produce false flags.
- **Confirmation link edge case:** when a statement is stored separately and its embedding is ≥ 0.90 similar to an existing memory with the same details, `save_memory` still links it as confirmation instead of inserting (existing behaviour).
- **Behaviour changes that existing tests may not expect:**
  - exact duplicates no longer call the decision model;
  - some model DUPLICATE/UPDATE decisions now become separate saves;
  - the `save_memory` semantic skip now requires preserved details;
  - main.py's memory context is now provenance-filtered and categorized.

  These are unverified until tests are allowed.
- **Extra read per turn:** the context service makes one extra read-only query pair per answer.
- **Pending approvals:** categories and quarantine are not persisted, and each needs schema approval.

**TESTING NOT RUN — testing remains strictly disabled by user instruction. No tests, smoke checks, integration checks, or evaluation scripts were executed. Only static review and optional syntax compilation were performed.**
