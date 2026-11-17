# Stage 9 Phase E2 — WP2: Development Runner Repair

Status: done. All work is uncommitted on `audit/stage9-evaluation-readiness` (nothing staged by WP2).

## Problem

After Phase E0, importing `eval/phase35/run_eval.py` no longer switches to the scratch database. The switch, the services imports and the binding of `llm_service`, `generate_grounded_answer`, `assemble_context` and `generate_answer` now happen only in `run_eval.bootstrap_execution()`. Three dev-only runners still depended on the old import-time switch and imported `services.*` at module level. They failed closed at `harness.assert_scratch()` and could not be used. Stage 6 also wrapped `run_eval.generate_grounded_answer`, which was now `None`.

## Design

**Lazy bootstrap in each runner's entry point.** Importing any of the three modules now has no side effect: it opens no database connection, does not switch to the scratch database and imports no `services.*` module. The scratch switch happens first inside the existing preflight function (`preflight()` / `prepare()`). The services are imported after it and bound to module globals that start as `None`. A helper called before bootstrap fails closed with `AttributeError` on `None`. It does not silently use a non-scratch connection.

- **stage6 uses `run_eval.bootstrap_execution()`.** Stage 6 needs the provider (live Gemini). It also needs the same `run_eval` globals that `run_eval.run_tier1` and `run_tier2` use, and `capture_answers()` wraps `run_eval.generate_grounded_answer`. Reusing run_eval's own bootstrap gives one source of truth for the switch and the services binding. A copy could drift. Side note: `bootstrap_execution` also calls `os.makedirs(run_eval.RESULTS_DIR, exist_ok=True)`. That directory already holds the baseline files, so this changes nothing.
- **stage8 has no bootstrap of its own.** It already calls `s6.preflight()` before touching `rag` or `llm`, so it inherits stage6's bootstrap. It reads `s6.rag` and `s6.llm` after that call.
- **h1 uses `harness.use_scratch_database("rag_phase35_eval")` directly, not `bootstrap_execution()`.** h1 does retrieval only ("no LLM call"). `bootstrap_execution` would import `services.llm_service` and `services.answer_service` (google-genai client code) for nothing. The test checks that h1 imports neither. h1 calls `run_eval.build_scratch_corpus`, which imports its services lazily and does not depend on the run_eval globals.
- `eval/phase35/run_eval.py` is unchanged (E0 behaviour kept).

## Diff summary

### eval/stage6_live_dev_eval.py (+19 / −4)
- Docstring, "Safety:" paragraph (lines 15–20): states that `preflight()` first calls `bootstrap()` and that importing the module has no side effect.
- Lines 30–36: the stale comment `# noqa: E402 (points DATABASE_URL at rag_phase35_eval)` is replaced with `# import has no side effects since Stage 9 E0`. The module-level `import services.llm_service as llm` and `import services.rag_service as rag` are removed. `llm = rag = None` is added, with a comment explaining why.
- Lines 100–106: new `bootstrap()`. It calls `run_eval.bootstrap_execution()`, then `import services.llm_service` and `services.rag_service`, and binds the globals `llm` and `rag`.
- Line 110: `preflight()` calls `bootstrap()` first, then the unchanged `harness.assert_scratch()`. All existing checks are unchanged: the DB state `(rag_phase35_eval, 135, 12)`, `GEMINI_API_KEY`, the `split == "dev"` filter, the 47/42 counts, equality with the baseline ids, and `split_of == "dev"`.
- `capture_answers()` is unchanged. It runs after preflight, so `run_eval.generate_grounded_answer` is bound when it wraps it.

### eval/stage8_p3_live_dev_eval.py (+7 / −5)
- Docstring (lines 10–13): notes that `s6.preflight()` does the scratch bootstrap.
- Line 21: the stale comment `(sets the scratch DB via run_eval)` is replaced. The module-level `services.llm_service` and `services.rag_service` imports are removed.
- Line 29: `record_rewrite_and_classify()` uses `rag = s6.rag`, which is bound by `s6.preflight()`.
- Line 81: comment updated: `scratch bootstrap, dev-only selection + database checks`.
- Line 88: `llm = s6.llm` before the start banner.
- Selection logic is unchanged: `CASES` is looked up in `selected[2]` (Tier 2 dev), and a missing case raises `KeyError`.

### eval/h1_relevance_gate.py (+27 / −8)
- Docstring (lines 11–12): describes `prepare()` → `bootstrap()`.
- Line 30: the stale comment `(sets the scratch DB)` is replaced. The 7 module-level `services.*` imports are removed. `pgvector`, `harness` and `retrieval_metrics` stay at module level; none of them touches the DB.
- Lines 38–41: the 8 service names start as `None`.
- Lines 44–59: new `bootstrap()`. It calls `harness.use_scratch_database(SCRATCH_DB)`, then imports the retrieval services and binds the globals.
- Line 63: `prepare()` calls `bootstrap()` first. `harness.assert_scratch()`, the `current_database()` check, `load_all()`, the ingest and empty-corpus checks, and the `split == "dev" and tier == "both"` filter are unchanged.

### test_stage9_e2_dev_runners.py (new, 300 lines, repo root)
It follows the repo convention: `import testsafe` / `testsafe.require_scratch_db()`, then `check(label, cond)` prints PASS/FAIL and the script exits 1 on any failure.

Tripwires:
- `psycopg.connect` and `psycopg.Connection.connect` raise and record the attempt.
- `harness.use_scratch_database` is replaced by a recorder. It only sets `DATABASE_URL` to an unreachable URL, `127.0.0.1:1/rag_phase35_eval`.
- `run_eval.bootstrap_execution` is wrapped by a recorder that calls the real function, so the real E0 bootstrap code path is exercised.
- `run_eval.RESULTS_DIR` points to a temp dir.
- `GEMINI_API_KEY` is a fake value.
- Every `services.*` module is a stub served by a `sys.meta_path` finder. The finder records `import:<name>` in the same call log, and any services module it does not know raises `ImportError`. No real services module, model or provider client is ever loaded.
- The run_eval, s6 and h1 globals and `sys.modules` are restored afterwards.
- Network is blocked by `TESTSAFE_BLOCK_NETWORK=1`.

Coverage (38 checks):
- **(a)/(e) No side effect on import.** Each runner is imported in a fresh interpreter (subprocess) with the tripwires in place. Checks: import succeeds; no psycopg, `use_scratch_database` or `bootstrap_execution` call; `DATABASE_URL` unchanged; no `services*` entry in `sys.modules`.
- **(b) Order: scratch switch before any services import.**
  - stage6: `bootstrap_execution` is the first call, and `use_scratch_database:rag_phase35_eval` comes before the first `import:services*`. The stub `services.database` also records that, at its import time, `DATABASE_URL` was already the scratch URL.
  - h1: the same order and URL checks. In addition, `bootstrap_execution` is not used and neither `llm_service` nor `answer_service` is imported.
- **(c) Globals are bound after bootstrap.**
  - The four run_eval globals are bound, and so are `s6.llm` and `s6.rag`.
  - The wrapped `run_eval.generate_grounded_answer` calls through and fills `CAPTURE`.
  - stage8's `record_rewrite_and_classify()` installs its recorders on the bootstrapped `rag`.
  - `capture_answers()` fails closed before bootstrap.
  - h1's eight service names are bound.
- **(d) Dev-only selection.**
  - stage6 `preflight()` returns 47 / 42 cases, all with `split_of == "dev"` (the real dataset is read, plus a read-only read of the recorded baseline id files).
  - A forged dataset that labels a held-out case `split="dev"`, with a matching temp baseline, is rejected with `a non-dev case was selected`.
  - An extra case is rejected with `does not match the recorded baseline`.
  - Wrong DB state is rejected (`unexpected evaluation database state`).
  - h1's selection is Tier 2 dev only and contains no held-out id. h1 refuses a non-scratch `current_database()`.
  - No psycopg connect is attempted on any path.

Mutation check: I temporarily moved stage6's services import above `bootstrap_execution()`. The test then reported 2 FAILs: "bootstrap_execution first" and "scratch switch before services import". I restored the file afterwards and confirmed with grep.

## Commands run (real output)

```
cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B test_stage9_e2_dev_runners.py
-> 38 PASS, 0 FAIL, "0 failure(s)", exit 0

cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B test_stage9_e2_dev_runners.py   (with the temporary mutation in stage6)
-> 2 FAIL ("preflight calls run_eval.bootstrap_execution first", "scratch switch happens before any services import"); file restored

cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B test_stage9_e2_dev_runners.py   (after final edits)
-> 38 PASS, "0 failure(s)", exit 0

cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B test_stage9_e0_runner_gate.py
-> 108 PASS, "0 check(s) failed", exit 0

.venv/bin/python -B -m py_compile eval/stage6_live_dev_eval.py eval/stage8_p3_live_dev_eval.py eval/h1_relevance_gate.py test_stage9_e2_dev_runners.py
-> compiled (no errors)
```

## Not done / uncertainties
- **No lint.** ruff is not installed (not in `.venv` and not on PATH), and neither is pyflakes. Only `py_compile` was run. I checked by eye that no imports are left unused.
- **Not registered in `run_tests.py`.** The lead does that, per the guardrails.
- **No live run.** No runner `main()` was run and no database or provider was contacted, so real execution against `rag_phase35_eval` and Gemini has not been tested end to end.
- **stage8's `KeyError` check is not covered.** That check sits inside `main()`, which the guardrails forbid running. It is unchanged and gets its input from the `s6.preflight()` selection, which is tested.
- **Tests read real files.** The stage6 tests read the real `eval/phase35/results/tier{1,2}_dev.jsonl` baseline id files (read-only) and the real dataset (dev definitions, plus held-out case objects that are used only as mislabelled fixtures and never executed).
- **h1's dev filter is unchanged, including a pre-existing gap.** The filter trusts `c["split"]`. Unlike stage6, it does not re-check `split_of()`. I kept it exactly as it was, per the "preserve selection logic" requirement. Adding a `split_of` re-check to h1 would be a small hardening that the owner can decide on.
- **`bootstrap()` runs on every `preflight()` call.** That is once per process in normal use (stage8 calls `s6.preflight()` once).
