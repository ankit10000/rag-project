# Stage 9 Phase E0: Runner Safety Gate + Reproducible Evaluation Manifest

**Date:** 2026-11-17. **Authorization:** Phase E0 (approved 2026-11-16): implementation and tests only. **Phase E0.1** (a limited follow-up, approved 2026-11-17): refuse `--limit` with held-out/all, and document the accepted `run_eval.py` hash change (§3, §4, §7, §11).

**Not done:**
- No held-out or `--split all` execution.
- No official-runner experiment.
- No LLM/provider call and no database connection.
- No dataset, scorer, threshold, review or source-PDF change.
- Nothing committed or pushed.

## 1. Git state

| | Baseline | Final |
|---|---|---|
| Branch | `audit/stage9-evaluation-readiness` | unchanged |
| HEAD | `69e8b8ec6822959a72d40a18688442808540f3c8` (= `main` = `origin/main`) | unchanged (no commits) |
| Working tree | untracked Phase A report only | see below |
| Phase A report | SHA-256 `96dbff88…2a43` | identical (unchanged) |

Final `git status --porcelain`:
```
 M eval/framework/__init__.py
 M eval/framework/cli.py
 M eval/framework/integrity.py
 M eval/framework/safety.py
 M eval/phase35/run_eval.py
 M run_tests.py
?? docs/remediation/STAGE9_FROZEN_MANIFEST.md
?? docs/remediation/STAGE9_PHASE_A_EVALUATION_READINESS_AUDIT.md
?? docs/remediation/STAGE9_PHASE_E0_COMPLETION_REPORT.md
?? eval/framework/frozen_manifest.py
?? eval/framework/hashing.py
?? eval/phase35/frozen_manifest.json
?? test_stage9_e0_frozen_manifest.py
?? test_stage9_e0_runner_gate.py
```

## 2. Changed files

| File | Change |
|---|---|
| `eval/phase35/run_eval.py` | The scratch DB call and the `services.*` imports **moved from import time into `bootstrap_execution()`**. `main()` calls `enforce_split_gate()` → `safety.runner_gate()` first. New args `--approval-file` and `--frozen-manifest`; `main(argv=None)`. **Scoring, split and tier code untouched** (§7) |
| `eval/framework/safety.py` | The approval file is now structured JSON, **bound** to splits, tiers, output paths and the frozen-manifest `content_sha256` (replaces the bare marker-substring check). New `runner_gate()`, which reuses `check_run_request()` |
| `eval/framework/hashing.py` (new) | Portable SHA-256 (CRLF → LF for text), raw SHA-256, git blob id |
| `eval/framework/frozen_manifest.py` (new) | Build, load and verify the frozen manifest |
| `eval/framework/integrity.py` | `file_hashes()` uses the portable hash (values unchanged for the LF data modules); docstring |
| `eval/framework/cli.py` | `frozen-manifest` and `verify-frozen-manifest` commands (new file only, mode `x`) |
| `eval/framework/__init__.py` | Docstring (module list; the runner no longer has import side effects) |
| `run_tests.py` | Two new tests registered in the `unit` category |
| `eval/phase35/frozen_manifest.json` (new) | The frozen manifest |
| `test_stage9_e0_runner_gate.py`, `test_stage9_e0_frozen_manifest.py` (new) | Tests |
| `docs/remediation/STAGE9_FROZEN_MANIFEST.md` (new) | Manifest format and normalization documentation |
| `docs/remediation/STAGE9_PHASE_E0_COMPLETION_REPORT.md` (new) | This report |

## 3. Gate behaviour

**Order inside `run_eval.main()`:**
1. parse args;
2. compute the output path;
3. **`runner_gate`** (pure: file reads only);
4. on any problem, print `REFUSED` with the reasons and exit **3**;
5. only then `bootstrap_execution()`: the scratch DB is created/connected, `services.*` (provider) is imported and the results dir is created;
6. the original flow follows (`assert_scratch`, load, `--fresh`, ingestion, cases).

**Before E0, merely importing `run_eval` created and connected the scratch DB.** Now import has no side effects: verified with `psycopg.connect` patched to raise; no `services.*` or `google.genai` module was loaded.

| Split | Requirement |
|---|---|
| `dev` (default) | None: `runner_gate` returns `[]` without reading anything. Behaviour unchanged, `--limit` included |
| `heldout` | No `--limit` (E0.1) + `check_run_request(mode="heldout", splits=["heldout"], …)` + verified frozen manifest + bound approval |
| `all` | As above with `splits=["dev","heldout"]` |

**Failure modes (each refuses, exit 3, before any side effect):**
- approval missing;
- approval not JSON, or not an object (malformed);
- a required field missing (incomplete);
- wrong marker or empty `approved_by` / `approved_on`;
- splits mismatch (a `heldout` approval used for `all`, or the reverse);
- tiers mismatch, including `true` given as a tier;
- output-path mismatch;
- `frozen_manifest_sha256` mismatch;
- frozen manifest missing, unreadable, wrong format or self-hash mismatch;
- any frozen asset, dataset, threshold or section differing from the working tree;
- current dataset invalid;
- held-out output file already exists (`--fresh` cannot delete it first: the gate runs before `--fresh`);
- unknown split;
- **(E0.1) `--limit` supplied with `heldout` or `all`**, with any value including `0`. This is checked first, so it refuses even with an otherwise valid approval.

**Unchanged safeguards:**
- `harness._check_scratch_name` allow-list (`rag_db` is still refused);
- `assert_scratch`, `protect_output`, the live-provider opt-in;
- `compare_to_manifest`, `FROZEN_THRESHOLDS`.

**Approval file format:** documented in the `safety.py` docstring. No real approval file was created. Test fixtures exist only inside `TemporaryDirectory` and are bound to temporary output paths; the test proves such a fixture is refused against the real results path.

## 4. Test evidence

Commands. Run individually; `run_tests.py` was **not** used because it fingerprints `rag_db`, which opens a DB connection. `DATABASE_URL` points to an unreachable port and the network is blocked:
```
export DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1
.venv/bin/python test_stage9_e0_runner_gate.py        # 108 PASS, 0 FAIL, exit 0 (E0: 91; E0.1 added 17)
.venv/bin/python test_stage9_e0_frozen_manifest.py    # 25 PASS, 0 FAIL, exit 0
.venv/bin/python test_p4_eval_framework.py            # 22 PASS, 0 FAIL, exit 0 (existing; unchanged)
```

**Runner-gate test method:** `run_eval.main()` is called in-process. Every boundary is a recording tripwire:
- `harness.use_scratch_database` (DB create/connect);
- `psycopg.connect`;
- `build_scratch_corpus` (TRUNCATE + ingest);
- `run_tier1` / `run_tier2` (case execution and LLM calls).

`RESULTS_DIR` is a temp dir with a pre-existing `tier1_dev.jsonl`. The test snapshots it byte for byte before and after.

| Scenario | Result |
|---|---|
| Default split | Runs without approval: 47 dev cases, in dataset order, to `tier1_dev.jsonl` (case runner mocked) |
| Explicit dev (`--limit 3`) | Runs without approval; first 3 dev ids (`--limit` unchanged for dev) |
| **E0.1:** `heldout --limit 5` and `all --limit 5`, each with an otherwise **valid** test approval | Refused (`--limit is not allowed`); zero tripwire calls; results unchanged |
| **E0.1:** Tier 2 `heldout --limit 0` (valid approval); `all --limit 1` (no approval) | Refused, likewise |
| **E0.1:** `runner_gate("dev", …, limit=3)` | `[]` (allowed) |
| Dev Tier 2 | 42 dev cases; the ingestion step still runs first (mocked) |
| Held-out / all / Tier 2 held-out `--fresh`, no approval | Refused; zero tripwire calls; results unchanged |
| Malformed (text, JSON list) | Refused, likewise |
| Incomplete (missing `frozen_manifest_sha256`) | Refused, likewise |
| Wrong split (both directions), tier, bool tier, output path, manifest hash, marker, empty approver | Refused, likewise |
| Missing, edited, or stale (re-hashed, scorer hash changed) frozen manifest | Refused, likewise |
| Existing held-out output with `--fresh` | Refused; the file was **not** deleted |
| Test fixture against the real `eval/phase35/results` | Refused (`output_paths`); real results dir unchanged |
| **Valid test approval** (`heldout` T1, `all` T2) | Gate accepted. Execution stopped at the **first** boundary (`use_scratch_database` tripwire); no case and no ingestion ran; no result file was written |
| Provider boundary | No `services.*` module imported during the whole test |

- **Mutation checks** (in memory only):
  - with `runner_gate` stubbed to always allow, the refusal checks fail as expected;
  - **(E0.1)** with the `limit` argument dropped before the gate, all 10 `--limit` checks fail (10 failed, every other check passes);
  - in both cases the tripwires still stopped the run at the DB boundary, and `eval/phase35/results` stayed clean.
- **Static checks:** `py_compile` OK on all changed Python files; an AST scan found no unused imports. **`ruff` is not installed** in the venv (installing it needs approval), so no lint was run.
- **Size:** `run_eval.py` was 313 lines at HEAD and is now 346 (both over the 300-line guideline). `main()` was 54 lines and is now 59. The frozen scoring code could not be moved in this phase.

## 5. Manifest

- **Generation:** `python -m eval.framework.cli frozen-manifest --dataset-version phase35-corrected-2026-11-12 --output eval/phase35/frozen_manifest.json`
- **`content_sha256` (current, after E0.1):** `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.
  - E0 generated `1208d0ba…6544`.
  - E0.1 changed `run_eval.py`, a manifest input. The verifier reported `frozen asset changed: eval/phase35/run_eval.py`, and the manifest was regenerated once.
  - A diff of the two manifests shows the `run_eval.py` asset entry as the **only** change: no other asset or section changed.
- **Contents:** 27 assets; dataset valid; 160 cases (47 dev / 113 held-out; held-out T1 113, T2 106, answer-only 7); `dataset_sha256` `5c58796a…a7d6`, `split_sha256` `a185fa1c…4424`, matching the values in the Stage 5 report.
- **Format, groups and normalization rules:** see `STAGE9_FROZEN_MANIFEST.md`. In short:
  - text: CRLF → LF only; the BOM is preserved;
  - binary: raw;
  - git blob id of the normalized bytes;
  - raw hashes and time/HEAD/platform go in non-hashed `provenance`.

**Reproducibility:**
- `verify-frozen-manifest` prints **`frozen manifest REPRODUCED`** (exit 0). It rebuilds the content independently and compares it.
- The test also checks that the rebuilt `content_sha256` equals the frozen value.
- The verifier caught a real change: the first manifest was generated before a final `run_eval.py` refactor, and verify reported `frozen asset changed: eval/phase35/run_eval.py`. That file was deleted and regenerated.
- A second `frozen-manifest` run to the same path was refused (`FileExistsError`; no overwrite).

**Portability evidence** (deterministic tests; only macOS was available):
- Synthetic CRLF vs LF fixtures give an equal portable hash. A lone CR, a BOM and trailing whitespace are **not** normalized; binary files are hashed raw.
- Known git blob of `hello\n` (with CRLF too): `ce013625…`.
- **Simulated Windows checkout:** all 27 assets were copied to a temp dir with every text asset converted to CRLF. ≥10 files had different bytes, and `asset_records()` is identical to the LF checkout.
- **Against the recorded Windows hashes:**
  - `validate.py` in CRLF form reproduces `1727a334…`;
  - both review CSVs, written as Windows `csv` output, reproduce `9bd00720…cf77` and `fbe1426e…99ca`;
  - in each case the portable hash equals the macOS one;
  - `data_A..D.py` portable hashes equal the four freeze values exactly.
- **Not tested:** an actual run on Windows.

## 6. Frozen asset integrity

- **Byte-level check:** 34 files were hashed before any edit. The set: data modules, `validate.py`, `run_eval.py`, `answer_scoring.py`, every results/log file, the freeze and correction docs, the Phase A report, all review assets and all PDFs. After the work, the only mismatch is **`eval/phase35/run_eval.py`**, which is intended (§7).
- **Git blob check:** every asset's manifest `git_blob_sha1` equals `git ls-files -s`, except `run_eval.py`.
- **Not modified:** dataset cases, `answer_scoring.py`, `validate.py`, thresholds, the review workbook/CSVs, `source_pages.md`, the PDFs and `eval/phase35/results/*`.

## 7. `run_eval.py` and the freeze: decided in E0.1

- The handoff required wiring the gate into the official runner. That cannot be done without changing the file: its import-time DB creation had to move behind the gate.
- **Top-level AST comparison against `69e8b8e`:**
  - **identical:** `split_of`, `score_generic`, `norm_numbers`, `tier1_context`, `run_tier1`, `run_tier2`, `build_scratch_corpus`, `load_all`, `NUM_RE`, `REF_RE`, `DATA_MODULES`, `RESULTS_DIR`, `ROOT`;
  - **changed:** `main` only;
  - **added:** `bootstrap_execution`, `enforce_split_gate`, `FROZEN_MANIFEST`, and placeholders for the four lazily bound service names.
- The freeze rules cover the split logic and `score_generic`; neither changed. The integrity test `runner_split_logic_matches()` still passes.
- The whole-file SHA-256 recorded in `HELDOUT_THRESHOLD_FREEZE.md` (`3b066a5b…`) no longer matches the working file.
- **Decision (user, E0.1):** accepted as a **non-scoring implementation modification**. See §11 for the hash record.
  - The original hash stays in `HELDOUT_THRESHOLD_FREEZE.md`; that file is byte-unchanged.
  - Thresholds and scorer definitions were **not** re-frozen.
  - The frozen manifest is the integrity reference for the current working tree.

## 8. Safety confirmations

- **No database connection was opened.**
  - Tests ran with `DATABASE_URL` on port 1, `psycopg.connect` tripwires and the testsafe guard.
  - `run_tests.py` was not run, so the `rag_db` fingerprint was skipped.
  - Manifest generation reads files only.
  - `rag_db`, `rag_phase35_eval` and `rag_test_scratch` were not touched.
- **No LLM/provider call:** `TESTSAFE_BLOCK_NETWORK=1`; no `services.*` import; case runners mocked.
- **No held-out case executed.** No `--split heldout|all` run of the real runner. The only real-runner invocation was `run_eval.py --help` (argparse exits before the gate; the import is side-effect free). No held-out question, answer or gold content was read.
- **Approval artefacts:** no real approval file exists; the test fixtures were deleted with their temp dirs.
- **No `--fresh`.**
- **No commits, pushes or staging.**

## 9. Remaining limitations

- **No resume for held-out:** held-out output must not exist, so an interrupted held-out run (crash or quota) leaves a partial file that blocks completion (fail-closed). Partial runs via `--limit` are refused as of E0.1.
- **Blocking on any change:** the gate refuses on any change to any manifest asset, including the human-review workbook. After Phase B the manifest must be regenerated (a re-freeze needing approval) before held-out can pass the gate.
- **Approval provenance:** the file is a structural check. Its authenticity (who wrote it) is not cryptographically verified.
- **`run_eval.py` hash:** accepted (§7, §11). The freeze document still shows the original hash by design. Anyone verifying against it must use this report or the manifest for the current file.
- **Not tested:** an actual Windows run; `ruff` lint (not installed); the full suite via `run_tests.py` (needs a DB connection).
- **Other runners:** they were not gated; they remain dev-only by their own preflights, per Phase A.
- **Stale doc statement:** `PHASE4_EVALUATION_FRAMEWORK.md` still says the gate is not wired in. That historical document was not edited.

## 10. Recommended next phase (not started)

**Phase B:**
1. Independent human review of the 113 held-out rows in the existing workbook.
2. Then the documented re-validation and re-freeze, including regenerating the frozen manifest.

Every later phase needs separate approval.

## 11. Phase E0.1: implementation-integrity record

**Changes in E0.1:**
- `safety.runner_gate(..., limit=None)` refuses any supplied `--limit` for `heldout` / `all`, before the manifest, the approval or any side effect.
- `run_eval.enforce_split_gate` passes `limit=args.limit`; the module docstring has one added sentence.
- 5 new test scenarios (17 checks).
- The frozen manifest was regenerated because `run_eval.py` changed.

**`run_eval.py` hash record:**

| | Original freeze (`69e8b8e`) | Current implementation (E0 + E0.1) |
|---|---|---|
| SHA-256 | `3b066a5b3b4c1de908cb5a555db17762af2bd70606f0854d5f2ba0ce7106e989` (recorded in `HELDOUT_THRESHOLD_FREEZE.md`, kept there unchanged) | `9d4670ce5488499ec79f0cc50598993fc2594ba9d1edb95555b1a6ae379ace94` (portable = raw on this checkout) |
| git blob | `c96a69c1e04a6aef67354d74967123728f6f3716` | `596d8d571abd54a12e64920d9638a2dedcaf0f0c` |
| Status | historical record of the frozen scorer | accepted non-scoring implementation change |

- **AST comparison against `69e8b8e`** (re-run after E0.1): unchanged from §7. All split, scoring and tier functions and constants are identical; `main` changed; `bootstrap_execution`, `enforce_split_gate`, `FROZEN_MANIFEST` and the service placeholders were added.
- **Not modified:** `HELDOUT_THRESHOLD_FREEZE.md` (SHA-256 `3e4bd5d7…be66`, unchanged), the thresholds, the scorer definitions, the dataset and the review assets.
- **Byte-level check after E0.1:** of the 34 pre-change hashes, only `run_eval.py` differs.

**E0.1 verification** (the same commands as §4):
- `test_stage9_e0_runner_gate.py`: 108/108 pass.
- `test_stage9_e0_frozen_manifest.py`: 25/25 pass (includes "frozen manifest reproduces" and "rebuilt content hash equals the frozen `content_sha256`").
- `test_p4_eval_framework.py`: 22/22 pass.
- `verify-frozen-manifest`: `REPRODUCED`.
- `py_compile`: OK.

**E0.1 safety:**
- no held-out or `all` execution;
- no LLM/provider call;
- no DB connection or write;
- no scorer, dataset, threshold or workbook change;
- no commits, pushes or staging;
- all E0 work preserved.

## Addendum (Phase E2, 2026-11-17)

This addendum was added in Phase E2 (work package WP1, documentation only). Sections 1–11 above are left as written; where they conflict with this addendum, the addendum applies.

### A1. Regression: three dev runners broken by E0 (ARCH-1, SEC-1, DOC-1)

§9 says the other runners "remain dev-only by their own preflights". That is true for split selection, but **E0 also broke them**, and this report did not mention it.

- **Cause:** before E0, importing `eval/phase35/run_eval.py` pointed `DATABASE_URL` at the scratch DB `rag_phase35_eval` and imported the `services.*` modules. E0 moved both steps into `bootstrap_execution()` (`run_eval.py:259-269`), which only `run_eval.main()` calls. The module-level service names are now `None` until then (`run_eval.py:47`).
- **Affected runners:** each relied on that import side effect, as its own comments say:
  - `eval/stage6_live_dev_eval.py`: `from eval.phase35 import run_eval  # … (points DATABASE_URL at rag_phase35_eval)`; it also wraps `run_eval.generate_grounded_answer`, which is now `None`;
  - `eval/stage8_p3_live_dev_eval.py`: `from eval import stage6_live_dev_eval as s6  # … (sets the scratch DB via run_eval)`;
  - `eval/h1_relevance_gate.py`: `from eval.phase35.run_eval import build_scratch_corpus, load_all  # … (sets the scratch DB)`.
- **Effect:** they fail closed. Nothing has pointed `DATABASE_URL` at the scratch DB, so `harness.assert_scratch()` refuses (unless the environment already names an allowed scratch DB; `.env` was not read in E1 or E2). No non-scratch database is written. The runners cannot be used as dev runners until repaired. This was found by static reading and grep in Phase E1; the runners were not executed.
- **Repair:** Phase E2 work package WP2 repairs them by calling `run_eval.bootstrap_execution()` explicitly before any `services` import, and corrects the comments. See `docs/remediation/phase_e2_engineering/WP2_RUNNER_REPAIR_REPORT.md`. The official runner `run_eval.py` is not affected.

### A2. Corrected hashes in §5 (DOC-10)

§5 "Contents" abbreviates two hashes with the wrong endings (`…a7d6`, `…4424`). The full values, read from `eval/phase35/frozen_manifest.json` (`content.dataset`), are:

| Field | SHA-256 |
|---|---|
| `dataset_sha256` | `5c58796af13ffe296a08421d9119bbb7f23430d7070d4ace3b281a82e9a7d6a1` |
| `split_sha256` | `a185fa1c1cc49b7cfdd8f73205193cd4886154d05907b8509a5b559f60e44244` |

The manifest itself was always correct; only the abbreviations in this report were wrong.

### A3. Git state is point-in-time

§1 ("Git state") and the git notes in §8 and §11 describe the working tree **when E0 and E0.1 finished**. Later phases (B, C, D, E1, E2) added files, and the project owner has since staged the Stage 9 work. Run `git status` for the current state. `docs/remediation/STAGE9_STATUS_INDEX.md` lists each Stage 9 document and its status.

### A4. Related Phase E2 documents

- `docs/remediation/STAGE9_RUNBOOK.md`: platform, environment variables, commands and the re-freeze procedure.
- `docs/remediation/STAGE9_FROZEN_MANIFEST.md`: the Phase E2 notes on line-reference drift.
