# Cycle 1 - 03 Phases: work packages for P1-04 and P1-08 tests

Role: phase divider. Source: `cycle1_02_plan.md` (section numbers below refer to it). Nothing executed.
Python: `.venv\Scripts\python.exe`. All runs go through `run_tests.py` only (scratch DB `rag_test_scratch`, network blocked for unit/integration). Never touch `rag_db`, app code, `.env`.

## Global conventions for every WP

- Work packages are file-disjoint: each WP creates/rewrites exactly one test file. `run_tests.py` is edited in every WP, but only by adding/moving ONE registry line for that WP's file (single editor, sequential execution, so no conflict). No other file is edited by more than one WP.
- Registry check: after each WP, run `.venv\Scripts\python.exe run_tests.py --list` and confirm the WP's file appears under the intended category and no file is reported unclassified (runner flags unclassified files near line 140). The file is therefore created BEFORE its registry line is added, and both land in the same WP.
- Acceptance run per WP: `.venv\Scripts\python.exe run_tests.py <file>`. Pass means: runner reports PASS for the file (exit code 0), output has zero `FAIL |` lines, and the file ran under the runner's network block (no Gemini call; any attempted network use is a failure of the WP, fix the mock). `FINDING |` lines are expected and do NOT fail the WP; they are copied into the final defect report.
- Each file follows plan section 0 (testsafe header first, `check`/`probe`/`quiet` inline, `sys.exit(1)` iff a check failed, prints `N check(s) failed, M finding(s)`).
- If a WP file fails because of an application behaviour that differs from the plan, the executor re-pins the check to the observed behaviour only if that is clearly the current behaviour (rules: pin, do not change), otherwise records it as a FINDING. Never edit `services/` or `main.py`.
- Old live scripts stay unchanged and registered as they are (except the detector rewrite).

## Dependency graph

WP1, WP2 independent. WP3 independent of WP1/WP2 (but sequenced after for risk). WP4 after WP3 (reuses the same embedding/fixture pattern; copy inline, no import). WP5 independent of DB WPs but last (most integrated). WP6 depends on all.

Order: WP1 -> WP2 -> WP3 -> WP4 -> WP5 -> WP6.

---

## WP1 - Detector rewrite (pure, no mocks, no DB)

- Create/rewrite: `test_memory_delete_detector.py` (REWRITE; plan section 1). Keep the original 15 cases verbatim; add positives, prefixes, negation, deletion terms, normalisation, negatives, falsy-input checks, <5 s performance guard on `"a"*100000` and `"delete "*2000`, probes P-A, P-B, P-C.
- Registry: move `test_memory_delete_detector.py` from `live` to `unit`.
- Dependencies: none.
- Acceptance: `.venv\Scripts\python.exe run_tests.py test_memory_delete_detector.py` -> PASS under the network block; `--list` shows it under `unit`, not under `live`, and no unclassified file. Expected FINDINGs: false positives (clear memory in Python, memory leak, etc.), non-str truthy input raising, possibly slow `"delete "*20000`.
- Risk: LOW. Pure regex. Only risks: a checked negative that the regex actually matches (re-pin or demote to probe after reading the actual patterns in `services/memory_delete_service.py`), and the timing bound being flaky on a slow machine (bound is generous, 5 s).

## WP2 - Decision parsing (LLM mocked, no DB)

- Create: `test_p1_decision_parsing.py` (plan section 2a + 2b). Patch `services.memory_decision_service.generate_answer`; assert prompt contents via `call_args`; PROBEs for `None` response and raising `generate_answer` in `decide_memory_action`, bool/float coercion and raising in `decide_memories_to_delete`.
- Registry: add to `unit`.
- Dependencies: none (WP1 not required).
- Acceptance: `run_tests.py test_p1_decision_parsing.py` PASS; `generate_answer` mock call_count asserts hold (0 for empty existing); `--list` clean. If import fails under unit (missing key/env), apply the plan fallback: move the registry line to `integration` and note it. `test_model_fallback.py` (unit) imports the same modules, so unexpected.
- Risk: LOW-MEDIUM. Many cases and exact prompt-string asserts; verify each prompt substring against `services/memory_decision_service.py` before hard-asserting, otherwise soften to a probe. The `None` response behaviour differs between the two functions (pin both as stated in plan).

## WP3 - process_memory + delete_matching_memories (scratch DB)

- Create: `test_p1_process_memory.py` (plan sections 3a + 3b). Real storage on scratch DB; distinct one-hot embeddings patched into `services.memory_storage_service.generate_embeddings`; mock `automatic.decide_memory_action` and `automatic.decide_memories_to_delete`; spies via `wraps=` on `save_memory`/`update_memory`/`delete_memory`/`confirm_memory`/`get_memory_details`. Two conversations (`conv`, `other`) created with `create_conversation`, cleaned up in `finally`. No hard-coded ids.
- Registry: add to `integration`.
- Dependencies: none functionally; sequenced after WP1-2 because it is the first DB test. Reuse patterns from `test_memory_sources_regression.py` by copying inline only.
- Acceptance: `run_tests.py test_p1_process_memory.py` PASS; row-fingerprint asserts show unrelated rows unchanged; the DELETE-ban cases (22, 23, 27) pass; afterwards re-run `run_tests.py test_memory_sources_regression.py` and `test_phase5_provenance.py` to confirm no cross-test pollution (optional sanity, still scratch DB only). Run once more immediately to prove cleanup/idempotence (second run also PASS).
- Risk: MEDIUM. Largest file (about 30 + 11 cases). Hazards: 22 memories for the limit-20 case need distinct texts; `get_recent_memories` ordering; save_memory semantic-duplicate skip at 0.90 (hence one-hot vectors, not zeros); assistant/foreign source raising `ValueError` and transaction rollback; leftover rows if `finally` cleanup fails. If this file grows unwieldy the executor may split 3b into the same file's second section but MUST NOT create a second file (keeps WPs disjoint).

## WP4 - update_memory / delete_memory / get_memory_details (scratch DB)

- Create: `test_p1_memory_update_delete_integration.py` (plan section 4). Real DB, patched distinct embeddings, `generate_embeddings` call-count asserts for empty-text rejection, orphan `memory_sources` probe, non-int id probe.
- Registry: add to `integration`. `test_memory_update.py` stays `manual`, untouched.
- Dependencies: WP3 pattern only (fixture helpers copied inline).
- Acceptance: `run_tests.py test_p1_memory_update_delete_integration.py` PASS; foreign-conversation hijack and delete-ownership checks pass; source `ValueError` cases leave fingerprints unchanged; `--list` clean.
- Risk: MEDIUM. Exact exception types and `memory_id` string handling are unverified; treat as pins/probes where uncertain. A DB error inside a probe must not leave an aborted transaction affecting later checks (use fresh connections via the services). Orphan-source behaviour depends on FK cascade: print only, never assert.

## WP5 - main.py routing (fully patched, most integrated)

- Create: `test_p1_delete_routing.py` (plan section 5): `run_main(inputs, **overrides)` harness patching `builtins.input` and the collaborator set in 5.2 on `main`; scenarios R1-R3, D1-D10, E1-E5, N1-N8, probes P-R1..P-R3. Stdout captured; input iterator always ends with `"exit"`.
- Registry: add to `integration`.
- Dependencies: none in code, but sequenced last among test files because importing `main` pulls `rag_service` and the retrieval stack. Before writing, executor must read `main.py` imports and confirm every patched name exists as an attribute of `main` (`mock.patch.object` fails loudly otherwise).
- Acceptance: `run_tests.py test_p1_delete_routing.py` PASS in the network-blocked runner (import of `main` must not make network calls at import time; if it does, that is a blocker to report, not to fix). Verify no real DB write: all DB/LLM collaborators patched. `--list` clean.
- Risk: HIGHEST. Import side effects of `main` (model/embedding loading time, scratch-DB requirement, possible network at import); exact answer strings (copy from `main.py` verbatim); `StopIteration`/`EOFError` from an exhausted input iterator (harness guards); inconsistent-result pins D8-D9 are ambiguous. Fallback if `main` import is too slow or network-touching: stub the heavy modules via `sys.modules` before `import main` (still no app edits), and note it in the report.

## WP6 - Registry reconciliation and full default suite

- Create/rewrite: none (no new test file). Edits only `run_tests.py` if a registration correction is needed (e.g. fallback move of WP2 to `integration`); otherwise read-only.
- Steps, in order:
  1. `.venv\Scripts\python.exe run_tests.py --list` -> final classification: `unit` has detector + decision parsing; `integration` has the three DB/main files; `live` still contains `test_memory_conflicts.py`, `test_memory_decision.py`, `test_memory_delete_classifier.py`, `test_memory_delete_decision.py`; `manual` has `test_memory_update.py`; zero unclassified.
  2. Full default suite (unit + integration, network blocked, no `--live`/`--manual`/`--allow-network`): `.venv\Scripts\python.exe run_tests.py --clean`. `--clean` empties the scratch DB only, afterwards.
  3. Optionally re-run the five new files individually once more to confirm they pass in isolation after the full run (order independence).
- Dependencies: WP1-WP5 complete.
- Acceptance: full run exits 0 with all new files PASS and no regression in previously passing tests (compare against the pre-existing pass list if the executor recorded it; if any older test fails, determine whether it failed before this cycle; do not fix app code). Scratch DB empty after `--clean`.
- Risk: LOW-MEDIUM. Order-dependent shared state in the scratch DB (another test leaving rows that break counts) or a timeout (default 900 s per test) from the `main` import. Pre-existing unrelated failures are reported, not fixed.

## Deliverable hand-off after WP6

Final report lists: per-file PASS/FAIL, counts of checks, all `FINDING |` lines grouped by plan section 7 (items 1-8) with minimal reproductions, and any pinned-but-ambiguous behaviours.
