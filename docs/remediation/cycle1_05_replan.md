# Cycle 1 - 05 Re-plan (final ordered work packages)

Scope: P1-04, P1-07, P1-08. Deferred: P1-06 (to P5-05), P1-09 (to P5-03). Rules: cycle1_RULES.md. Conventions and WP1..WP6 detail: cycle1_03_phases.md (unchanged). Every run via `.venv\Scripts\python.exe run_tests.py <file>` only; PASS = exit 0, zero `FAIL |` lines, network blocked; `FINDING |` lines are reported, not failures. After each WP: `run_tests.py --list` shows the file in the intended category, nothing unclassified.

## P1-07 gap analysis (services/memory_cleanup_service.py)

ALREADY COVERED (evidence, mocked LLM, scratch DB):
- verifier says YES (leak) -> RESET, summary "" , checkpoint 0: test_extraction_and_summary_guards.py "semantic leak (not verbatim) caught -> RESET"
- verifier raises -> RESET: "verification call failure -> RESET"; unparseable / non-boolean verifier -> RESET (two checks); "model changed nothing is still verified -> RESET"
- rewrite call raises -> RESET: test_deletion_cleanup.py "Gemini failure -> RESET (fact never left in place)"
- destructive / still-leaking rewrite -> RESET; nothing left (sentinel) -> EMPTIED; no summary -> NO_SUMMARY; unrelated -> UNCHANGED
- echo scan bad JSON / Gemini failure -> [] (find_echo_message_ids only)

GENUINELY MISSING (new WP5b): apply_deletion_cleanup end-to-end under failure (existing tests only run it on the happy path REWRITTEN, or just check prompt forwarding).

## Final order

WP1 -> WP2 -> WP3 -> WP4 -> WP5 -> WP5b -> WP6

1. WP1 `test_memory_delete_detector.py` (rewrite, pure) - register live->unit. Accept: PASS; original 15 cases verbatim; perf guards <5 s; `--list` unit.
2. WP2 `test_p1_decision_parsing.py` (mocked, unit; fallback integration) - Accept: PASS; generate_answer call_count 0 for empty existing; FINDING probes for None/raising generate_answer.
3. WP3 `test_p1_process_memory.py` (integration, scratch DB) - Accept: PASS twice in a row (idempotent cleanup); DELETE-ban cases 22, 23, 27 pass; row fingerprints of unrelated rows unchanged; test_memory_sources_regression.py and test_phase5_provenance.py still PASS.
4. WP4 `test_p1_memory_update_delete_integration.py` (integration) - Accept: PASS; foreign-conversation hijack and delete-ownership blocked; source ValueError cases leave fingerprints unchanged. test_memory_update.py stays manual.
5. WP5 `test_p1_delete_routing.py` (integration, main fully patched) - Accept: PASS under network block; every patched name exists on `main`; no real DB/LLM call; input iterator ends with "exit". Fallback: sys.modules stubs, noted in report.
6. WP5b `test_p1_cleanup_failure.py` (NEW, integration, mocked LLM `services.memory_cleanup_service.generate_answer`, scratch DB; conversation via create_conversation, cleanup in finally; register `integration`). Cases, each asserting the stored summary and checkpoint after the call:
   a. apply_deletion_cleanup, rewrite call raises -> summary_status "RESET", get_conversation_summary == "", messages_excluded > 0 (deterministic exclusion survives LLM failure), forgotten text absent from history.
   b. apply_deletion_cleanup, verifier says YES -> "RESET", summary "", checkpoint 0, source message + paired reply excluded.
   c. apply_deletion_cleanup, verifier raises -> "RESET", summary "".
   d. apply_deletion_cleanup, find_echo_message_ids raises (patched) -> no exception, summary_status still produced, source messages still excluded.
   e. rewrite returns empty string "" (not sentinel) -> pin observed status (expected RESET) and summary contains no forgotten text; if it leaves the old summary, FINDING.
   f. Invariant on every failure branch above: summary is either "" or free of every deleted fact (substring check); never the original leaky summary.
   g. Other conversation's summary and messages untouched (isolation fingerprint).
   Accept: `run_tests.py test_p1_cleanup_failure.py` PASS, second run PASS, zero real Gemini calls (mock call_count > 0 and network block holds), `--list` clean. Risk LOW. No app edits; a branch leaving a leaky summary is a FINDING with minimal repro.
7. WP6 reconcile and docs (docs and run_tests.py registry only):
   a. `run_tests.py --list`: unit has detector + decision parsing; integration has process_memory, update_delete, delete_routing, cleanup_failure; 4 old live scripts still live; test_memory_update.py manual; zero unclassified.
   b. `run_tests.py --clean` (full default suite) exits 0; scratch DB empty after; re-run the six new files individually.
   c. Edit docs/remediation/MASTER_GAP_REGISTER.md: correct stale P4-07 row (line 53) from NOT STARTED to VERIFIED COMPLETE (infrastructure done; default run 12/12 passed, 2 smoke-only; rag_db fingerprint unchanged, per p4_07_verification_and_phase1_plan.md); update Phase 1 rows P1-01..P1-05, P1-07, P1-08 Final column only to what the WP6 run proves; leave P1-06, P1-09 as deferred (P5-05, P5-03) and P1-10 done once step d exists.
   d. Write docs/remediation/phase1_remediation.md (docs only): per-file PASS/FAIL and check counts, all FINDING lines grouped by plan section 7 with minimal repros, P1-07 coverage table (covered vs WP5b), deferred items, strict VERIFIED COMPLETE count.
   Accept: suite exit 0; register P4-07 row no longer NOT STARTED; phase1_remediation.md exists; no file in services/, main.py, .env touched.
