# D5 fix report — strict memory-id validation in `decide_memories_to_delete()`

Date: 2026-11-11. Scope: D5 only. D6/D7, D1–D4 logic, storage, ownership, cleanup untouched. Nothing committed. No live Gemini (network blocked for every run). `rag_db` untouched.

## Defect
`decide_memories_to_delete()` ran `int(memory_id)` on every raw entry of the classifier's `memory_ids`, so `true` became id 1 and `2.7` became id 2 (`[true, 2.7]` → `[1, 2]`), turning invalid values into real memory ids.

## ID contract (after the fix)
| Raw JSON entry | Result |
|---|---|
| integer (`1`, `3`) | accepted if it is one of the provided memory ids |
| numeric string (`"2"`) | **still accepted** — existing, pinned contract (the earlier test `string id '2' coerced to 2` is unchanged); documented decision, not silently changed |
| `true` / `false` | rejected (never id 1/0) |
| any float (`2.7`, `2.0`, `1e0`, `-1.5`, `0.0`) | rejected, including whole-number floats |
| `null`, list, dict | rejected (nested lists are not unwrapped) |
| non-numeric / non-integer strings (`"abc"`, `""`, `"3.0"`, `"1,2"`, `"true"`) | rejected (`int()` raises → skipped, as before) |
| `0`, negative, unknown ints | dropped by the existing "must be in the provided list" filter (0 is valid only if it is a provided id); behaviour preserved |
| duplicates / order | order of first appearance kept, duplicates removed (unchanged) |
All-invalid list → `NO_MATCH` with `[]`. `NO_MATCH`/`UNCERTAIN` forcing `[]`, non-list `memory_ids` → `UNCERTAIN`, non-numeric existing id → `UNCERTAIN` are unchanged.

## Change (one application file: `services/memory_decision_service.py`, the id loop in `decide_memories_to_delete`)
Before `int()`: `if isinstance(memory_id, bool) or not isinstance(memory_id, (int, str)): continue`. Nothing else changed.

## Tests
- **New** `test_p1_d5_delete_ids.py` (unit, registered): **40 PASS, 0 FAIL** — integers, order, duplicates, unknown/zero/negative ints, `true`/`false`, positive/negative/whole-number/exponent floats, the audit repro `[true, 2.7]`, numeric and non-numeric strings, null, nested list, dict, mixed valid+invalid lists, "no invalid value selects any id from a list containing 0..11", "all-invalid never returns DELETE", unchanged surrounding behaviour.
- **Edited** `test_p1_decision_parsing.py`: the three D5 FINDING probes (bool, 2.7, "3.0") are now assertions (PASS 113 → 116, FINDING 2 → 0).

## Results (executed)
| File | PASS | FAIL | FINDING lines |
|---|---|---|---|
| `test_p1_d5_delete_ids.py` | 40 | 0 | 0 |
| `test_p1_decision_parsing.py` | 116 | 0 | 0 |
| `test_p1_d3_decision_errors.py` (D3) | 50 | 0 | 0 |
| `test_p1_d4_delete_decision_errors.py` (D4) | 54 | 0 | 0 |
| `test_memory_delete_detector.py` (D1) | 213 | 0 | 3 (D6 probes) |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 37 | 0 | 1 |
| `test_p1_delete_routing.py` (D1) | 137 | 0 | 0 |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |

Full default suite (`run_tests.py --clean`): **22 / 22 passed, 0 failed** (includes D1, D2 43-check test, D3, D4); `rag_db` fingerprint unchanged: **True**.

## Mutation evidence (repo not edited; module loaded from modified source)
| Mutation | Test | Result |
|---|---|---|
| MA: guard removed (original unsafe `int()` coercion) | D5 test | caught: exit 1, 16 FAIL |
| MA | `test_p1_decision_parsing.py` | caught: exit 1, 3 FAIL (the converted assertions) |
| MB: bool allowed again, floats still rejected | D5 test | caught: exit 1, 10 FAIL |
| MC: floats allowed again, bool still rejected | D5 test | caught: exit 1, 12 FAIL |

## Safety
`rag_db` fingerprint unchanged; all runs on `rag_test_scratch`, network blocked, scratch emptied by `--clean`; no migration, no commit.

## Remaining limitations
- Numeric strings are deliberately still accepted (`" 2 "`, `"+2"` also convert via `int()`); tightening this would change the existing contract and needs your decision.
- `delete_matching_memories` (D2) independently rejects bool/float ids, so there are now two layers.
- D6 (detector non-str input / repeated-"delete" timing) and D7 (`delete_memory` id validation) are untouched.
