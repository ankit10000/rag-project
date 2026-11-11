# Phase 1 remediation report (Cycle 1: P1-04, P1-07, P1-08)

Scope: tests only. No file in `services/`, `main.py`, `.env`, `requirements.txt` was changed. Candidate defects are reported, not fixed.

## Result

Default suite: `.venv\Scripts\python.exe run_tests.py --clean` -> run / passed / failed 18 / 18 / 0 (2 smoke-only: `test_similarity.py`, `test_memory_storage.py`); application database `rag_db` fingerprint unchanged: True; scratch DB emptied afterwards.

## Per-file results (all PASS under the runner's network block)

| File | Category | Checks (PASS lines) | FINDINGs |
|---|---|---|---|
| test_memory_delete_detector.py (rewrite, original 15 cases kept) | unit | 75 | 11 |
| test_p1_decision_parsing.py | unit | 110 | 5 |
| test_p1_process_memory.py | integration | 103 | 1 |
| test_p1_memory_update_delete_integration.py | integration | 37 | 1 |
| test_p1_delete_routing.py (`main` fully patched) | integration | 121 | 3 |
| test_p1_cleanup_failure.py | integration | 54 | 0 |

## FINDINGs (candidate defects, minimal reproductions)

1. Detector false positives (P1-04). `is_explicit_memory_delete_request(m)` returns True for: "How do I clear memory in Python?", "remove the memory leak", "delete memory from the cache", "How do I delete a file from memory?", "Don't save it as a PDF", "Why do you stop remembering things?", "Forget all the tests I wrote".
2. Detector robustness. Non-str truthy input raises: `123` and `["forget my name"]` -> AttributeError; `b"forget my name"` -> TypeError. `"delete " * 20000` takes about 28 s (quadratic backtracking in pattern 4); `"delete " * 2000` is under the 5 s guard.
3. Routing consequence (P1-04). In `main.main()` the false positives above enter the deletion flow: RAG is skipped, the user gets "I couldn't find any memories that clearly match your deletion request..." and both messages are persisted ("How do I clear memory in Python?", "remove the memory leak", "Forget all the tests I wrote"). Cleanup runs on `deleted_count > 0`, regardless of status (pinned, e.g. status UNCERTAIN with deleted_count 2). EOFError at the prompt propagates out of `main()` (informational).
4. `decide_memory_action` (P1-08). `generate_answer` returning `None` raises TypeError (outside the except tuple); `generate_answer` raising RuntimeError propagates. Repro: patch `services.memory_decision_service.generate_answer` to return None, call `decide_memory_action("x", [(1, "a")])`.
5. `decide_memories_to_delete`. `generate_answer` raising RuntimeError propagates (None is handled -> UNCERTAIN). Booleans and floats are coerced to ids: `[true]` -> id 1, `[2.7]` -> id 2.
6. `delete_matching_memories`. Unknown classifier status (e.g. "MAYBE") with a valid id deletes the memory (status not validated; the real classifier normalises unknown to UNCERTAIN, so latent). String ids from the classifier are filtered out -> NO_MATCH (pinned).
7. `delete_memory("abc")` raises a raw psycopg `InvalidTextRepresentation` (no input validation). No orphan `memory_sources` rows remain after delete (FK cascade, 0 rows).

## P1-07 coverage

| Branch | Where covered |
|---|---|
| verifier YES -> RESET (summary "", checkpoint 0) | extraction_and_summary_guards (existing); test_p1_cleanup_failure [b] end-to-end |
| verifier raises -> RESET | existing; [c] end-to-end |
| unparseable / non-boolean verifier -> RESET | existing; [f3], [f4] end-to-end |
| rewrite call raises -> RESET | test_deletion_cleanup (existing); [a] end-to-end with exclusion + history checks |
| rewrite returns empty string -> RESET | [e] (new; summary "" and checkpoint 0, no leak) |
| rewrite still leaks / too short / whitespace -> RESET | existing; [f1], [f2], [f5] end-to-end |
| echo scan raises (patched) or its LLM fails | [d], [d2] (new): no exception, deterministic exclusion kept |
| other conversation untouched | [g] in every branch |
| invariant: summary is "" or free of the fact, never the leaky original | asserted in every failure branch |

No branch left a leaky summary, so no P1-07 defect.

## Deferred

- P1-06 paired-assistant handling -> P5-05.
- P1-09 legacy memory behaviour (sourceless memories) -> P5-03.
- Old live scripts (`test_memory_conflicts.py`, `test_memory_decision.py`, `test_memory_delete_classifier.py`, `test_memory_delete_decision.py` and others) remain `live`; `test_memory_update.py` remains `manual`.

## Strict VERIFIED COMPLETE count (Phase 1 rows, Final column)

P1-01, P1-02, P1-03, P1-04, P1-05, P1-07, P1-08 = 7 verified; P1-10 done (this document); P1-06 and P1-09 deferred. P1-04 and P1-08 are verified as tests/pins; the findings above are open defects awaiting a decision.
