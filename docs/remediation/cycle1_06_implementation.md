# Cycle 1 - 06 Implementation report

## Files created / changed
- Rewritten: `test_memory_delete_detector.py` (75 checks, 11 FINDINGs; original 15 cases verbatim; moved live -> unit)
- New: `test_p1_decision_parsing.py` (110; 5 FINDINGs; unit)
- New: `test_p1_process_memory.py` (103; 1 FINDING; integration)
- New: `test_p1_memory_update_delete_integration.py` (37; 1 FINDING; integration)
- New: `test_p1_delete_routing.py` (121; 3 FINDINGs; integration; `main` imported, all 14 collaborators patched on `main`, every name verified to exist; no sys.modules fallback needed)
- New: `test_p1_cleanup_failure.py` (54; 0 FINDINGs; integration)
- Edited: `run_tests.py` (CATEGORIES only), `docs/remediation/MASTER_GAP_REGISTER.md` (P4-07, P1-01..P1-10 Final cells), new `docs/remediation/phase1_remediation.md`.
- Not touched: `services/`, `main.py`, `.env`, `requirements.txt`.

## Runner summary (`run_tests.py --clean`)
```
run / passed / failed : 18 / 18 / 0
of the passes, smoke-only (exit code only, no assertions) : 2 ['test_similarity.py', 'test_memory_storage.py']
not run (by category) : 18
application database 'rag_db' fingerprint unchanged : True
```
Six new files re-run individually via the runner: `6 / 6 / 0`, fingerprint unchanged True, exit 0. `--list`: unit has detector + decision parsing; integration has the four new files; four old live scripts still live; `test_memory_update.py` manual; no unclassified file.

## FINDINGs
See phase1_remediation.md (items 1-7) for the full list with reproductions.

## Notes / skipped
- WP3 idempotence: the file passed in the full run and again individually (cleanup in `finally`; both runs against the same scratch DB).
- Check counts are PASS lines printed; probes (FINDING/PROBE-OK/INFO) are not counted.
- Runner prints only the last 8 lines of a passing test, so FINDINGs were read via a temporary helper outside the repo (`%TEMP%\showrun.py`, same scratch URL and network-block env as the runner). Nothing was written to the repo by it.
- Item 9 of the plan [orphan memory_sources] is observed 0 rows (FK cascade), so no finding.
- Skipped: nothing from WP1-WP6. P1-06 and P1-09 deferred by design.
