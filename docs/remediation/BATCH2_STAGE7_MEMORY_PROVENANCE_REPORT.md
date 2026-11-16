# Batch 2, Stage 7: Deterministic Memory Source Attribution & Deletion Integrity

**Date:** 2026-11-16. **Scope:** memory provenance only.
**Not done:**
- No migration. Proposal 004 is still unapplied.
- No change to retrieval, answer generation, grounding, providers or evaluation assets.
- Nothing committed, staged or pushed.

**Approved decisions (user, after the Phase A audit):**
1. Orphaned memories: keep them stored, classified `MISSING_SOURCE`, never in answer context.
2. Paired assistant replies: existing behaviour (not deleted, not additionally excluded).
3. `update_memory()` requires at least one valid source.
4. Extraction batch atomicity: document only.

## 1. Preflight and Git state

| Item | Value |
|---|---|
| Branch / HEAD | `main` at `09e6007`; `origin/main` = `09e6007` (fetched). Reflog: no commit since the clone |
| At Stage 7 start | Nothing staged. Unstaged: the Stage 5 H.1 and Stage 6 changes. Untracked: H.1, Stage 6 files and `.vscode/` |
| During Stage 7 | That earlier work was **staged by someone other than this agent**: 26 files, including `.vscode/settings.json`. Stage 7 ran no `git add`, apart from a path-limited `git add -N` / `git reset` of its own new test file for `git diff --check`. Stage 7's own changes are all **unstaged** (5 modified files + 1 new test). `run_tests.py` is `MM`: the staged Stage 6 registration plus one unstaged Stage 7 line |
| Database for tests | `rag_test_scratch`. `run_tests.py` sets it; `testsafe` refuses any other name; every probe checked `current_database()` first and refused anything else |
| `rag_db` | Only read (`run_tests.fingerprint`, a read-only transaction); unchanged (see 11) |

**Live schema verification** (before any change, `rag_test_scratch`, read from `pg_constraint`, `pg_indexes` and `information_schema`). It **matches migrations 000–003 exactly**:
- `memory_sources` columns: `conversation_id`, `memory_id`, `source_message_id`, `created_at`, `link_kind` (default `origin`), `source_role` (default `user`), all NOT NULL.
- Primary key `(memory_id, source_message_id)`.
- `memory_sources_memory_fk` → `conversation_memories(conversation_id, id)`, ON DELETE CASCADE.
- `memory_sources_message_fk` → `messages(conversation_id, id, role)`, no action, DEFERRABLE INITIALLY DEFERRED.
- `memory_sources_link_kind_ck`.
- `memory_sources_user_source_ck`: `NOT VALID`, as 003 intends.
- Index `memory_sources_message_idx`, plus the unique indexes `(conversation_id, id)` and `(conversation_id, id, role)` on messages and memories.
- `conversation_memories.source_message_id` → `messages(id)`, ON DELETE SET NULL.
- No `memory_provenance_quarantine` table.

No discrepancy.

## 2. Existing memory architecture (audited)

| Lifecycle step | Where | Behaviour |
|---|---|---|
| Message creation | `conversation_service.save_message` | Plain insert |
| Extraction | `main.run_turn` → `memory_service.extract_and_save_memories` (every `MEMORY_EXTRACTION_THRESHOLD=4` messages) | The LLM returns `source_message_ids`. Every id must be a user message **in the batch**, and the whole batch is checked in the database (user messages of this conversation) **before the first write**. No fallback attribution (the deprecated `source_message_id` argument is never used) |
| Creation | `memory_storage_service.save_memory` | All sources validated (user role, same conversation) inside the write transaction. A semantic duplicate gets `confirmation` links instead of a new row. Links are inserted with `ON CONFLICT DO NOTHING` |
| Update | `automatic_memory_service.process_memory` → `update_memory` | Old links kept; new sources appended as `update`; content + embedding + links in one transaction |
| Attribution store | `memory_sources` (+ legacy scalar `conversation_memories.source_message_id`) | Composite, conversation-scoped, role-aware foreign keys |
| Explicit deletion | `main.run_turn` → `delete_matching_memories` → `delete_memory` → `apply_deletion_cleanup` | The classifier's ids are validated against this conversation's memories. The sources come from `memory_sources` (`get_memory_details`). The recorded sources, their immediately paired assistant replies and the deletion-turn messages are excluded deterministically. The LLM echo scan only adds to that. Unknown provenance → summary cleared and checkpoints fenced (`INCOMPLETE`) |
| Message deletion | `memory_provenance_service.delete_message_with_provenance` | One transaction: detach both link representations, delete the message, report `orphaned` / `still_supported`; **never deletes a memory**. **No production caller:** neither the CLI nor the API exposes message deletion |
| Conversation deletion | Database cascade only | Not exposed in the CLI or API |
| Context use | `memory_context_service.assemble_memory_context` | Only memories classified `USER_SUPPORTED` by the pure classifier (`legacy_provenance_classifier`) reach answer context |

## 3. Root cause and demonstrated defects

The audit found that provenance was **already deterministic** (Phases 1, 2 and 5). It also found two narrow defects, each **reproduced on `rag_test_scratch` before the fix** (probe outside the repository, own conversation, deleted afterwards):

| # | Defect | Reproduction (before) |
|---|---|---|
| D1 | `delete_message_with_provenance` coerced the id with `int(message_id)`. A float, bool or other bad id could be truncated into **another** message's id | `delete_message_with_provenance(cid, 2285 + 0.7)` → `deleted=True`, **message 2285 removed** |
| D2 | `update_memory()` accepted **zero** sources: the content changed with no evidence recorded | `update_memory(cid, mid, "User likes green tea.")` → `True`, text changed, links unchanged |

Gaps recorded without a fix (approved: document only, or outside scope):
- **Extraction batch atomicity.** Items are written one by one. If item *k* is `UNCERTAIN`, items before *k* are already stored, while the checkpoint is not advanced. The retry is safe: re-processing restatements adds `confirmation` links, and existing pairs are skipped. But the batch is not all-or-nothing.
- Message and conversation deletion have no user-facing entry point.

## 4. Schema and migration proposal

**No migration is proposed or applied.** The existing schema already represents:
- multiple sources (primary key);
- roles (`source_role` + the role-aware foreign key);
- conversation ownership (composite foreign keys);
- referential integrity (cascade from the memory; a non-cascading, deferred check from the message, so a linked message cannot disappear silently);
- duplicate prevention (primary key + `ON CONFLICT`);
- legacy rows (`link_kind='legacy'`, `NOT VALID` user check).

Proposal 004 (quarantine table) remains **unapplied**, as approved. The latest migration is still `003`.

## 5. Implemented changes

| File | Change | Status |
|---|---|---|
| `services/memory_provenance_service.py` | The message id is validated with the existing `normalize_positive_id` (memory-id delete contract: positive int or numeric string; no bool, no float). An invalid id returns the existing no-op shape `{"deleted": False, "orphaned": [], "still_supported": []}` **before any SQL**. Fixes D1 | Implemented, tested, mutation-checked |
| `services/memory_storage_service.py` | `update_memory` calls `normalize_source_ids(..., required=True)`: a missing source raises `ValueError` before any embedding or SQL, the same rule as `save_memory`. Fixes D2 | Implemented, tested, mutation-checked |
| `test_p1_memory_update_delete_integration.py` [u2] | The check that asserted the D2 behaviour ("no source: update True, text changed") now asserts the approved contract: `ValueError`, text, scalar and links unchanged | Approved contract change |
| `test_memory_sources_regression.py` [7] | The wrong-conversation update check now passes the other conversation's own valid user message (`foreign`). It still tests the ownership refusal (`False`, links unchanged), which previously relied on having no source | Intent kept |
| `test_stage7_memory_provenance.py` (new, integration, 42 checks) | Focused Stage 7 tests (see 9) | New |
| `run_tests.py` | Registers the new test (integration) | Registry |

**Not changed:**
- the deletion semantics, pairing, orphan handling, extraction contract and decision contract;
- `answer_service.py`, `grounding_service.py`, retrieval, the provider and the evaluation assets.

**Known unchanged caller:** `test_memory_update.py` is a registered **manual** legacy script (hard-coded conversation id, never run by the runner) that calls `update_memory` without a source. Under the approved contract it would now raise `ValueError`. Left unchanged and listed here.

## 6. Creation and update behaviour (tested)

**Creation:**
- One or more sources are linked as `origin`.
- Duplicate ids (including the integral-float form of the same id) collapse to one link.
- Rejected with nothing written: an assistant source, another conversation's message, an unknown id, a bool, a fractional float, zero, `None`, or an empty list.

**Update:**
- Earlier links are kept and new sources are added as `update`.
- Repeating sources creates no duplicate.
- Rejected with `ValueError`, changing neither content nor provenance: no source, an assistant source, or a foreign source.
- A failure **after** the `UPDATE` statement (link insert forced to fail) rolls back content **and** provenance together.

## 7. Deletion and cleanup behaviour (tested)

**Message deletion (`delete_message_with_provenance`):**
- Invalid ids are refused with the no-op shape and nothing is deleted: `True`, `id + 0.7`, `float(id)`, `0`, a negative id, `"abc"`, `None`, `[id]`.
- A numeric-string id is still accepted.
- Another conversation's message: no-op.
- Deleting one of several sources: the memory stays `still_supported`.
- Deleting a source shared by two memories: one memory still supported, the other `orphaned`. **Both are kept** (policy a); only that source's links are removed.
- Repeated deletion: idempotent no-op.

**Pairing (existing contract):** deleting a user message leaves its immediately following assistant reply in place, and it is not excluded. Explicit memory deletion still excludes source + paired reply, through the provenance-driven cleanup.

**Explicit deletion:** classifier ids that are a bool, a string, another conversation's memory or unknown delete nothing (`NO_MATCH`). The other conversation's memory and its links are untouched.

## 8. Legacy memory policy (tested; conservative, no backfill)

| Case | Classification | Context | Deleted? |
|---|---|---|---|
| Orphaned by message deletion (no links, scalar nulled) | `MISSING_SOURCE` | **Excluded** | No (policy a) |
| No source rows, NULL scalar | `MISSING_SOURCE` | Excluded | No |
| Partial: valid user link + assistant legacy scalar | `USER_SUPPORTED`, issue recorded | Allowed (it has a verified user source) | No |
| Stale: legacy scalar pointing into another conversation | `INCONSISTENT_SOURCE` | Excluded | No |
| A user message with the identical text appears later | Not linked (no guessed backfill) | Unchanged | No |

- Historical attribution is never reconstructed from text, similarity or echoes.
- Unknown-provenance memories stay stored and unused until an approved policy (e.g. proposal 004) exists.

## 9. Test results

**Command:** `.venv/bin/python run_tests.py test_stage7_memory_provenance.py` (`rag_test_scratch`) → **PASS, 42/42 checks**. Covers:

| Area | Checks |
|---|---|
| Creation | One and multiple sources, duplicate ids, invalid id (bool, float, zero, None, empty, unknown), wrong conversation, wrong role |
| Updates | Preserve, add, no duplicate, no source / assistant / foreign source refused, rollback of content + provenance |
| Message deletion | One of several sources, final source, shared source, paired reply, repeated deletion, cross-conversation, 8 invalid id forms |
| Orphan | `MISSING_SOURCE` + excluded from `assemble_memory_context` |
| Legacy | No rows, partial, stale foreign reference, no backfill |
| Explicit delete | Invalid decision ids, cross-conversation isolation, source + paired reply exclusion |
| Checkpoint (`main.run_turn`, real DB, only the LLM mocked) | Assistant-sourced extraction → `rejected_will_retry`, checkpoint stays 0, no memory. Valid extraction → `checkpoint_advanced` to the last batch message id, linked to the user source |
| Cleanup | No test conversations left |

**Mutation check** (fix reverted in place, then restored; source diff verified afterwards):
- D1 reverted → **8 FAIL**.
- D2 reverted → **3 FAIL** (no-source refusal, unchanged state, rollback).

**Directly affected existing tests:** baseline before the change 11/12, after the change **12/13 including the new test**. These pass:
- `test_phase5_provenance`, `test_p1_task1_strict_attribution`, `test_p1_task2_safe_deletion`, `test_p1_task3_provenance_reconcile`;
- `test_memory_sources_regression`, `test_deletion_cleanup`, `test_extraction_and_summary_guards`, `test_p1_d7_storage_id_validation`;
- `test_p1_memory_update_delete_integration`, `test_p3_memory_intelligence`, `test_p1_d5_delete_ids`.

`test_p1_process_memory` fails, pre-existing (see 10).

## 10. Regression results

| Run | Run / passed / failed | Notes |
|---|---|---|
| `run_tests.py` (unit + integration) after Stage 7 | **48 / 46 / 2** (18 live/manual not run) | Stage 6 end: 47 / 45 / 2; +1 = the new test |

**Pre-existing failures, re-verified at an untouched HEAD checkout** (temporary `git worktree`, removed afterwards). The failed checks and errors are **identical** to HEAD:
- `test_p1_process_memory.py`: `[5] whitespace-only memory -> SKIPPED, no row` (`AttributeError: 'NoneType' object has no attribute 'kwargs'`).
- `test_p1_delete_routing.py`: `[N2] memory_summary composition` (×2) and `[N3] 4 messages -> extraction with last id as source`.

Not fixed (no approval to change memory code beyond Stage 7).

**Stage 4/5/6 suites:** all pass in the full run, including `test_stage5_retrieval` and `_integration`, `test_stage6_answer` and `_integration`, and the Stage 4 ingestion tests.

## 11. Database safety evidence

| Item | Evidence |
|---|---|
| `rag_db` | Fingerprint (row count + md5 per table) identical to the one taken before H.1; `run_tests` reported "unchanged" on every run |
| Scratch target | `current_database()` = `rag_test_scratch` checked before the schema query and in the defect probe; `testsafe` guards every test |
| Writes performed | `rag_test_scratch` only: probe and test conversations, messages, memories, links; all deleted |
| Residue | After all runs: conversations 0, messages 0, memories 0, links 0, chunks 0 |
| Proposal 004 | `memory_provenance_quarantine` absent in `rag_test_scratch` and `rag_db` |
| Frozen assets | `eval/phase35/results/*`, the H.1 artifacts and `.vscode/settings.json` are SHA-256 identical to the pre-live-run record; migrations, `eval/phase35`, `eval/framework` and proposals are unchanged vs HEAD |
| Stage 5/6 code | No unstaged change to `grounding_service.py`, `answer_service.py`, `rag_service.py`, `main.py`, retrieval services |
| Hygiene | `git diff --check` clean (including the new file); secret-pattern scan clean |

## 12. Remaining limitations

**Implemented and tested:** D1 and D2 fixes; orphan classification and context exclusion; legacy conservatism; checkpoint behaviour both ways.

**Documented, not changed (approved):**
- Extraction batches are not atomic (see 3). Retries are safe but not all-or-nothing.
- Orphaned and unknown-provenance memories stay stored indefinitely; storage is never reclaimed without a policy.

**Requires further approval:**
- Proposal 004 (quarantine markers).
- A user-facing message or conversation deletion entry point. Today `delete_message_with_provenance` is reachable only from tests.
- The two pre-existing memory test failures.

**Observations:**
- `delete_message_with_provenance` still raises `ValueError` for an invalid **conversation** id (UUID parse), before any SQL. That is unchanged and safe.
- `test_memory_update.py` (manual) would raise under the new `update_memory` contract.

## 13. Final status

**PASS.**
- **Provenance is deterministic:** every write path validates user-role, same-conversation sources before writing, with no fallback attribution.
- **Creation and updates keep every valid source relationship.** An update can no longer change content without a source (D2 fixed).
- **Deletion uses explicit provenance:** link rows, and the legacy scalar where links are absent. Invalid ids can no longer reach the wrong message (D1 fixed).
- **Cross-conversation isolation is verified, and legacy memories are handled conservatively,** with no guessed backfill and orphans kept but unused.
- **All focused tests pass,** with no new unexplained regression (the 2 failures are identical at HEAD).
- **`rag_db` is unchanged.**

Not committed, staged or pushed.
