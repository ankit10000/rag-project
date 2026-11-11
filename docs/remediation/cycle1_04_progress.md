# Cycle 1 - 04 Progress check (Role 4, read-only except this file)

Method: compared `MASTER_GAP_REGISTER.md` rows P1-01..P1-10 and `p4_07_verification_and_phase1_plan.md` with files on disk and `.venv\Scripts\python.exe run_tests.py --list` (lists only; no tests run).

## Disk state versus plan (WP1..WP5)

| Planned item | WP | Exists on disk? | Registered in run_tests.py |
|---|---|---|---|
| `test_memory_delete_detector.py` rewrite | WP1 | NO. Original 33-line script (no rewrite) | still `live` (planned: `unit`) |
| `test_p1_decision_parsing.py` | WP2 | NO | not registered |
| `test_p1_process_memory.py` | WP3 | NO | not registered |
| `test_p1_memory_update_delete_integration.py` | WP4 | NO | not registered |
| `test_p1_delete_routing.py` | WP5 | NO | not registered |
| Registry reconciliation, full suite | WP6 | not done | n/a |

New tests present: 0 of 5 (glob `test_p1*` finds nothing). Unclassified files in `--list`: none.

Current classification from `--list`:
- unit (6): test_testsafe, test_answer_scoring, test_context_and_citations, test_answer_phase3, test_model_fallback, test_similarity
- integration (6): test_memory_sources_regression, test_deletion_cleanup, test_extraction_and_summary_guards, test_retrieval_phase2, test_phase5_provenance, test_memory_storage
- live (11): includes the four old live scripts `test_memory_conflicts.py`, `test_memory_decision.py`, `test_memory_delete_classifier.py`, `test_memory_delete_decision.py` (all still live, as intended) and `test_memory_delete_detector.py` (still live, to move in WP1)
- manual (8): includes `test_memory_update.py` (still manual, as intended)

P4-07 result (from its doc): infrastructure done; default run 12/12 passed (2 smoke-only), `rag_db` fingerprint unchanged. Register row P4-07 itself still reads NOT STARTED / pending (stale, not yet updated).

## Phase 1 register status

Register vocabulary: VERIFIED COMPLETE, IMPLEMENTED NOT VERIFIED, PARTIALLY COMPLETE, NOT STARTED, BLOCKED, NOT APPLICABLE. All "Final" cells are still `pending`; the "VERIFIED (baseline)" entries were observed earlier but stage work must re-verify and record them.

| ID | Requirement | Register status now | Closed by |
|---|---|---|---|
| P1-01 | User-only extraction | VERIFIED (baseline), Final pending | existing guards test; re-verify in WP6 full run |
| P1-02 | Assistant text never evidence | VERIFIED (baseline), Final pending | existing + P5 tests; WP6 |
| P1-03 | Automatic extraction cannot DELETE | VERIFIED (baseline), Final pending | WP3 (DELETE-ban cases 22, 23, 27) + WP6 |
| P1-04 | Explicit deletion detection | IMPLEMENTED, NOT VERIFIED | WP1 (detector rewrite), WP5 (routing) |
| P1-05 | Ownership / isolation | VERIFIED (baseline), Final pending | WP3 (delete_matching other-conversation), WP4 (hijack, ownership) |
| P1-06 | Paired-assistant handling | VERIFIED (baseline), Final pending | no Phase 1 WP; deferred to P5-05 |
| P1-07 | Cleanup / summary rewrite | VERIFIED (baseline, mocked), Final pending | extra "failed cleanup cannot leave misleading summary" test is NOT in WP1..WP5; gap in plan |
| P1-08 | Classification / conflict / update | IMPLEMENTED, NOT VERIFIED | WP2 (decision parsing), WP3 (process_memory), WP4 (update/delete) |
| P1-09 | Legacy memory behaviour | PARTIALLY COMPLETE | no Phase 1 WP; deferred to P5-03 (approval gate) |
| P1-10 | Documentation | NOT STARTED | no WP; `phase1_remediation.md` still to write after WP6 |

## Numerator / denominator

- Phase 1 items VERIFIED COMPLETE (final, strict count): **0 / 10**.
- For reference only, items carrying the weaker "VERIFIED (baseline)" mark with Final still pending: 6 / 10 (P1-01, 02, 03, 05, 06, 07). These are not counted as verified.
- Items needing new work (P1-04, P1-08): 0 of 2 closed; planned new test files on disk 0 / 5; WPs complete 0 / 6.

## What remains

1. WP1: rewrite detector test, move registry line live -> unit.
2. WP2: create `test_p1_decision_parsing.py`, register unit.
3. WP3: create `test_p1_process_memory.py`, register integration.
4. WP4: create `test_p1_memory_update_delete_integration.py`, register integration.
5. WP5: create `test_p1_delete_routing.py`, register integration (highest risk, `main` import).
6. WP6: `--list` check, full `run_tests.py --clean`, update register Final column, write P1-10 `phase1_remediation.md`.
7. Plan gaps not covered by any WP: P1-07 extra cleanup test; P1-06 and P1-09 depend on Phase 5; register row P4-07 needs status update.
