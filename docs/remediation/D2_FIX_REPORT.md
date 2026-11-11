# D2 fix report — fail-safe classifier status in `delete_matching_memories`

Date: 2026-11-11. Scope: defect D2 only (D1, D3–D7 untouched). Nothing committed. No live Gemini call (network blocked for every run). `rag_db` untouched.

## The defect
`delete_matching_memories()` only rejected the statuses `UNCERTAIN` and `NO_MATCH`. Any other value (e.g. `"MAYBE"`, `None`, a list) together with a valid memory id fell through to the deletion loop. (Latent in production because the real classifier normalises unknown statuses, but the deleting function had no defence of its own.)

## Change (one application file)
`services/automatic_memory_service.py`, inside `delete_matching_memories()` (new lines ≈276–330):
1. If the classifier result is not a `dict` it is treated as `{}` (→ `UNCERTAIN`, as before for an empty dict).
2. `memory_ids` that is not a list is treated as empty.
3. Selected ids must be genuine `int`s (not `bool`, not unhashable values) that belong to this conversation; the existing `in valid_ids` filter is kept.
4. **New gate (l.321):** `if decision_status not in ("DELETE", "NO_MATCH")` → return `UNCERTAIN`, `deleted_count 0`, nothing deleted. Because `UNCERTAIN` is handled just above, the only status that can reach the deletion loop is exactly the string `"DELETE"` (case-sensitive, no whitespace tolerance — deliberately fail-safe).

Unchanged: the classifier (`memory_decision_service.py`), its status definitions, `delete_memory` and its ownership check, return shapes, `NO_MATCH`/`UNCERTAIN` results, `DELETE` + empty ids → `NO_MATCH`.

## Required behaviour → evidence
| # | Requirement | Test evidence (all executed) |
|---|---|---|
| 1 | Explicit `DELETE` preserved | `[delete]` checks: DELETED with exactly the intended id, `delete_memory` called once with that `memory_id`, row and its `memory_sources` links gone, sibling memory intact, `deleted_memories` captures text/sources, other conversation untouched; mixed own + foreign + junk ids delete only the own valid id |
| 2 | `UNCERTAIN` no delete | blocked + `[pin]` check |
| 3 | `NO_MATCH` no delete | blocked + `[pin]` check |
| 4 | Unknown status | `MAYBE`, `delete`, `Delete`, ` DELETE`, `DELETE `, `DELETED`, `""`, `TRUE`, `YES`, `ALL` → `UNCERTAIN`, nothing deleted |
| 5 | Missing / None status | key missing, `None` → `UNCERTAIN` |
| 6 | Invalid status type | `1`, `True`, `['DELETE']`, `{...}`, `b'DELETE'` → `UNCERTAIN`; malformed whole result (`None`, list, string, `{}`) → `UNCERTAIN` |
| 7 | Invalid / missing ids | with `DELETE`: key missing, `None`, `[]`, string, bare int, string ids, float ids, `True`, unhashable list, `None` entry, nonexistent/negative → `NO_MATCH`, nothing deleted |
| 8 | Ownership & isolation | `DELETE` with only another conversation's id → `NO_MATCH`, `delete_memory` not called, both conversations byte-identical; `delete_memory`'s own ownership check untouched |
| 9 | No unrelated behaviour change | all 18 earlier tests + 5 other Cycle-1 files pass unchanged (below) |

For every blocked case the test asserts: result status, `deleted_count == 0`, `deleted_ids == []`, **`delete_memory` call_count 0**, and a full before/after snapshot of memories (including the embedding text) and `memory_sources` for both the target and the other conversation.

## Test changes
- **New** `test_p1_d2_classifier_status.py` (integration, registered in `run_tests.py`): real storage + scratch DB, only `decide_memories_to_delete` mocked, one-hot embeddings patched, conversations created per test (no hard-coded ids), cleaned up in `finally`. **43 PASS, 0 FAIL.**
- **Edited** `test_p1_process_memory.py`: the D2 FINDING probe is now a real assertion (`[D2] unknown status 'MAYBE' with a valid id -> UNCERTAIN, nothing deleted`, with `delete_memory` spy and DB state check). PASS 103 → 104, FINDING lines 1 → 0.
- **Edited** `run_tests.py`: registered the new file under `integration`.

## Results (exact, executed in this session)
Focused D2 file: `exit=0 PASS=43 FAIL=0`.

All six Cycle-1 files (network blocked, scratch DB):
| File | PASS | FAIL | FINDING lines |
|---|---|---|---|
| `test_memory_delete_detector.py` | 75 | 0 | 11 |
| `test_p1_decision_parsing.py` | 110 | 0 | 5 |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 37 | 0 | 1 |
| `test_p1_delete_routing.py` | 121 | 0 | 3 |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |
| (sum) | 501 | 0 | 20 |

Full default suite (`run_tests.py --clean`):
```
run / passed / failed : 19 / 19 / 0
of the passes, smoke-only (exit code only, no assertions) : 2 ['test_similarity.py', 'test_memory_storage.py']
not run (by category) : 18
application database 'rag_db' fingerprint unchanged : True
```

## Mutation evidence
The repo files were not edited; the module was loaded from source with parts of the fix removed in memory.
| Mutation | Test run | Result |
|---|---|---|
| **MA:** remove only the explicit-DELETE-only gate (l.321 block) | `test_p1_d2_classifier_status.py` | **caught: exit 1, 17 FAIL** (e.g. `MAYBE`, `delete`, `DELETED`, `""`, `YES`, `None`, `1`, `True`, `['DELETE']` all fail to block) |
| MA | `test_p1_process_memory.py` | caught: exit 1, 2 FAIL (the converted D2 assertion plus one status-dependent check) |
| **MB:** full revert to the pre-fix code (gate + dict/list/int guards) | D2 test | caught: exit 1, 16 FAIL after the run aborted (the original code raises on a `None` classifier result) |
| MB | `test_p1_process_memory.py` | caught: exit 1, 2 FAIL |
With the gate removed the valid-`DELETE` checks still pass (27 PASS under MA), confirming the failures are specific to the safety restriction.

## Database safety evidence
- `rag_db` row counts before and after: 261 conversations, 1,340 messages, 127 memories, 93 links, 9 chunks; runner fingerprint "unchanged: True".
- All tests ran with `DATABASE_URL` pointing at `rag_test_scratch`, network blocked (`TESTSAFE_BLOCK_NETWORK=1`); scratch DB emptied by `--clean` afterwards.
- Files newer than the re-audit report under `services/` and `main.py`: only `services/automatic_memory_service.py`.

## Remaining limitations
- The gate is case-sensitive and exact by design (`"delete"` is blocked); the real classifier already upper-cases/normalises, so production behaviour is unchanged.
- D1 and D3–D7 are not fixed. D2's neighbouring risk remains: the detector still sends false positives (D1) into this function; this fix only guarantees that an unclear classifier answer cannot delete.
- `[true]`/`2.7` coercion inside the classifier (D5) still happens upstream; `delete_matching_memories` now rejects bool/float ids on its own side, but an `int`-coerced `1`/`2` from `decide_memories_to_delete` still passes.
- Mutation harness lives outside the repo (job temp folder), not part of the committed suite.
