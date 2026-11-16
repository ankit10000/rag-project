# Batch 2, Stage 8, Phase B: Memory Test Contract Recovery

**Date:** 2026-11-16. **Scope (approved):** P1 + P2, tests only. P3 (classification) **not** approved and not touched.
**Not done:**
- No application, migration, runner, evaluation, retrieval, grounding, provider or classifier change.
- No LLM call.
- No manual database cleanup; `--clean` not used.
- Nothing committed or pushed.

## 1. Test files changed

| File | Lines |
|---|---|
| `test_p1_process_memory.py` | +40 / −10 |
| `test_p1_delete_routing.py` | +17 / −8 |

No other file was modified by this phase. `git diff --quiet` on `services/`, `main.py`, `migrations/`, `eval/`, `backend/`, `run_tests.py` and `testsafe.py` is clean.

Git note: `docs/remediation/BATCH2_STAGE8_PHASE_A_AUDIT.md` and `POST_MERGE_BASELINE_REPORT.md` appear **staged (`A`)**. That was not done by this phase (no `git add` was run). They are left as found. The two test files are unstaged.

## 2. Old versus new expectations

| Check | Old expectation | New expectation | Contract |
|---|---|---|---|
| `[5]` | `"   "` → `SKIPPED` | → **`UNCERTAIN`**, no row, no decision call | Phase 1 Task 4: `normalize_memory_text` returns None → reject |
| `[7]` | Text `"x"` with candidates `[("5","x"), (None,"y"), ("abc","z"), (7,"w")]`; decision receives `[(5,"x"),(7,"w")]` (crashed: `"x"` is an exact duplicate, so no decision call) | Non-duplicate text `"something else"`; decision receives `[(5,"x"),(7,"w")]` | Candidate normalisation (unchanged intent) |
| `[7b]` (new, 2 checks) | — | An exact restatement (`"user likes  tea."` vs `"User likes tea"`) → `SKIPPED`, **decision not called**, rows unchanged, restating message linked as `confirmation` | Phase 3 exact-duplicate shortcut (`process_memory`) |
| `[13]` ×3 *(surfaced, category A; see 4)* | DUPLICATE decision with None / foreign / nonexistent id, new text `"Seed A"` → nothing linked | New text `"Seed A, restated"` (not an exact duplicate), so the model's DUPLICATE decision is actually reached → nothing linked | Phase 3 shortcut; the model-decision path |
| `[19]` | `updated_memory=123` stored as `"123"` | → **`UNCERTAIN`**, text unchanged (`"User lives in Delhi"`), no coercion | Phase 1 Task 4: no `str()` coercion |
| Guards (`[6]`, `[7]`, `[b2]`, `[b11]`) | `d.call_args.kwargs[…]` / `.args` (raises if the mock wasn't called) | `call_kwargs(m)` / `call_args(m)` helpers return `{}` / `None` → a readable FAIL instead of `AttributeError` aborting the file | Test robustness |
| `[N2]` ×3 | `search_memories` mocked as `[{"memory":"M1"},…]` (no `id`); `memory_summary == "S\nM1\nM2"` / `"M1\nM2"` / `""` | `main.assemble_memory_context` mocked as `{"text": "CTX"}`: `"S\nCTX"` / `"CTX"` / `""` | Phase 3: `run_turn` composes summary + context text. Provenance filtering stays covered by the Phase 3 / Stage 7 tests |
| `[N2]` harness | — | `assemble_memory_context` added to the patched set as a **pass-through** (`wraps=` the real function) by default, so `[N1]` still verifies the `search_memories` call through it | — |
| `[N3]` | `extract_and_save_memories(conversation_id="conv-test", messages=batch, source_message_id=14)` | `extract_and_save_memories(conversation_id="conv-test", messages=batch)`; exact call equality proves no fallback `source_message_id`. The checkpoint assertion is unchanged | Phase 1 Task 1 strict attribution |

## 3. P1: `test_p1_process_memory.py` complete check count

| Run | Command | Database | Result |
|---|---|---|---|
| 1 | `.venv/bin/python run_tests.py test_p1_process_memory.py` | `rag_test_scratch` | FAIL: 103 PASS / **3 FAIL** (`[13]`, see 4); the file **ran to completion** for the first time since 2026-11-15 |
| 2 (after the `[13]` correction) | Same | `rag_test_scratch` | **PASS: 106 / 106 checks, 0 FAIL, 0 FINDING, exit 0** |

Full per-check output was captured by running the same file with the runner's exact environment (scratch URL, `TESTSAFE_BLOCK_NETWORK=1`, offline models), because the runner prints only the last 8 lines of a failing file.

## 4. Previously hidden checks executed

**Before Phase B,** the crash at `[7]` stopped the file after **13** checks (`[1]`–`[6]`). Now executed:
- **91** previously hidden original checks:
  - `[7]`;
  - `[8]`–`[29]` + `[20b]` (65 checks);
  - `[D2]`;
  - `part_b` `[b1]`–`[b11]` + probe (25 checks).
- plus the 2 new `[7b]` checks.

**Newly surfaced failure and its classification:**

| Check | Classification | Evidence |
|---|---|---|
| `[13]` DUPLICATE with None / foreign / nonexistent id → "confirm_memory not called, nothing linked" (3 FAIL; the paired "→ SKIPPED" checks passed) | **A: outdated test expectation** | The new text `"Seed A"` exactly restates the seeded own-conversation memory `"Seed A"`. The documented Phase 3 shortcut (`process_memory`: "an exact restatement … is a DUPLICATE without a model call. The new source is linked as confirmation") correctly linked the user message to that **real, owned** memory, so the mocked invalid-id decision was never reached. `find_exact_duplicate("Seed A", [(1,"Seed A")]) → 1` (DB-free). The provenance written was valid. Corrected by using non-duplicate text so the check tests its intended path; it then passes |

- **Category B (potential real implementation defect): none found.**
- **Category C (environment or fixture problem): none.**

## 5. DELETE-ban and isolation results

**P1-03, automatic extraction cannot DELETE (`[22]`–`[27]`): 18/18 PASS.**
- **Without `allow_delete`:** a DELETE with a valid id → `SKIPPED` and `delete_memory` is not called (`[22]`). The ban applies even before the invalid-id check (`[23]`).
- **With `allow_delete`:** a valid id → `DELETED`, the sibling and the other conversation are intact (`[24]`). None / foreign / nonexistent ids → `UNCERTAIN`, nothing deleted (`[25]`). Storage refusal → `SKIPPED` (`[26]`).
- **`delete_only`:** only DELETE acts. NEW / DUPLICATE / UPDATE / UNCERTAIN → `UNCERTAIN`, with no save, update or confirm and rows unchanged (`[27]`, 9 checks).

**P1-05, ownership and isolation: all PASS.**
- `[9]` other conversation untouched.
- `[13]` foreign DUPLICATE id: nothing linked.
- `[16]` foreign UPDATE id: no update.
- `[21]` foreign-conversation source raises `ValueError` and is rolled back.
- `[24]` other conversation intact.
- `[25]` foreign delete id refused.
- `[b2]` classifier receives only own memories.
- `[b4]` only foreign/nonexistent ids → `NO_MATCH`.
- `[b5]` mixed own + foreign → only own removed, other conversation intact.

## 6. P2 results

| Run | Database | Result |
|---|---|---|
| `.venv/bin/python run_tests.py test_p1_delete_routing.py` | `rag_test_scratch` (the test itself is fully mocked) | **PASS: 137 / 137 checks, exit 0** |

`[N1]` (5 checks), `[N2]` (3) and `[N3]` (4) all pass.

**Related provenance and checkpoint tests** (`run_tests.py test_stage7_memory_provenance.py test_p1_task1_strict_attribution.py test_phase5_provenance.py test_p1_memory_update_delete_integration.py test_extraction_and_summary_guards.py test_p3_memory_intelligence.py`): **6/6 PASS**, `rag_db` unchanged.

## 7. Full regression

| Run | Result |
|---|---|
| `.venv/bin/python run_tests.py` (unit + integration, `rag_test_scratch`) | **48 run / 48 passed / 0 failed**, exit 0. 2 smoke-only passes (`test_similarity.py`, `test_memory_storage.py`); 18 live/manual tests not run (out of scope). `rag_db` fingerprint unchanged |
| Post-merge baseline (before Phase B) | 48 / 46 / 2 |

## 8. Database fingerprints

Method: `run_tests.fingerprint` (row count + md5 per table, read-only transaction, `current_database()` verified), applied to every existing table.

| Database | Before Phase B | After P1 | After everything |
|---|---|---|---|
| `rag_db` | 0 / 0 / 0 / 0 / 0 rows (conversations / messages / memories / links / chunks) | identical | **identical** |
| `rag_test_scratch` | 0 / 0 / 0 / 0 / 0 | identical (the test removed its own fixtures in `finally`) | **identical** |
| `rag_phase35_eval` | chunks 135 (other tables absent) | identical | **identical** |

- Scratch target verified (`current_database() = rag_test_scratch`) before execution.
- No manual cleanup and no `--clean`; no database created or dropped.
- Frozen results (`eval/phase35/results/*`), the H.1 artifacts and `.vscode/settings.json` are SHA-256 identical to the earlier record.
- `git diff --check` clean; secret scan clean.

## 9. Newly discovered defects

**None.** The only newly surfaced failure (`[13]`) was an outdated expectation. Every other previously hidden check, 88 of the 91, passed against the current code with no change.

## 10. Final status and recommended next step

**PASS.**
- Both formerly failing memory test files pass completely: 106/106 and 137/137.
- The 91 checks hidden since 2026-11-15, including the DELETE ban and isolation, executed and pass.
- The full suite is green at 48/48.
- No application code changed, and every database is unchanged.

**Recommended next steps:**
1. **Review and commit these two test files on a feature branch,** separately from the staged reports. CLAUDE.md requires a feature branch, never `main`. Example message: `test: update memory tests to current Task 1/4 and Phase 3 contracts`.
2. **Update `MASTER_GAP_REGISTER.md` (P1-03 / P1-05 / P1-08)** to cite the restored 106-check run, with your approval.
3. **P3 (classification) remains a separate decision:** option 1 from the Phase A audit (classify the rewritten query) plus a small dev-only live check.
