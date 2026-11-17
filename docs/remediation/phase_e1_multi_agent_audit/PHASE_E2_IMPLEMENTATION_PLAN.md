# Phase E2 implementation plan (proposed; requires owner approval per work package)

**Effort estimates are rough:**
- **S:** ≤ 0.5 day;
- **M:** 1–3 days;
- **L:** 3–7 days.

**"Frozen asset"** means a change requires the documented re-freeze.

## Recommended order

| # | Work package | Depends on | Touches frozen assets? | Effort (impl. / tests) | Can start now? |
|---|---|---|---|---|---|
| WP1 | **Reviewer-exposure and docs fixes:** extend the anti-anchoring lists to `technical_dataset_audit/`, `phase_d_decision_package/` and `phase_e1_multi_agent_audit/` (DOC-3) **before any reviewer starts**; E0 addendum (ARCH-1, DOC-10); PHASE4 banner; platform, env and re-freeze runbook (DOC-4/5/8/15); Phase D supersession note (DOC-7); gap register (DOC-6) | Owner S-2 decision for the merge scope | No (`heldout_review/README.md` and `REVIEW_SIGNOFF_REPORT.md` are frozen: leave them untouched) | S–M / S | Yes |
| WP2 | **Repair the dev runners** (stage6, stage8, h1): explicit `run_eval.bootstrap_execution()` before `services` imports; fix the comments | — | No | S / S (import tests with tripwires) | Yes |
| WP3 | **Test robustness:**<br>• decouple live-state checks (TEST-10/11, DOC-2);<br>• E0/B branch tests (TEST-13/14), including the two `checks.py` functional gaps;<br>• harden the probe harness (TEST-1/2/3/7: citation/status/context modes, sub-signal asserts, annotations field, manifest pin, CSV consistency);<br>• fix the P-TS1-06/09 expectations;<br>• add the new probes (value-swap, hedges, history echo, DATA-1);<br>• register as a unit test | — | No | M / M | Yes |
| WP4 | **Revised correction proposals** (new documents only; all stay PENDING):<br>• TA-02 rationale and alternatives; TA-05; TA-06 (defer, or reword plus "other arm"); TA-07; TA-08; TA-10;<br>• **TA-11 "batteries"**; TP-06 A-multipage-01; `£40`;<br>• TA-D4 context note; TP-10 evidence;<br>• hedge trade-offs (TEST-5) | — | No | S / S (in-memory validate and probes) | Yes |
| WP5 | **Scorer v2 design v2.1** (document):<br>• SCORER-1…15, TEST-4/8/9;<br>• exact Tier 2 rebuild and dataset pinning;<br>• scoped-cue polarity;<br>• history-echo rule;<br>• tokeniser and splitter;<br>• `disclosure` kind;<br>• explicit annotations interface | — | No | M / — | Yes |
| WP0 | **Owner decisions:** S-1/S-2, TA/TA-D/TP, V-1…V-5, R-1/R-2, plus E1 additions:<br>• run-once/`all` policy (ARCH-3/4);<br>• error-row policy (ARCH-10, SEC-3);<br>• config binding (ARCH-5, SEC-5);<br>• review-COMPLETE gate (ARCH-7);<br>• approval provenance (SEC-4);<br>• TA-03 vs v2 (SCORER-13);<br>• `.DS_Store` unstaging | WP4/WP5 inform them | — | — | Yes (owner) |
| WP6 | **Scorer v2 implementation** (`eval/scoring_v2/`, `rescore.py`, sidecar, unit, property and immutability tests, dev re-score golden diff) | V-1–V-3 approved; WP5 | New assets (added to the manifest at re-freeze) | L / L | After approval |
| WP7 | **Runner and gate hardening:**<br>• O_EXCL claim and run ledger; refuse `all`;<br>• provider preflight and circuit breaker;<br>• run-header provenance and per-row models;<br>• gate and `services` assets frozen;<br>• review status in the manifest (format bump) and lineage (ARCH-12);<br>• ISO date check; `lexists`;<br>• scratch allow-list (SEC-7, harness not frozen);<br>• `dev_artifact` `"xb"` save (SEC-6) | Owner policy decisions (WP0) | **Yes** (`run_eval.py`, `safety.py`, manifest format) | L / L | After approval |
| WP8 | **Correction application and re-freeze:** one documented set; `validate.py`; regenerate the review package (DATA-7); new `data_*` hashes in the freeze doc (rule 2); new manifest with lineage; re-freeze report | Owner decisions; **independent human review complete**; WP7 if bundled | Yes | M / M | After review |
| WP9 | **Held-out readiness review** (release checklist part B) | All of the above | — | S / — | Last |

## Parallelism

- **Now, in parallel:** WP1, WP2, WP3, WP4 and WP5. None touches frozen assets, and none needs a decision beyond S-2 for WP1's merge scope. WP1's anti-anchoring change should come first.
- **The human review runs independently.** It must not see the Phase C, D or E1 material until its decisions are recorded.
- **Bundling:** WP6 and WP7 can be one implementation phase; WP8 then performs a single re-freeze covering the data, runner and v2 assets.

## Blocking issues

| Blocks | Issue |
|---|---|
| Merging the Stage 9 PR | DOC-1/ARCH-1, DOC-2, DOC-3, DOC-14 |
| v2 adoption as acceptance scorer | SCORER-1, -2, -6, -12 (plus V-5) |
| Correction application | Owner decisions; human review; DATA-1 fix in the proposal |
| Held-out run | Everything in release checklist part B |
