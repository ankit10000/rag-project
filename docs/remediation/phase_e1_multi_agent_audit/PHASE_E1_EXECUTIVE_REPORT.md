# Phase E1: multi-agent audit, executive report

**Date:** 2026-11-17. **Method:** six read-only specialist agents (Explore type: no Edit/Write tools) audited in parallel. The lead independently verified every High finding and every disagreement against the repository.

**Not done:**
- no protected asset was modified;
- no database, provider or network access;
- no held-out evaluation;
- no git state change.

## Status

| Complete | Incomplete |
|---|---|
| E0/E0.1 gate, frozen manifest, review tooling, Phase C audit, Phase D package; all six agent reports consolidated (6 audits, the findings matrix, this report and the E2 plan) | Independent human review (reviewers not named); owner decisions; corrections; scorer v2; runner hardening; re-freeze |

## Key findings (lead-verified unless noted)

| ID | Sev. | Finding |
|---|---|---|
| E1-1 (ARCH-1 = SEC-1 = DOC-1) | High | **E0 regression by the lead:** three dev runners (stage6, stage8, h1) relied on `run_eval`'s old import-time scratch-DB setup. They now fail closed, and this was undocumented |
| E1-2 (SCORER-1) | High | v1 and the v2 design accept wrong numbers from assistant history: "$65 or $85" passes; "GBP 1,800 or 2,000" passes after TA-03 |
| E1-3 (SCORER-6 = TEST-4) | High | The v2 correction-cue rule would accept "It is 2,000, not 1,800" (two agents independently; design analysis) |
| E1-4 (ARCH-8, SCORER-2/3) | High | v2 re-scoring: Tier 1 context depends on the dataset version of the run (verified). Tier 2 can be rebuilt exactly (verified: 135 chunks, 74/74 refs), so the Phase D page-superset approach must be dropped |
| E1-5 (SCORER-12, TEST-1/2/3) | High | The probe harness cannot test v2 as designed. P-TS1-06 (verified artefact) and P-TS1-09 v2 expectations are wrong (Phase D errors) |
| E1-6 (DATA-1) | High | Phase D's TA-11 would fail the source's own "Batteries and filters" wording |
| E1-7 (DOC-2 = TEST-10/11) | High | Registered unit tests assert live repository state and will fail once review or corrections start |
| E1-8 (DOC-3) | Med–High | Anti-anchoring lists omit the Phase C, D and E1 directories |
| E1-9 (ARCH-3/4, SEC-2/4/6) | Medium | Run-once and concurrency not enforced; reusable approval; `--split all` output unusable |
| E1-10 (SEC-3, ARCH-10) | Medium | A provider outage can use up the single held-out run as a FAIL |
| E1-11 (ARCH-5/6/7, SEC-5) | Medium | Runtime config, gate code and review completion are not bound by the gate |
| E1-12 (DATA-2/4/5/8, TEST-5) | Medium | Refinements to TA-02/05/06/07/08/10 and TP-06; untested hedge trade-offs |
| E1-13 | Low | `.DS_Store` staged; stale docs; DOC-10 hash truncation (lead error); scratch allow-list too loose (SEC-7, verified) |

## Disagreements and resolutions

| Topic | Positions | Resolution |
|---|---|---|
| Runner-break severity | High (ARCH, DOC) vs Medium (SEC: fails closed) | **High for release, not a safety hole** |
| Tier 2 reconstruction | ARCH-8 "approximation only" vs SCORER-2 "exact rebuild feasible" | **SCORER-2 verified by the lead** at (doc, page) level; per-chunk text identity unproven |
| TA-06 | Phase D proposal vs Agent 3 DISAGREE | Owner decides; the lead agrees TA-06 does not fix the issue under v1 |
| TP-06 (A-multipage-01) | Phase D vs DATA-4 | **DATA-4 verified**; the Phase D recommendation is insufficient |
| TA-02 "misprint" | Phase C/D vs DATA-8 | Wording is interpretive; the 31 Nm correction stands |
| TA-03 vs v2 assertion annotation | Phase D vs SCORER-13 | Owner, tied to V-5 |
| Generic leak markers | Design (literal) vs SCORER-11 (separate disclosure kind) | SCORER-11 adopted as a proposal |

**Lead's own errors surfaced by the agents:**
- E1-1 (the E0 regression);
- DOC-10 (hash truncation);
- DATA-1 (TA-11 proposal);
- the ARCH-8 design claim (Tier 1 re-scoring);
- the P-TS1-06/09 expectations;
- the TEST-12 overclaim ("already checked in E0").

## What can proceed now, and what is blocked

- **Can proceed independently:** WP1–WP5 (docs, runner repair, test hardening, revised proposals, v2 design revision). None touches frozen assets.
- **Needs owner approval:** WP0 decisions, then WP6 (v2 build) and WP7 (runner and gate hardening; frozen).
- **Needs the independent human review:** WP8 (corrections and re-freeze) and WP9.
- **Recommended order:** WP1 (anti-anchoring first) → WP2–WP5 in parallel → WP0 → WP6 + WP7 → human review complete → WP8 → WP9.
- **Effort:** roughly 2–3 weeks of engineering for WP1–WP8, with testing effort about equal to implementation. Details in `PHASE_E2_IMPLEMENTATION_PLAN.md`.

## Execution record

| Item | Value |
|---|---|
| Git before | HEAD `69e8b8e`; 47 staged, 0 unstaged, 0 untracked |
| Git after | Unchanged, plus the new untracked files in this directory |
| Lead commands | Read-only greps; pure verification snippets (unreachable DB URL, network blocked, `-B`) |
| Lead disclosure | One snippet imported `services.retrieval_config`, which calls `load_dotenv()`. It loaded `.env` into a short-lived process's memory; nothing was printed, no connection was made. Later checks avoided that module |
| Agent tests (Agent 4) | Run three times each: `test_stage9_e0_runner_gate.py` 108/0, `test_stage9_e0_frozen_manifest.py` 25/0, `test_stage9_b_review_tools.py` 40/0, `test_p4_eval_framework.py` 22/0, probe suite 72/72 |
| Agent 2 | Ran the probe suite (72/72); its `.env` grep was refused by the permission classifier |
| Files created (9 of 9) | `PHASE_E1_EXECUTIVE_REPORT.md`, `ARCHITECTURE_AUDIT.md`, `SCORER_V2_AUDIT.md`, `DATASET_CORRECTION_AUDIT.md`, `TEST_COVERAGE_AUDIT.md`, `SECURITY_RELIABILITY_AUDIT.md`, `RELEASE_READINESS_AUDIT.md`, `AGENT_FINDINGS_MATRIX.csv`, `PHASE_E2_IMPLEMENTATION_PLAN.md` |
| Findings matrix | 79 consolidated findings (duplicates folded into one row with `corroborated_by`): 23 lead-verified, 5 corroborated by several agents, 51 agent-only (code reading) |
| Protected-asset check | SHA-256 of all 464 working-tree files (excluding `.venv`, `.git`), before the agents started and after consolidation: **no pre-existing file changed or was removed**. The only differences are the new files in this directory |
