# D7 fix report — safe memory-id validation in `delete_memory()`

Date: 2026-11-11. Scope: D7 only. D1–D6 not reopened. Nothing committed. No live Gemini (network blocked for every run). `rag_db` untouched. "Executed" = run in this session; "static" = code inspection.

## Root cause
`services/memory_storage_service.py::delete_memory(conversation_id, memory_id)` passed `memory_id` straight into SQL (`WHERE id = %s`). `id` is `bigint`; psycopg sends strings as untyped text, so PostgreSQL cast them itself: `"abc"` or a full-width digit raised a raw `psycopg.errors.InvalidTextRepresentation`, and out-of-range ints would raise a numeric-overflow error. (Executed probe on the scratch DB: `2`, `"2"`, `" 2 "`, `"+2"`, `"-2"` all worked; `"２"` (full-width digit) raised.)

## Existing API contract (static + executed)
- Returns `bool`: `True` = row existed in this conversation and was deleted; `False` = nonexistent id, other conversation's id (ownership check), or already deleted. Genuine DB failures propagate.
- Callers (static): `process_memory` (id from `normalize_memory_id`, always `int`, after `memory_id in valid_ids`) and `delete_matching_memories` (ints validated by D2); tests/manual scripts pass ints. No caller passes strings today.
- Zero / negative ints: valid integers that match no row → `False` (unchanged).
- No new return type is introduced.

## Change (one application file: `services/memory_storage_service.py`; added `import re`)
New `_valid_memory_id()` called at the top of `delete_memory`, before any diagnostics/SQL:
| Input | Result |
|---|---|
| genuine `int` within bigint range (incl. 0, negatives) | accepted, goes to SQL (0/negative simply match no row) |
| `bool` (`True`/`False`) | rejected |
| any `float` (`2.7`, `2.0`, `0.0`, `inf`, `nan`) | rejected |
| ASCII integer strings `"2"`, `" 2 "`, `"+2"`, `"-2"`, `"\t2\n"`, `"002"` | **accepted — existing compatibility preserved** (they already worked via the PostgreSQL cast); converted to `int` before SQL |
| other strings (`"abc"`, `""`, `" "`, `"2.0"`, `"1e1"`, `"0x2"`, `"2 3"`, `"2abc"`, `"--2"`, `"2;DROP"`, full-width / Arabic-Indic digits) | rejected |
| `None`, list, tuple, set, dict, bytes, objects | rejected |
| ints outside bigint range (`2**70`, `-2**70`) | rejected |
Rejected input → prints `Memory deletion refused: invalid memory ID (type <T>).` (type only, never the value), returns `False`, **no connection is opened, no SQL runs**. Ownership check, the `AND conversation_id = %s` delete clause, commit behaviour, provenance and cleanup are untouched. Only the input check is handled; DB exceptions are not caught.
Numeric-string decision: kept (not silently changed), documented and tested; it is the narrowest rule that preserves everything that worked before while removing the raw-error cases.

## Tests (executed)
- **New** `test_p1_d7_storage_id_validation.py` (integration, scratch DB, registered): **52 PASS, 0 FAIL** — 32 invalid inputs (each: `False`, no exception, `get_connection` call count 0, full DB snapshot of both conversations unchanged); existing row id disguised as float/bool/list/dict/`"N.0"`/`"Nx"` deletes nothing; valid int deletes only that row and its links, sibling and other conversation intact, second delete → `False`; 5 numeric-string forms delete exactly that memory; zero/negative/`"-5"`/nonexistent/bigint max/min → `False`, nothing deleted; foreign-conversation id as int and numeric string → `False`, ownership check ran, rows intact; a genuine `RuntimeError` from the connection still propagates; log shows type only.
- **Edited** `test_p1_memory_update_delete_integration.py`: the D7 FINDING probe is now `[d4] non-int id 'abc' -> False, no exception` (PASS 37 → 38, FINDING 1 → 0). The unrelated orphan-links INFO line was already not a finding.
- `run_tests.py`: new file registered under `integration`.

## Results (executed)
| File | PASS | FAIL | FINDING |
|---|---|---|---|
| `test_p1_d7_storage_id_validation.py` | 52 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 38 | 0 | 0 |
| `test_memory_delete_detector.py` (D1/D6) | 271 | 0 | 0 |
| `test_p1_decision_parsing.py` | 116 | 0 | 0 |
| `test_p1_d3_decision_errors.py` | 50 | 0 | 0 |
| `test_p1_d4_delete_decision_errors.py` | 54 | 0 | 0 |
| `test_p1_d5_delete_ids.py` | 40 | 0 | 0 |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_delete_routing.py` | 137 | 0 | 0 |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |
Full default suite (`run_tests.py --clean`): **23 / 23 passed, 0 failed** (includes D2's 43-check test and memory-sources/provenance/deletion-cleanup tests); `rag_db` fingerprint unchanged: **True**.

## Mutation evidence (executed; repo not edited, module loaded from modified source)
| Mutation | Test | Result |
|---|---|---|
| MA: validation removed | D7 test | caught: exit 1, 32 FAIL (then aborted by a raw DB error) |
| MA | memory update/delete integration | caught: 2 FAIL |
| MB: bool allowed again | D7 test | caught: 3 FAIL |
| MC: floats allowed again | D7 test | caught: 8 FAIL |
| MD: invalid values passed on to SQL | D7 test | caught: 33 FAIL (then aborted by a raw DB error) |
| MF: all exceptions swallowed (DB errors disguised) | D7 test | caught: 2 FAIL |
| MG: ownership bypassed completely (mismatch check **and** `AND conversation_id` clause removed) | D7 test | caught: exit 1, 3 FAIL |
| ME: only the first ownership check removed | D7 / integration | **not caught — equivalent mutant**: the `DELETE … AND conversation_id = %s` clause is a second layer that yields the same `False`; MG shows the tests detect the loss of ownership enforcement once both layers are gone |
MG on the integration test was not interpretable (the mutated delete statement broke that file's parameter count); only the D7 result is claimed.

## Safety (executed)
`rag_db` fingerprint unchanged; all runs on `rag_test_scratch`, network blocked, scratch emptied by `--clean`; no schema/migration change; no commit.

## Remaining limitations
- `update_memory` and `get_memory_details` do not have the same boundary check (out of scope; they were not part of D7).
- Numeric strings with surrounding whitespace/sign are still accepted by design; changing that is a contract decision for you.
- The pre-existing `process_memory` normaliser (`int(memory_id)`) can still turn a classifier `True`/`2.7` into an int before it reaches storage; D5 fixed the classifier, this boundary now guards storage only for direct callers.
- `delete_memory` still leaves no orphan links (FK cascade verified by earlier tests); no cleanup semantics were changed.
