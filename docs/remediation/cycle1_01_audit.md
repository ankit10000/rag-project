# Cycle 1 - 01 Audit: Phase 1 test coverage for P1-04 and P1-08

Role: auditor (read-only except this doc). Nothing was executed; findings come from reading the code and tests.
Plan reference: B2 in `p4_07_verification_and_phase1_plan.md`.

## 1. Headline

- None of the six named tests is a verifying test. All six are registered under `live` (five) or `manual` (`test_memory_update.py`) in `run_tests.py` CATEGORIES. They need real Gemini (or a hard-coded conversation id) and the runner blocks the network, so they cannot pass or give signal in the deterministic suites.
- Only `test_memory_delete_detector.py` and `test_memory_delete_classifier.py` assert anything. Detector is pure and would be deterministic, but it is classified `live`. Classifier asserts against live LLM output.
- `test_memory_decision.py`, `test_memory_conflicts.py`, `test_memory_delete_decision.py` only `print`; they exit 0 whatever the model returns. `test_memory_update.py` uses a hard-coded conversation id and memory id 25 and would act on arbitrary data.
- None use mocks. No `test_p1_*.py` file exists yet.
- Partial incidental coverage exists in other files (mocked, scratch DB): `test_memory_sources_regression.py`, `test_phase5_provenance.py`, `test_deletion_cleanup.py`. They test source-linking and cleanup, not decision semantics.

## 2. P1-04 Explicit deletion detection

### Code under audit
- `services/memory_delete_service.py`: `is_explicit_memory_delete_request(message)`. 4 regexes after lowercase + whitespace collapse. Falsy -> False. No type guard (`re.sub` on non-str raises TypeError; `.lower()` on non-str raises AttributeError).
- `main.py` lines ~85-175: if detector True -> `delete_matching_memories`, build answer by status (UNCERTAIN / SKIPPED / NO_MATCH / deleted_count>0 / else), save user + assistant messages, `apply_deletion_cleanup` only if `deleted_count > 0` (cleanup exceptions caught), then `continue` (no RAG, no extraction). Non-delete messages proceed to history/summary/RAG.
- `services/automatic_memory_service.py::delete_matching_memories`: described in section 3.

### Existing: `test_memory_delete_detector.py`
- Exists: 15 (message, expected) pairs; PASS/FAIL printed; counts failures.
- Asserts: yes, per case, but the script ends with `print("N failure(s)")` and never calls `sys.exit(1)`. A failing case still exits 0, so the runner would report success. (Needs verification against how run_tests judges pass; not run.)
- Covers: forget my / forget everything / please forget / stop remembering / don't remember my / "delete this memory" / "remove my preference from memory"; negatives "Don't forget to", "I forget the formula", "I forgot my password", "Forget it, move on", "Hey, forget my", "remove a column", "Explain embeddings", empty.
- Registered as `live` although it is pure.
- Missing versus plan:
  - Positives: erase my; kindly/can you/could you/would you/will you prefixes; "do not remember/keep/store/save"; delete/remove/erase/clear/wipe + memory/memories variants; mixed case; extra whitespace/newlines; curly apostrophe (`don’t`); "forget about my ...", "forget what I", "forget the fact", "forget our".
  - Negatives: "forget" without trigger noun ("forget password reset steps").
  - Failure inputs: `None`, non-str (int, list), very long input with time bound (catastrophic backtracking check on `.*` patterns).
  - Probes (report only): "How do I clear memory in Python?", "remove the memory leak", "delete memory from the cache" - pattern 4 matches any delete/remove/erase/clear/wipe followed later by memory/memories. Expected: likely True (false positive).
  - Other likely-true surprises worth pinning/probing: "Don't remember to ..." patterns? Pattern 3 requires my/me/this/that/it anywhere later, so "Don't save it as a file" (programming) would match. "Forget me" / "Forget all the tests I wrote" match pattern 1 (`all`). "stop remembering" matches anywhere in the string, e.g. "Why do you stop remembering things?" -> True.
- Candidate defect (probe, not fixed): `None` input returns False (guarded by `if not message`), but non-str truthy input raises.

### Existing: routing in `main.main()`
- No test exists. Closest: `test_deletion_scenarios.py` and `test_deleted_facts_regression.py` drive `main.main` with real Gemini (`live`); `test_memory_sources_regression.py` replicates the main.py flow (delete_matching_memories with classifier mocked + apply_deletion_cleanup) but does not call `main.main`.
- Missing (plan row `test_p1_delete_routing.py`): delete request -> deletion path, `ask_question` and extraction never called; non-delete message -> RAG path and `delete_matching_memories` never called; automatic extraction never receives DELETE; ambiguous message ("Forget it, move on") -> normal flow; each status branch's user-visible answer text (UNCERTAIN, SKIPPED, NO_MATCH, DELETED with failed_ids suffix, FAILED); cleanup only when deleted_count>0; cleanup exception does not crash loop; both messages saved; `exit` and empty input handling. Needs `builtins.input` scripted and many `main` collaborators mocked (names to inspect in main.py imports before writing).

## 3. P1-08 Memory classification, conflict, update

### `decide_memory_action` (memory_decision_service.py)
Behaviours in code:
- empty/None `existing_memories` -> NEW with no LLM call.
- Prompt includes `ID: x | Memory: y` lines and safety rules.
- Response fences stripped; `json.loads`; `action` upper-cased via `result.get("action","").upper()`; unknown -> ValueError -> UNCERTAIN; catches JSONDecodeError, ValueError, AttributeError only.
- Returns `memory_id` and `updated_memory` verbatim (no id validation here; validation is in `process_memory`).
- NOT caught: `generate_answer` raising (propagates); `generate_answer` returning `None` (re.sub raises TypeError -> not in except tuple; and the `re.sub` is inside the try, so TypeError escapes); JSON list result (`.get` AttributeError -> caught, UNCERTAIN); `action` non-string e.g. `null`/int (`.upper()` AttributeError -> caught); `{"action": null}` -> `None.upper()` AttributeError caught.
- Candidate defects to probe: exception from `generate_answer` and `None` return are unhandled (TypeError). No test exists.

Existing tests: `test_memory_decision.py` (one live call, prints), `test_memory_conflicts.py` (3 live calls: additional DB, replacement, different projects; prints only), `test_memory_delete_decision.py` (2 live calls: explicit forget, factual change; prints only). Assert nothing, exit 0 always, depend on Gemini. All `live`.

Missing: every valid action parsed; fenced JSON; lower-case action; unknown action -> UNCERTAIN; malformed/empty/prose -> UNCERTAIN; JSON list; `None`/exception probes; string memory_id passthrough; empty existing -> NEW without calling `generate_answer`; prompt content asserts (all ids present, "never invent" rules).

### `decide_memories_to_delete`
Behaviours: empty memories -> NO_MATCH without LLM; status upper/strip, unknown -> UNCERTAIN; non-DELETE forces `[]`; non-list `memory_ids` -> UNCERTAIN; ids coerced `int()` (so `True` -> 1, `2.7` -> 2, `"3"` -> 3), invalid/foreign dropped, de-duplicated; all invalid -> NO_MATCH; parse errors (JSONDecodeError, ValueError, AttributeError, TypeError) -> UNCERTAIN, so `None` response (TypeError from re.sub) IS caught here, but `generate_answer` raising is not caught.
Note int coercion: bool True and float 2.7 map to existing ids silently; pin behaviour.
Existing: `test_memory_delete_classifier.py` - live, 6 cases x N runs, asserts status and id set, prints failure count, no `sys.exit(1)`. Registered `live`. Not deterministic (depends on model).
Missing: all of the deterministic parse/filter behaviours above; prompt asserts (candidate ids present, "forget everything" broad rule present); exception from `generate_answer`.

### `process_memory` (automatic_memory_service.py)
Branches to cover: candidate source (supplied vs `get_recent_memories`); id normalization drops non-int ids; no candidates (delete_only -> UNCERTAIN; `allow_new=False` -> SKIPPED; else save -> SAVED/SKIPPED); DELETE blocked unless `allow_delete` or `delete_only` -> SKIPPED; `delete_only` with non-DELETE -> UNCERTAIN; NEW (allowed / `allow_new=False` -> SKIPPED; save False -> SKIPPED); DUPLICATE (valid id -> `confirm_memory`, invalid -> not linked; always SKIPPED); UPDATE (invalid id -> UNCERTAIN; empty/whitespace text -> UNCERTAIN; success -> UPDATED; storage False -> SKIPPED); DELETE with `allow_delete` (invalid id -> UNCERTAIN; delete False -> SKIPPED; success -> DELETED); unknown action -> UNCERTAIN.
Existing coverage (mocked `decide_memory_action`, scratch DB): `test_memory_sources_regression.py` - UPDATED A->B->C source attribution, update with chain; `test_phase5_provenance.py` - DUPLICATE with provenance. Neither asserts NEW/allow_new, UPDATE invalid-id / empty-text, DELETE blocking, delete_only, unknown action, or contradictory-fact scenario.
Missing: everything in the "Branches" list except UPDATED/DUPLICATE source linking. Also nothing asserts text+embedding changed after UPDATE or that unrelated memories stay untouched. Note: `get_recent_memories` fetches all rows for the conversation (limit 20) - `ORDER BY id DESC` confirmation untested.
Observation: `process_memory` is only called in production from `memory_service.py` line 314 with `delete_only=False`, `allow_delete` default False; `main.py` imports it but does not use it (unused import). Automatic DELETE blocking is therefore the key safety property.

### `delete_matching_memories`
Branches: no memories -> SKIPPED (note: unreachable-code style - code after `return` is only an indented comment, fine); classifier UNCERTAIN -> nothing deleted, `skipped_ids`; NO_MATCH or empty selection -> NO_MATCH; ids outside conversation filtered; success -> DELETED with `deleted_memories` details captured before delete; `delete_memory` False -> failed_ids; exception per-id -> failed_ids; status FAILED when nothing deleted.
Existing: `test_memory_sources_regression.py` (~lines 158-170) mocks `decide_memories_to_delete` and runs delete + cleanup; asserts deleted memory details/sources. Not covered there (not verified in full): UNCERTAIN/NO_MATCH deleting nothing, foreign-conversation ids, partial failure, second-conversation untouched.
Observation: when classifier returns DELETE with ids all foreign, the result is NO_MATCH (via `not selected_ids`), return dict lacks `deleted_memories` key in non-DELETED returns (main.py uses `.get` so safe).

### Storage: `update_memory`, `delete_memory`
- `update_memory`: strips text; empty -> False; embeds (`generate_embeddings`); `_validate_source_messages` (raises on foreign/assistant source? - exact behaviour not re-read; test plan expects rejection); UPDATE scoped by `id` + `conversation_id` -> False for foreign conversation.
- `delete_memory`: nonexistent id -> False; ownership mismatch -> False; delete scoped by conversation.
- Existing: `test_memory_update.py` is a manual script with a hard-coded conversation id (991c4838-...) and memory id 25; asserts nothing; classified `manual` so it never runs. `test_memory_sources_regression.py` covers update-with-source idempotency and a foreign-conversation hijack check (line ~236: `update_memory(other, mid, "hijack") is False`) and foreign source rejection (~228). `test_memory_storage.py` is SMOKE_ONLY.
- Missing: update row-content assertions (memory text and embedding changed), empty/whitespace text rejected, assistant source rejected (partially covered ~228), unchanged row fingerprint after rejected update; `delete_memory` foreign-conversation and nonexistent id; deletion cascades to source links (not verified).

## 4. run_tests.py findings
- Categories: unit, integration, live, manual. Every named file is `live` except `test_memory_update.py` (`manual`). Moving or adding deterministic replacements to `unit` (no DB) or `integration` (scratch DB) is needed; new files must be added to CATEGORIES (runner flags unclassified files at line ~140).
- Pure detector tests belong in `unit`. Decision parsing (mocked `generate_answer`, but `import services.memory_decision_service` imports `services.llm_service` - confirm it imports without a key; also the `testsafe.require_scratch_db()` rule applies even to unit tests) -> `unit`. Anything touching `process_memory` or storage -> `integration`.
- The old live scripts should remain in `live` unchanged (Rules: pin, do not delete). Consider not editing them, only adding new files.
- Exit-code gap: several old scripts print failure counts but do not `sys.exit(1)`; the runner judges by exit code (assumption; verify in `run_tests.py` before relying).

## 5. Gap summary table

| Requirement | Exists | Asserts | Missing |
|---|---|---|---|
| P1-04 detector | 15 cases, live-category | per-case, no exit code | positives/prefix/whitespace/curly, failure inputs, long-input timing, probes |
| P1-04 routing (main.py) | none deterministic | n/a | whole file `test_p1_delete_routing.py` |
| P1-08 decide_memory_action | 3 live print scripts | nothing | whole parse matrix, None/exception probes, prompt asserts |
| P1-08 decide_memories_to_delete | live classifier (6 cases) | status+ids, live | deterministic parse/filter matrix, exception/None, prompt asserts |
| P1-08 process_memory | indirect (UPDATED, DUPLICATE) | source links only | NEW/allow_new, UPDATE guards, DELETE gating, delete_only, unknown, no-candidate paths, contradiction scenario |
| delete_matching_memories | partial (success path) | deleted details | UNCERTAIN/NO_MATCH, foreign ids, partial failure, isolation |
| update_memory/delete_memory | manual script, partial regression | foreign hijack, source rejection | row content, empty text, delete ownership |

## 6. Candidate defects (to probe, do not fix)
1. Detector false positives: "How do I clear memory in Python?", "remove the memory leak" (pattern 4: verb ... memory). Also possible: "Don't save it as a PDF" (pattern 3 with `it`), "stop remembering" anywhere in a sentence.
2. Detector raises on non-str truthy input (`re.sub`/`.lower()`); `None` is safe.
3. `decide_memory_action`: `generate_answer` raising propagates; `None` response -> TypeError (not caught). `decide_memories_to_delete` catches None (TypeError) but not a raising `generate_answer`.
4. `decide_memories_to_delete` int coercion accepts `True` and floats as ids.
5. Old tests exit 0 despite failures (no `sys.exit(1)`).

## 7. Recommended order of work (matches approved plan)
1. Rewrite `test_memory_delete_detector.py` (unit, pure).
2. `test_p1_decision_parsing.py` (mock `services.memory_decision_service.generate_answer`).
3. `test_p1_process_memory.py` (mock `services.automatic_memory_service.decide_memory_action`; patch `generate_embeddings` as in `test_memory_sources_regression.py`).
4. `test_p1_memory_update_delete_integration.py`.
5. `test_p1_delete_routing.py` (needs main.py collaborator inspection).
6. Register all in `run_tests.py`; reclassify the detector from `live`.
