# D3 fix report — fail-safe `decide_memory_action()`

Date: 2026-11-11. Scope: D3 only. D4 (`decide_memories_to_delete`), detector (D1), D2 logic, storage, ownership, cleanup untouched. Nothing committed. No live Gemini (network blocked for every run). `rag_db` untouched.

## Defect
In `services/memory_decision_service.py::decide_memory_action`, `generate_answer(prompt)` ran before the `try`, so any LLM exception escaped; a `None` (or other non-string) response made `re.sub` raise `TypeError`, which the `except` (JSONDecodeError/ValueError/AttributeError) did not cover.

## Change (one application file: `services/memory_decision_service.py`, `decide_memory_action` only)
1. `generate_answer(prompt)` is wrapped in `try/except Exception` → returns `UNCERTAIN` (`memory_id` None, `updated_memory` None). The log prints only the exception **type** (`Memory decision LLM call failed (RuntimeError).`) — no message, prompt, memory text or key.
2. A non-`str` response (None, int, list, dict, bytes, …) → prints the existing `Memory decision parsing failed.` and returns `UNCERTAIN`.
3. Existing parsing, allowed actions, return structure, the "no existing memories → NEW without LLM call" short-circuit and the parse-failure `except` are unchanged. Fallbacks are fresh dicts (not shared state).
Callers: only `automatic_memory_service.process_memory`, which still treats `UNCERTAIN` as no action (and blocks DELETE outside delete mode — unchanged).

## Tests
- **New** `test_p1_d3_decision_errors.py` (unit, registered in `run_tests.py`): 50 checks, 0 FAIL — all five valid actions unchanged (+ fenced/lower-case); 10 exception types (RuntimeError, ConnectionError, TimeoutError, ValueError, KeyError, OSError, Exception, AttributeError, TypeError, JSONDecodeError) → UNCERTAIN and log contains only the type (no fake key, prompt or memory text); 21 bad responses (None, empty, whitespace, int, float, bool, list, valid-looking dict, bytes, object, malformed JSON, prose, unknown/missing/null/int/list action, JSON list/null/string/number) → UNCERTAIN; every failure mode never yields DELETE or any id/replacement text; no-existing-memories short-circuit unchanged.
- **Edited** `test_p1_decision_parsing.py`: the two `decide_memory_action` probes (None, RuntimeError) are now assertions (PASS 110 → 112, FINDING 5 → 3). The remaining probes belong to `decide_memories_to_delete` (D4) and are untouched.

## Results (executed)
| File | PASS | FAIL | FINDING lines |
|---|---|---|---|
| `test_p1_d3_decision_errors.py` | 50 | 0 | 0 |
| `test_p1_decision_parsing.py` | 112 | 0 | 3 (D4/D5 probes) |
| `test_memory_delete_detector.py` (D1) | 213 | 0 | 3 (D6) |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 37 | 0 | 1 |
| `test_p1_delete_routing.py` (D1) | 137 | 0 | 0 |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |

Full default suite (`run_tests.py --clean`): **20 / 20 passed, 0 failed** (includes D1 detector/routing and the 43-check D2 test); `rag_db` fingerprint unchanged: **True**.

## Mutation evidence (repo not edited; module loaded from modified source)
| Mutation | Test | Result |
|---|---|---|
| MA: remove LLM-exception handling | D3 test | caught: exit 1, 21 FAIL (then aborted by an uncaught exception in a later check) |
| MA | `test_p1_decision_parsing.py` | caught: aborts with the unhandled RuntimeError at the converted assertion |
| MB: remove non-str guard only | D3 test | caught: exit 1, 10 FAIL |
| MC: both removed (original behaviour) | D3 test | caught: exit 1, 29 FAIL |

## Safety
`rag_db` fingerprint unchanged; all runs on `rag_test_scratch`, network blocked, scratch emptied by `--clean`; no migration, no commit.

## Remaining limitations
- `except Exception` deliberately does not catch `KeyboardInterrupt`/`SystemExit`.
- A syntactically valid but semantically wrong answer (e.g. DELETE with a made-up id) is still returned as-is; `process_memory` validation/blocking handles that (D5 id coercion is separate).
- `decide_memories_to_delete` still lets an LLM exception escape (D4, not started).
