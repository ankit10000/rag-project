# D4 fix report — fail-safe `decide_memories_to_delete()`

Date: 2026-11-11. Scope: D4 only. D5–D7, `decide_memory_action` (D3), detector (D1), D2 logic, storage, ownership, cleanup untouched. Nothing committed. No live Gemini (network blocked for every run). `rag_db` untouched.

## Defect
`decide_memories_to_delete()` called `generate_answer(prompt)` outside its `try`, so any LLM exception escaped to `delete_matching_memories` (its only caller). `None`/empty responses were already `UNCERTAIN` (the existing handler catches the resulting `TypeError`/`JSONDecodeError`).

## Change (one application file: `services/memory_decision_service.py`, `decide_memories_to_delete` only)
1. `generate_answer(prompt)` wrapped in `try/except Exception` → `{"status": "UNCERTAIN", "memory_ids": []}`; log is `Memory deletion decision LLM call failed (<ExceptionType>).` — type only, no message, prompt, request, memory text or key.
2. Explicit non-`str` response guard (None, int, list, dict, bytes, bool, object) → the existing `Memory deletion decision parsing failed.` message and `UNCERTAIN`.
3. Fallbacks are fresh dicts (not shared state). Status names, return shape, id validation/coercion (D5 untouched), fenced-JSON parsing and the no-memories → `NO_MATCH` shortcut are unchanged. `decide_memory_action` not touched in this step.

## Tests
- **New** `test_p1_d4_delete_decision_errors.py` (unit, registered): **54 PASS, 0 FAIL** — valid DELETE / NO_MATCH / UNCERTAIN / fenced / foreign-id / duplicates+order / unknown status unchanged; no-memories shortcut makes no LLM call; 10 exception types → `UNCERTAIN`, log contains the type only; 23 bad responses (None, empty, whitespace, int, float, bool ×2, list, valid-looking dict, bytes, object, malformed JSON, prose, JSON list/null/string/number, non-list `memory_ids` ×3, missing/null/list status) → `UNCERTAIN`, no ids, not raised; every failure mode never DELETE and never ids; fallback not shared state.
- **Edited** `test_p1_decision_parsing.py`: the `decide_memories_to_delete` RuntimeError probe is now an assertion (PASS 112 → 113, FINDING 3 → 2; remaining 2 are the D5 coercion probes, untouched).

## Results (executed)
| File | PASS | FAIL | FINDING lines |
|---|---|---|---|
| `test_p1_d4_delete_decision_errors.py` | 54 | 0 | 0 |
| `test_p1_d3_decision_errors.py` (D3) | 50 | 0 | 0 |
| `test_p1_decision_parsing.py` | 113 | 0 | 2 (D5) |
| `test_memory_delete_detector.py` (D1) | 213 | 0 | 3 (D6) |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 37 | 0 | 1 |
| `test_p1_delete_routing.py` (D1) | 137 | 0 | 0 |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |

Full default suite (`run_tests.py --clean`): **21 / 21 passed, 0 failed** (includes D1, D2 43-check test, D3); `rag_db` fingerprint unchanged: **True**.

## Mutation evidence (repo not edited; module loaded from modified source)
| Mutation | Test | Result |
|---|---|---|
| MA: remove LLM-exception handling | D4 test | caught: exit 1, 23 FAIL |
| MA | `test_p1_decision_parsing.py` | caught: aborts on the unhandled RuntimeError at the converted assertion |
| MC: remove exception handling + non-str guard | D4 test | caught: exit 1, 23 FAIL |
| MB: remove **only** the non-str guard | D4 test | **not caught (exit 0)** — equivalent mutant, see below |
| MD: remove non-str guard **and** `TypeError` from the existing parse handler | D4 test | caught: exit 1, 11 FAIL (non-str responses escape) |

**Honest note on MB:** in this function the pre-existing `except (…, TypeError)` already turns `re.sub(non-str)` into `UNCERTAIN` with the identical log message, so the new guard is defence-in-depth with no observable difference; no test can distinguish it. MD shows the tests do detect the loss of non-string handling once that second layer is gone.

## Safety
`rag_db` fingerprint unchanged; all runs on `rag_test_scratch`, network blocked, scratch emptied by `--clean`; no migration, no commit.

## Remaining limitations
- `except Exception` does not catch `KeyboardInterrupt`/`SystemExit` (intended).
- Id coercion (`True`, `2.7`, `"3.0"` → ids) is D5 and unchanged.
- A syntactically valid DELETE with real ids is still passed on; downstream D2 gate and ownership checks decide.
