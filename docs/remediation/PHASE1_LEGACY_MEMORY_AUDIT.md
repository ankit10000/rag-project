# Phase 1 Legacy Memory Integrity Audit

**Status:** The original audit was read-only. Subsequent approved Task 1, Task 2, and Task 3 implementations resolve PH1-D01, PH1-D02, PH1-D03's checkpoint-reprocessing path, and PH1-D04's dual-representation deletion accounting; PH1-L01 has an explicit incomplete-cleanup policy, PH1-L03's adjacency rule is defined, and PH1-L02's assistant-role distinction is preserved. Evidence is appended below. No historical production data, schema, dataset, retrieval configuration, or evaluation result was changed. Task 4 (PH1-C01, PH1-C02) was subsequently implemented as contract code and documentation; it is **implemented but not yet tested** (see the Task 4 section at the end). The full suite was not run.

## Scope and evidence

The audit traced extraction, memory writes and updates, conversation-scoped search, explicit deletion, provenance cleanup, message deletion, summary rewrite, and the related migrations. It distinguishes code facts from historical production-database observations. No application records were queried directly; database safety evidence comes only from the existing read-only `rag_db` fingerprint helper.

The selected integration tests used `rag_test_scratch` through `testsafe`. Their LLM-facing decisions were mocked. The runner set `TESTSAFE_BLOCK_NETWORK=1`, `HF_HUB_OFFLINE=1`, and `TRANSFORMERS_OFFLINE=1` for the selected tests. It reported the `rag_db` fingerprint unchanged. No Gemini/API request or model download was made.

## Retrieval and deletion flow inspected

1. `main.main()` fetches up to `MEMORY_EXTRACTION_THRESHOLD = 4` new, non-excluded messages. It passes the batch to `extract_and_save_memories`, and advances the extraction checkpoint after that function returns without raising.
2. `memory_service.extract_memories()` sends user-role messages only, with their IDs, to the extraction prompt. `_parse_json_memories()` accepts single-ID and multi-ID output and filters IDs against user messages in that batch. Bullet-format fallback has no per-memory IDs.
3. `extract_and_save_memories()` requires explicit per-memory source IDs; it has no last-user fallback. `automatic_memory_service.process_memory()` compares against up to the latest 20 stored memories, then calls storage for NEW or UPDATE actions. `save_memory()` and `update_memory()` trim outer whitespace, embed that trimmed text, and persist it. Duplicate detection uses cosine similarity `>= 0.90`.
4. `search_memories()` embeds the query, scopes the database query to the conversation, retrieves `top_k=3` by default, and keeps results with similarity `>= 0.35`.
5. Explicit deletion first loads all memories for the conversation. The classifier's selected IDs are restricted to that candidate set; storage checks the memory's conversation again and deletes with both ID and conversation ID. Memory details are captured before deletion. Modern source links are combined with the compatibility `source_message_id` column.
6. `apply_deletion_cleanup()` excludes recorded sources, the immediately following assistant message only when it is the next row in that conversation, and caller-supplied deletion-turn messages. It then asks for supplemental echo-message IDs among at most 40 recent live messages. That scan is best-effort and cannot identify old or unknown sources. Failed summary rewrite/verification clears the summary and advances both summary and extraction checkpoints to at least the current conversation maximum message ID. Unknown provenance always clears the summary, fences both pipelines at that high-water ID, and returns `INCOMPLETE`.
7. `delete_message_with_provenance()` discovers affected memory IDs from the union of modern join links and legacy scalar references, explicitly detaches both representations, deletes the message, then reports whether each memory still has a valid same-conversation user source. All operations share one transaction.

## Current defaults and behavior

| Setting or rule | Current value / behavior | Source |
|---|---|---|
| Extraction batch threshold | 4 non-excluded messages | `main.py::MEMORY_EXTRACTION_THRESHOLD` |
| Existing memories considered for automatic update | 20 most recent by ID | `automatic_memory_service.get_recent_memories()` |
| Duplicate-memory similarity | 0.90 | `memory_storage_service.SIMILARITY_THRESHOLD` |
| Memory search top K | 3 | `memory_search_service.search_memories()` |
| Memory search relevance | similarity at least 0.35 | `memory_search_service.MEMORY_RELEVANCE_THRESHOLD` |
| Summary context | keep 6 recent messages; summarize only with at least 10 older messages | `memory_service.update_long_term_memory()` and `conversation_service.get_messages_to_summarize()` |
| Echo scan | last 40 non-excluded messages by default | `memory_cleanup_service.find_echo_message_ids()` |
| Summary rewrite length guard | 0.40–1.05 of original length | `memory_cleanup_service.MIN_LENGTH_RATIO` / `MAX_LENGTH_RATIO` |
| Embedding model | `cfg.EMBEDDING_MODEL`; configured default is `all-MiniLM-L6-v2` | `embedding_service.py`, `retrieval_config.py` |
| Storage text normalization | outer whitespace only, before both embedding and persistence | `save_memory()` / `update_memory()` |

No retrieval/default tuning is recommended in this audit. The memory text is internally consistent between embedding and persisted text after `.strip()`. A broader canonicalization rule is not specified in the current code or tests.

## Confirmed defects in the original audit baseline

### PH1-D01 — Missing extraction source is silently attributed to the last user message

**Current status:** Resolved in Task 1 and covered by the focused regression `test_p1_task1_strict_attribution.py`. The original behavior below records the audit baseline only.

- **Relevant code:** `services/memory_service.py::_parse_json_memories`, `extract_and_save_memories`; `main.py` extraction call.
- **Original audited behavior:** Valid JSON with no usable source ID and bullet-fallback memories both received the batch's last user ID. `main.py` also supplied the batch's last row as a fallback argument; the extractor preferred the last user row when one existed. A fact from an earlier user message could therefore be recorded against an unrelated later user message. The storage ownership/role check did not catch this because the wrong message was still a valid user message in the same conversation.
- **Reproduction:** Give a two-user-message batch, have the extractor return a fact supported by the first message but omit `source_message_ids` (or return bullet output). `extract_and_save_memories()` passes the second user's ID to `process_memory()`.
- **Expected behavior:** Do not invent a source. Require valid per-memory source IDs, or explicitly represent unknown provenance and prevent it from being mistaken for a verified source.
- **Severity / impact:** **High.** A false link makes later deletion omit the actual origin and deterministically exclude an unrelated message instead.
- **Proposed correction:** Remove the implicit last-user attribution. Propagate an explicit unknown/uncertain source outcome and define whether such a memory may be stored; do not silently convert unknown into a concrete link.
- **Required regressions:** Multiple user messages with a fact tied to the first; missing IDs; invalid IDs; bullet fallback; verify no wrong source link and verify deletion behavior for unknown provenance.
- **Scratch testable:** Yes. Mock extraction/decision calls and use `rag_test_scratch`.
- **Existing coverage:** `test_extraction_and_summary_guards.py` currently asserts that missing IDs use the last user ID. This pins the behavior rather than its attribution correctness; its expectation should change with the approved implementation.

### PH1-D02 — Source and decision IDs are lossily coerced before validation

**Current status:** Resolved in Task 1 and covered by focused raw-ID validation regressions. The original behavior below records the audit baseline only.

- **Relevant code:** `services/memory_service.py::_parse_json_memories`; `services/memory_storage_service.py::normalize_source_ids()` and `_validate_source_messages()`; `services/automatic_memory_service.py::normalize_memory_id()` and `process_memory()`.
- **Original audited behavior:** Source normalization used `int(raw)`, which accepted booleans (`true` became `1`) and truncated floats (`1.8` became `1`). The storage validator then checked that the coerced source ID belonged to a user message in this conversation, so a malformed value could become a valid but incorrect source link. Separately, `normalize_memory_id()` coerced a one-memory decision's target ID the same way before checking it against candidates; malformed model output could select an existing memory for UPDATE (or DELETE in an explicitly allowed delete mode). `delete_matching_memories()` had a stricter raw-ID guard, but it did not cover `process_memory()`.
- **Reproduction:** In a fixture where user message ID `1` exists, pass `source_message_id=1.8` to storage or return `source_message_ids: [1.8]` / `[true]` from the mocked extractor; the coerced ID is `1` and passes message-role/ownership validation. Separately, seed candidate memory ID `1`, return `{"action":"UPDATE","memory_id":1.8,"updated_memory":"wrong target"}`, and `process_memory()` normalizes the target to `1` before membership validation.
- **Expected behavior:** Reject booleans and non-integral numeric types without coercion. Retain only an explicitly defined integer representation and then validate source ownership or candidate membership.
- **Severity / impact:** **Medium.** It can silently corrupt provenance or update the wrong memory; malformed IDs are less common than missing IDs.
- **Proposed correction:** Validate raw source and decision ID types before conversion; keep one strict shared rule, with only explicitly supported numeric strings preserved for compatibility.
- **Required regressions:** `True`, `False`, integral and non-integral floats, numeric strings if supported, out-of-range values, valid integer IDs, and mixed valid/invalid source lists; assert invalid source IDs create no links and invalid decision IDs change/delete no memory.
- **Scratch testable:** Yes. Parser and service-routing cases can be unit-tested; storage cases can use a scratch conversation and mocked embeddings/decisions.

### PH1-D03 — Summary reset can reintroduce a forgotten fact when no source was excluded

**Current status:** Resolved for the approved policy in Task 2. On failed rewrite/verification, summaries are cleared and both pipeline checkpoints advance to current history. For unknown provenance, cleanup always clears and fences and returns an explicit incomplete outcome. The original failure mode below records the audit baseline only.

- **Relevant code:** `services/memory_cleanup_service.py::apply_deletion_cleanup`, `find_echo_message_ids`, `rewrite_summary_without`; `services/conversation_service.py::reset_conversation_summary`, `get_messages_to_summarize`; `services/memory_service.py::update_long_term_memory`.
- **Current behavior:** With no source IDs, deterministic exclusion has no origin to mark. The echo scan covers at most 40 recent messages and silently returns an empty list on failure. If summary rewrite or verification then fails, reset sets summary checkpoint to zero. A later summary update reads older, non-excluded messages again, including any source message that was not discovered by the echo scan.
- **Reproduction:** Delete a source-less memory whose original user message is outside the 40-message scan window (or make the echo scan fail); make summary rewrite fail so cleanup resets the summary; then run the summary update with that old message among the older non-excluded messages. The reset makes it eligible for summarization again.
- **Expected behavior:** A deletion flow must not report cleanup as complete while an unknown source can be reintroduced through history or summary rebuilding. Unknown provenance needs an explicit safe policy, and a reset must not blindly rebuild from known-unfiltered history.
- **Severity / impact:** **High.** This can resurface information the user asked the application to forget.
- **Proposed correction:** Add a fail-safe path for unknown-provenance memories and make summary checkpoint/reset behavior consistent with that path. The policy must preserve unrelated conversation data where possible and must never claim successful cleanup if the source cannot be identified. Do not guess a source message.
- **Required regressions:** Source-less memory + echo failure; source older than scan window; rewrite and verifier failure; subsequent summary rebuild; subsequent history/extraction checks; confirm no resurfacing and no cross-conversation changes.
- **Scratch testable:** Yes. Mock all LLM calls, seed a scratch conversation with more than 40 messages, and exercise cleanup followed by summary update.
- **Existing coverage gap:** `test_p1_cleanup_failure.py` verifies immediate summary clearing and deterministic exclusion for a known source. It does not test rebuilding after reset when the deleted memory has no source.

### PH1-D04 — Message deletion can silently orphan a legacy source-only memory

**Current status:** Resolved in Task 3. Affected IDs are the deduplicated union of `memory_sources` and `conversation_memories.source_message_id`. The scalar and join references are detached and the message deleted in one transaction. A memory is still supported only if a remaining source in either representation resolves to a same-conversation user message; otherwise it is reported orphaned and retained.

- **Relevant code:** `services/memory_provenance_service.py::delete_message_with_provenance()`.
- **Original audited behavior:** It discovered affected memories only through `memory_sources`. The legacy `conversation_memories.source_message_id` column could exist without a join-table row (the regression suite explicitly models this legacy shape). Deleting the message could therefore clear the only stored source while returning no orphan memory ID.
- **Original reproduction:** Create a memory with `source_message_id` set and no `memory_sources` row; call `delete_message_with_provenance()` for that source. Before Task 3, the affected list was empty because the query read only the join table; the legacy pointer was cleared by its FK.
- **Expected behavior:** Source deletion must account for both the modern relation and the legacy scalar pointer, and report any memory that loses its last source.
- **Severity / impact:** **Medium.** The memory remains but its provenance is silently lost, impairing later cleanup and auditability.
- **Proposed correction:** Compute affected IDs from the union of join-table links and legacy scalar references, then assess remaining sources using both representations before returning orphaned/still-supported IDs. Keep the operation atomic.
- **Required regressions:** Legacy-column-only source; modern link; both representations; shared memory with another source; missing message; foreign conversation; assert rollback/atomicity on failure.
- **Scratch testable:** Yes. Build a source-only legacy fixture in `rag_test_scratch`; no production database is needed.

## Limitations and concerns, not misreported as confirmed defects

### PH1-L01 — Historical source-less memories cannot be deterministically repaired from current data

**Current status:** Historical source IDs remain unknowable. Task 2 does not backfill or broadly exclude messages; it deletes the selected memory, clears the summary, fences summary and extraction checkpoints, preserves original rows, and returns `INCOMPLETE`.

- **Relevant code:** `services/memory_storage_service.py::get_memory_details`, `save_memory`; `add_memory.py` insert.
- **Current behavior:** `get_memory_details()` returns an empty source list when both modern links and the legacy scalar source are absent. Since Task 1, `save_memory()` requires a source and `add_memory.py` requires an explicit source-message argument and routes through shared storage validation. This limitation now applies to historical source-less memories only; no historical row was repaired or queried for this implementation.
- **Reproduction:** Create a legacy memory with a NULL scalar source and no join rows, then call `get_memory_details()`; the result has `source_message_ids=[]`. No deterministic function maps its text back to a specific message.
- **Expected behavior:** New memories should not silently appear to have verified provenance when none exists. Historical records with no source should remain explicitly unknown; their source must not be guessed.
- **Assessment:** Confirmed provenance limitation. The missing source cannot be reconstructed reliably from the memory text alone. Prior audit documents report 34 such rows in `rag_db`; that historical count was not re-queried for this read-only audit.
- **Severity / impact:** **High** for deletion completeness because the source messages cannot be selected deterministically.
- **Proposed correction:** For new writes, require valid provenance or record an explicit unknown-provenance state. For existing rows, do not fabricate/backfill source IDs; use an approved safe deletion policy. Any production migration or data review needs separate approval.
- **Tests / scratch:** New-write policy and cleanup policy are scratch-testable; real historical counts/data are not verified here.

### PH1-L02 — Assistant-origin legacy links remain tolerated; `legacy` is not an incorrect role label

**Current status:** Historical assistant links remain untouched and distinguishable: `link_kind='legacy'` continues to identify backfill origin, while the stored `source_role` and actual message role identify assistant origin. Assistant rows do not count as valid user-source support after deletion. New assistant-source writes remain rejected. A future quarantine procedure is proposed in `PHASE1_LEGACY_ASSISTANT_PROVENANCE_QUARANTINE_PROPOSAL.md`; no inventory or quarantine was run.

- **Relevant code:** `migrations/003_memory_sources_provenance.sql`; `services/memory_storage_service.py::_validate_source_messages`, `get_memory_details`.
- **Current behavior:** Migration `003_memory_sources_provenance.sql` assigns `link_kind='legacy'` to pre-existing backfilled links and records the actual `source_role` separately. The NOT VALID user-role check tolerates historical assistant rows while new storage writes reject assistant sources.
- **Reproduction:** A pre-migration link to an assistant message is backfilled: it has `link_kind='legacy'`, `source_role='assistant'`, and passes the unvalidated historical constraint. `get_memory_details()` returns its message ID; a new `save_memory()` call with an assistant ID is rejected.
- **Expected behavior:** Historical source role should remain accurately distinguishable and should not be treated as user-origin evidence. The `legacy` link kind can remain because it describes the backfill's provenance, not the message role.
- **Assessment:** The suspected label error is **not confirmed**: `legacy` describes how the link entered the provenance table; `source_role` separately records `assistant`. However, legacy assistant links remain invalid evidence and are surfaced as source IDs by `get_memory_details()`. Prior audit documents reported four such links; no current database query was made.
- **Severity / impact:** **Medium** if a legacy assistant message is treated as the evidence for a user memory or excluded during deletion cleanup.
- **Proposed correction:** Inventory and quarantine/reconcile legacy assistant-source rows under a separately approved data plan. Do not relabel them as user evidence or blindly delete them.
- **Tests / scratch:** New assistant-source rejection is covered by scratch regressions. Quarantine semantics can be tested on scratch only; current production row counts are unverified.

### PH1-L03 — Assistant pairing is an adjacency heuristic, not a persisted reply relation

**Current status:** Task 2 adopts immediate next-message adjacency as the cleanup contract. No turn/reply schema was added. An intervening user prevents pairing with a later assistant; excluded rows still count when determining the next row by ID.

- **Relevant code:** `services/conversation_service.py::get_paired_assistant_ids`; `services/memory_cleanup_service.py::apply_deletion_cleanup`.
- **Current behavior:** `get_paired_assistant_ids()` examines only the first later message by ID and pairs it only if that row is an assistant. It does not search later assistant messages when an intervening user message exists. No reply-to/turn ID is stored to identify the true answer.
- **Reproduction:** For ordered rows `user U1`, `user U2`, `assistant A`, a cleanup for U1 finds U2 as the first later row and returns no assistant ID. The database has no turn relation to determine whether A answered U1, U2, or both.
- **Expected behavior:** The cleanup contract should identify the intended reply or explicitly define immediate adjacency as the only supported pairing rule; it should not guess a later assistant message.
- **Assessment:** The schema still has no persisted reply/turn relation, but Task 2 adopts immediate next-message adjacency as the explicit cleanup policy. Pairing an arbitrary later assistant is not permitted. This is now a documented limitation rather than an unresolved cleanup rule.
- **Severity / impact:** **Medium** potential cleanup risk if the assistant echo is not adjacent and the best-effort echo scan misses it.
- **Proposed correction:** Define the supported turn-pairing contract first. If exact pairing is required, store an explicit reply/turn relationship; do not infer an arbitrary later assistant as a source.
- **Tests / scratch:** Yes. Include adjacent user/assistant, consecutive user messages, consecutive assistant messages, excluded rows, and unrelated conversations after the contract is set.

### PH1-C01 — Text normalization contract is underspecified

**Current status (Task 4, implemented, not yet tested):** The trim-only contract is now explicit and centralized in `memory_storage_service.normalize_memory_text()`; see the Task 4 section. The original finding below is kept unchanged.

- **Relevant code:** `services/memory_storage_service.py::save_memory`, `update_memory`; `services/automatic_memory_service.py::process_memory`.
- **Current behavior:** Memory text gets `.strip()` before both embedding and storage. Internal whitespace, casing, punctuation, and equivalent phrasing are not canonicalized. Similarity duplicate detection is the only additional duplicate mechanism.
- **Reproduction:** Submit two strings differing only in internal whitespace or casing. Both are trimmed but otherwise preserved and embedded as distinct inputs; duplicate behavior then depends on their embedding similarity.
- **Expected behavior:** A documented normalization contract should make clear which representation is stored and embedded. The current code satisfies the minimal trim-only contract but has no stronger canonicalization rule.
- **Assessment:** No consistency defect was confirmed: the embedded text and stored text are the same trimmed string. There is no written canonicalization contract, so more aggressive normalization could alter meaning.
- **Severity / impact:** **Low** potential duplicate/formatting concern; not a confirmed integrity defect.
- **Proposed correction:** Specify a minimal normalization contract and tests before changing content. Preserve case/punctuation unless the product contract says otherwise.
- **Tests / scratch:** Pure normalization cases need no database; embedding/storage consistency can be tested with mocked embeddings in scratch.

### PH1-C02 — Recent-candidate window and extraction checkpoint behavior need a product contract

**Current status (Task 4, implemented, not yet tested):** The latest-20 window is kept and documented as a limitation (`AUTOMATIC_CANDIDATE_WINDOW`), and the three-outcome extraction contract is explicit; see the Task 4 section. The original finding below is kept unchanged.

- **Relevant code:** `services/automatic_memory_service.py::get_recent_memories`, `process_memory`; `services/memory_service.py::extract_memories`; `main.py` extraction checkpoint block.
- **Current behavior:** Automatic update decisions still inspect only the latest 20 memories. Task 1 changed extraction handling: explicit `[]` or `NONE` remains a successful empty outcome, while empty, non-text, unparseable, missing/invalid-provenance, or unresolved extraction outcomes raise and leave the checkpoint unchanged. The 20-memory candidate window remains outside Task 1.
- **Reproduction:** Store more than 20 memories and place a matching fact outside the latest 20, then submit a correction; the decision prompt omits that older memory. Separately, return malformed non-bullet extraction output; `extract_memories()` returns `[]`, `extract_and_save_memories()` returns normally, and the caller advances the checkpoint.
- **Expected behavior:** The product contract should state whether older memories must remain candidates and should distinguish valid empty extraction from malformed output if malformed output must be retried.
- **Assessment:** Current behavior is confirmed; whether it violates the intended memory recall/extraction contract is unverified. Similarity duplicate detection partially mitigates NEW duplicates, but cannot reliably replace an UPDATE decision about an older fact.
- **Severity / impact:** **Medium** potential missed updates or unretained facts.
- **Proposed correction:** Decide whether candidate recall must cover all memories and distinguish a valid empty extraction from an unparseable/uncertain result before checkpointing.
- **Tests / scratch:** Yes. Test a matching memory older than 20 candidates and malformed, empty, and valid-empty extraction responses with checkpoint assertions.

## Behaviors verified as protected in current code

- New source IDs are checked against user messages in the requested conversation before memory writes; new assistant and cross-conversation source IDs are rejected.
- `delete_memory()` validates raw memory IDs, checks owner conversation, and deletes with both memory ID and conversation ID. `delete_matching_memories()` uses all conversation-owned candidates, filters classifier IDs to those candidates, rejects unknown status, and reports partial failures.
- Modern memory-source links retain multiple origin/update/confirmation messages; `get_memory_details()` falls back to the legacy scalar when no join rows are present.
- Summary rewrite failures clear the current summary and fence both pipelines at current history; source-less cleanup remains explicitly incomplete because original-message provenance cannot be reconstructed.

## Original audit test matrix and execution results

| Test / evidence | Result | Coverage / limitation |
|---|---|---|
| `test_memory_sources_regression.py` via `run_tests.py` | **PASS** | Multi-source updates, source validation, legacy scalar fallback, memory deletion cleanup, conversation scoping. Does not cover message deletion of a scalar-only source. |
| `test_p1_process_memory.py` via `run_tests.py` | **PASS** | NEW/DUPLICATE/UPDATE/DELETE routing and per-conversation candidates under mocked decisions. Does not validate missing-source attribution semantics. |
| `test_p1_memory_update_delete_integration.py` via `run_tests.py` | **PASS** | Update/delete ownership, invalid text/source, source links, partial failures. |
| `test_p1_cleanup_failure.py` via `run_tests.py` | **PASS** | Rewrite/verification/echo failure handling and immediate summary reset for a known source. No post-reset rebuild for unknown provenance. |
| `test_p1_d7_storage_id_validation.py` via `run_tests.py` | **PASS** | Strict raw memory-ID validation and cross-conversation deletion protection. This does not validate source-message ID coercion. |
| `test_phase5_provenance.py`, `test_extraction_and_summary_guards.py`, `test_deletion_cleanup.py` | **Inspected only** | Existing evidence and gaps are described above; not run in this audit. |
| Full default suite | **Not run** | Explicitly out of scope for this audit. |

Runner result: 5 selected tests / 5 passed / 0 failed; 48 other registered tests not run. Runner reported `application database 'rag_db' fingerprint unchanged : True`. No smoke-only test was included.

## Original audit database, network, and repository safety

- All database-writing test fixtures targeted `rag_test_scratch` and use `testsafe.require_scratch_db()`; the selected tests include fixture cleanup in `finally` blocks. The runner was not invoked with `--clean`, so it did not globally clear scratch tables.
- The runner's `rag_db` fingerprint connection sets `default_transaction_read_only=on`; before/after fingerprints matched. No application database write, migration, backfill, or direct database inspection was performed.
- Outbound network and Hugging Face downloads were disabled for selected tests. The tested LLM calls were mocked. No Gemini/API calls occurred.
- During the original read-only audit, no source, schema, migration, dataset, test, or configuration file was edited. That audit created only the two requested audit documents.
- Git status had pre-existing held-out dataset/review-package changes before the original audit; they were left untouched in both the audit and the subsequent Task 1 implementation.

## Files inspected

Application: `main.py`; `add_memory.py`; `services/memory_service.py`; `services/memory_storage_service.py`; `services/memory_search_service.py`; `services/memory_delete_service.py`; `services/automatic_memory_service.py`; `services/memory_cleanup_service.py`; `services/memory_provenance_service.py`; `services/memory_decision_service.py`; `services/conversation_service.py`; `services/embedding_service.py`; `services/retrieval_config.py`; `services/database.py`.

Tests: `test_memory_sources_regression.py`; `test_p1_process_memory.py`; `test_p1_memory_update_delete_integration.py`; `test_p1_cleanup_failure.py`; `test_p1_d7_storage_id_validation.py`; `test_phase5_provenance.py`; `test_extraction_and_summary_guards.py`; `test_deletion_cleanup.py`; `run_tests.py`; `testsafe.py`.

Schema and prior records: `migrations/001_add_messages_context_excluded.sql`; `migrations/002_add_memory_sources.sql`; `migrations/003_memory_sources_provenance.sql`; `migrations/003_memory_sources_provenance_down.sql`; `migrations/README.md`; `docs/remediation/phase1_remediation.md`; `docs/remediation/p4_07_verification_and_phase1_plan.md`; `docs/remediation/MASTER_GAP_REGISTER.md`; `docs/PROJECT_COMPLETION_AUDIT.md`; `docs/phase5_audit.md`; `docs/phase5_final_report.md`; `docs/remediation/STATUS_AND_GAPS_REPORT.md`.

## Task 1 implementation evidence — PH1-D01 and PH1-D02

**Outcome:** Implemented under the subsequent approved Task 1 request. Extraction now requires explicit per-memory source IDs. Each source must be a positive, valid ID belonging to a user message in the extraction batch; storage additionally verifies user role and conversation ownership. Missing, malformed, assistant, foreign, or mixed-validity provenance raises an extraction error and prevents checkpoint advancement. Parser-detectable invalid provenance rejects the batch before the first memory write. The deprecated `source_message_id` argument to `extract_and_save_memories()` remains accepted for call compatibility but is never used as a fallback.

Storage and manual creation require source provenance. `add_memory.py` is import-safe, requires `--source-message-id`, validates positive ASCII digits within PostgreSQL bigint range, and delegates to shared storage validation. Automatic UPDATE and DELETE decision IDs are validated from their raw value before candidate matching or mutation. An extraction exception or unresolved `UNCERTAIN` outcome is caught by `main.py` without advancing the checkpoint; the batch remains eligible for retry. Explicit empty outcomes (`[]` and `NONE`) remain successful no-memory outcomes. No production memory data was queried, rewritten, migrated, or backfilled.

**Identifier compatibility:** Source IDs do not accept numeric strings; there was no explicit source-string compatibility contract, and extractor source IDs are emitted as JSON numbers. Positive ASCII numeric strings remain supported for memory decision IDs and storage deletion IDs because existing tests/contracts explicitly exercise this representation. Exact, safely representable integral floats are accepted by source and single-memory decision normalization without truncation; booleans, fractional/non-finite/unsafe floats, malformed strings, zero, negatives, and out-of-bigint-range IDs are rejected. Direct storage deletion retains its existing stricter behavior of rejecting all floats, including `2.0`.

**Tests run:** All selected tests ran through `run_tests.py`, which directs database-writing fixtures to `rag_test_scratch` through `testsafe`, blocks outbound network, and sets Hugging Face/Transformers offline flags. Embedding, extraction, and decision calls in the focused cases were mocked.

| Test | Result | Evidence / qualification |
|---|---|---|
| `test_p1_task1_strict_attribution.py` | **PASS** | Missing and bullet provenance; valid single/multi-source extraction; invalid source types/lists; assistant, foreign and out-of-batch sources; strict UPDATE/DELETE IDs; creation entry points; checkpoint remains unchanged on rejected extraction. |
| `test_extraction_and_summary_guards.py` | **PASS** | Replaces the prior last-user fallback pin with strict rejection; cleanup added for its test fixture. |
| `test_phase5_provenance.py` | **PASS** | Mixed invalid provenance rejected; valid source IDs deduplicated. |
| `test_memory_sources_regression.py` | **PASS** | Existing source storage and update regressions. |
| `test_p1_process_memory.py` | **PASS** | Existing automatic decision routing. |
| `test_p1_memory_update_delete_integration.py` | **PASS** | Existing update/delete integration and ownership regressions. |
| `test_p1_d7_storage_id_validation.py` | **PASS** | Existing storage ID compatibility contract. |
| `test_memory_storage.py` | **PASS (smoke-only)** | Runner classifies this test as smoke-only, so it is not assertion-verified. |

Focused result: **1/1 test file passed**. Directly affected existing result: **7/7 selected test files passed**, including one smoke-only file. The full suite was not run.

**`rag_db` safety fingerprint:** The guarded runner and a separate read-only before/after fingerprint reported no change. The fingerprint values matched exactly:

| Table | Before count / fingerprint | After count / fingerprint |
|---|---:|---:|
| `conversations` | 261 / `7f4fb6de3077bde3c0b591efcaac70d5` | 261 / `7f4fb6de3077bde3c0b591efcaac70d5` |
| `messages` | 1,340 / `502d43b77c943ab25edcc6c166eb15c8` | 1,340 / `502d43b77c943ab25edcc6c166eb15c8` |
| `conversation_memories` | 127 / `88d8b76aa327ce9d882ee52ef98e0f38` | 127 / `88d8b76aa327ce9d882ee52ef98e0f38` |
| `memory_sources` | 93 / `7d877c75385fe995aaa9fcbc48096a36` | 93 / `7d877c75385fe995aaa9fcbc48096a36` |
| `document_chunks` | 9 / `711aa64fa4cb7bd330743dc0f341b5cb` | 9 / `711aa64fa4cb7bd330743dc0f341b5cb` |

No Gemini/API calls or model downloads occurred. The runner was not invoked with `--clean`; focused fixtures perform their own cleanup. No files were staged, committed, or pushed. Pre-existing held-out dataset/review-package work was left untouched.

**Task 1 files changed:** `services/memory_service.py`, `services/memory_storage_service.py`, `services/automatic_memory_service.py`, `main.py`, `add_memory.py`, `run_tests.py`, `test_p1_task1_strict_attribution.py`, `test_extraction_and_summary_guards.py`, `test_phase5_provenance.py`, `test_memory_storage.py`, and related manual memory scripts updated to provide explicit source messages: `test_auto_memory.py`, `test_automatic_memory.py`, `test_duplicate_memory.py`, `test_memory_delete.py`, `test_memory_relevance.py`, and `test_semantic_memory.py`. The current implementation evidence was added to this report and Task 1's completion status was recorded in `PHASE1_LEGACY_MEMORY_REMEDIATION_PLAN.md`.

**Remaining limitations:** Historical source-less and assistant-source records remain unchanged and unrepaired. Persistent malformed extraction output will keep the extraction checkpoint behind and retry the same batch until a valid explicit outcome is returned. Task 2's incomplete-cleanup policy for unknown provenance is recorded below; Task 3's deletion reconciliation is recorded below; Task 4 was not started.

## Task 2 implementation evidence — PH1-D03, PH1-L01, and PH1-L03

**Outcome:** Implemented under the approved Task 2 policy. No schema change was needed: the existing `summary_up_to_message_id` and `memory_extraction_up_to_message_id` checkpoints already gate the summary and automatic-extraction selectors, and those selectors also omit `context_excluded` rows.

### Known provenance

- Cleanup combines all recorded source IDs from the modern source list and legacy scalar field, marks every source excluded, and asks `get_paired_assistant_ids()` only for the next message by ID in the same conversation. It pairs that row only if it is an assistant. An intervening user prevents pairing with any later assistant. Excluded rows still count as the immediate next row; unrelated conversation rows do not.
- Echo scanning remains supplemental and bounded to the latest 40 live messages. A scan failure cannot undo deterministic source/reply exclusions.
- If rewrite validation or semantic verification fails, `clear_summary_and_advance_checkpoints()` clears the summary and sets both checkpoints to at least the current maximum message ID. This prevents old messages, including non-excluded messages, from being submitted again after a failed rewrite. Original message rows remain stored.
- Cleanup returns `status="COMPLETE"` and prints an explicit completion message for known provenance after deterministic exclusions. A failed rewrite is represented by `rewrite_status="RESET"`; in that case the empty summary and both high-water checkpoints provide the fail-closed outcome.

### Unknown provenance

- A deleted-memory record with no valid recoverable source ID (or no returned detail record) is treated as unknown. Any valid source IDs on other selected memories are still excluded.
- After the supplemental echo scan and rewrite attempt, the summary is cleared unconditionally, and both checkpoints advance monotonically to the current conversation maximum message ID. No source is inferred, and no original conversation message is deleted or broadly marked excluded.
- Cleanup returns `status="INCOMPLETE"`, `provenance_status="UNKNOWN"`, and `summary_status="CLEARED_UNKNOWN_PROVENANCE"`. The cleanup path prints: “Memory deleted, historical cleanup incomplete…” so callers and users are not told that historical cleanup completed.
- Because both selectors require IDs above their respective checkpoint, a later summary rebuild or automatic-extraction selection cannot include pre-cleanup messages. New messages above the high-water mark remain eligible normally. Original messages remain in the database; this policy does not claim to erase them.

### Focused verification

All tests ran sequentially through `run_tests.py` on `rag_test_scratch`; every database-writing test requires `testsafe`. Network access was blocked and Hugging Face/Transformers were offline. LLM and embedding calls in the affected tests were mocked. The runner was not invoked with `--clean`.

| Test | Result | Coverage / qualification |
|---|---|---|
| `test_p1_task2_safe_deletion.py` | **PASS** | Unknown legacy memory, echo failure, possible source outside the 40-message scan, rewrite failure, verification failure, verified rewrite still cleared, checkpoint fencing, message preservation, unrelated conversation isolation, post-cleanup summary/extraction inputs, and assistant adjacency cases. |
| `test_deletion_cleanup.py` | **PASS** | Existing successful known-source cleanup and summary rewrite; embeddings are mocked and fixtures are cleaned. |
| `test_p1_cleanup_failure.py` | **PASS** | Known-source rewrite/verification failures now assert both checkpoints fence current history; fixtures are cleaned. |
| `test_extraction_and_summary_guards.py` | **PASS** | Existing rewrite/verification regressions now assert checkpoints are not lowered; fixtures are cleaned. |

Final selected run: **4 tests / 4 passed / 0 failed / 0 smoke-only**. The full suite, held-out evaluation, and unrelated tests were not run.

### Database and network safety

The runner reported `application database 'rag_db' fingerprint unchanged : True` for both the initial focused run and final four-test run. The exact read-only fingerprint before and after this task was identical to the Task 1 baseline:

| Table | Before count / fingerprint | After count / fingerprint |
|---|---:|---:|
| `conversations` | 261 / `7f4fb6de3077bde3c0b591efcaac70d5` | 261 / `7f4fb6de3077bde3c0b591efcaac70d5` |
| `messages` | 1,340 / `502d43b77c943ab25edcc6c166eb15c8` | 1,340 / `502d43b77c943ab25edcc6c166eb15c8` |
| `conversation_memories` | 127 / `88d8b76aa327ce9d882ee52ef98e0f38` | 127 / `88d8b76aa327ce9d882ee52ef98e0f38` |
| `memory_sources` | 93 / `7d877c75385fe995aaa9fcbc48096a36` | 93 / `7d877c75385fe995aaa9fcbc48096a36` |
| `document_chunks` | 9 / `711aa64fa4cb7bd330743dc0f341b5cb` | 9 / `711aa64fa4cb7bd330743dc0f341b5cb` |

The exact final values were read through the runner's existing read-only fingerprint helper. No other `rag_db` query, write, migration, or backfill was performed. No Gemini/API call or model download occurred.

### Files changed and limits

Task 2 changed `services/conversation_service.py`, `services/memory_cleanup_service.py`, `run_tests.py`, `test_p1_task2_safe_deletion.py`, `test_deletion_cleanup.py`, `test_p1_cleanup_failure.py`, and `test_extraction_and_summary_guards.py`, plus this report and Task 2's status in `PHASE1_LEGACY_MEMORY_REMEDIATION_PLAN.md`. `services/memory_service.py` was inspected but did not require changes: summary and extraction input selection already enforces the two conversation checkpoints and excluded-message filter.

Unknown provenance remains irrecoverable. Its cleanup is deliberately reported incomplete, and historical messages remain stored. When a known-source summary rewrite fails, the entire summary is cleared and all pre-cleanup messages are fenced from both pipelines; unrelated old messages remain stored but are no longer available for later generated context. The adjacency rule is explicitly positional because the schema has no persisted reply/turn relation. Task 3 reconciles the two provenance representations during message deletion, but does not repair historical assistant links. Task 4 was not started. Existing held-out review-package work was preserved; no files were staged, committed, or pushed.

## Task 3 implementation evidence — PH1-D04 and PH1-L02

**Outcome:** Implemented under the separately approved Task 3 request. `delete_message_with_provenance()` now scopes lookups and mutations to the requested conversation and discovers affected memories with a SQL `UNION` of `memory_sources.memory_id` and `conversation_memories.id` rows whose legacy `source_message_id` matches the deleted message. `UNION` deduplicates a memory represented in both stores.

### Support classification and atomicity

- Join references to the deleted message and scalar references to it are explicitly detached before message deletion. The three mutations and post-detachment classification run inside one database connection context/transaction.
- An affected memory is `still_supported` when another source in either representation resolves to a message in the same conversation whose actual role is `user`. For a modern join row, both `memory_sources.source_role` and `messages.role` must be `user`. The legacy scalar has no stored role, so the joined message role is checked.
- Assistant-origin rows do not count as verified user support. Memories with no remaining valid user source are reported `orphaned`; the memory records themselves are retained.
- A missing or foreign-conversation message returns the existing no-op shape (`deleted=False`, empty `orphaned` and `still_supported`) and leaves records untouched.
- Any exception during detachment or message deletion exits the transaction with an error and rolls back the full operation. Failure injection after join detachment and after both detachments verifies links, scalar source, and message are restored.
- The existing success and no-op return dictionary shape is unchanged; no compatibility contract change was needed.

### Historical assistant links

No historical row was relabeled, deleted, inventoried, or quarantined. Reads preserve `source_role='assistant'` and `link_kind='legacy'`; `legacy` remains the migration/backfill origin, not a role label. The new write path continues to reject assistant messages as sources. The read/support regression models the historical assistant row with a mocked query result because normal current constraints reject creating such a row as new scratch data. A read-only inventory and reviewed quarantine/reconciliation proposal is at `PHASE1_LEGACY_ASSISTANT_PROVENANCE_QUARANTINE_PROPOSAL.md`.

### Focused verification

Selected tests ran sequentially through `run_tests.py` using `rag_test_scratch` and `testsafe`. The runner blocked outbound network and set Hugging Face/Transformers offline flags. Embeddings were mocked in the focused and existing provenance tests; no LLM, Gemini/API, or model download was used.

| Test | Result | Evidence / qualification |
|---|---|---|
| `test_p1_task3_provenance_reconcile.py` | **PASS** | Scalar-only, join-only, duplicate representation, surviving user source, conversation-scoped support query, missing message, foreign conversation, rollback injection at scalar detachment and message deletion, assistant-source write rejection, and historical role/link-kind read behavior. The historical assistant row was simulated via a mocked read, not persisted in scratch. |
| `test_phase5_provenance.py` | **PASS** | Existing provenance deletion and shared/legacy support regressions; embeddings mocked. |
| `test_memory_sources_regression.py` | **PASS** | Existing source storage and update regressions; embeddings mocked. |

Final selected run: **3 test files / 3 passed / 0 failed / 0 smoke-only**. No full suite, held-out evaluation, or unrelated tests were run.

### Database safety

The guarded runner reported `application database 'rag_db' fingerprint unchanged : True`. Before and after values matched:

| Table | Before count / fingerprint | After count / fingerprint |
|---|---:|---:|
| `conversations` | 261 / `7f4fb6de3077bde3c0b591efcaac70d5` | 261 / `7f4fb6de3077bde3c0b591efcaac70d5` |
| `messages` | 1,340 / `502d43b77c943ab25edcc6c166eb15c8` | 1,340 / `502d43b77c943ab25edcc6c166eb15c8` |
| `conversation_memories` | 127 / `88d8b76aa327ce9d882ee52ef98e0f38` | 127 / `88d8b76aa327ce9d882ee52ef98e0f38` |
| `memory_sources` | 93 / `7d877c75385fe995aaa9fcbc48096a36` | 93 / `7d877c75385fe995aaa9fcbc48096a36` |
| `document_chunks` | 9 / `711aa64fa4cb7bd330743dc0f341b5cb` | 9 / `711aa64fa4cb7bd330743dc0f341b5cb` |

Only the runner's existing read-only fingerprint accessed `rag_db`; no production record inventory, write, migration, or backfill was performed. Scratch fixtures were cleaned by the test. No API/network/model access occurred.

### Files changed and remaining limits

Task 3 added changes to `services/memory_provenance_service.py`, `run_tests.py`, and `test_phase5_provenance.py`, plus the new `test_p1_task3_provenance_reconcile.py` and `PHASE1_LEGACY_ASSISTANT_PROVENANCE_QUARANTINE_PROPOSAL.md`; this audit and `PHASE1_LEGACY_MEMORY_REMEDIATION_PLAN.md` record the implementation. Earlier uncommitted work was preserved. No files were staged, committed, or pushed.

This implements accounting when a message is deleted; it does not resolve unknown historical source IDs or repair/quarantine assistant-origin rows. The assistant row classification is covered by mocked read evidence because current constraints block creating a new assistant source row. Task 4 remained unstarted at the time of the Task 3 report (it is recorded below). The report makes no claim that production data was repaired or independently reviewed.

## Task 4 implementation evidence — PH1-C01 and PH1-C02

**Outcome:** Implemented under the separately approved Task 4 request.
- **Not tested:** per the user's instruction, implementation came first. No unit, integration, smoke or regression test was run.
- **Checks done:** only static review, plus `python -m py_compile` on the modified modules. That is a syntax check, not a test.

### A. Normalization contract (PH1-C01)
- **Contract: trim-only.** `normalize_memory_text(text)` in `services/memory_storage_service.py` returns `text.strip()`. Casing, punctuation and internal whitespace (including repeated spaces and newlines) are preserved.
- **Rejected input:** non-string input, and text that is empty after trimming, returns `None`, which means reject and write nothing.
- **Examples:**

  | Input | Result |
  |---|---|
  | `"  I live in Jaipur.  "` | `"I live in Jaipur."` |
  | `"I Live in Jaipur."` | unchanged |
  | `"I live in Jaipur!!!"` | unchanged |
  | `"I  live in Jaipur."` | unchanged |
  | `"I live\nin Jaipur."` | unchanged |
  | `"   "` | rejected |
- **One function, every writer.** The same function is used by:
  - `save_memory`, the storage boundary for `add_memory.py` and for NEW decisions;
  - `update_memory`;
  - `automatic_memory_service.process_memory`, for the new memory text before the decision model sees it, and in its UPDATE path for the model's `updated_memory`;
  - the extraction parser, `memory_service._parse_json_memories`.

  There is no second normalization implementation.
- **Exact text-to-embedding consistency.** In `save_memory` and `update_memory`, the normalized string is the only value passed to `generate_embeddings([...])` and the value written to `conversation_memories.memory`.
- **Deliberate, narrow behaviour changes:**
  - A non-string `memory` in extraction JSON, or a non-string `updated_memory` from the decision model, is now rejected instead of being coerced with `str()`.
  - A blank or non-string `new_memory` reaching `process_memory` returns `UNCERTAIN`. Before, it reached the decision model or returned `SKIPPED`.
- **Historical data:** historical rows and embeddings are not touched.

### B. Automatic candidate coverage (PH1-C02, part 1)
- **No behaviour change.** `AUTOMATIC_CANDIDATE_WINDOW = 20` is the default of `get_recent_memories()`, which `process_memory` uses when no explicit candidates are passed. Unchanged: the window size, the ordering (`ORDER BY id DESC`), the similarity threshold (0.90) and the ranking. No fallback full-history scan was added.
- **Documented limitation:** automatic NEW/DUPLICATE/UPDATE detection considers only the latest 20 memories of the conversation. A conflicting or duplicate memory older than that window is not seen by automatic update detection.
  - `save_memory`'s nearest-neighbour duplicate check (similarity ≥ 0.90) still covers all memories of the conversation. It can only skip near-duplicates; it cannot perform an UPDATE.
  - Explicit deletion requests still use all conversation memories (`get_all_conversation_memories`).

### C. Extraction parsing and checkpointing (PH1-C02, part 2)
| Extraction response | Behaviour |
|---|---|
| `[]` (optionally fenced as ```` ```json ````) | success, no memories → `[]` |
| exact `NONE` (any case, after trimming) | success, no memories → `[]` |
| batch with no user messages | success, no memories → `[]` (no model call) |
| JSON list of valid records | processed |
| record with missing, invalid, out-of-batch or non-user source IDs | `InvalidMemoryProvenanceError` before any write |
| record that is not an object, or whose `memory` is missing, blank or non-text | `MemoryExtractionError` |
| JSON that is not a list (object, `null`, string), malformed JSON, or JSON with extra prose | `MemoryExtractionError` (never `[]`) |
| bullet-style output | `InvalidMemoryProvenanceError`. Bullets carry no per-memory source IDs, so the fallback never produces records. |
| empty or non-text response | `MemoryExtractionError` |
| decision `UNCERTAIN` for a record | `MemoryExtractionError` |

- **Never silently empty:** a malformed or ambiguous response is never converted to `[]`. The three outcomes are documented in `services/memory_service.py`, and `EXPLICIT_NO_MEMORY_TOKEN = "NONE"`.
- **New in Task 4, a whole-batch source check:** after the in-batch checks, `extract_and_save_memories` calls the new read-only `memory_storage_service.validate_source_messages()` once, for the union of all source IDs. It checks that every ID is a user message of this conversation. A batch with any invalid source is therefore rejected **before its first memory write**. This complements Task 1's per-write validation.
- **Checkpoint, unchanged in code:** `main.py` advances `memory_extraction_up_to_message_id` only when `extract_and_save_memories` returns normally, i.e. outcome 1 or 2. `MemoryExtractionError`, its subclass, or any other exception leaves the checkpoint unchanged, and the batch is retried.

### Static review (not testing)
- **Writers inspected:** every memory writer and every embedding call for memory text (`save_memory`, `update_memory`, `process_memory`, the parser, `add_memory.py`). `memory_search_service` embeds queries only, and `memory_provenance_service` updates only `source_message_id`.
- **Candidate window:** confirmed unchanged.
- **Empty vs. failed:** the empty-success outcome is distinguishable from failures, which are typed exceptions.
- **Checkpoint:** confirmed to advance only on a normal return.
- **No partial batch:** confirmed that all validation, including the database pre-check, precedes the first write.
- **Tasks 1–3:** their provenance and deletion code paths were not modified.

### Files changed (Task 4)
- `services/memory_storage_service.py`:
  - added `normalize_memory_text` and `validate_source_messages`;
  - `save_memory` and `update_memory` use the shared normalizer.
- `services/automatic_memory_service.py`:
  - `AUTOMATIC_CANDIDATE_WINDOW` is the documented default (value 20, unchanged);
  - `process_memory` and its UPDATE path use the shared normalizer.
- `services/memory_service.py`:
  - documented extraction contract and `EXPLICIT_NO_MEMORY_TOKEN`;
  - the parser uses the shared normalizer, so non-text memories are rejected;
  - the empty-response check now comes before the `NONE` check;
  - a whole-batch source pre-check runs before writes.
- This audit and `PHASE1_LEGACY_MEMORY_REMEDIATION_PLAN.md`.
- **Not changed:** `main.py`, `add_memory.py`, `conversation_service.py`, schemas, migrations, retrieval, ranking and thresholds.

### Remaining limitations
- **Candidate window:** memories older than the latest 20 are not considered for automatic UPDATE. This is an explicit decision.
- **Not transactional:** a batch is validated as a whole, but the per-memory model decisions are not one transaction. If a later record resolves `UNCERTAIN` after earlier records were saved, the batch raises and is retried. The earlier saves remain, and their re-extraction is absorbed by the duplicate/confirmation path. This is the existing Task 1 behaviour.
- **No retry limit:** persistent malformed output keeps the checkpoint behind indefinitely; there is no automatic recovery.
- **The new database pre-check performs a real read.** A test that calls `extract_and_save_memories` with a mocked `process_memory`, but with synthetic or non-existent message or conversation IDs, would now fail at this check.
  - Reading the two relevant tests suggests they are not affected. `test_extraction_and_summary_guards.py` rejects its synthetic batch earlier, in the parser. `test_p1_task1_strict_attribution.py` uses real scratch IDs.
  - This is unverified until tests are run.
- **No Task 4-specific tests** were written or run. The required regressions in the plan remain to be done after approval.

**Testing status: NOT RUN — intentionally deferred until the complete implementation has been reviewed and approved by the user.**
