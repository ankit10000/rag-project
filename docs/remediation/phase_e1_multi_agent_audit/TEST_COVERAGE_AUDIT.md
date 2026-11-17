# Phase E1: test coverage audit (Agent 4, consolidated)

## Commands run (Agent 4)

Every command used `-B`, an unreachable DB URL and a blocked network. Each test file ran three times with identical results.

| Command | Exit | Result |
|---|---|---|
| `scorer_regression_probes.py --validate-proposals` | 0 | 72/72 PASS; proposals VALID |
| `test_stage9_e0_runner_gate.py` | 0 | 108 PASS / 0 FAIL |
| `test_stage9_e0_frozen_manifest.py` | 0 | 25 / 0 |
| `test_stage9_b_review_tools.py` | 0 | 40 / 0 |
| `test_p4_eval_framework.py` | 0 | 22 / 0 |

No `__pycache__` was written (`-B`). `git status` was unchanged.

## Probe inventory (72)

| Area | Count | v1 classification |
|---|---|---|
| TS-1 | 9 | FN 5, TP 1, FP 2, residual FP 1 |
| TS-2 | 7 | FN 4, dataset FN 1, TP 1, FP 1 |
| TS-3 | 7 | FN 4, TN 3 |
| TS-4 | 12 | FN 8, FP 3, TP 1 |
| TS-5 | 4 | FP 1, residual FP 1, TN 2 |
| TA proposals | 33 | TP 14, TN 13, FP 3, FN 3 |

The matrix CSV matches the probe list. **Nothing enforces this.**

## Findings

| ID | Sev. | Finding | Action |
|---|---|---|---|
| TEST-1 | **High** | The harness (`scorer_regression_probes.py:203-208`) always cites every gold page, uses gold-only context and sets `status="answered"`. As a result:<br>• `fabricated` is always 0;<br>• `conflict_ok` reduces to the phrase check;<br>• the `abstained`/`unverified`/`error` branches are untested;<br>• v2 numeric-guard expectations become artefacts. **[LEAD-VERIFIED]**: P-TS1-06's v2=False would not hold in a real Tier 1 context, because the A-noanswer-01 distractors contain "3".<br>P-TAD4-1 duplicates P-TS1-01 and does not test TA-D4's citation effect | Per-probe citations, status and context mode (`gold` or a real `tier1_context`); assert `citation_completeness` for TA-D4 |
| TEST-2 | **High** | Probes assert only `correct`, so a probe can pass for the wrong reason | Record and assert the expected sub-signals (`fact_recall`, `forbidden_hits`, `abstain_ok`, `partial_ok`, `conflict_ok`, `ungrounded_numbers`) |
| TEST-3 | **High** | Some v2 expectations cannot be met:<br>• P-TS1-09 expects v2=True on the current A-compound-03, but that only happens with TP-02's data change. **This is a Phase D error.**<br>• Annotation-dependent probes (P-TS3-01/03/05/07, P-TS5-01) cannot express annotations.<br>• P-TS3-07's cue "separately" is not in the design's cue list.<br>• Signature mismatch: `score_generic_v2(..., annotations)` vs the v1-signature `--v2` contract. | Fix the expectations or model TP-02; add an `annotations` field per probe; agree the entry point |
| TEST-4 | **High** | The v2 TS-3 design lets a value swap pass ("It is GBP 2,000, not 1,800."; "On P-205 use 18 g, not the 30 g used on P-204"). Same as SCORER-6 | Must-reject probes; cue scoped to the forbidden token |
| TEST-5 | Medium | Hedges pass v1 after the proposals, but only TA-01/02 have hedge probes: PROP TA-03 "either 1,800 or 2,000" (**lead-verified True**), TA-04 "120 or 90 days", TA-D1 "500 h or 750 h", TA-D2 "14 or 21 days", TA-D3 "USD 58 or USD 64". TA-D2 has no negative probe | Add "v1 false positive (trade-off)" probes; note them in the owner decisions |
| TEST-6 | Medium | TA-06's purpose (the question echo) is untested | Echo-pair probes on the current and proposed definitions |
| TEST-7 | Medium | The probe suite sits in `docs/`, has no testsafe guard, is not registered, patches only `psycopg.connect` (not `Connection.connect` / `AsyncConnection.connect`), has no dataset or manifest pin, and nothing checks the CSV, the proposal CSVs or unique ids. Deterministic, and fails loudly on errors | Root-level `test_stage9_scorer_probes.py` with the guard; pin the manifest hash; consistency checks |
| TEST-8 | Medium | The v2 numeric guard would reject correct abstentions containing clause numbers or dates | Probes; tokeniser rules (see SCORER-4/9) |
| TEST-9 | Medium | TS-4 false matches from number-word compounds, `1.0`→`1` breadth, minus sign, and `1 hour` inside "11 hours" | Probes and table restrictions |
| TEST-10 | Medium | `test_stage9_b_review_tools.py:251-259` asserts 0 reviewed / 113 and 7 pending on the **real** workbooks, so it fails at the first reviewer decision. **[LEAD-VERIFIED]** (also DOC-2) | Assert 0 errors, unchanged bytes and `pending + reviewed == expected` |
| TEST-11 | Medium | `test_stage9_e0_runner_gate.py` (valid-approval path) and `test_stage9_e0_frozen_manifest.py:79,118` need the live manifest to reproduce, so they fail after any approved change. **[LEAD-VERIFIED]** | Fixture manifests for the gate path; move live-state checks to a separately named readiness check; print the gate's problem list on failure |
| TEST-12 | Low–Med | The Phase D design says AST identity was "already checked in E0", but no test does that | Explicit v1-immutability test |
| TEST-13 | Medium | Untested branches:<br>• `safety.py:186-187` (OSError), `:157-160`;<br>• `frozen_manifest.py:139-145,161-169`;<br>• `approved_on` accepts "yesterday";<br>• approval path is a directory; non-UTF-8 approval; duplicate splits;<br>• `NO_FROZEN_THRESHOLD`; invalid mode | Branch tests |
| TEST-14 | Medium | Untested branches in `review/checks.py`:<br>• structure errors; `_covers` multi-range; invalid JSON; drift in history/forbidden/sources/tier/category/data_file;<br>• `_flag("yes")`; impossible date 2026-02-30;<br>• ledger split mismatch (the fixture `dev_split` can never fire it); deleted history;<br>• without a baseline, unmarked new ledger entries are **silently ignored** (functional gap);<br>• `historical_verified` reports a count even when the check failed;<br>• "no sign-off fields"; `IN_PROGRESS`; whitespace-padded decisions | Branch tests plus fixes for the two functional gaps |
| TEST-15 | Low | `run_tests.py` runs without `-B` and always needs a DB (no DB-free unit mode); the B test leaves file handles open | DB-free unit mode (owner approval) |

## Proposed additional probes (summary)

The full list, with expected v1 and v2 values, is in Agent 4's report. The lead has added the DATA-1 and SCORER-1 cases.

| Area | Additional probes |
|---|---|
| TS-1 | Clause-number abstention; context-dependent guard; status=`abstained` with a fabricated price; status=`unverified`; a contraction ("don't include"); a non-source subject ("Plan Basic does not include…") |
| TS-2 | Negated lexicon ("There is no conflict…"); "meanwhile"; single value; partial citation; "6.1" and "vs." splitter cases |
| TS-3 | Value-swap must-reject pair; parenthetical correction; `2,000` inside `12,000`; a payload quoted in a warning |
| TS-4 | "11 hours"; "£0.50"; "12 visits"; number-word compound; `3 mg/L` breadth; currency forms (£65, "65 USD", US$65.00, "$ 65"); NBSP and `×`; "119,800"; time forms; dash spacing; TA-07 line-start, markdown and "5-litre" |
| TS-5 | Refusal containing "system prompt"; marker outside an injection case; steering regression |
| SCORER-1 history echo | The six lead-verified wrong-history hedges (A-followup-02, B-follow-01 + TA-03, D-follow_up-01, C-follow_up-04, B-follow-02, A-followup-04) |
| Per proposal | TA-02 "31Nm"/"31 N·m"/"131 Nm"; TA-03 "11,800"; TA-06 echo pair; TA-08 paraphrases; TA-09 "Level 2"; TA-10 range forms; **TA-11 "Batteries and filters" (DATA-1)**; TA-D1–D3 hedges and boundary forms; TA-D4 `citation_completeness`; TP-02/03/04/06 if accepted |

## Recommended v2 test plan

1. **Unit tests per module:**
   - one positive and one negative case for every table entry and regex family;
   - splitter edge cases.
2. **Table and property tests:**
   - idempotence;
   - distinct values never match;
   - an adjacent digit or "." breaks a match;
   - "1,000" ≠ "1.000".
   - Use `random.Random(0)` for generated inputs; Hypothesis would need owner approval.
3. **v1 immutability:**
   - file hash;
   - `ast.dump` snapshots of `score_generic`, `norm_numbers`, `NUM_RE` and `REF_RE`;
   - phrase lists unchanged (22 / 7) after importing v2;
   - `run_eval` does not import v2;
   - all 72 v1 probe results unchanged.
4. **Probe suite as a registered unit test:**
   - sub-signal asserts;
   - modes;
   - CSV consistency;
   - unique ids;
   - manifest pin.
5. **Re-scoring diff test on the tracked dev results:**
   - v1 re-score reproduces the stored `correct`;
   - Tier 1 `ungrounded_numbers` reproduce;
   - v1→v2 flips match a human-approved golden list;
   - outputs go to a temp dir with mode `x`;
   - source hashes are unchanged.
6. **Registration:**
   - testsafe guard first;
   - `psycopg` tripwires;
   - assert no `services.*` import.
   - Until a DB-free mode exists, run with the unreachable-DB command.
