# Stage 9 Phase E2: WP3 test engineering report (Agent 3)

**Scope:** TEST-1 to TEST-14, SCORER-1/6/12/13 and DATA-1, as far as they concern tests.

**Guardrails kept:**
- No database, LLM, provider or network access, and `.env` was never read.
- `run_eval.py main` and `run_tests.py` were not run, and nothing was evaluated on the held-out split.
- No git write operations.
- Files I do not own were not edited, including `run_tests.py`, `eval/answer_scoring.py`, `eval/phase35/*`, `eval/framework/*` and the Phase D package.
- The v1 scorer and the dataset are unchanged; `test_stage9_v1_immutability.py` proves this.

## Files

| File | Change |
|---|---|
| `eval/probes/__init__.py` | new package |
| `eval/probes/scorer_regression.py` | new: the harness engine and CLI. Replaces the Phase D script, which stays unchanged as a historical record |
| `eval/probes/schema.py` | new: the probe record (`probe()`) and the v1 sub-signal shorthand (`S()`) |
| `eval/probes/proposals.py` | new: the 15 Phase D proposals with TA-11 corrected, potential proposal TP-02, the superseded Phase D TA-11 (lookup only) and the synthetic case |
| `eval/probes/probes_phase_d.py` | new: the 72 Phase D probe ids, with full v1 sub-signals and annotations; 3 corrected |
| `eval/probes/probes_e2.py` | new: 38 Phase E2 probes |
| `eval/probes/probe_data.py` | new: `PROBES` = Phase D probes + E2 probes (110) |
| `test_stage9_scorer_probes.py` | new |
| `test_stage9_v1_immutability.py` | new |
| `test_stage9_review_checks_branches.py` | new |
| `test_stage9_gate_branches.py` | new |
| `check_stage9_readiness.py` | new live-state readiness report (not a test) |
| `test_stage9_e0_runner_gate.py` | uses a fixture manifest |
| `test_stage9_e0_frozen_manifest.py` | uses a fixture manifest; live checks moved to the readiness report |
| `test_stage9_b_review_tools.py` | real-workbook checks no longer depend on review progress; file handles are closed |
| `eval/review/checks.py` | the two TEST-14 functional gaps fixed (diff below) |

## Commands and real results

Every command below ran from `/Volumes/Storage/rag-project` as:

`DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B <file>`

| File | Exit | PASS | FAIL | Before E2 |
|---|---|---|---|---|
| `test_stage9_e0_runner_gate.py` | 0 | 110 | 0 | 108 / 0 |
| `test_stage9_e0_frozen_manifest.py` | 0 | 24 | 0 | 25 / 0 |
| `test_stage9_b_review_tools.py` | 0 | 44 | 0 | 40 / 0 |
| `test_stage9_scorer_probes.py` | 0 | 134 | 0 | new |
| `test_stage9_v1_immutability.py` | 0 | 21 | 0 | new |
| `test_stage9_review_checks_branches.py` | 0 | 38 | 0 | new |
| `test_stage9_gate_branches.py` | 0 | 40 | 0 | new |
| `-m eval.probes.scorer_regression --validate-proposals` | 0 | 110 probes, 0 failures | | Phase D: 72 |
| `check_stage9_readiness.py` (not a test) | 0 | 0 problems, 0 warnings | | new |

**Results of the harness and readiness runs:**
- **Harness, `--validate-proposals`:** both proposal sets validate as VALID, Phase D's 15 alone and the 15 plus TP-02.
- **Harness, `--v2 eval.probes.schema`:** this module has no `score_case`, so the run printed "v2 expectations skipped" and exited 0.
- **Readiness report:**
  - the committed manifest REPRODUCED (`1b73a208…`);
  - the dataset is pinned;
  - all historical freeze hashes match;
  - held-out workbook: NOT_STARTED, 0 reviewed / 113 pending;
  - dev workbook: NOT_STARTED, 0 reviewed / 7 pending.

**Side effects checked:**
- `git status` was identical before and after `test_stage9_gate_branches.py`.
- No `__pycache__` appeared in `eval/probes`.

## How each test was decoupled from live state (TEST-10 / TEST-11)

### `test_stage9_e0_runner_gate.py` (108 → 110 checks)

**How the fixture works:**
- At start-up the test builds `frozen_manifest.build_content(version)` from the current working tree.
- It writes that content, with its `content_sha256`, to a `TemporaryDirectory`.
- `sandbox()` patches `run_eval.FROZEN_MANIFEST` to point at the fixture. The argparse default reads it when `main()` runs, so every argv stays identical.

**What stays the same:**
- The gate really verifies the fixture against the tree; nothing is mocked out.
- Approvals are bound to the fixture's hash.
- The tampered and stale manifests are derived from the fixture.
- All existing refusal, tripwire and result-unchanged assertions are kept.

**What was added:**
- 2 checks: the fixture loads, and the runner's default path is still the committed `eval/phase35/frozen_manifest.json`.
- If the valid-approval check fails, it prints the gate's problem list.

**Evidence that the test no longer depends on the committed manifest:** I patched `build_content` in-process to simulate an approved change to `data_A.py`. The committed manifest then reported `frozen asset changed: eval/phase35/data_A.py`, and the test still passed with 0 failures.

### `test_stage9_e0_frozen_manifest.py` (25 → 24 checks)

**Moved to `check_stage9_readiness.py` (6 checks):**
- "committed manifest reproduces";
- "rebuilt hash equals the committed content_sha256";
- dataset modules equal the recorded Windows freeze hashes (TEST-11's line 79);
- `validate.py` equals its recorded CRLF hash;
- the two review CSVs equal their recorded hashes.

**Added (5 checks):**
- the fixture manifest loads;
- the fixture reproduces;
- the rebuild is deterministic (the hash equals the fixture's);
- a manifest that records a different asset hash does not reproduce (it names the asset);
- the committed manifest uses the same format, hashing and asset groups as the builder.

**Kept:**
- the hashing-rule checks;
- the portable CRLF/LF equalities on the real files;
- the simulated Windows checkout;
- the committed manifest's self-consistency and its recorded counts and thresholds.

### `test_stage9_b_review_tools.py` (40 → 44 checks)

**Replaced:** the 2 real-workbook checks that required 0 reviewed and 113/7 pending.

**New checks, 3 for each workbook:**
- `validate` exits 0 with no errors;
- `rows == expected` and `pending + reviewed == expected`;
- the file is byte-identical after reading and validating.

**Moved:** live status and counts are now reported by the readiness script.

**Also fixed:** `open(...).read()` without closing the file was replaced by a `with` helper (TEST-15). It now runs clean under `-W error::ResourceWarning`.

### `check_stage9_readiness.py`

Read-only; it imports no services and writes nothing.

| Exit 1 (PROBLEM) | WARNING | INFO |
|---|---|---|
| The committed manifest does not load or reproduce | Current files differ from the historical freeze (expected after an approved re-freeze) | Workbook status, counts and ledger summary |
| The dataset differs from the manifest's `dataset_sha256` | | |
| Workbook integrity errors or wrong row counts | | |
| A workbook changes while being read | | |

## Probe harness (`eval/probes`)

### Per-probe fields

| Field | Values |
|---|---|
| `id`, `limitation`, `target` | target is a case id, `PROP:<id>` or a synthetic id |
| `answer`, `truth` | |
| `status` | default `answered`; also `abstained`, `unverified`, `error`, `partial` |
| `citations` | `all_gold` (default), `none`, or an explicit list of chunk ids, which may include ids outside the context |
| `context` | `gold` (default) or `tier1`, built with the real seeded `run_eval.tier1_context` |
| `extra_context` | extra (document, page) pairs added to a `gold` context |
| `annotations` | dict for v2 |
| `v1` | expected v1 sub-signals |
| `v2`, `v2_reason` | intended v2 outcome; `None` requires a reason |
| `classification`, `reason` | |
| `phase_d_change` | how a Phase D probe was changed |

**v1 sub-signals asserted for every probe:** `correct`, `fact_recall`, `forbidden_hits`, `abstain_ok`, `partial_ok`, `conflict_ok`, `fabricated`. Where relevant, also `citation_completeness`, `citation_correctness` and `ungrounded_numbers`. Every value was recorded from the real v1 output.

**v2 contract:** `--v2 MODULE` calls `score_case(case, result, chunk_pair, context_ids, context_text, history, annotations)` if the module defines it. If not, it prints a skip message.

### Corrected Phase D probes (3)

| Probe | Correction |
|---|---|
| P-TS1-06 | Now runs in a real **Tier 1** context. Its distractors, Orchard Lane p2 and the Kestrel agreement p5, contain "3", so `ungrounded_numbers=[]`, and v2 is set to **True** (a residual false positive). Phase D's False was an artefact of the gold-only context. |
| P-TS1-09 | v2 changed True → **False**, with a reason: no v2 rule maps "people" to "visitors". The companion P-E2-TS1-09B runs on `PROP:TP-02` and passes v1 and v2. |
| P-TAD4-1 | Replaced with a `citation_completeness` probe: `PROP:TA-D4`, Tier 1 context, citing only chunk 2 gives completeness 0.5, and `correct` stays True. Controls are P-E2-TAD4-2 (current definition: 1.0) and P-E2-TAD4-3 (both pages cited: 1.0). |

**Proposal correction:** TA-11 G1 is now `["battery", "batteries"]` (DATA-1).

**Annotations added to Phase D probes:** P-TS3-01/02/03/04/05/07, P-TS5-01, P-TA01-3, P-TA02-3 and P-TA06-2, using the design's `{"forbidden": [{"text", "kind", "allowed_with"}]}` format and `negatable_groups`.

### Added probes (38)

**Notable v1 results:**
- **P-E2-SWAP-02:** once TA-03 is applied, **v1 accepts the value swap "It is GBP 2,000, not 1,800."**. This is evidence for the SCORER-13 owner decision.
- **P-E2-NUM-03:** `12,000` triggers the forbidden `2,000` (a v1 false negative).

| Group | Probe ids | v1 result | Intended v2 |
|---|---|---|---|
| Companions | P-E2-TS1-06B (Tier 1, ungrounded $4.25), P-E2-TS1-09B, P-E2-TAD4-2, P-E2-TAD4-3 | — | — |
| DATA-1 | P-E2-TA11-3: "Batteries and filters get 6 months; a replacement gets the rest of the warranty or 90 days." | True under the revised TA-11 | — |
| DATA-1 (superseded) | P-E2-TA11-4: same answer on the superseded Phase D TA-11 | False | None, with reason |
| History echo (SCORER-1) | P-E2-HIST-01 (A-followup-02 "$65 or $85…"), -02 (B-follow-01 + TA-03 "GBP 1,800 or 2,000."), -03 (D-follow_up-01 "18 g…; some sources say 30 g."), -04 (C-follow_up-04), -05 (B-follow-02), -06 (A-followup-04), -07 (C-follow_up-03) | **True** | False; annotated `history_wrong_values` |
| Value swaps | P-E2-SWAP-01 (B-follow-01) | False | False |
| | P-E2-SWAP-02 (same answer on `PROP:TA-03`) | **True** | False |
| | P-E2-SWAP-03 (D-direct-02, "On P-205 use 18 g, not the 30 g used on P-204.") | False | False |
| Hedges | P-E2-HEDGE-TA03 / -TA04 ("Either 120 days or 90 days' notice.") / -TAD1 / -TAD2 / -TAD3 | **True** | False, with annotation |
| TA-D2 negative | P-E2-NEG-TAD2 | False | False |
| Number boundaries | P-E2-NUM-01 ("within 11 hours"), P-E2-NUM-02 ("$650"), P-E2-NUM-04 ("0.58") | True | False |
| | P-E2-NUM-03 ("12,000" contains "2,000"; Kestrel call p3 added as extra context) | False | True |
| Status branches | P-E2-STAT-01 (abstained + fabricated price) | **True** | False |
| | P-E2-STAT-02 (genuine abstention) | True | True |
| | P-E2-STAT-03 / -04 / -05 (`abstained` on an answerable case; `unverified`; `error`) | False | False |
| | P-E2-STAT-06 (`partial`) | True | None (SCORER-8 owner decision) |
| Citations | P-E2-CIT-01 (citation id 99 outside the context) | correct True, `fabricated=1`, `citation_correctness=0.5` | — |
| | P-E2-CIT-02 (partial-citation conflict on B-conf-02: one page cited, so `conflict_ok` False, completeness 0.5) | False | False |
| TA-06 echo pair | P-E2-TA06-3 / -4 (negated "same appointment", current and proposed definitions) | True, both | False, `negatable_groups` |
| | P-E2-TA06-5 / -6 ("you can have them together", current and proposed) | False, both | False (needs a data change; DATA-5) |

### `test_stage9_scorer_probes.py` checks

- **Probe data:**
  - unique ids;
  - every target exists, including a proposal's case;
  - every probe asserts the 7 core sub-signals;
  - v2 `None` needs a reason; the schema refuses a missing reason.
- **v1 assertions:**
  - all v1 sub-signals for all 110 probes, one check per probe;
  - a negative control shows that a wrong expectation is reported.
- **Dataset pin:** `dataset_hash == manifest dataset_sha256`. If they differ, it prints **SKIP** and does not run the v1 assertions (no silent pass).
- **No mutation:** the dataset is unchanged after scoring.
- **Phase D correspondence:**
  - all 72 rows of `SCORER_REGRESSION_MATRIX.csv` are harness probes;
  - the matrix equals the Phase D `PROBES` literal, read with `ast` and never imported;
  - harness probes differ from Phase D **only** at P-TAD4-1, P-TS1-06 and P-TS1-09, which carry `phase_d_change`.
- **Proposals:**
  - TA-11 is corrected;
  - `validate.validate` returns no errors with the 15 proposals, and with 15 + TP-02, applied in memory.
- **v2 hook:**
  - a fake module without `score_case` is skipped;
  - a fake `score_case` receives the case, the history and the annotations.
- **CLI:** `--write-matrix` writes 110 rows in a temp dir and refuses to overwrite.
- **Imports:** no `services.*` module is imported.

## `test_stage9_v1_immutability.py` (21 checks)

**Checks:**
- **Scoring file:** the portable SHA-256 of `eval/answer_scoring.py` is `c3b54228…67af`.
- **AST identity with HEAD:** `ast.dump` SHA-256 of `score_generic`, `norm_numbers`, `split_of`, `tier1_context`, `NUM_RE` and `REF_RE` are compared with `git show HEAD:eval/phase35/run_eval.py`, which is read-only and is skipped with a message if git is unavailable.
- **AST identity with the recording:** the same hashes are compared with values recorded now. They are compared only on Python 3.14, because `ast.dump` output depends on the Python version.
- **Phrase lists:**
  - 22 / 7 entries;
  - `run_eval` uses the very same list objects;
  - still 22 / 7 after importing the probe harness.
- **scoring_v2:** no import in `run_eval.py` (checked statically) and none loaded at runtime.
- **services:** none imported.

## `eval/review/checks.py`: the two TEST-14 fixes

```diff
-    history = 0
+    history, history_check = 0, "not run (no baseline)"
     if baseline is not None:
         base = [...]
-        history = len(base)
+        history, history_check = len(base), "passed"
         if entries[:history] != base:
             errors.append(f"historical ledger entries 1-{history} were changed")
+            history_check = "FAILED"
 ...
-    proposed_ids = set()
+    proposed_ids, unverified = set(), []
 ...
             if baseline is not None:
                 errors.append(f"ledger #{n} ({cid}): new entry not marked {PROPOSED_PREFIX!r}")
+            else:
+                unverified.append(n)
             continue
 ...
+    if unverified:
+        incomplete.append(f"ledger entries {unverified} are not marked {PROPOSED_PREFIX!r} and were not "
+                          "verified as historical: no baseline given (use --baseline-git)")
 ...
-    return ..., {"entries": len(entries), "historical_verified": history,
+    verified = history if history_check == "passed" else 0
+    return ..., {"entries": len(entries), "historical_verified": verified,
+                                "historical_check": history_check,
```

### Fix (a): unmarked ledger entries without a baseline

**Change:** they are now reported as **incomplete**, not as an error.

**Why incomplete:**
- Without a baseline, an unmarked entry cannot be told apart from history. The real held-out workbook has 26 legitimate historical entries.
- An error would make every `validate` without `--baseline-git` fail with exit 1, including on the untouched real workbook.
- As incomplete, the review can **never reach COMPLETE** unless a baseline verifies the history, and nothing is silently ignored any more.
- With a baseline, the existing error behaviour is unchanged.

### Fix (b): count after a failed history check

**Change:** `historical_verified` is now 0 when the check failed, and a new `historical_check` field reads `passed`, `FAILED` or `not run (no baseline)`.

All other behaviour is unchanged.

**Evidence:**
- `test_stage9_b_review_tools.py` passes all 44 checks.
- Run against the original `checks.py` (a copy loaded in-process), the new "FIXED" checks fail.

## `test_stage9_review_checks_branches.py` (38 checks)

**Pure helpers:**
- `_flag`: `"yes"`, blank, TRUE / FALSE;
- `valid_date`: 2026-02-30 rejected, date cells accepted;
- `_covers`: multi-range in both directions; a single cell.

**Definition drift**, one check per field: history, forbidden, sources, tier, category, `data_file`, `expected_facts_json` (invalid JSON), and a flag set to `"yes"`. A blank history cell counts as `[]`.

**Structure:**
- missing or wrong-choice dropdown;
- dropdown not covering the case rows, including a multi-range;
- missing column;
- different ledger layout;
- a real temp xlsx with no case, ledger or read-me sheets;
- no sign-off fields.

**Rows and status:**
- IN_PROGRESS;
- whitespace-padded decisions counted;
- impossible date;
- read-me without sign-off.

**Ledger:**
- split mismatch, using a split function that returns `heldout` for X-1;
- deleted history;
- both fixed gaps;
- an unmarked entry with a baseline is still an error;
- PROPOSED-only entries without a baseline still reach COMPLETE;
- the baseline is not modified.

## `test_stage9_gate_branches.py` (40 checks)

Everything runs in temp dirs with monkeypatching.

**`load_frozen_manifest`:**
- not JSON; not UTF-8;
- a JSON list; content missing; dataset missing;
- wrong format; content hash mismatch;
- path is a directory, `None`, or missing.

**`verify_frozen_manifest`:**
- extra source PDF, which also changes the PDF/document match section;
- frozen asset missing from the tree;
- threshold drift via `mock.patch.dict(safety.FROZEN_THRESHOLDS)`;
- invalid dataset, via a patched `build_manifest`.

**`runner_gate`:**
- the valid fixture is accepted;
- the OSError path names the error class and file;
- a malformed manifest stops before verification.

**Approval file:**
- path is a directory;
- non-UTF-8 bytes; a BOM is accepted;
- duplicate splits; duplicate tiers; a string instead of a split list;
- an empty output path; an empty `approved_on`.
- **KNOWN GAP ARCH-11 (for WP7):** `approved_on: "yesterday"` is ACCEPTED. The test documents current behaviour; `safety.py` was not changed.

**`check_run_request`:**
- invalid mode;
- offline mode with a live provider;
- development without opt-in;
- offline + heldout;
- unknown split / tiers;
- dataset differs (names the field);
- invalid dataset manifest.

**`threshold_result`:**
- NO_FROZEN_THRESHOLD;
- 97/113 PASS, 96/113 FAIL;
- INCOMPLETE.

## For the lead: register in `run_tests.py` CATEGORIES["unit"]

- `test_stage9_scorer_probes.py`
- `test_stage9_v1_immutability.py`
- `test_stage9_review_checks_branches.py`
- `test_stage9_gate_branches.py`

`check_stage9_readiness.py` is **not** a test. It reports live state and is meant to be run on its own.

## Not done, and uncertainties

### Owned by other people

| Owner | Item |
|---|---|
| progress.py (not mine) | `eval/review/progress.py` prints `historical_verified or 'not checked (no baseline)'`. After a **failed** history check it will now say "not checked (no baseline)". The report's `errors` still names the failure and the status is NEEDS_RESOLUTION. progress.py should print `historical_check` |
| WP4 / Phase D owner | The proposal CSVs in the Phase D package still show TA-11 as `["battery"]`. I left the package unchanged as required |
| framework owner | `eval/framework/integrity.py:runner_split_logic_matches` leaves a file handle open; it shows up only under `-W error::ResourceWarning` |
| WP7 | ARCH-11, the `approved_on` validation |

### My uncertainties

- **v2 expectations:** they are design intent and have not been run, because v2 does not exist.
  - The annotation format follows the Phase D design.
  - `history_wrong_values` and `negatable_groups` are names I chose, from SCORER-1 and the "fact-negation guard"; v2 must adopt or rename them.
  - The hedge probes' v2=False assumes the owner keeps the superseded value as an assertion annotation (SCORER-13).
- **Real held-out workbook:** without `--baseline-git` it now carries one extra *incomplete* item (the 26 unmarked historical ledger entries). `--baseline-git HEAD` cannot be used yet, because the workbook is only staged and is not in HEAD.
- **Tooling:** no `ruff` is installed in `.venv` and none was installed. Instead I checked with Python's `ast` module: no unused imports, no function over 50 lines, and all new files are under 300 lines. A few test lines are over 120 characters, as in the existing Stage 9 tests.
- **Machine-specific checks:** the recorded AST hashes are checked only on Python 3.14. The git HEAD comparison applies on every version.
