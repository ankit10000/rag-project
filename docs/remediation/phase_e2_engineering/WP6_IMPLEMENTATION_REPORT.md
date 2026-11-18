# WP6 — Scorer v2.1 implementation and validation

Date: 2026-11-17. Baseline: clean local `main`, commit `690fcfb`.

**Status:** the opt-in experimental implementation and deterministic engineering validation are complete. Formal WP5 §16 acceptance is **not complete**: richer real-case annotations and a human-approved flip golden list remain pending. No acceptance-scorer selection, threshold change, correction approval, held-out evaluation or re-freeze is implied.

## Recovered dependency map

| Work | Actual starting state | Current disposition |
|---|---|---|
| WP0 | Owner choices listed in `PHASE_E2_REMAINING_DECISIONS.md`; no approval inferred | Still pending |
| WP1 | Documentation and reviewer protection present | Preserved |
| WP2 | Three dev runners explicitly bootstrap lazily; tripwire tests present | Preserved and regression-tested |
| WP3 | 110 probes, v1 immutability and gate/review regressions present | Harness extended for explicit v2 scores and optional sub-signal assertions |
| WP4 | Revised proposals, potential issues and validator present; proposals pending | Byte-identical; validator passes |
| WP5 | Authoritative `wp5/SCORER_V2_1_SPEC.md`; no scorer package existed | Byte-identical; implemented experimentally |
| WP6 | Not started | Pure scorer, offline runner, baseline annotations and tests implemented |
| WP7 | Frozen live-runner/gate hardening not started | Partially prepared: context/hash/header verification and exclusive output mechanics tested in the offline runner; frozen live paths untouched |
| WP8 | Corrections and re-freeze depend on owner choices and independent human review | Not executed; see `WP7_WP8_DEPENDENCIES.md` |

The current implementation request authorizes engineering work; it does not convert pending owner recommendations into approved acceptance policy.

## Implementation and contracts

New package: `eval/scoring_v2/`.

- Pure modules: `tables`, `normalize`, `numbers`, `text_units`, `negation`, `signals`, `forbidden`, `history`, `annotations`, `context`, `score`, and `__init__`.
- Offline I/O: `rescore.py`; pure metadata helpers: `rescore_meta.py`.
- Identity: `phase35-scorer`, version `2.1.0`, tables version `2.1.0`.
- API: `score_case(case, result, chunk_pair, context_ids, context_text, history, annotations)`; explicit `bind_v1_signature` adapter. No implicit module-level `score_generic` alias.
- Implements typed numeric grounding, explicit user/assistant history separation, per-occurrence correction handling, polarity, literal/assertion/distractor/disclosure kinds, abstention and disagreement signals, citation arithmetic, null/unavailable context and canonical error-row behavior.
- Malformed input and annotations fail explicitly. Falsey malformed citations do not silently become valid empty lists. History corrections cannot excuse a separate repetition of the same wrong value.
- Full annotations validation covers AV-1–AV-10. `annotations.json` is a complete **160-case literal-only baseline**, pinned to unchanged current data. It applies no proposed corrections or richer case interpretations.
- Package imports perform no file I/O and import no services. The offline runner imports only the pure `services.chunker` from the services layer. Every package Python module is under 300 lines.

### Explicit offline integration

`python -m eval.scoring_v2.rescore` selects v2 explicitly. The frozen live runner, v1 scorer, report defaults and acceptance settings are unchanged.

Required inputs are stored results, tier, a dataset revision or run header, complete pinned annotations, and a new output path. Tier 2 historical reconstruction additionally records `--chunk-config 100,20,words` as an assumed configuration. Only dev rows are accepted by this experimental CLI.

The runner verifies dataset pinning, independently binds run-header identity to the manifest committed at that revision, pins restated pipeline ASTs, reconstructs exact contexts, and compares stored/current v1 separately from v2. JSONL, sidecar and Markdown comparison outputs are created exclusively; collisions and reconstruction failures cannot overwrite source results.

Exit codes 4–8 follow WP5. Missing acceptance prerequisites are an ordinary CLI configuration refusal (exit 2); WP5 does not assign a scorer-specific code for that preflight case. Current frozen metadata cannot authorize v2 acceptance. Page-superset fallback is explicitly `NON_ACCEPTANCE`.

Sidecars record portable source/annotation identity, v1 AST identity, dataset pins, source-result hashes, environment versions, context configuration, per-row context hashes, reconstruction/drift/flip counts and eligibility. Run-header production integration remains a WP7 dependency; the experimental header contract is documented in `rescore.py`.

## Specification clarifications and traceability

No rule was widened to satisfy stale intended probe outcomes.

1. WP5 Appendix B governs the four recorded disagreements: P-TS1-06, P-TS1-08, P-TS4-10 and P-E2-STAT-06. Their v2 expectations were aligned; v1 expectations were preserved.
2. Executable §4.3 boundary checks identify three additional stale v2 intents: P-TS4-11 (`Tuesday` versus `Tuesdays`), P-TA11-2 and P-E2-TA11-3 (`filter` versus `filters`). Quantity-only plural relaxation does not apply. The v2 expectations and observed recall signals now record that rule; datasets and proposed corrections were not altered.
3. The explicit M2 quote table is preserved before NFKC destroys the identity of `″`; otherwise M1 followed literally by M2 produces two apostrophes instead of the specified double quote. No glyph outside the closed table was added.
4. Unit canonicalisation is completed after number-word conversion so the required M-idempotence property holds (`twelve months` has one canonical form).
5. AV-10 duplicate checking applies within each collection. The §13.3 example deliberately repeats `2,000` across forbidden and history annotations; rejecting that cross-collection repetition contradicts the example.
6. Unresolved prose inconsistency: the §7 residual example using an epistemic clause followed by comma/`but` implies narrower scope than the formal §6 grammar, which explicitly does not split commas or `but`. The implementation follows the closed formal grammar; it does not add an unapproved splitter rule. This remains an owner clarification/residual limitation.
7. The §4.4 explicit compound grammar uses tens plus two–nine; it does not invent a tens-plus-one conversion despite the prose range “21–99.” Unknown string status values similarly are not assigned an invented rejection policy; malformed non-string statuses are rejected.

## Final validation

Environment for deterministic scripts:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B <script>
```

The URL is deliberately unreachable. No database test or connection was required. `run_tests.py` was not executed because its normal execution fingerprints the application database; only its registry checker was used.

| Script or command | Result | Exit |
|---|---:|---:|
| `test_stage9_scoring_v2.py` | 18 unittest methods; 120 normative rows plus generated aliases, properties, adversarial and malformed-input assertions | 0 |
| `test_stage9_v2_runner.py` | 22 unittest methods; repeated after adding the shared test guard | 0 |
| `test_stage9_v2_integrity.py` | 8 unittest methods | 0 |
| `test_stage9_v1_immutability.py` | 21 checks | 0 |
| `test_stage9_scorer_probes.py` | 134 checks | 0 |
| `test_stage9_e0_runner_gate.py` | 110 checks | 0 |
| `test_stage9_e0_frozen_manifest.py` | 24 checks | 0 |
| `test_stage9_b_review_tools.py` | 44 checks | 0 |
| `test_stage9_e2_dev_runners.py` | 38 checks | 0 |
| `test_stage9_review_checks_branches.py` | 38 checks | 0 |
| `test_stage9_gate_branches.py` | 40 checks | 0 |
| `test_p4_eval_framework.py` | 22 checks | 0 |
| `-m eval.probes.scorer_regression --v2 eval.scoring_v2.score --validate-proposals` | 110 probes, zero failures; proposal copies valid | 0 |
| `-m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json` | REPRODUCED | 0 |
| `docs/remediation/phase_e2_engineering/wp4/validate_revised_proposals.py` | OK; zero unexpected findings | 0 |

These are 48 new unittest methods, 471 existing regression checks and 110 dual-scorer probes. No checks were skipped. Human approval/golden-list validation, acceptance evaluation, live/provider evaluation, held-out evaluation and WP7/WP8 activation were **not run**.

### Actual offline dev comparisons

The real stored dev JSONL files were read at operator pin `c1bbcae`, with temporary complete literal annotations constructed for that revision. The CLI parser was invoked through `rescore.main` under the shared network guard. Each invocation wrote new diagnostic files and exited 0.

| Tier | Exact rows | Mismatch / fallback / v1 drift | Observed correctness flips |
|---|---:|---:|---:|
| 1 | 47/47 | 0 / 0 / 0 | 3 |
| 2 | 42/42; 135 reconstructed chunks | 0 / 0 / 0 | 1 |

Both final sidecars have scorer SHA-256 `af81bae9df469cd880c8fec8a970a95bf5e0b275679111b783ee867d4e813a2c` for that historical annotation input, and `acceptance_eligible: false`. Flips carry applicable rule codes; they are **not a human-approved golden list**. Historical chunk text identity remains indirect: references and v1 signals reproduce, but historical runs have no per-chunk text hashes. The runtime chunk-table hash differs from WP5's environment-specific evidence and is recorded rather than substituted.

Local evidence: `/private/tmp/wp6-final-validated-results.json`, `/private/tmp/wp6-final-dev-evidence.json`, and the new comparison files under `/private/tmp/wp6-final-dev-hnuo27v0/`. Commands, exit codes and individual test logs are recorded there. The tests reconstruct their own temporary fixtures and do not depend on these evidence files.

## Repository and evaluation integrity

All 44 pre-recorded protected files are byte-identical, including the 27 frozen assets, manifest, dataset modules, thresholds, review assets, proposals and historical dev results. Frozen manifest identity remains `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.

Six pre-existing tracked files changed: four `eval/probes/` harness/data/schema files, `test_stage9_scorer_probes.py`, and `run_tests.py` registration. New files are limited to the scorer package, synthetic fixtures, three focused test scripts and these two WP6/WP7 notes. The original index and all unrelated tracked files are unchanged. No staging, commit, push, production-memory operation, schema change, held-out run or external provider call was performed. No query or write touched `rag_db`.

## Recommendation

Use v2.1 for explicit offline diagnostic comparisons and continue independent WP7 preparation. Do not mark formal WP6 acceptance or all of Phase E2 complete until the owner-reviewed real-case annotation policy, human-approved flip list and applicable owner decisions are resolved. Frozen live runner/gate changes and acceptance adoption remain WP7/WP8 work.
