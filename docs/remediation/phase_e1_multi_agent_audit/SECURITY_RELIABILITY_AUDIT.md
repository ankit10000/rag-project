# Phase E1: security and reliability audit (Agent 5, consolidated)

**Bottom line (agent, confirmed by the lead where marked):**
- The official runner's gate is **sound against accidental held-out runs**.
- **No path reaches `rag_db` by accident.**
- **No Critical or High findings.**
- **Main risks:**
  - dev runners broken by E0 (failing closed);
  - concurrency;
  - a provider outage using up the single held-out run;
  - the approval and runtime configuration not being bound by the gate.

## Commands run (Agent 5)

Two pure checks, with `psycopg.connect` stubbed:
1. Manifest load and verify: 0 problems.
2. `run_eval` import: no `services.*` or `dotenv` loaded; `llm_service` is `None`; `runner_gate` refuses `heldout`/`all` without an approval.

## Verified-safe properties

| Property | Evidence |
|---|---|
| Side-effect-free import; gate runs before bootstrap | `run_eval.py:297-298`; test `test_stage9_e0_runner_gate.py:226` |
| Gate refusals | Missing, malformed or incomplete approval; any split, tier, output or manifest mismatch; `--limit`; manifest self-hash and reproduction; OSError |
| Path handling | `realpath(join(ROOT, p))` normalises relative paths and `..`; case mismatch fails closed |
| `--fresh` vs held-out | The gate requires the output not to exist, so `--fresh` cannot delete held-out output |
| Dev-only selection everywhere | `split_of` is duplicated and AST-checked; stage6, stage8, h1 and replay assert dev |
| Env loading | `load_dotenv` with `override=False` keeps the harness scratch URL; `assert_scratch` runs after bootstrap |
| testsafe | `dbname` must fully match `[a-z0-9_]`; connect guard on `connect`, `Connection.connect` and `AsyncConnection.connect` |
| `run_tests.py` | Fingerprints `rag_db` with `default_transaction_read_only=on` |
| Review tooling | Reading never writes; CLI outputs use mode `x` |

## Findings

| ID | Sev. | Finding | Evidence | Action |
|---|---|---|---|---|
| SEC-1 | Medium (agent) / **High** (consolidated) | Same as ARCH-1 / DOC-1: dev runners broken by E0. They fail closed via `assert_scratch`. A workaround (exporting the scratch URL) would make stage6 write all-error rows | Lead-verified lines (see ARCHITECTURE_AUDIT). Severity disagreement recorded in the executive report | Explicit bootstrap in the runners; tests |
| SEC-2 | Medium | Concurrent runs are not prevented: existence check at `safety.py:74`, first write at `run_eval.py:335` after ingestion and one case. Tier 2 `TRUNCATE … RESTART IDENTITY` on a shared `rag_phase35_eval` (`:193-194`); h1 shares that DB | Needs two simultaneous launches (plausible with parallel agents) | O_EXCL output claim at gate time; run lock plus `pg_advisory_lock`; refuse `--no-ingest` for held-out or fingerprint the corpus |
| SEC-3 | Medium | A provider outage turns the single held-out run into a complete-looking FAIL: errors become rows; the runner continues; `threshold_result` then sees evaluated == required | **[LEAD-VERIFIED]** `answer_service.py:117-120,197` returns `_result(ERROR_MESSAGE, "error", …)`; `run_eval.py:325` catches all | Provider preflight; circuit breaker after N errors; error rows are "not evaluated" for held-out reporting |
| SEC-4 | Medium (governance) | The approval is self-asserted, unauthenticated and reusable after the output is moved; all binding values are public | `safety.py:92-96`; test fixture pattern | Require a git-tracked approval at HEAD in a fixed directory; a consumed marker (O_EXCL); a sidecar with the approval SHA |
| SEC-5 | Medium | Runtime config (prompts, `services/*`, model env vars, retrieval config, `--no-ingest` corpus state, gate code) is not frozen or bound | `frozen_manifest.py:30-46`; `llm_config.py:33,37`; `retrieval_config.py:17-75`. Overlaps ARCH-5/6 | Add assets; bind the resolved config hash; refuse held-out with overrides |
| SEC-6 | Low | Check-then-write races and dangling-symlink following: runner (`exists` then `open(…,"a")`); `dev_artifact.py:116` exists check then `:137 wb.save` | **[LEAD-VERIFIED]** for `dev_artifact.py` (Phase B code by the lead) | `os.path.lexists` plus O_EXCL; open with `"xb"` and save to the handle |
| SEC-7 | Low | The harness scratch allow-list matches `rag_members`, `rag_embeddings`, `rag_db_eval`, and `drop_scratch_database` uses `DROP … WITH (FORCE)`. The testsafe pattern matches `rag_latest` and `rag_attestations` | **[LEAD-VERIFIED]** by regex check. Hypothetical unless such DBs exist | Anchored explicit allow-list |
| SEC-8 | Low | Eval runners do not install the testsafe connect guard; `assert_scratch` checks the URL string, not `current_database()`; URL rewrite drops query params | `harness.py:39,110-116` | Guard plus `SELECT current_database()` after bootstrap |
| SEC-9 | Low | Network block does not cover `connect_ex`, UDP, C-level sockets or subprocesses | `testsafe.py:101-122` | Patch `connect_ex`; document the limits |
| SEC-10 | Low | Dev `--fresh` deletes git-tracked baselines (pre-existing); dev runs append to them | `run_eval.py:308-309` | New default dev output |
| SEC-11 | Low | No fsync, so a torn last line breaks resume; no documented recovery for an interrupted held-out run; `RUNNER ERROR: {error!r}` may write provider payloads into results | `run_eval.py:313,327,335` | Line flush and fsync; tolerate a torn line; record the error type only |
| SEC-12 | Low | `git show` option injection through `--baseline-git` (operator input) | `review/cli.py:62` (lead's Phase B code) | Reject a leading `-`; `rev-parse --verify --end-of-options` |
| SEC-13 | Info | openpyxl without defusedxml; repository inputs only; `read_workbook` never saves | `workbook.py:81` | — |
| SEC-14 | Low | `.DS_Store` staged; the B test breaks once review starts; saving the review xlsx blocks the gate until re-freeze (intended, undocumented) | Corroborated by DOC-2, DOC-14 and TEST-10 | See the release audit |

## Multi-agent concurrency note (this phase)

**Read-only enforcement:**
- All six E1 agents were read-only by tool design (no Edit/Write tools).
- Agents 2–5 executed only pure snippets or the permitted test files, with `-B`.
- The lead compared a SHA-256 snapshot of all 464 working-tree files taken before the agents started with the post-audit tree. The only additions are this directory's files (see the completion section of the executive report).

**One environment-loading event:**
- The lead's own verification snippet imported `services.retrieval_config`, which calls `load_dotenv()` at import. That loaded `.env` values into the memory of a short-lived process.
- Nothing was printed, no connection was opened, and the process exited.
- The following verification avoided that module.

## Uncertainties (agent)

- DB-touching paths were analysed statically.
- Hugging Face model loading at import in h1 was not verified.
- Older benchmark scripts were grep-checked only. `embedding_audit.py` reads the application DB through `.env` without a read-only session; that is pre-existing and outside Stage 9.
