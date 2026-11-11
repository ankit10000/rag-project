# D6 fix report — detector input safety and performance

Date: 2026-11-11. Scope: D6 only (`services/memory_delete_service.py`). D7 not started; D1–D5 behaviour unchanged (all their tests re-run). Nothing committed. No live Gemini (network blocked for every run). `rag_db` untouched. Everything below marked **executed** was run in this session; "static" means code inspection only.

## Root cause (inspected, then measured)
1. **Non-string input** (static + executed in the audit): `is_explicit_memory_delete_request` did `message.lower()` / `re.sub` on whatever it received → `AttributeError` for int/list, `TypeError` for bytes.
2. **Quadratic time** (executed): the *original pre-D1* detector contained the unanchored pattern `\b(?:delete|remove|erase|clear|wipe)\b.*\b(?:memory|memories)\b` (and a `.*` in the don't-pattern). For `"delete " * N` every `delete` start position scans to the end of the string looking for "memory" → O(N²). Re-measured on the original patterns: 1000 → 0.072 s, 2000 → 0.276 s, 4000 → 1.179 s (≈4× per doubling).
3. **Current state before D6** (executed): the D1 rewrite had already removed those `.*` patterns, so `"delete " * N` was linear (0.001/0.001/0.002 s for 1000/2000/4000). The only remaining super-linear spot was the repeated politeness group `^(?:(?:please|can you|…)[ ,]+)*` present in every pattern: `"please " * N` showed ≈2.3–3× per doubling (0.098 s at 20 000, 0.258 s at 40 000), i.e. a mildly super-linear regex-backtracking risk that D6 removes.

## Change (one application file: `services/memory_delete_service.py`)
- **Input contract:** `if not isinstance(message, str) or not message: return False`. None, int, float, bool, list, tuple, dict, set, bytes, bytearray and arbitrary objects return `False`; nothing is converted with `str()` (an object whose `__str__` raises is also safe). `str` subclasses work.
- **Matching restructure:** the repeated politeness group was removed from every pattern. Leading politeness phrases are skipped by one short linear loop (`_skip_prefix`) and the patterns are matched at that position with `pattern.match(message, pos)`. Patterns are grouped by position: `_EXPLICIT`, `_WEAK` (forget-prefix), `_DONT` (don't-prefix, which keeps its own smaller prefix list), `_ANYWHERE` (`stop remembering …`, the only unanchored pattern, no repetition).
- **No semantic change:** pattern texts, personal-noun lists and the D1 design rule are unchanged; no truncation, no technical-word veto added.

## Benchmark (executed, `perf_counter`, same machine)
| Input | before D6 (post-D1) | after D6 |
|---|---|---|
| `"delete " * 1000 / 2000 / 4000 / 20000` | 0.001 / 0.001 / 0.002 / 0.007 s | 0.0003 / 0.0007 / 0.0016 / 0.0071 s (100 000: 0.036 s) |
| `"please " * 4000 / 20000` | 0.006 / 0.094 s | 0.004 / 0.018 s (100 000: 0.095 s) |
| `"forget my " * 20000 / 100000` | 0.012 s / – | 0.0125 / 0.067 s |
| `"stop remembering " * 20000 / 100000` | 0.019 s / – | 0.019 / 0.099 s |
| `"can you " * 100000` | – | 0.134 s |
| `"delete my saved " * 100000` | – | 0.113 s |
| original pre-D1 detector `"delete " * 1000/2000/4000` | 0.072 / 0.276 / 1.179 s | (replaced in D1) |
All inputs scale ≈ linearly (5× size → ≈5× time).

## Tests
`test_memory_delete_detector.py` (unit): the D6 FINDING probes are now assertions; **271 PASS, 0 FAIL, 0 FINDING** (was 213 PASS + 3 FINDING). Added:
- 18 unsupported-input cases (None, ints, floats, bools, list, tuple, dict, set, bytes, bytearray, raising-`__str__` object, empty, whitespace, punctuation-only) → `False`, no exception; str subclass and a normal command still `True`.
- Timing guards (generous 2 s bound, **not** tight) for seven repeated-keyword units × sizes 1 000 / 2 000 / 4 000 / 20 000 / 100 000, each also requiring `False`; BENCH lines print the measured times; 20 000 politeness prefixes + real command → `True`; repeated bare verbs/"memory"/"my" never match; 100 000 characters of text before a command → `False` (anchored).
- All earlier D1 positive/negative/technical/ambiguous cases unchanged and passing.

## Results (executed)
| File | PASS | FAIL | FINDING |
|---|---|---|---|
| `test_memory_delete_detector.py` | 271 | 0 | 0 |
| `test_p1_delete_routing.py` | 137 | 0 | 0 |
| `test_p1_decision_parsing.py` | 116 | 0 | 0 |
| `test_p1_d3_decision_errors.py` | 50 | 0 | 0 |
| `test_p1_d4_delete_decision_errors.py` | 54 | 0 | 0 |
| `test_p1_d5_delete_ids.py` | 40 | 0 | 0 |
| `test_p1_process_memory.py` | 104 | 0 | 0 |
| `test_p1_memory_update_delete_integration.py` | 37 | 0 | 1 (pre-existing, not D6) |
| `test_p1_cleanup_failure.py` | 54 | 0 | 0 |

Full default suite (`run_tests.py --clean`): **22 / 22 passed, 0 failed** (includes D1–D5 tests); application database `rag_db` fingerprint unchanged: **True**.

## Mutation evidence (executed; repo not edited, mutations applied in memory)
| Mutation | Test | Result |
|---|---|---|
| MA: remove the non-string guard | detector test | caught: exit 1, 11 FAIL |
| MB: add back the original unanchored `verb .* memory` pattern | detector test | caught: many assertion FAILs (the D1 false positives return) **and** the `'delete ' * 20000` guard fails (28.2 s); the run then hangs and is killed by the 90–150 s timeout (exit 124) because the 100 000-size case is quadratic |
| MC: detector always `False` | detector test | caught: 73 FAIL |
| MC | routing test | caught: 17 FAIL |
| MD: detector always `True` | detector test | caught: 177 FAIL |
| MD | routing test | caught: 33 FAIL, no traceback |
Not meaningfully testable: restoring only the repeated politeness group would be only mildly super-linear (≈2–3× per doubling), which the generous 2 s guard cannot reliably tell apart on this machine; it is protected structurally (no repetition in the patterns) rather than by timing.

## Safety (executed)
`rag_db` fingerprint unchanged; all runs on `rag_test_scratch` with network blocked; scratch emptied by `--clean`; no schema/migration change; no storage, ownership, cleanup, provenance or classifier edits; no commit.

## Remaining limitations
- Timing tests are regression guards (2 s bound), not precise complexity proofs.
- A `str` containing extremely long text is still scanned linearly per pattern (no truncation by design).
- The polite-prefix list is unchanged; unknown prefixes ("hey,") still prevent a match by design (D1).
- D7 (`delete_memory` id validation) is untouched.
