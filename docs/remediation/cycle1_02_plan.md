# Cycle 1 - 02 Plan: Phase 1 tests P1-04 and P1-08

Role: planner. Code read: `main.py`, `services/memory_delete_service.py`, `memory_decision_service.py`, `automatic_memory_service.py`, `memory_storage_service.py`, `run_tests.py` CATEGORIES. Nothing executed. All behaviour below is CURRENT behaviour to pin (not endorsed).

## 0. Conventions for every file

- Header: `import testsafe` then `testsafe.require_scratch_db()` BEFORE importing `services.*` / `main`.
- Each file defines inline (about 20 lines, no shared helper module, so the runner registry stays clean):
  - `check(label, cond)`: prints `PASS | label` or `FAIL | label`, appends to a `FAILURES` list.
  - `probe(label, fn)`: runs `fn()` in try/except; `fn` returns `(is_defect: bool, detail: str)`. Prints `FINDING | label | detail` when is_defect, `PROBE-OK | label` otherwise, `FINDING | label | raised <Type>: msg` on exception. Probes NEVER touch `FAILURES`. A `FINDINGS` counter is printed at the end.
  - `quiet(fn, ...)`: `contextlib.redirect_stdout(io.StringIO())` wrapper (services print heavily); returns `(result, captured_text)` variant where output is asserted.
  - End of file: print `N check(s) failed, M finding(s)`; `sys.exit(1)` iff `FAILURES`.
- LLM mocks: `mock.patch.object(<module>, "generate_answer", ...)`; never call `services.llm_service` directly.
- DB tests: conversations via `create_conversation(...)` (two: `conv`, `other`), cleanup in `finally` (delete rows via `get_connection`, same style as `test_memory_sources_regression.py`; conversations deleted if a helper exists there, otherwise the scratch DB is wiped by runner `clean_scratch`).
- Embeddings (DB tests): patch `services.memory_storage_service.generate_embeddings` with a function returning a DISTINCT one-hot 384-vector per distinct text (dict text -> next index). Do NOT reuse `np.zeros(384)` here: zero vectors make `similarity` NaN/undefined and could mask or fake the 0.90 semantic-duplicate skip. Same text -> same vector (so duplicate-skip is testable deliberately).
- Failure injection convention: "failure" cases = mocked LLM raising/returning junk, or storage returning False/raising.
- Registration (section 6): keep the old live scripts unchanged except the detector rewrite.

---

## 1. `test_memory_delete_detector.py` (REWRITE) - unit

Purpose: pin the regex detector `is_explicit_memory_delete_request` (P1-04). Pure, no mocks, no DB (still starts with the testsafe header). Existing 15 cases are retained; script now `sys.exit(1)` on failure.

Hard-checked cases (message -> expected):

Positive (True):
1. "Forget my favourite colour", "forget everything", "Forget all the tests I wrote", "Forget me", "forget what I told you", "forget that I use vim", "forget the fact that I live in Delhi", "forget our plan", "Forget about my project" (pattern 1, `about` optional).
2. Prefixes: "Please forget my name", "kindly forget my name", "Can you forget my name?", "Could you forget my name", "Would you forget my name", "Will you forget my name", stacked "Could you please kindly forget my name".
3. "Erase my preferences", "Erase everything", "please erase all".
4. "Stop remembering my address", "please stop remembering".
5. Negated: "Don't remember my password", "Do not remember my password", "Dont remember my name", curly "Don’t remember my name", "Please don't store this", "Can you not..." is NOT included (see negatives), "do not keep it", "Don't save that".
6. Deletion terms: "Delete this memory", "Remove my preference from memory", "Clear my memories", "Wipe all memories", "erase this memory", "delete memory", "Remove the memory about X".
7. Normalisation: "FORGET MY NAME" (case), "  forget   my   name  " (extra spaces), "forget\nmy\tname" (newline/tab collapsed), "Delete\nthis\nmemory".

Negative (False):
8. Existing ones: "Don't forget to save", "I forget the formula", "I forgot my password", "Forget it, move on", "Hey, forget my name" (anchored, not at start), "Remove a column from the table", "Explain embeddings", "" (empty).
9. "Forget password reset steps" (no trigger word after forget), "forgetting my keys" (`forget\s+` needed), "Forget mystery novels" (`my\b` boundary), "Don't remember" (no trailing my/me/this/that/it), "Don't keep the logs" (no trailing my/me/this/that/it), "Don't forget to call me" (forget is not in pattern 3 verbs), "Deleting memory" (`\bdelete\b` does not match "deleting"), "memory delete" (wrong order), "Delete the memoryview" (`memory\b`), "I will remember you" , "What do you remember about me?".
10. Documented pin: "Would you don't remember my name" -> False (P3 prefix list lacks would/will you; P1 has them) - ambiguous, pin as-is.

Failure inputs (hard-checked, current behaviour):
11. `None` -> False; `""` -> False; `"   "` -> False; `0` and `[]` (falsy non-str) -> False.
12. Performance guard: `"a" * 100000` and `"delete " * 2000` complete in < 5 s (generous bound, hard check) and return False. Time printed.

Ambiguous/PROBE sections (print FINDING, do not fail):
- P-A false positives, expected-by-design False but current True: "How do I clear memory in Python?", "remove the memory leak", "delete memory from the cache", "How do I delete a file from memory?", "Don't save it as a PDF" (pattern 3 `it`), "Why do you stop remembering things?" (pattern 2 anywhere), "Forget all the tests I wrote" (pattern 1 `all`; arguably programming). Finding = True returned. Print the detector's result so the report lists each.
- P-B non-str truthy input: `123`, `["forget my name"]`, `b"forget my name"` -> currently raise `AttributeError`/`TypeError`. FINDING if it raises (record exception type); PROBE-OK if returns bool.
- P-C quadratic backtracking: `"delete " * 20000` timing; FINDING if > 2 s (print seconds). (Smaller 2000 size above is the hard check.)

Mocks: none.

---

## 2. `test_p1_decision_parsing.py` (NEW) - unit

Purpose: pin `decide_memory_action` and `decide_memories_to_delete` parsing, filtering and prompt contents with `generate_answer` mocked (P1-08). Import precedent: `test_model_fallback.py` (unit) already imports `services.llm_service` and `services.memory_decision_service`, so it imports under the runner. No DB used.

Mock: `mock.patch.object(services.memory_decision_service, "generate_answer", side_effect/return_value=...)`. Helper `run(fn, response, *args)` returns `(result, call_count, prompt)`; stdout captured.

### 2a. decide_memory_action (EXISTING = [(1, "User lives in Delhi"), (2, "User likes Python")])

Positive:
- Each action parsed and returned verbatim: `{"action":"NEW","memory_id":null,"updated_memory":null}` -> NEW; DUPLICATE (memory_id 1); UPDATE (memory_id 1, updated_memory "User lives in Mumbai") -> memory_id 1, updated_memory preserved; DELETE (memory_id 2, updated_memory null); UNCERTAIN.
- Lower/mixed-case `"update"`, `"Delete"` -> upper-cased.
- Fenced: "```json\n{...}\n```" and "```\n{...}\n```" parsed.
- `memory_id` passthrough unchanged: int 1, string "7", null, an id NOT in the list (99) is returned as-is (validation happens in `process_memory`).
- Empty/None existing memories: `existing_memories=[]` and `None` -> `{"action":"NEW","memory_id":None,"updated_memory":None}` and mock call_count == 0.
- Prompt checks (one call, `call_args.args[0]`): contains new_memory text, "ID: 1 | Memory: User lives in Delhi", "ID: 2 | Memory: User likes Python", "Never invent a memory ID", "Only use DELETE for an explicit request", "I no longer use X", "Return valid JSON only", generate_answer called exactly once.

Negative (-> UNCERTAIN with memory_id None, updated_memory None; "Memory decision parsing failed." printed):
- Unknown action "MERGE"; `{}` (missing action -> "" invalid); `{"action":""}`; `" UPDATE "` with spaces (no strip - pin); `{"action": null}`; `{"action": 5}`; `{"action": ["NEW"]}`.
- Empty string response, prose ("Sure, I think NEW"), truncated JSON `{"action": "NEW"`, prose + JSON ("Here you go: {...}") , JSON + trailing prose.
- Non-object JSON: `[]`, `["NEW"]`, `"NEW"`, `null`, `12`.

Ambiguous (hard-pinned current behaviour):
- Action UPDATE with `updated_memory` missing and memory_id missing returns UPDATE with None/None (not validated here).
- DELETE with memory_id as a string "abc" returned verbatim.
- Duplicate keys / extra keys ignored.

Failure / PROBE (FINDING, not failing):
- `generate_answer` returns `None`: currently `re.sub(None)` raises `TypeError` which is outside the `except (JSONDecodeError, ValueError, AttributeError)` tuple. FINDING if it raises; PROBE-OK if UNCERTAIN.
- `generate_answer` raises `RuntimeError("quota")`: propagates. FINDING if propagates.
- Print the actual exception type.

### 2b. decide_memories_to_delete (EXISTING = [(1,"A"),(2,"B"),(3,"C")])

Positive:
- `DELETE [1,3]` -> `{"status":"DELETE","memory_ids":[1,3]}`; order preserved `[3,1]`; duplicates `[1,1,2]` -> `[1,2]`.
- `NO_MATCH` and `UNCERTAIN` with extra ids `[1]` -> ids forced to `[]`.
- Status normalisation: "delete", " no_match ", "Uncertain".
- Fenced JSON.
- Id coercion (pin): `["2"]` -> `[2]`.
- Empty existing (`[]`, `None`) -> NO_MATCH, `[]`, call_count 0.
- Prompt checks: contains user request, "ID: 1 | Memory: A", all three ids, `"Forget everything about me" is broad`, "Never select memories from outside the provided list", "If status is NO_MATCH or UNCERTAIN, memory_ids MUST be []".

Negative:
- DELETE with only foreign ids `[99]` -> NO_MATCH `[]`; DELETE `[]` -> NO_MATCH; DELETE with `memory_ids` key missing -> NO_MATCH; mixed `[1, 99]` -> DELETE `[1]`.
- Non-list `memory_ids`: `"1,2"`, `{"a":1}`, `5`, `null` -> UNCERTAIN `[]`.
- Unknown status "MAYBE", missing status, `"status": null` (-> "NONE") -> UNCERTAIN `[]`.
- Unselectable items skipped: `["abc", null, [1], {"x":1}, 2]` -> DELETE `[2]` (TypeError/ValueError per item swallowed).
- Malformed JSON, prose, empty string -> UNCERTAIN; JSON list / string / null -> UNCERTAIN (AttributeError caught).
- `generate_answer` returns `None` -> UNCERTAIN (TypeError IS in the except tuple here; hard check, contrast with 2a).
- Existing memories with a non-numeric id (e.g. `[("x","A")]`) and a DELETE response -> `int("x")` ValueError caught -> UNCERTAIN (pin).

Ambiguous / PROBE (print FINDING when True, do not fail):
- Bool and float coercion: `[true]` -> `[1]`; `[2.7]` -> `[2]`; `["3.0"]` -> skipped. FINDING if bools/floats silently map to real ids.
- `generate_answer` raises `RuntimeError`: FINDING if it propagates (not caught).

---

## 3. `test_p1_process_memory.py` (NEW) - integration (scratch DB)

Purpose: pin `process_memory` branching and the automatic-extraction DELETE ban, and that `delete_matching_memories` is conversation-scoped. Real storage on scratch DB; embeddings patched (distinct one-hot); `automatic.decide_memory_action` and `automatic.decide_memories_to_delete` mocked. Spies: `mock.patch.object(automatic, "save_memory"/"update_memory"/"delete_memory", wraps=real)` so calls are countable while still writing.

Fixtures: `conv`, `other`; user messages `m1..m4` in `conv` (role user), assistant message `a1`, foreign user message `f1` in `other`. Seed helper `seed(conv, [texts])` -> list of ids through `storage.save_memory`. Row-fingerprint helper `rows(conv)` = `[(id, memory, str(embedding), source_message_id)]` ordered by id, for before/after equality.

### 3a. process_memory cases

No-candidate paths (decide mock must NOT be called):
1. empty conversation, default -> "SAVED", one row, text equals new_memory, source linked.
2. `allow_new=False` -> "SKIPPED", zero rows.
3. `delete_only=True` -> "UNCERTAIN", zero rows.
4. `candidate_memories=[]` supplied while an identical-text memory exists (same embedding) -> save_memory returns False (semantic duplicate) -> "SKIPPED"; row count unchanged; a `confirmation` source link is added to the existing row (pin).
5. Whitespace-only `new_memory` ("   ") with no candidates -> save returns False -> "SKIPPED", no row.

Candidate sourcing / normalisation:
6. `candidate_memories=None`: seed 22 memories; decide mock records `existing_memories`; assert passed list length 20 (limit), newest id first (DESC order).
7. Supplied `candidate_memories=[("5","x"),(None,"y"),("abc","z"),(7,"w")]` -> decide receives `[(5,"x"),(7,"w")]` (ints, invalid dropped).
8. All candidates unparsable (`[(None,"y")]`) behaves as "no candidates" (case 1 path; decide not called).

NEW:
9. decide NEW, default -> "SAVED", new row, seeded rows byte-identical (fingerprints).
10. decide NEW + `allow_new=False` -> "SKIPPED", no new row.
11. decide NEW but save returns False (patch `automatic.save_memory` return False) -> "SKIPPED".

DUPLICATE:
12. valid memory_id -> "SKIPPED", text/embedding unchanged, a `confirmation` link to the source message exists, row count unchanged.
13. memory_id None, memory_id not in candidates (foreign conv id) -> "SKIPPED", no link added (`confirm_memory` spy not called).

UPDATE:
14. valid id, new text "  User lives in Mumbai  " -> "UPDATED"; row text == stripped text; embedding string differs from before; other seeded rows unchanged; row count unchanged; `update` link to source present; earlier `origin` link retained.
15. memory_id as string "7" (int-coercible) -> "UPDATED" (normalisation).
16. memory_id None / id of memory in `other` conversation / id not among candidates -> "UNCERTAIN"; both conversations' rows unchanged; `update_memory` spy not called.
17. updated_memory None / "" / "   " -> "UNCERTAIN", rows unchanged, spy not called.
18. storage refuses (patch `automatic.update_memory` return False) -> "SKIPPED".
19. updated_memory non-str `123` -> stored as "123" (ambiguous, pin).
20. Contradictory fact scenario: seed "User lives in Delhi"; new "I moved to Mumbai"; decide returns UPDATE -> exactly one residence row, text Mumbai, and a second `process_memory` whose decide returns UNCERTAIN leaves it unchanged -> "UNCERTAIN". Different-project scenario: seed "Project A uses Python"; new "Project B uses Go"; decide NEW -> two rows; project A row unchanged.
21. Assistant message as source (`source_message_id=a1`) with UPDATE -> `ValueError` propagates, row fingerprint unchanged (transaction rolled back). Foreign-conversation source `f1` likewise.

DELETE ban (key safety property):
22. decide DELETE valid id, defaults -> "SKIPPED"; `delete_memory` spy not called; rows unchanged.
23. decide DELETE with INVALID id, defaults -> "SKIPPED" (ban checked before id check).
24. `allow_delete=True`, valid id -> "DELETED"; that row gone, others intact, other conversation intact.
25. `allow_delete=True`, invalid/None/foreign id -> "UNCERTAIN"; nothing deleted.
26. `allow_delete=True`, storage False (patch `automatic.delete_memory` False) -> "SKIPPED".
27. `delete_only=True`, DELETE valid -> "DELETED". `delete_only=True` with decide NEW, DUPLICATE, UPDATE, UNCERTAIN -> "UNCERTAIN", and save/update/confirm spies not called, rows unchanged.

Unknown / odd decisions:
28. action "MERGE", missing action key, `None`, lowercase " update " (normalised -> UPDATED if id valid), action "UNCERTAIN" -> "UNCERTAIN" / UPDATED as stated.

Failure:
29. `decide_memory_action` raises `RuntimeError` -> propagates out of `process_memory`; rows unchanged (pin; caller `memory_service.py` handles).

### 3b. delete_matching_memories cases (mock `automatic.decide_memories_to_delete`)

1. Conversation without memories -> `status "SKIPPED"`, `deleted_count 0`, `deleted_ids []`, classifier call_count 0, no `deleted_memories` key (pin).
2. Classifier call args: `existing_memories` == all `conv` memories ascending as `(int, text)` tuples (none from `other`), `user_request` passed through.
3. UNCERTAIN (even when mock also returns ids `[id1]`) -> "UNCERTAIN", `deleted_count 0`, `skipped_ids` == set of all ids, rows intact.
4. NO_MATCH -> "NO_MATCH", intact. DELETE with `memory_ids=[]` -> "NO_MATCH". DELETE with only foreign ids (an `other` memory id + a nonexistent id) -> "NO_MATCH"; `other` row intact; `delete_memory` spy not called.
5. DELETE mixed own + foreign ids -> "DELETED", only own removed, `other` row intact; `deleted_memories` has only own details.
6. DELETE success multi-id -> "DELETED", `deleted_ids` order == selected order, `deleted_count` N, `failed_ids []`, `skipped_ids` == unselected ids, `deleted_memories` entries contain `id`, `memory` (text captured before deletion) and `source_message_ids` including the origin message; rows gone; unselected rows and `other` conversation untouched.
7. Partial failure: `automatic.delete_memory` side_effect False for one id -> that id in `failed_ids`, others deleted, status "DELETED". Exception for one id (RuntimeError) -> in `failed_ids`, loop continues, no raise.
8. All fail (delete_memory always False) -> status "FAILED", `deleted_count 0`, `deleted_memories == []`, `failed_ids` == selected.
9. Classifier returns `{}` -> status default UNCERTAIN, nothing deleted.
10. Classifier raises RuntimeError -> propagates (pin).
11. Memory source cleanup contract: `get_memory_details` called with `conv` and selected ids (spy).

PROBE (FINDING, not failing):
- Unknown classifier status with ids, e.g. `{"status":"MAYBE","memory_ids":[id1]}`: status is not validated in `delete_matching_memories`, only `UNCERTAIN`/`NO_MATCH` short-circuit, so the memory is deleted. FINDING if a row was deleted. (Real classifier normalises unknown to UNCERTAIN, so latent only.)
- Classifier returning `status "DELETE"` with ids as strings `["5"]` -> filtered out (str not in int set) -> NO_MATCH. Report observed result.

---

## 4. `test_p1_memory_update_delete_integration.py` (NEW) - integration (scratch DB)

Purpose: row-level behaviour of `update_memory`, `delete_memory`, `get_memory_details` (replaces the hard-coded manual `test_memory_update.py` coverage). Embeddings patched with the distinct one-hot function; real DB.

update_memory:
- Positive: updates text (stripped) and embedding (`embedding::text` differs), same id, count unchanged, other rows and other-conversation rows unchanged, returns True; `source_message_id` set to new source and an `update` link added with older links retained; `source_message_id=None` leaves the previous `source_message_id` (COALESCE) and adds no link; `source_message_ids=[m2,m3]` links both.
- Negative: empty / whitespace text -> False, `generate_embeddings` NOT called (mock call_count), row fingerprint unchanged; nonexistent id -> False; id belonging to `other` conversation called with `conv` -> False and `other` row unchanged ("hijack").
- Failure: assistant message source -> `ValueError`, fingerprint unchanged; foreign-conversation source -> `ValueError`, unchanged; unknown message id -> `ValueError`; `generate_embeddings` raises -> propagates, row unchanged.
- Ambiguous (pin): same text as current (no-op update) -> True; `memory_id` as a numeric string works or not (record result; print as pin).

delete_memory:
- Positive: own row deleted -> True; row gone; sibling rows and `other` rows intact; second delete of same id -> False.
- Negative: nonexistent id (e.g. 2_000_000_000) -> False; id of `other` conversation called with `conv` -> False, row intact.
- PROBE: `memory_sources` rows for a deleted memory: print count after delete; FINDING if orphan rows remain (depends on FK cascade; do not assert). Non-int id `"abc"` -> record exception type (FINDING if it is an unclassified DB error, informational).

get_memory_details:
- Returns details for own ids only (foreign id absent), `{}` for empty list, includes legacy `source_message_id` fallback in `source_message_ids`.

---

## 5. `test_p1_delete_routing.py` (NEW) - integration (imports `main`, which imports `rag_service` and the retrieval stack; category integration for safety even though every collaborator is patched and no DB is touched)

Purpose: pin `main.main()` routing for P1-04: delete requests take the deletion branch only, with correct answers per status, cleanup rules and message persistence.

### 5.1 How main.py behaves (facts the design relies on)

- `main.py` calls bare `input()` twice: once for conversation id (`.strip()`), then inside `while True` for `"\nYou: "`. Both resolve through `builtins.input`, so patch `builtins.input` with an iterator. Exhausted iterator raises `StopIteration` (a test bug): the harness always ends the script with `"exit"` and fails the run if a StopIteration/EOFError escapes.
- Loop: `strip()`; `lower() == "exit"` -> print "Goodbye!" and break; empty -> continue; then ONE big `try` whose `except Exception` prints `\nError: {error}` (no crash).
- Delete branch (`is_explicit_memory_delete_request(query)` True): prints "Explicit memory deletion request detected."; calls `delete_matching_memories(conversation_id=..., user_request=query)` (keyword args); answer by status; saves user then assistant message (`save_message(conversation_id, "user", query)` then `"assistant", answer`, positional); prints answer; if `deleted_count > 0` calls `apply_deletion_cleanup(conversation_id=, deleted_memories=result.get("deleted_memories", []), extra_message_ids=[user_id, assistant_id], user_request=query)` in its own try/except (prints "Deletion cleanup: N message(s) excluded; summary: S." or "Warning: deletion cleanup failed; ... {err}"); then `continue` (history/summary/search/RAG/extraction/summary-update skipped).
- Answer text by branch (checked in order): status UNCERTAIN; SKIPPED; NO_MATCH; `deleted_count > 0`; else. The status of FAILED/DELETED/anything else with `deleted_count == 0` all fall into the last else.
- `process_memory` is imported by main but never called (unused import).

### 5.2 Patch set (all via `mock.patch.object(main, NAME, ...)`, applied by `run_main(inputs, **overrides)`)

| name in `main` | default |
|---|---|
| `builtins.input` | `side_effect=iter(inputs)` (patched on `builtins`) |
| `create_conversation` | returns `"conv-test"` |
| `conversation_exists` | returns True |
| `save_message` | `side_effect` counter returning 101, 102, 103... |
| `delete_matching_memories` | MagicMock, return set per scenario |
| `apply_deletion_cleanup` | `{"messages_excluded": 2, "summary_status": "UNCHANGED"}` |
| `ask_question` | `{"answer": "RAG ANSWER", "sources": []}` |
| `get_conversation_history` | `[]` |
| `get_conversation_summary` | `""` |
| `search_memories` | `[]` |
| `get_messages_for_memory_extraction` | `[]` |
| `extract_and_save_memories`, `update_memory_extraction_checkpoint`, `update_long_term_memory`, `process_memory` | MagicMock |

`is_explicit_memory_delete_request` is NOT patched (real detector) so detector + router are tested together; one test patches it to prove main trusts it. Stdout captured with `redirect_stdout`; `run_main` returns `(output_text, mocks_dict)`. Because every DB/LLM collaborator is patched, no DB or network is touched. Inputs always start with `""` (new conversation) and end with `"exit"` unless a scenario tests the resume prompt.

### 5.3 Test cases

Session handling:
- R1 `["", "", "   ", "exit"]` -> "Goodbye!", create_conversation called once, nothing else called, save_message not called.
- R2 `"EXIT"` and `"  exit  "` exit (case-insensitive, stripped).
- R3 resume: `["abc", "exit"]` with `conversation_exists` True -> create_conversation not called, conversation id used in later calls. Not found -> output "Conversation not found!", returns, input called once. `conversation_exists` raising `ValueError` -> "Invalid Conversation ID!", returns.

Delete branch by status (query "Forget my RAG project"; assert in every case: `delete_matching_memories` called once with `conversation_id="conv-test"`, `user_request="Forget my RAG project"`; `ask_question`, `get_conversation_history`, `get_conversation_summary`, `search_memories`, `get_messages_for_memory_extraction`, `extract_and_save_memories`, `update_memory_extraction_checkpoint`, `update_long_term_memory`, `process_memory` all NOT called; `save_message.call_args_list == [call("conv-test","user",query), call("conv-test","assistant",answer)]` in that order; output contains "Explicit memory deletion request detected." and the answer; answer printed before any "Deletion cleanup"):
- D1 UNCERTAIN: exact text "I'm not sure which memories you want me to forget. Could you specify the topic or information?"; cleanup NOT called.
- D2 SKIPPED: "There are no stored memories in this conversation, so nothing was deleted."; cleanup NOT called.
- D3 NO_MATCH: "I couldn't find any memories that clearly match your deletion request. No memories were deleted."; cleanup NOT called.
- D4 DELETED, `deleted_count=2`, `failed_ids=[]`, `deleted_memories=[{"id":1,...},{"id":2,...}]`: "Deleted 2 matching memory/memories."; cleanup called ONCE with `conversation_id="conv-test"`, `deleted_memories` == the same list, `extra_message_ids=[101,102]`, `user_request=query`; output has "Deletion cleanup: 2 message(s) excluded; summary: UNCHANGED."
- D5 DELETED with `deleted_count=1`, `failed_ids=[9,10]`: "Deleted 1 matching memory/memories. 2 deletion(s) could not be completed."; cleanup called.
- D6 FAILED, `deleted_count=0`, `failed_ids=[3]`: "No memories were deleted. The deletion operation could not be completed."; cleanup NOT called.
- D7 `{}` (missing keys) -> status defaults UNCERTAIN: D1 text, no cleanup.
- D8 DELETED with `deleted_count=0` (inconsistent) -> last-else text, no cleanup.
- D9 Inconsistent-but-pinned: status "UNCERTAIN" with `deleted_count=2` -> UNCERTAIN text AND cleanup still called (rule is `deleted_count > 0`, not status). Status "FAILED" with `deleted_count=1` -> "Deleted 1 ..." text + cleanup. Mark as ambiguous pin; print note only.
- D10 No `deleted_memories` key in result with `deleted_count=1` -> cleanup receives `deleted_memories=[]`.

Cleanup and error resilience:
- E1 `apply_deletion_cleanup` raises `RuntimeError("boom")` -> no exception escapes `main()`; output contains "Warning: deletion cleanup failed" and "boom"; both messages already saved (2 save_message calls); loop continues: a following input "What is RAG?" reaches `ask_question` and prints "RAG ANSWER"; then exit.
- E2 cleanup returns dict missing `messages_excluded` -> KeyError swallowed by the same except -> warning printed, no crash (pin).
- E3 `delete_matching_memories` raises -> output "Error: ...", `save_message` NOT called, cleanup NOT called, loop continues to exit.
- E4 `save_message` raises on the 2nd call (assistant) in the delete branch -> "Error:" printed; user message was already saved (1 call completed); cleanup NOT called.
- E5 `ask_question` raises in the normal branch -> "Error:" printed, no save_message, extraction not run, loop continues.

Normal (non-delete) routing:
- N1 "What is RAG?": `delete_matching_memories` and `apply_deletion_cleanup` NOT called; `get_conversation_history("conv-test", limit=16)`, `get_conversation_summary`, `search_memories(conversation_id="conv-test", query=..., top_k=5)` called; `ask_question(query=, history=, memory_summary=)` called once; `save_message` calls == user then assistant "RAG ANSWER"; `get_messages_for_memory_extraction(..., limit=4)` and `update_long_term_memory("conv-test", keep_recent=6)` called.
- N2 memory_summary composition: summary "S", `search_memories` returns `[{"memory":"M1"},{"memory":"M2"}]` -> `memory_summary == "S\nM1\nM2"`; summary "" -> "M1\nM2"; both empty -> "".
- N3 extraction threshold: `get_messages_for_memory_extraction` returns 3 messages -> `extract_and_save_memories` not called, output "Memory extraction skipped. 3 new messages; 4 required."; returns 4 messages (ids 11..14) -> `extract_and_save_memories(conversation_id=, messages=, source_message_id=14)` and checkpoint updated with `last_message_id=14`. Extraction raising -> Warning printed, checkpoint not updated, `update_long_term_memory` still called.
- N4 Ambiguous messages do NOT take the deletion path (real detector): "Forget it, move on", "Don't forget to save the file", "I forgot my password", "Hey, forget my name", "How do I remove a column?" -> `delete_matching_memories` not called, `ask_question` called, 2 messages saved.
- N5 Automatic extraction never receives a DELETE: across D1-D6 and N1, `process_memory` is never called (spy) and in the delete branch `extract_and_save_memories` is never called.
- N6 Query normalisation: input "  FORGET MY RAG project  " -> `delete_matching_memories(user_request="FORGET MY RAG project")` (stripped, case preserved).
- N7 Trust-the-detector: patch `main.is_explicit_memory_delete_request` to True for "hello" -> delete branch taken; to False for "forget my name" -> RAG branch taken.
- N8 Mixed session `["", "Forget my RAG project", "What is RAG?", "exit"]` -> save_message called 4 times, ids 101-104, the delete branch's extra_message_ids == [101, 102] only (not the RAG pair).

PROBES (print FINDING, never fail):
- P-R1 "How do I clear memory in Python?" and "remove the memory leak": FINDING if `delete_matching_memories` was called (legitimate programming question hijacked into the deletion flow; RAG is skipped and the user receives a "couldn't find any memories" reply). Run each with `delete_matching_memories` returning NO_MATCH and record the answer printed.
- P-R2 "Forget all the tests I wrote" same treatment.
- P-R3 `main()` with `input` raising `EOFError` at the prompt: record whether it propagates (informational only).

Total cost note: ~35 scenarios; each `run_main` call is milliseconds because everything is patched.

---

## 6. Registration in `run_tests.py` CATEGORIES (the only edit to that file)

- `unit`: add `test_memory_delete_detector.py` (remove it from `live`), `test_p1_decision_parsing.py`.
- `integration`: add `test_p1_process_memory.py`, `test_p1_memory_update_delete_integration.py`, `test_p1_delete_routing.py`.
- Leave `test_memory_conflicts.py`, `test_memory_decision.py`, `test_memory_delete_classifier.py`, `test_memory_delete_decision.py` in `live` unchanged, and `test_memory_update.py` in `manual`.
- Verify with `.venv\Scripts\python.exe run_tests.py --list` that no file is unclassified, then run each new file via `run_tests.py <file>` only.
- Fallback: if `test_p1_decision_parsing.py` fails to import under the unit runner (missing key in the scratch environment), move it to `integration`; `test_model_fallback.py` (unit) already imports the same modules so this is not expected.

## 7. Candidate-defect probe summary (all report-only)

1. Detector false positives (programming questions, "stop remembering" anywhere, "it" in pattern 3, "all" in pattern 1).
2. Detector raises on non-str truthy input; quadratic backtracking timing.
3. `decide_memory_action`: `None` response -> TypeError, `generate_answer` exception unhandled.
4. `decide_memories_to_delete`: bool/float id coercion; `generate_answer` exception unhandled.
5. `delete_matching_memories`: unknown classifier status with ids still deletes.
6. `main`: false-positive detector routes legitimate questions into the deletion flow and persists them; cleanup runs on `deleted_count > 0` regardless of status.
7. `delete_memory`: possible orphan `memory_sources` rows (informational).
8. Old live scripts exit 0 despite failures (already noted by the audit; no action in this cycle).

## 8. Implementation order and risks

Order: detector (1) -> decision parsing (2) -> process_memory (3) -> storage (4) -> routing (5) -> registration (6).
Risks for the executor: (a) importing `main` pulls in `rag_service`/embedding stack and may be slow or need the scratch DB, so keep it `integration`; (b) distinct embeddings are mandatory for DB tests (see section 0); (c) `get_recent_memories` limit test needs 22 distinct texts; (d) keep probes isolated so a probe exception never aborts later checks (`probe()` catches all); (e) rewrite of the detector must keep the original 15 cases verbatim.
