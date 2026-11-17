# Stage 9 document status index

**Written:** 2026-11-17 (Stage 9 Phase E2, work package WP1). **Update this index** whenever a Stage 9 document is added or superseded.

> **Human reviewers:** this index only names documents. Opening most of the analysis documents listed here before you record your own decisions breaks independence. See `heldout_review/REVIEWER_CHECKLISTS.md` §2.

**Status values:**
- **current:** the document to follow today.
- **point-in-time:** an accurate record of its phase; later work may have changed the state it describes (git state, file counts, "not yet" statements). Do not edit it to keep it current.
- **superseded by X:** follow X instead; the document is kept as a record.
- **frozen:** a frozen-manifest asset; it must not be edited outside an owner-approved re-freeze.

Paths are relative to `docs/remediation/`.

## Frozen and pre-Stage 9 references

| Document | Phase | Status | Note |
|---|---|---|---|
| `HELDOUT_THRESHOLD_FREEZE.md` | pre-Stage 9 | **frozen**, current | Line reference `run_eval.py:269-270` is now `303-304`; the `run_eval.py` hash is the historical one (see `STAGE9_FROZEN_MANIFEST.md`) |
| `HELDOUT_DATASET_CORRECTIONS.md` | pre-Stage 9 | **frozen**, current | — |
| `heldout_review/README.md`, `heldout_review/REVIEW_SIGNOFF_REPORT.md`, `heldout_review/source_pages.md`, review CSVs and workbook, `source_pdfs/` | pre-Stage 9 | **frozen** | The workbook becomes the reviewer's working file; any change needs a re-freeze before a held-out run |
| `PHASE4_EVALUATION_FRAMEWORK.md` | Phase 4 | **superseded in part** by the E0 report, `STAGE9_FROZEN_MANIFEST.md` and `STAGE9_RUNBOOK.md` | Banner at the top lists the stale lines (DOC-5) |
| `MASTER_GAP_REGISTER.md` | pre-Stage 9 | **not updated in Stage 9** | P35-01/02/04 still read NOT STARTED although Stage 9 addresses them (DOC-6). Left for an owner decision |

## Stage 9 top-level documents

| Document | Phase | Status | Note |
|---|---|---|---|
| `STAGE9_PHASE_A_EVALUATION_READINESS_AUDIT.md` | A | point-in-time | Its statements "no manifest exists" and "gate not wired" are superseded by E0. Its phase plan uses names that later phases did not follow exactly |
| `STAGE9_PHASE_E0_COMPLETION_REPORT.md` | E0 / E0.1 | point-in-time, **plus a current Phase E2 addendum** | The addendum records the dev-runner regression (ARCH-1) and the corrected full hashes (DOC-10); §1 git state is point-in-time |
| `STAGE9_FROZEN_MANIFEST.md` | E0 (notes added in E2) | **current** | Manifest format; E2 notes cover the interpreter, the freeze-doc line drift and the re-freeze pointer |
| `STAGE9_PHASE_B_PROGRESS_REPORT.md` | B | point-in-time | Its §7 git state is as of Phase B |
| `STAGE9_PHASE_B_STRUCTURAL_INVENTORY.md` | B | point-in-time | "`openpyxl` is not installed" is no longer true; the owner later approved it as a dev-only tool (`requirements-dev.txt`) |
| `STAGE9_RUNBOOK.md` | E2 (WP1) | **current** | Platform, env vars, commands, re-freeze procedure |
| `STAGE9_STATUS_INDEX.md` | E2 (WP1) | **current** | This file |

## Reviewer packages (Phase B)

| Document | Status | Note |
|---|---|---|
| `heldout_review/HUMAN_REVIEW_GUIDE.md` | **current** | Anti-anchoring list extended in E2 to cover the Phase C/D/E1/E2 folders |
| `heldout_review/REVIEWER_CHECKLISTS.md` | **current** | As above (§2) |
| `heldout_review/REVIEW_PROGRESS_REPORT_TEMPLATE.md` | **current** | Template; quotes the manifest hash |
| `dev_review/README.md`, `dev_review/dev_review_sheet.xlsx` | **current** | README anti-anchoring list extended in E2 |

## Phase C: `technical_dataset_audit/` (AI-assisted technical audit)

| Document | Status | Note |
|---|---|---|
| `STAGE9_PHASE_C_TECHNICAL_AUDIT_REPORT.md` | point-in-time | Findings stand as evidence. **Recommendations are superseded by Phase D**, and Phase D's are being revised in Phase E2 (see "Supersession notes" below) |
| `ISSUE_REGISTER.md` | point-in-time | As above; TA-06/07/08 recommendations differ from Phase D |
| `DEV_CASE_FINDINGS.csv`, `HELDOUT_CASE_FINDINGS.csv` | point-in-time | Per-case AI verdicts (reviewers: do not open before deciding) |
| `AUDIT_COMPLETION_CHECKLIST.md` | point-in-time | — |
| Phase C scorer probes | **superseded** by the Phase D probe suite, which is in turn being superseded by the WP3 harness | The Phase C probes were kept in a scratchpad and are not reproducible from the repository (DOC-9) |

## Phase D: `phase_d_decision_package/` (decision package; nothing applied)

| Document | Status | Note |
|---|---|---|
| `STAGE9_PHASE_D_DECISION_REPORT.md`, `PHASE_D_COMPLETION_REPORT.md`, `PHASE_D_IMPACT_MATRIX.md` | point-in-time | — |
| `HELDOUT_CORRECTION_PROPOSALS.csv`, `DEV_CORRECTION_PROPOSALS.csv` | **superseded by** the Phase E2 WP4 revisions in `phase_e2_engineering/wp4/` (in progress) | Phase E1 found 7 of 15 proposals need changes and 1 is wrong as written (`phase_e1_multi_agent_audit/DATASET_CORRECTION_AUDIT.md`). Every proposal remains PENDING owner decision |
| `POTENTIAL_ISSUE_DECISIONS.md` | point-in-time; partly revised by WP4 | — |
| `OWNER_DECISION_CHECKLIST.md` | current as a checklist, **with additions** from `phase_e1_multi_agent_audit/PHASE_E2_IMPLEMENTATION_PLAN.md` (WP0) | — |
| `SCORER_V2_DESIGN.md` | **superseded by** `phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md` (in progress) | E1 findings in `phase_e1_multi_agent_audit/SCORER_V2_AUDIT.md` |
| `scorer_regression_probes.py`, `SCORER_REGRESSION_MATRIX.csv` | current until WP3 lands, then **superseded by** `eval/probes/scorer_regression.py` and `test_stage9_scorer_probes.py` (Phase E2 WP3, in progress) | — |

## Phase E1: `phase_e1_multi_agent_audit/` (read-only multi-agent audit)

| Document | Status | Note |
|---|---|---|
| `PHASE_E1_EXECUTIVE_REPORT.md` | point-in-time | — |
| `ARCHITECTURE_AUDIT.md`, `SCORER_V2_AUDIT.md`, `DATASET_CORRECTION_AUDIT.md`, `TEST_COVERAGE_AUDIT.md`, `SECURITY_RELIABILITY_AUDIT.md`, `RELEASE_READINESS_AUDIT.md` | point-in-time | Findings are the input to Phase E2 |
| `AGENT_FINDINGS_MATRIX.csv` | point-in-time | — |
| `PHASE_E2_IMPLEMENTATION_PLAN.md` | **current** plan (proposed; each work package needs owner approval) | — |

## Phase E2: `phase_e2_engineering/` (in progress)

| Document | Status |
|---|---|
| `WP1_DOCUMENTATION_REPORT.md` | current (this work package) |
| `WP2_RUNNER_REPAIR_REPORT.md` | in progress (dev-runner repair; see the E0 addendum) |
| `wp4/` | in progress (revised correction proposals) |
| `wp5/SCORER_V2_1_SPEC.md` | in progress (scorer v2.1 specification) |

## Supersession notes

1. **Phase C → Phase D (DOC-7).** Phase D's correction proposals supersede the Phase C recommendations. Three differ in substance, and Phase D did not record why:

   | Issue | Case | Phase C recommendation (`ISSUE_REGISTER.md`) | Phase D proposal (`HELDOUT_CORRECTION_PROPOSALS.csv`) |
   |---|---|---|---|
   | TA-06 | `A-multichunk-01` | reword the question **or** drop `same appointment` from G3 | reword the question only; G3 unchanged |
   | TA-07 | `D-injection-03` | anchored forms: `more than 5 litres`, `over 5 litres`, `more than 5 liters`, `five litres`, ` 5 litres`, ` 5 liters` | ` 5 litres`, ` 5 liters`, ` 5 l `, `five litres` (interim) |
   | TA-08 | `A-multipage-02` | G1 = `adult who is not the patient`, `adult other than the patient`, `not the patient`; G2 split into `10:00` and `16:00` | the same, plus `other than the patient` in G1 |

2. **Phase D → Phase E2 WP4.** Phase E1 found that TA-06 as written does not fix its issue, and that TA-07/TA-08 need more alternatives (`DATASET_CORRECTION_AUDIT.md`). The WP4 revisions in `phase_e2_engineering/wp4/` replace the Phase D proposals. Nothing is applied until the owner decides.
3. **Scorer v2:** `SCORER_V2_DESIGN.md` → `phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md`.
4. **Probes:** Phase C scratchpad probes → Phase D `scorer_regression_probes.py` → Phase E2 WP3 `eval/probes/scorer_regression.py` (+ `test_stage9_scorer_probes.py`).
5. **Dev runners:** broken by E0 and undocumented until the E0 addendum; Phase E2 WP2 repairs them (`phase_e2_engineering/WP2_RUNNER_REPAIR_REPORT.md`).
