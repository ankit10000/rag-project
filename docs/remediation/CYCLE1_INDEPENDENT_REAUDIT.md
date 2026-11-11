# Cycle 1 — independent re-audit of Phase 1 tests

Date: 2026-11-11. Read-only on the repository: no application code, test file, migration or config was edited and nothing was committed. Tests were run through the approved infrastructure against the scratch database `rag_test_scratch` with outbound network blocked (so no Gemini call was possible). Helper scripts used for this audit live outside the repo (job temp folder).

Labels: **VERIFIED** = I executed or reproduced it in this audit. **REPORTED** = taken from the implementer's report, not re-checked. **NOT VERIFIED** = not checked.

## 1. Files inspected
`test_memory_delete_detector.py` (126 lines), `test_p1_decision_parsing.py` (249), `test_p1_process_memory.py` (537), `test_p1_memory_update_delete_integration.py` (245), `test_p1_delete_routing.py` (329), `test_p1_cleanup_failure.py` (224); `run_tests.py`, `testsafe.py`; application code `services/memory_delete_service.py`, `services/memory_decision_service.py`, `services/automatic_memory_service.py`, `services/memory_storage_service.py`, `services/memory_cleanup_service.py`, `main.py` (deletion/extraction branches). Test files were read at structure level plus targeted sections (fixtures, helpers, key assertions); not every line of the 1,710 test lines was read.

## 2. Tests actually executed (VERIFIED)

### 2a. The six files, run one by one (network blocked, scratch DB)
| File | Exit | PASS lines | FAIL | FINDING lines |
|---|---|---|---|---|
| `test_memory_delete_detector.py` | 0 | 75 | 0 | 11 |
| `test_p1_decision_parsing.py` | 0 | 110 | 0 | 5 |
| `test_p1_process_memory.py` | 0 | 103 | 0 | 1 |
| `test_p1_memory_update_delete_integration.py` | 0 | 37 | 0 | 1 |
| `test_p1_delete_routing.py` | 0 | 121 | 0 | 3 |
| `test_p1_cleanup_failure.py` | 0 | 54 | 0 | 0 |
| **Total** | | **500** | **0** | 21 |

**The reported 500 checks are confirmed: 500 `PASS` lines were produced and 0 `FAIL`.** (A "check" here = one printed `PASS` line; some checks are generated in loops. FINDING lines are probes that print but cannot fail the suite.)

### 2b. Full default runner (`run_tests.py --clean`)
`run / passed / failed : 18 / 18 / 0`; 2 passes are smoke-only (`test_similarity.py`, `test_memory_storage.py`, no assertions); 18 tests not run by design (10 live, 8 manual); `application database 'rag_db' fingerprint unchanged : True`. The scratch DB was emptied afterwards.

### 2c. Mutation sensitivity check (do the tests catch real bugs?)
I injected one deliberate defect at a time into the in-memory application functions (no file edits) and ran the matching test. A good test must fail.

| Injected bug | Test run | Result |
|---|---|---|
| Detector never matches | detector | caught (exit 1, 47 FAIL) |
| Detector matches everything | detector | caught (23 FAIL) |
| Decision parser ignores the LLM response | decision parsing | caught (80 FAIL) |
| Automatic-mode DELETE ban removed (`allow_delete` forced True) | process_memory | caught (4 FAIL) |
| `delete_memory` ignores conversation ownership | update/delete integration | caught (3 FAIL) |
| same ownership bug | process_memory | **NOT caught** (exit 0) |
| Cleanup claims success but leaves the summary | cleanup failure | caught (34 FAIL) |
| Cleanup skips message exclusion | cleanup failure | caught (13 FAIL) |
| `main` never detects delete requests | routing | caught (17 FAIL) |

8 of 9 injected bugs were caught. Side effect to be aware of: the mutation runs wrote to the scratch DB only.

### 2d. Static checks on the six files (VERIFIED)
Guard lines present at the top of all six; no hard-coded UUIDs; each ends with `sys.exit(1 if FAILURES else 0)`; no live-LLM possible (all passed with the network blocked); the real storage layer and real scratch DB are used in the three integration files (state compared before/after), not just mock return values.

## 3. Do the tests verify behaviour or just mocked values? (VERIFIED by reading + mutation)
- **Decision parsing:** mocks only the raw LLM text and tests the real parser (JSON, fences, case, filtering, de-duplication). Mutation M3 breaks it → 80 failures. Genuine.
- **process_memory / delete_matching_memories:** real DB rows, embeddings, links; compared before/after, including a second conversation. Genuine. Only the LLM decision is mocked, which is the correct boundary.
- **Cleanup failure:** real `apply_deletion_cleanup` with mocked LLM; checks the stored summary, checkpoint and `context_excluded` rows. Genuine.
- **Routing:** patches 14 collaborators of `main.main()`, so it verifies main's wiring and branching (which function is called, which text is shown, what is saved), not downstream behaviour. Appropriate, but it cannot detect problems below `main`.
- **Detector:** pure function; genuine.

## 4. Requirement-to-test mapping (Phase 1)
| Req | Implementation | Test evidence | Status |
|---|---|---|---|
| P1-01 user-only extraction | `memory_service.extract_memories` | `test_extraction_and_summary_guards.py` (ran in the 18/18 run) | VERIFIED |
| P1-02 assistant never evidence | parser + DB check | guards test; `test_phase5_provenance.py` (both in the 18/18 run); update/delete integration rejects assistant sources | VERIFIED |
| P1-03 automatic extraction cannot DELETE | `automatic_memory_service.py:145` | process_memory DELETE-ban cases; mutation M4 catches removal | VERIFIED |
| P1-04 explicit deletion detection | `memory_delete_service.py:8-25`, `main.py:~88` | detector (75) + routing (121); mutations M1, M2, M8 caught | VERIFIED (behaviour pinned; defects below) |
| P1-05 ownership / isolation | `memory_storage_service.py:~315` (mismatch check), composite keys | integration + process_memory (state of the other conversation compared) | VERIFIED (ownership bug caught by the integration test, not by process_memory) |
| P1-06 paired-assistant handling | `conversation_service.get_paired_assistant_ids` | covered indirectly by cleanup tests only | Deferred (P5-05) — NOT VERIFIED in Cycle 1 |
| P1-07 cleanup / summary rewrite / verification | `memory_cleanup_service.py:153,283` | cleanup failure (54) + older cleanup tests; mutations M6, M7 caught | VERIFIED (LLM mocked) |
| P1-08 classification / conflict / update | `memory_decision_service.py`, `process_memory`, `update_memory` | decision parsing (110), process_memory (103), update/delete (37) | VERIFIED (behaviour pinned; defects below) |
| P1-09 legacy memories | — | none in Cycle 1 | Deferred (P5-03) |
| P1-10 documentation | `phase1_remediation.md` | exists | REPORTED (not re-read in full) |

## 5. Defects reproduced independently (all VERIFIED by running the code)
Reproduction used the real functions with the LLM mocked; no database write except where noted.

| # | Defect | Location | Reproduction result | Severity (my assessment) |
|---|---|---|---|---|
| D1 | Detector treats ordinary technical/other requests as memory-deletion requests | `services/memory_delete_service.py:8-25` (patterns 1, 2 and the delete/remove/erase/clear/wipe + memory pattern at line 23) | True for: "How do I clear memory in Python?", "Please remove the memory leak in my code", "delete memory from the cache", "Forget all the tests I wrote", "Don't save it as a PDF", "Why do you stop remembering things?". False for "What is a memory leak?", "How much memory does numpy use?", "I want to forget about my exam". In `main.py` (~l.88-121) such a message skips document search and goes to `delete_matching_memories`; whether anything is deleted then depends on the LLM classifier (NOT VERIFIED live). | Medium: a user question is swallowed; potential wrong deletion if the classifier mis-selects |
| D2 | `delete_matching_memories` deletes on an unknown classifier status | `services/automatic_memory_service.py:300-310` (only UNCERTAIN and NO_MATCH are checked) | With status `MAYBE` and a valid id: result status `DELETED`, ids `[1]`, `delete_memory` called. Latent in production: the real classifier maps unknown statuses to UNCERTAIN (`memory_decision_service.py:~243`). | Low-Medium (missing defence in depth) |
| D3 | `decide_memory_action` crashes on LLM error or `None` | `services/memory_decision_service.py:75` (`generate_answer` is called before the `try` at ~l.77); `re.sub` on `None` | `None` → `TypeError`; exception from `generate_answer` → propagates (`RuntimeError`); empty string → handled (UNCERTAIN) | Medium-Low |
| D4 | `decide_memories_to_delete` does not catch LLM exceptions | `services/memory_decision_service.py:222` | exception → propagates; `None` and empty string → handled (UNCERTAIN) | Medium-Low |
| D5 | Id coercion accepts `true` and `2.7` | `services/memory_decision_service.py:261,269` (`int(...)`) | `[true, 2.7]` → ids `[1, 2]` | Low |
| D6 | Detector raises on non-str input and is quadratic on repeated keywords | `services/memory_delete_service.py` (`message.lower()` / regex) | `123`, `['a']` → `AttributeError`; `b'x'` → `TypeError`. Time for `"delete " * n`: n=1000 → 0.09 s, 2000 → 0.39 s, 4000 → 1.53 s (≈4× per doubling = quadratic; ~28 s at 20,000 per the test run) | Low (single-user CLI) |
| D7 | `delete_memory` with a non-integer id raises a raw database error | `services/memory_storage_service.py` (~l.284 query) | `delete_memory(<uuid>, 'abc')` → `psycopg InvalidTextRepresentation` | Low (ids are internal) |

Impact of D3/D4 in context (by reading `main.py`, NOT executed): extraction runs inside a `try/except` in `main.py` (~l.277-319), so the app continues; but an exception inside `process_memory` aborts the remaining memories of that batch (no per-item guard in `memory_service.extract_and_save_memories`, ~l.314).

## 6. Suspected defects needing more investigation (NOT VERIFIED)
- S1: `main.py:146` runs cleanup whenever `deleted_count > 0` regardless of `status`. Cannot be triggered with the real `delete_matching_memories` (status and count are consistent); latent only.
- S2: D1 consequences with the real classifier (does it delete a Python-related memory when asked "How do I clear memory in Python?"). Needs a live, scratch-DB, quota-consuming check — not run (no live Gemini allowed).
- S3: positional user→assistant pairing and shared-source exclusion remain unverified design limits (Phase 5 items).
- S4: pattern 3 (negated "remember/keep/store/save") fires on any "don't save/keep/store … it/this/my" sentence — only one example reproduced.

## 7. Weak or insufficient evidence
1. **Probes cannot fail.** The 21 FINDING lines document defects but never fail the suite, so a regression that makes a defect *worse* would not be caught. They must become real assertions when each defect is fixed.
2. **Ownership defence in `process_memory` is not covered by the `process_memory` test** (mutation M5 survived there); it is covered by the separate update/delete integration test, so the overall suite is protected, but not at that layer.
3. **Routing test tests `main`'s wiring only** (14 patched collaborators); a defect below `main` would not surface there.
4. **Smoke-only tests** (`test_similarity.py`, `test_memory_storage.py`) assert nothing and are included in "18/18".
5. **Detector test runtime** is ~30-48 s because of a 20,000-repetition performance probe; inflates the run time and is machine-dependent (the `< 5 s` guards use the 2,000-repetition case, which measured ~0.4 s here).
6. **Embeddings are replaced by one-hot vectors** in the DB tests, so the real 0.90 similarity behaviour is not exercised there (it is exercised in the Phase 5/sources tests).
7. Not read line-by-line: roughly the middle portions of `test_p1_process_memory.py` and `test_p1_delete_routing.py`; only structure and sampled assertions were reviewed.

## 8. Not executed
- Live Gemini tests (10 live scripts) and manual scripts (8): by instruction/safety.
- Real-classifier behaviour for D1 (S2).
- P1-06 and P1-09 behaviour (deferred).

## 9. `rag_db` unchanged (VERIFIED)
Row counts before and after this audit: 261 conversations, 1,340 messages, 127 memories, 93 links, 9 chunks (identical to the baseline). The runner's read-only fingerprint (row counts + content hash of five tables) matched before/after the full run. No file under `services/`, `main.py`, `.env`, `requirements.txt` is newer than `cycle1_01_audit.md`. Writes performed by the audit: scratch DB rows (tests, mutation runs), then emptied by `--clean`.

## 10. Verdict on the Cycle 1 claims
- 500 passing checks: **VERIFIED** (500 PASS, 0 FAIL, executed here).
- 18/18 default suite, `rag_db` unchanged: **VERIFIED**.
- Tests genuinely verify behaviour: **VERIFIED** for 8 of 9 injected-bug scenarios; one gap (§7.2).
- 7 candidate defects: **VERIFIED** D1-D7 (the implementer's list is accurate; precision: D3's `None` crash applies to `decide_memory_action` only, `decide_memories_to_delete` handles `None`).
- Register rows P1-01, 02, 03, 04, 05, 07, 08: can be changed from REPORTED to VERIFIED (P1-04 and P1-08 with the defects above noted); P1-06 and P1-09 stay deferred; P1-10 is REPORTED.

## 11. Recommended fix order (awaiting your approval; nothing fixed)
1. **D2** — guard the classifier status in `delete_matching_memories` (accept only `DELETE`). Smallest change, closes a safety gap. Flip the matching probe to an assertion.
2. **D1** — tighten the detector (require a clear subject such as my/our/your stored memory or "forget my …"; drop the broad "stop remembering" and bare delete+memory matches). Needs a design review because the existing tests pin intentionally conservative behaviour; update the negative list with the six verified false positives.
3. **D3/D4** — wrap `generate_answer` and parsing in `memory_decision_service.py` so errors and `None` return UNCERTAIN; add a per-memory guard in `extract_and_save_memories` so one failure does not drop the rest of the batch.
4. **D5** — reject bool/float ids in `decide_memories_to_delete`.
5. **D7** — validate integer ids in `delete_memory`.
6. **D6** — type-check input and make the regex linear (or cap input length).
7. After each fix: convert its FINDING probe into a failing-capable `check`, re-run the six files, the 18-test default suite and the mutation check.
