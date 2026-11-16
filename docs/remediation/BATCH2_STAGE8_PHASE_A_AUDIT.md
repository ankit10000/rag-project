# Batch 2, Stage 8, Phase A: Memory Reliability & Classification Audit

**Date:** 2026-11-16. **Scope:** read-only audit.
**Not done:**
- No code, test, migration, dataset, scorer or configuration change.
- No database write.
- No Gemini or other LLM call.
- Nothing committed or pushed.

## 1. Git and environment preflight

| Item | Value |
|---|---|
| Branch / HEAD | `main` at `71767514a1e334af6c785f71c0dbc816c1674318` = `origin/main` (fetched) |
| Worktree | Only the untracked `docs/remediation/POST_MERGE_BASELINE_REPORT.md` from the previous task |
| Environment | Python 3.14.5 `.venv`, pins verified in the post-merge baseline; PostgreSQL 18.7 |
| Databases | `postgres`, `rag_db`, `rag_phase35_eval`, `rag_test_scratch` (unchanged; none created) |

## 2. Relevant architecture and call paths

**One turn** (`main.run_turn`, shared by the CLI and the API):
1. explicit-delete detection;
2. `get_conversation_history(limit=16)`;
3. `get_conversation_summary`;
4. **`assemble_memory_context(conversation_id, query, top_k=5, search_fn=search_memories)`**, then `memory_summary = summary + memory_context["text"]`;
5. `rag_service.ask_question`;
6. save the user and assistant messages;
7. extraction: when `get_messages_for_memory_extraction(limit=4)` returns ≥ 4 messages, call **`extract_and_save_memories(conversation_id=…, messages=…)`**, then `update_memory_extraction_checkpoint(last id)`. `MemoryExtractionError` leaves the checkpoint unchanged;
8. `update_long_term_memory`.

**Inside `rag_service.ask_question`:**
1. **`classify_question(query)`**: an LLM prompt, given the raw query only. A failure falls back to `DOCUMENT`.
2. `rewrite_query(query, history, memory_summary)`: an LLM call, only when there is history or memory. A failure falls back to the original query.
3. If the type is **`MEMORY`**: `results = []`, `retrieval_status = "not_run"`, no retrieval. Otherwise `hybrid_search_detailed(rewritten query)`.
4. Gating, then `assemble_context`, then `generate_grounded_answer(question_type=…)`.

**Memory processing** (`automatic_memory_service.process_memory`):
- source validation;
- `normalize_memory_text`: non-string or blank → **`UNCERTAIN`**;
- candidates;
- **exact-duplicate shortcut** (`find_exact_duplicate` → `confirm_memory` → `SKIPPED`, no model call);
- `decide_memory_action`, then the NEW / DUPLICATE / UPDATE / DELETE branches.

## 3. Failures: expected vs actual

### A. `test_p1_process_memory.py`
The reported symptom combines two separate problems.

| Check | Test expects | Actual (current code) | Effect |
|---|---|---|---|
| `[5]` `process_memory(conv, "   ", m1)` | `SKIPPED`, no row, no decision call | **`UNCERTAIN`**, no row, no decision call | FAIL (assertion) |
| `[7]` `process_memory(conv, "x", m1, candidate_memories=[("5","x"),(None,"y"),("abc","z"),(7,"w")])`, then `d.call_args.kwargs[...]` | `decide_memory_action` called with the normalised `[(5,"x"),(7,"w")]` | The new text `"x"` exactly duplicates candidate 5 → exact-duplicate shortcut → **`decide_memory_action` is never called** → `d.call_args is None` | **`AttributeError: 'NoneType' object has no attribute 'kwargs'`** (line 183). This is the reported error, and it **aborts the test file** |

**Consequence of the crash:**
- About **67 of 81** `check()` calls (plus the looped checks) after line 183 have not run since 2026-11-15. That covers `[8]`–`[27]` and all of `part_b()`.
- Among them are the **P1-03 DELETE-ban checks `[22]`–`[27]`** and the P1-05 isolation checks that `MASTER_GAP_REGISTER.md` cites as "VERIFIED COMPLETE (103 checks)".
- At least one of the hidden checks is also stale. `[19]` pins "non-str `updated_memory` 123 stored as `'123'`". Current `normalize_memory_text(123)` returns `None`, so the UPDATE path returns `UNCERTAIN` (confirmed without a database).
- How many other hidden checks are stale cannot be known without running the file past the crash, which writes to the scratch database (see 11).

### B. `test_p1_delete_routing.py` (134 PASS / 3 FAIL)

| Check | Test expects | Actual |
|---|---|---|
| `[N2]` summary + memories | With `search_memories` mocked as `[{"memory":"M1"},{"memory":"M2"}]` and summary `"S"`: `memory_summary == "S\nM1\nM2"` | `assemble_memory_context` reads `item["id"]` → `KeyError('id')` → `main.main` catches it per turn and prints `Error: 'id'` → **`ask_question` is never called** → the check compares `None` |
| `[N2]` memories only | `"M1\nM2"` | Same path |
| `[N2]` neither | `""` | PASS (no candidates, so no `id` access) |
| `[N3]` 4 messages | `extract_and_save_memories(conversation_id="conv-test", messages=batch, source_message_id=14)` | `extract_and_save_memories(conversation_id="conv-test", messages=batch)`: **no fallback source**. The checkpoint still advances to 14 (that check passes) |

Even with realistic mocked items (with `id`), the Phase 3 context step loads provenance from the database. The test's fake conversation id `conv-test` is not a UUID, so the step fails (`badly formed hexadecimal UUID string`). The fixture can no longer exercise `run_turn` without either mocking `assemble_memory_context` or supplying `provenance_fn`.

## 4. Root-cause evidence

| Evidence | Detail |
|---|---|
| DB-free reproduction, A | `process_memory(…, "   ", 1)` → `UNCERTAIN` (0 decision calls); `find_exact_duplicate("x", [(5,"x"),(7,"w")])` → `5` |
| DB-free reproduction, B | `test_p1_delete_routing.py` was run against a scratch-**named** database that does not exist (`rag_stage8_nonexistent_test`, so `testsafe` passes but any real connection would fail). Result: exit 1, **134 PASS / 3 FAIL**, exactly the 3 known checks, with **no connection attempted**. The actual `[N2]` / `[N3]` values above came from the same mocked harness |
| Real `search_memories` | Always returns `id` (`services/memory_search_service.py`), so the `[N2]` fixture shape is unrealistic. Not a product defect |
| History | Both test files were last changed in `3366ea8` (2026-11-12). Commit **`4a5e090`** (2026-11-15) changed **`main.py`** (switched to `assemble_memory_context`; removed the `batch_source_message_id = new_messages[-1]["id"]` fallback passed as `source_message_id`) and **`automatic_memory_service.py`** (Task 4 trim-only normalisation with blank → `UNCERTAIN`; Phase 3 exact-duplicate shortcut; no `str()` coercion). It updated 7 other test files, but **not these two** |
| Intended contracts | `memory_service.extract_and_save_memories` docstring: "`source_message_id` remains as a deprecated call-compatibility argument; it is deliberately never used as a fallback attribution" (Phase 1 Task 1). `normalize_memory_text`: "Returns None … callers must treat None as reject" (Phase 1 Task 4). `memory_context_service`: only `USER_SUPPORTED` memories (Phase 3) |

**Root cause (all four failing checks): tests not updated after the intended behaviour changes in `4a5e090`.** The code behaves as its Phase 1 / Phase 3 contracts state.
- **Pre-existing** since 2026-11-15, before Batch 1 (`90568c2`) and Batch 2. **Not a regression** of Stages 5–7.
- Earlier reports already listed both files as known failures (`BATCH2_STAGE4_INGESTION_REPORT.md`).
- Stage 6 and Stage 7 showed the failures identical at the pre-change HEAD.

## 5. MEMORY classification analysis

| Question | Answer from code / records |
|---|---|
| What is MEMORY? | The prompt in `classify_question`: "Questions about the user's project, preferences, **previous conversations**, personal details, or past decisions." DOCUMENT: "information contained in uploaded documents". MIXED: both |
| When is retrieval bypassed? | Exactly when the label is `MEMORY` (`rag_service.ask_question`, `retrieval_status = "not_run"`). The answer prompt still runs, with memory and history as non-evidence context and no sources |
| Follow-up questions | **Classified on the raw query alone.** `classify_question(query)` receives no history and no memory, and runs **before** `rewrite_query`. A follow-up such as "…after that trip?" refers to the previous conversation, which the prompt defines as MEMORY |
| Memory + documents together? | Yes: `MIXED` runs retrieval and passes memory as context. The design supports the distinction; the classifier just can't see what a follow-up refers to |
| Uncertain classification | A provider exception falls back to `DOCUMENT` (strictest). The label is parsed by substring with priority `MIXED` > `MEMORY` > otherwise `DOCUMENT`, so an unexpected reply is `DOCUMENT`. Edge: a reply mentioning both words (e.g. "DOCUMENT, not MEMORY") would parse as `MEMORY` |
| Deterministic? | **No.** It is a single LLM call (default sampling) and depends on which model serves it (fallback order under 429) |
| Recorded rates (Tier 2 dev, 42 cases) | Stage B baseline: DOCUMENT 36, MIXED 4, **MEMORY 2** (`C-direct-05`, `D-follow_up-04`). Stage 6 live: DOCUMENT 37, MIXED 4, **MEMORY 1** (`D-follow_up-04`). MIXED was the same 4 in both: `A-multipage-03`, `B-follow-03`, `D-multi_page-03`, `D-multi_page-04` (harmless: retrieval runs) |

## 6. `D-follow_up-04` and `C-direct-05`

**`D-follow_up-04`** (follow_up):
- **Question:** "How long must I wait before restarting after that trip?"
- **History:** E-41 is a bearing-overheat fault on Aquaflow pumps. Gold: Aquaflow manual p.3.
- **What happened, in both runs:** classified MEMORY → retrieval skipped (`not_run`, 0 retrieved) → refusal → incorrect. In the live run the classify call hit 429 on the primary and was served by `gemini-3.1-flash-lite`; a rewrite call also ran, but its standalone query was never used for classification or retrieval.
- **Cause:** a **deterministic design gap**, made worse by the prompt wording. The classifier sees only "…after that trip?", a reference to the previous conversation, which the prompt calls MEMORY. The rewritten, self-contained query exists, but only after classification.
- **Classification:** pre-existing, not a regression.

**`C-direct-05`** (direct_factual):
- **Question:** "What would a spare burr set for **my** B3 espresso machine set me back?"
- **What happened:** Stage B classified it MEMORY (no retrieval → abstained); Stage 6 live classified it DOCUMENT (retrieved the gold page → answered "£34 [S1]", correct). In the live run it was served by the fallback model; the baseline's model is not recorded.
- **Cause:** **classifier non-determinism** on a personal-pronoun document question ("my …" looks like "personal details"). Whether the flip came from sampling or from the model differing cannot be told from the records.
- No code change was involved.

## 7. Related or independent?

| Issue | Root cause | Relation |
|---|---|---|
| A `[5]`, A `[7]` (+ hidden `[19]`) | Test drift after `4a5e090` (Task 4 normalisation, Phase 3 exact duplicate) | Same commit as B, **independent** of classification |
| B `[N2]` ×2 | Test drift after `4a5e090` (Phase 3 memory context) | Same commit as A |
| B `[N3]` | Test drift after `4a5e090` (Task 1: no fallback source) | Same commit as A |
| `D-follow_up-04` | Classifier sees the raw follow-up without history, before the rewrite | **Independent** of A/B; a product behaviour |
| `C-direct-05` | LLM non-determinism / model variation in the classifier | Related to the same component as `D-follow_up-04`, but a different mechanism |

## 8. Minimal proposed fixes (not implemented)

**P1: fix test drift in `test_p1_process_memory.py` (tests only, no product change):**
- `[5]`: expect `UNCERTAIN` (Task 4 contract).
- `[7]`: split it in two.
  - (a) Use non-duplicate new text (e.g. `"something else"`) so `decide_memory_action` runs and candidate normalisation is still tested.
  - (b) Add an explicit check that an exact duplicate takes the shortcut (decide not called; a confirmation link is attempted only for an owned memory).
- Guard `call_args` so that a later drift fails as a check instead of aborting the file.
- `[19]`: expect `UNCERTAIN`, with no `str()` coercion (Task 4).
- Then run the **whole** file and review every further failure **individually**. Each must be classified as stale (update the test to the documented contract) or as a **real defect** (stop and report; don't hide it). This step restores the P1-03 / P1-05 verification that has silently not run.

**P2: fix test drift in `test_p1_delete_routing.py` (tests only):**
- `[N2]`: patch `main.assemble_memory_context` to return a known `{"text": "CTX"}` and assert `memory_summary == "S\nCTX"` / `"CTX"` / `""`. This tests `run_turn`'s composition contract. Memory filtering stays covered by the Phase 3 tests.
- `[N3]`: expect `extract_and_save_memories(conversation_id="conv-test", messages=batch)` (no `source_message_id`), and assert that no fallback source is passed.

**P3: classification of follow-ups (product change; needs a separate decision). Options, smallest first:**
1. **Classify the rewritten query.** Run `rewrite_query` before `classify_question` and classify the rewritten standalone query. No extra LLM call: both calls already run whenever there is history. Changes the order in `rag_service.ask_question` only.
2. Pass the recent history to `classify_question`. Larger prompt change.
3. Narrow the MEMORY definition in the prompt, so that "previous conversations" doesn't capture document follow-ups. Prompt change; its effect is LLM-dependent.
4. Never skip retrieval for MEMORY (treat it like MIXED). The largest contract change: it affects citation requirements and the MEMORY answer path.

**Recommendation for P3:** option 1, validated by unit tests (a fake LLM records the query the classifier receives) **and** a dev-only live check of the 2 MEMORY-misrouted cases plus the 4 MIXED cases. It cannot be proven offline, because classification is an LLM call. `C-direct-05`-style non-determinism is **not** fixed by option 1 (it has no history); it would need option 3 or a deterministic pre-check, which is a separate decision.

## 9. Regression test plan

| Fix | Tests |
|---|---|
| P1 | The whole `test_p1_process_memory.py` runs to completion (no abort); `[5]`, `[7a]`, `[7b]`, `[19]` pass under the documented contracts; every previously hidden check either passes or is triaged in writing; `[22]`–`[27]` (DELETE ban) are executed again. Plus the Stage 7 suite, `test_p1_task1`…`task3`, `test_phase5_provenance` |
| P2 | `test_p1_delete_routing.py` passes 137/137, with `[N2]` and `[N3]` asserting the current contracts; plus `test_p1_task1_strict_attribution` (checkpoint), `test_stage7_memory_provenance` (checkpoint advance) |
| P3 (if approved) | New unit test: with history, the classifier receives the rewritten query; without history, the original. Provider failure in rewrite still classifies the original query. The MEMORY path still skips retrieval. Full Stage 6 suite. A dev-only live spot check (≈ 6 cases, ≈ 12–20 Gemini calls) reported separately |
| All | The full `run_tests.py`: expected **48/48** after P1 + P2, with any newly surfaced hidden-check result reported, not assumed |

## 10. Risks and compatibility

- **P1/P2 change only test expectations.** The risk is codifying a wrong behaviour. Mitigation: every new expectation cites the documented contract (Task 1 / Task 4 / Phase 3). Any hidden-check failure that doesn't match a documented contract is treated as a possible defect and reported, not "fixed" by editing the test.
- **The hidden checks may reveal real defects.** About 67 checks, including the DELETE ban, haven't run for a day of active development (Batch 1, Stages 4–7). Some failures beyond `[19]` are possible. This is the main reason to do P1 before anything else.
- **P3 changes product behaviour.** It alters which query the classifier sees. It could move some MIXED/MEMORY labels to DOCUMENT or vice versa; MEMORY-only questions (user preferences) must still classify as MEMORY. It touches `rag_service`, a Stage 6 file, and the Stage 6 tests that mock `classify_question` / `rewrite_query` order (`test_b3`, `test_stage6_answer`). Measured only by a live dev check.
- **No impact** on retrieval thresholds, H.1, grounding, Stage 7 provenance or deletion semantics.

## 11. Database safety confirmation

- No database write and no database creation.
- The failure B reproduction targeted a **nonexistent** scratch-named database: no connection was attempted.
- The failure A reproduction was pure Python (no database path reached).
- Fingerprints of `rag_db`, `rag_test_scratch` and `rag_phase35_eval` are **identical** to the post-merge baseline after the audit.
- **Phase B setup required:** running `test_p1_process_memory.py` to completion writes fixture rows. It must go through `run_tests.py` against `rag_test_scratch`, which is empty, guarded by `testsafe`, and deletes its own conversations in `finally`. Before and after, run the read-only fingerprints of all three databases; no `--clean`.

## 12. Final recommendation

**Proceed to Phase B, limited to P1 and P2 (tests only), with P1 first.** P1 restores roughly 67 silently skipped memory checks, including the DELETE ban. Any real defect it surfaces must be reported before it is fixed.

**P3 (classification) needs a separate decision.** I recommend option 1 (classify the rewritten query), with a small dev-only live validation, as its own step after P1/P2. Option 3 or a deterministic pre-check for `C-direct-05`-style flips is optional and later.

No fix has been implemented.
