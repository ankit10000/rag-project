# Phase E1: architecture audit (Agent 1, consolidated by the lead)

**Source:** a read-only Explore agent (no Edit/Write tools). Findings were checked by the lead where marked **[LEAD-VERIFIED]**. Corroboration by another agent is noted. Unmarked findings are agent code-reading only.

**Scope:** the run_eval E0/E0.1 gate, approval binding, frozen manifest, CLI, other entry points, and the fit of the scorer v2 architecture.

## Verified working (positive findings)

| Property | Evidence |
|---|---|
| Scoring functions unchanged vs `69e8b8e` | AST comparison: `split_of`, `score_generic`, `norm_numbers`, `tier1_context`, `run_tier1`, `run_tier2`, `build_scratch_corpus`, `load_all` identical; only `main` changed, plus new helpers |
| No side effect before the gate | `run_eval.py:297` `enforce_split_gate` precedes `:298` `bootstrap_execution`. The import loads no `services.*` (also confirmed by Agent 5 and by the lead in E0) |
| Approval binding exact | `safety.py:90-125`: marker; splits as sorted string lists; `type(t) is int`; realpath outputs; manifest SHA. Malformed or incomplete approvals fail closed |
| Manifest cannot be bypassed by editing it | Self-hash (`frozen_manifest.py:146`). Content is rebuilt from code-defined assets and missing or extra assets are flagged (`:158-164`). The verifier reports REPRODUCED (`1b73a208…`) |
| `--fresh` cannot delete held-out output; `--limit` refused for heldout/all | `protect_output` runs before `run_eval.py:308`; `safety.py:177-178` |
| All other entry points select dev only | stage6 (`:108,113`), stage8 (via preflight), h1 (`:56`), replay (`:140`) |

## Findings

| ID | Sev. | Finding | Evidence | Action | Tests |
|---|---|---|---|---|---|
| ARCH-1 | **High** | E0 broke three dev runners that relied on `run_eval`'s former import-time scratch-DB setup. The E0 report does not mention this | `stage6_live_dev_eval.py:28` comment "(points DATABASE_URL at rag_phase35_eval)"; `:77` reads `run_eval.generate_grounded_answer` (now `None`, `run_eval.py:47`); `h1_relevance_gate.py:28` "(sets the scratch DB)"; `stage8_p3_live_dev_eval.py:19`. **[LEAD-VERIFIED]** by grep. Corroborated by SEC-1 and DOC-1. They fail closed at `harness.assert_scratch()` | Call `run_eval.bootstrap_execution()` (or `harness.use_scratch_database`) before any `services` import; fix the comments; add an addendum to the E0 report | Import test per runner with `psycopg`/provider tripwires |
| ARCH-2 | Medium | The gate is CLI-only. `run_tier1`/`run_tier2`/`bootstrap_execution` are public and unguarded; dev-only selection is per script | `run_eval.py:296-298` | Library-level held-out refusal (gate token), or a shared `assert_dev_only` | `run_tier1(heldout case)` without the gate raises |
| ARCH-3 | Medium | Run-once is not enforced: `heldout` then `all` writes different files; an approval is reusable after the output is moved; check-then-append race | `safety.py:71-79`; `run_eval.py:296,335`. Corroborated by SEC-2 and SEC-4 | O_EXCL output claim, held-out run ledger keyed by approval SHA; refuse `all` | Reuse / `all`-after-`heldout` / concurrent-claim refusals |
| ARCH-4 | Medium | An approved `--split all` run produces output no report path accepts (`cli report` takes only dev/heldout; `threshold_result` needs 113/106 rows) | `cli.py:131`; `safety.py:58-68` | Refuse `all` for held-out (recommended) | Gate test |
| ARCH-5 | Medium–High | The system under test is not frozen or recorded: no `services/*`, model or retrieval config in the manifest; rows drop the per-call model | `frozen_manifest.py:30-46`; `run_eval.py:170,177-179`; `llm_config.py:33,37`. Corroborated by SEC-5 | Run-header sidecar (manifest SHA, approval SHA, HEAD, models, config hash) and per-row `models_used`; optionally bind the config hash in the approval | Sidecar created before the first case; mismatch refused |
| ARCH-6 | Low–Med | Gate and integrity code (`safety.py`, `frozen_manifest.py`, `hashing.py`, `integrity.py`, `harness.py`) are not frozen assets | `frozen_manifest.py:30-46` | Add a `gate` asset group at the next re-freeze | Editing `safety.py` causes a verify mismatch |
| ARCH-7 | Medium | Completion of the human review is not part of the gate (freeze rule 4) | `safety.py:164-192`; `review/checks.py:196-201` | Record the review status and sign-off in the manifest; the gate requires `COMPLETE` (manifest format bump) | Gate refusal when not COMPLETE |
| ARCH-8 | **High** (v2 design) | Offline re-scoring cannot rebuild Tier 1 context from the *current* dataset after a correction | **[LEAD-VERIFIED]**: TA-D4 changes B-comp-04's context from `[(velmoor,5),(calder,2),(calder,4)]` to `[…,(calder,5),(calder,4)]`. Corroborated by SCORER-3 and DATA-6. Agent 1's Tier 2 conclusion ("approximation only") is **superseded** by SCORER-2 (see disagreements in the executive report) | Pin the dataset version per run (from the run header); store context text in rows going forward; handle error rows | v1 re-score reproduces the stored score; version-mismatch refusal |
| ARCH-9 | Medium | v2 does not fit the manifest, threshold or report model: hard-coded asset list and format string; thresholds keyed without a scorer; `cli report` reads only v1 `score`; review `DATASET_VERSION` hard-coded | `frozen_manifest.py:30-46,144`; `safety.py:31-36`; `cli.py:82,92`; `review/cli.py:26` | v2 asset group, `acceptance_scorer` in the manifest content (format bump), scorer-keyed thresholds, `report --scorer` | Corresponding unit tests |
| ARCH-10 | Low–Med | No resume for held-out; provider errors become permanent `correct=False` rows | `run_eval.py:322-334`. Corroborated by SEC-3 (rated Medium there) | Owner policy decision: error rows invalidate the run, or a bound "complete-partial" approval | Policy-specific |
| ARCH-11 | Low | `approved_on` is not format-checked although the docstring says YYYY-MM-DD | `safety.py:94-96` (TEST-13 agrees) | Validate ISO dates | Malformed date refused |
| ARCH-12 | Low | Re-freeze has no lineage; the old manifest must be deleted by hand | `cli.py:30-32,43-49` | Versioned manifests plus a pointer; a `supersede` command | Chain verification |
| ARCH-13 | Low | E0 report git state is out of date; `.DS_Store` files staged | `git status` shows `A docs/remediation/.DS_Store`, `A eval/.DS_Store` **[LEAD-VERIFIED]** | Owner unstages them and adds `.DS_Store` to `.gitignore` | — |
| ARCH-14 | Low | `phase35/summarize.py:155,161` overwrites reports (`"w"`); dev `--fresh` deletes git-tracked baselines (pre-existing) | Corroborated by SEC-10 | Mode `x` / explicit outputs | — |
| ARCH-15 | Low | `usage_log` trimming at 5,000 entries would break `usage_log[u0:]` slicing in long processes | `llm_service.py:93-94` | Monotonic counter | — |

## Uncertainties (agent)

- Did not import stage6, stage8 or h1, nor execute them; ARCH-1 is static, and the lead confirmed the cited lines.
- `.env` was not read, so the default `DATABASE_URL` name is unknown. Every analysis shows ARCH-1 failing closed unless `.env` already names a scratch DB.
