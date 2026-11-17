# Phase E2: remaining decisions, WP0 summary, and WP6/WP7 plan

Every item below is **PENDING_OWNER_DECISION**. Nothing has been applied, and WP6 and WP7 have **not** been started.

**Source documents:**
- Phase D: `OWNER_DECISION_CHECKLIST.md`
- E1: `PHASE_E2_IMPLEMENTATION_PLAN.md`
- E2: `wp4/REVISED_*`, `wp5/SCORER_V2_1_SPEC.md` §17, and the WP2/WP3 reports

## 1. WP0 owner-decision summary

### A. Sequencing and exposure

| ID | Decision | Recommendation (technical, non-binding) |
|---|---|---|
| S-1 | Correction work before, after, or parallel to the independent review | Parallel. Reviewer decisions stay authoritative |
| S-2 | When the reviewer may see the AI analyses (Phase C, D, E1, E2) | Only after their own decisions are recorded. All four folders are now on the "do not open" lists (WP1) |
| — | Name the independent held-out reviewer and the dev reviewer | **Blocking** for WP8 |

### B. Dataset corrections (revised in E2 WP4; details in `wp4/REVISED_*`)

**Held-out proposals:**

| ID | Revised recommendation | Options needing a choice |
|---|---|---|
| TA-01 | update; `multi_page`; 48 hours | — |
| TA-02 | errata supersedes; `["31 Nm","31Nm","31 N·m",…]` | B: `"31 N"` (matches "31 Nov") |
| TA-03 | remove forbidden `2,000` | B: keep `2,000` as a v2 assertion annotation. **Note:** after TA-03, v1 accepts the value swap "It is GBP 2,000, not 1,800" (probe P-E2-SWAP-02), so TA-03 is only safe together with v2 |
| TA-04 | remove forbidden `90 days` | Hedge risk is recorded |
| TA-05 | wider "2 visits" set incl. "twice" | `£40` forbidden: keep (rec.) or remove (a hedge then passes) |
| TA-06 | **A: no data change; defer to the v2 negation guard** | B, C, D reword options; each only moves error between false passes and false failures under v1 |
| TA-07 | anchored interim set (80 strings, incl. "1 hour") | B: defer to v2 boundaries (cleaner if v2 is adopted) |
| TA-08 – TA-11 | refined alternatives; **TA-11 `["battery","batteries"]`** | — |

**Dev proposals:**

| ID | Revised recommendation |
|---|---|
| TA-D1 – TA-D3 | update/override; extra forms |
| TA-D4 | add Calder p4. Tier 1 context changes (verified) |

**Potential issues:**
- TP-01 – TP-10 and TP-D1 – TP-D2 stay potential.
- Changes vs Phase D: TP-06 and TP-10 now **DEFER TO HUMAN REVIEW**; TP-05 now includes `£40`.

**Denominators and categories (unchanged denominators):**

| | Cases | T2 | conflicting | multi_page |
|---|---|---|---|---|
| Held-out | 113 | 106 | 7→5 | 12→14 |
| Dev | 47 | 42 | 6→3 | 5→8 |

### C. Scorer v2.1 (`wp5/SCORER_V2_1_SPEC.md` §17)

| ID | Decision | Spec recommendation |
|---|---|---|
| V-1 | Build v2.1 as a separate package (v1 untouched) | yes |
| V-2 | Scope (all requirements or a subset) | all 12 |
| V-3 | Per-case annotation work (`history_wrong_values`, assertion/distractor/disclosure kinds, `negatable_groups`) | yes |
| V-4 | Supplementary prompt-injection suite outside the acceptance set | yes |
| V-5 | Acceptance scorer for the held-out run (v1 or v2.1); freeze it before any result; possible threshold review | owner |
| V-6 | Should every ungrounded number fail `correct`? | no (report `numeric_grounded` separately) |
| V-7 | Does status `partial` count as the missing-part signal? | yes |
| V-8 | Do section/clause references and codes count in the numeric guard? | no |
| V-9 | Error-row policy for held-out | any error row invalidates the run |
| V-10 | Does status `conflict` count as a disagreement signal? | no |
| V-11 | Make literal matches boundary-aware (unlike v1) | yes |

### D. Runner, gate and process (from E1; WP7 scope)

| Decision | Options |
|---|---|
| Run-once enforcement | O_EXCL claim, held-out run ledger, consumed approval |
| `--split all` for held-out | refuse (recommended) |
| Provider-outage handling | preflight and circuit breaker; ties to V-9 |
| Bind runtime config and `services/*` to the manifest and approval | yes or no |
| Require human-review COMPLETE in the gate (manifest format bump) | yes or no |
| Approval provenance | git-tracked at HEAD in a fixed directory, ISO date, consumed marker |

### E. Smaller decisions raised in E2

| Item | Detail |
|---|---|
| `eval/review/checks.py` fix (a) (WP3) | Unmarked ledger entries without a baseline are now reported as **incomplete**, not as an error. An error would make every baseline-less `validate` fail on the 26 legitimate history rows. Confirm, or ask for error |
| h1 dev filter (WP2) | `h1_relevance_gate.py` trusts `c["split"]` and does not re-check `split_of()` like stage6. Small optional hardening |
| `MASTER_GAP_REGISTER.md` (DOC-6) | Update for Stage 9, or record it as unchanged |
| `.DS_Store` | Unstage `docs/remediation/.DS_Store` and `eval/.DS_Store`, and add `.DS_Store` to `.gitignore` (a git operation for you). The docs file was rewritten by Finder during E2 |
| DB-free unit mode for `run_tests.py` (TEST-15) | Today `run_tests.py` always opens a DB connection |
| v2 probe expectations | P-TS1-06, P-TS1-08, P-TS4-10 and P-E2-STAT-06 differ between the WP3 harness and the v2.1 spec (Appendix B). The **spec governs**; align them in WP6 step 1 |

### F. Independent human review

Its decisions are authoritative and are required before WP8 (corrections and re-freeze). Neither the review itself nor its sign-off can be done by an agent.

## 2. WP6 plan: scorer v2.1 implementation (do not start until V-1 – V-3 and V-6 – V-11 are approved)

1. Align the harness `expected_v2` values with the spec's Appendix B (the 4 probes above). Add the spec's test tables (about 120 rows) as probes and unit tests.
2. Implement the pure modules in dependency order (spec §2): `normalize` → `text_units` → `signals` → `forbidden` → `context` (Tier 1 pinned to the run's dataset revision; exact Tier 2 rebuild, failing closed) → `annotations` (schema AV-1 – AV-10) → `score` (`score_case` plus the `bind_v1_signature` adapter) → `rescore` (I/O, new files only).
3. Author `annotations.json`: `history_wrong_values` for the follow-up cases; assertion, distractor and disclosure kinds; `negatable_groups`. Owner-reviewed (it depends on the TA-03 decision).
4. Testing:
   - unit tests per module;
   - property tests;
   - the existing v1-immutability test (`test_stage9_v1_immutability.py`) must stay green;
   - `test_stage9_scorer_probes.py --v2 eval.scoring_v2.score`, with all v2 expectations met.
5. Offline re-score of the dev results pinned to dataset revision `c1bbcae` (WP5 evidence: reproduces v1 47/47). Produce the three-way diff (v1-stored / v1-current / v2.1) and an owner-approved golden list of v1→v2 flips (SCORER-14).
6. Acceptance: spec §16 (complete sidecar; reproducible hashes; no DB, network or LLM).

**Estimates:** L (about 1–1.5 weeks); testing effort roughly equal.

**Re-freeze:** the new v2 files become frozen assets at the WP8 re-freeze if v2 is chosen (V-5).

## 3. WP7 plan: runner and gate hardening (touches frozen assets; bundle with the WP8 re-freeze)

1. **Run-once:**
   - O_EXCL output claim at gate time;
   - held-out run ledger keyed by approval SHA;
   - refuse `--split all` for held-out;
   - `lexists` instead of `exists`.
2. **Reliability:**
   - provider preflight;
   - circuit breaker on N consecutive error rows;
   - the V-9 error-row policy;
   - line flush and fsync;
   - error type only in rows (SEC-11).
3. **Provenance:**
   - a run-header sidecar (manifest SHA, approval SHA, HEAD, models, config hash, dataset revision);
   - per-row `models_used`;
   - per-row context text or hashes, so re-scoring is exact (ARCH-5/8).
4. **Frozen scope:**
   - add `services/*` answer/retrieval modules and the gate modules (`safety.py`, `frozen_manifest.py`, `hashing.py`, `integrity.py`, `harness.py`) to the manifest assets;
   - bind the resolved config;
   - review status in the manifest and `COMPLETE` required by the gate (format bump);
   - manifest lineage and a `supersede` command (ARCH-6/7/12, SEC-5).
5. **Approval:**
   - ISO `approved_on`;
   - git-tracked approval at HEAD in a fixed directory;
   - consumed marker (ARCH-11, SEC-4).
6. **Isolation:**
   - library-level held-out refusal in `run_tier1`/`run_tier2` (ARCH-2);
   - anchored scratch allow-list in `harness.py` (SEC-7);
   - connect guard plus a `current_database()` check (SEC-8);
   - `connect_ex` block (SEC-9).
7. **Smaller fixes:**
   - review tooling: `dev_artifact` `"xb"` save (SEC-6); reject a leading `-` in `--baseline-git` (SEC-12);
   - docstrings (DOC-12);
   - `summarize.py` / dev `--fresh` protections (ARCH-14, SEC-10).
8. **Tests:**
   - one gate test per new refusal;
   - simulated provider failure;
   - concurrent-claim refusal;
   - the gate-branch test's ARCH-11 "known gap" check flips to "refused".

**Estimates:** L (about 1–1.5 weeks); testing effort roughly equal.

**Prerequisites:** the owner decisions in §1.D and V-9.

## 4. After WP6/WP7

**WP8** (needs the human review complete plus owner approvals):
- one documented correction set;
- `validate.py` VALID;
- review package regenerated;
- freeze doc rule-2 hashes;
- new manifest with lineage;
- re-freeze report (procedure in `STAGE9_RUNBOOK.md`).

**WP9:** held-out readiness review (release checklist part B). **No held-out run without separate explicit authorization.**
