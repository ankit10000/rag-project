# Evaluation policy finalization

**Disposition: engineering recommendations finalized; formal policy acceptance remains pending.** V1 is still the official scorer. No scorer rule, annotation, threshold, frozen asset, gate or owner-decision record was changed. The final-sprint instruction authorizes engineering and controlled live-provider work, but explicitly does not substitute for independent review, adoption decisions or run-specific held-out authorization.

This document consolidates the existing registers rather than replacing them. Authoritative inputs are `docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md`, `WP8_SPECIFICATION_CLARIFICATION_REGISTER.md`, the existing `eval/acceptance_preparation/clarifications/decision_package.json`, its three alternatives documents, `gate_policy/decision_register.json`, the frozen manifest and `docs/remediation/HELDOUT_THRESHOLD_FREEZE.md`. Recorded owner fields for the unresolved clarification and gate proposals are still null. No approval is inferred from a test, AI recommendation or a well-formed JSON object.

## Decision register: one recommendation per item

| Decision | Specification and actual behavior | Observable consequence | Recommended explicit decision | Current authority/status |
|---|---|---|---|---|
| SC-01 | WP5 Appendix B explicitly supersedes four earlier probe expectations; current probes follow it. | P-TS1-06/08 and P-TS4-10 are false; P-E2-STAT-06 is true. | Confirm the explicit Appendix B values without changing v1 or gold data. | Engineering resolved; formal review pending. |
| SC-02 | WP5 §4.3 relaxes plurals only for a quantity plus noun. `contains(M("2 visitors"), M("2 visitor"))` is true; bare Tuesday does not match Tuesdays. | General plural matching would silently broaden gold matching. | Confirm the quantity-only rule and keep bare-word alternatives literal. | Engineering resolved; formal review pending. |
| SC-03 | Literal M1-then-M2 order loses the identity of U+2033; the implementation applies the closed quote table first so `M("″")` is one ASCII double quote. | Blindly reversing the implementation order violates the explicit glyph mapping. | Confirm the existing quote-table precedence, with no new glyph mappings. | Engineering resolved; formal review pending. |
| SC-04 | WP5 §16 requires idempotence; the implementation completes closed quantity normalization after number words. `M("twelve months") == "12 month"` on the first and second application. | A single literal M12/M13 pass would give different first/second results. | Confirm the existing idempotence-preserving completion pass. | Engineering resolved; formal review pending. |
| SC-05 | WP5 §13.3's example puts `2,000` in both forbidden and history collections, while AV-10 says no duplicates within a case. Validation rejects duplicates within each collection but permits distinct roles. | A whole-case duplicate ban rejects the specification's own example. | Confirm collection-local uniqueness, preserving provenance/turn/gold-overlap checks. | Engineering resolved; formal review pending. |
| SC-06 | §6.1 says commas do not split clauses; §7.2 E extends epistemic scope through the clause. The §7 residual comma/but example implies a boundary that the formal grammar does not create. | “Documents do not say whether Visa is accepted, but Visa is fine” can excuse both Visa occurrences and pass; a semicolon makes the affirmative occurrence fail. | Select existing alternative **B**: terminate **family E only** at the first standalone `but/however/whereas/while/although/though/yet` after the epistemic match. Preserve protected spans, all other families, per-occurrence checks and full gold recall. Do not broaden the global splitter. | **PENDING_OWNER_DECISION**; proposed behavior not implemented. |
| SC-07 | §4.4 says `<tens>[- ]<two..nine>` but labels it 21–99. Current code preserves twenty-one/31-style words while converting twenty-two. | `M("twenty-one months")` stays literal; `M("twenty-two months") == "22 month"`. | Select existing alternative **B**: permit one only as the second component of an isolated approved tens compound. Preserve isolated one, scale-word blocking, idempotence and exclusion of number words from guard G. | **PENDING_OWNER_DECISION**; new mapping not implemented. |
| SC-08 | §10.3 retains v1-style status-only fact handling, but a complete malformed-status contract is absent. The pure scorer allows unknown/empty/missing/null fact statuses; non-string non-null values raise `ValueError`. The offline runner is stricter. | A fact answer can be correct with status `"mystery"`, `""`, absent or null. This is not an `answered` or error-row conversion. | Select existing alternative **B**: require one of six known strings and raise `ValueError` before scoring for unknown, empty, missing, null or non-string statuses. Do not silently synthesize canonical error rows. | **PENDING_OWNER_DECISION**; pure scorer unchanged. |
| Cross-sentence disagreement | WP5 §11 requires both groups in one sentence/list scope. A standalone “However” in a later sentence does not extend scope. | Tier 1 `D-conflicting-01` is rejected by v2 despite v1's global connective acceptance. | Keep the current closed rule unchanged until the existing independent review decides whether the qualified answer warrants a separately specified wider rule. Do not patch the scorer to recover this one result. | Implementation follows the formal rule; semantic correctness remains independently unreviewed. |
| V-5 acceptance scorer | Frozen threshold approval explicitly refers to unchanged `run_eval.score_generic`; v2 has only development selection and unapproved annotation/flip/clarification dependencies. | Passing v2 diagnostics cannot establish official adoption. | Record **v1 as the scorer for the next separately authorized formal run**; defer v2 adoption until review and any approved semantic changes are versioned and re-frozen. | V1 remains official already; run-specific selection/authorization and formal review are not fabricated here. |
| V-9 final errors/invalid records | WP5 §10.3 mirrors v1 canonical error rows as failures; §17 recommends invalidating an official run with any error. The proposal gate models BLOCK, but is not active. | A completed file can contain failed rows; file completeness alone is not technical validity. | Adopt an explicit **invalid-run** verdict for any final error or invalid record; preserve the evidence and require a separately authorized disposition. Do not silently drop rows or automatically rerun to improve scores. | **PENDING_OWNER_DECISION**; existing denominator/error semantics unchanged. |

Source implementation locations: `eval/scoring_v2/normalize.py::light/M/occurrences`, `annotations.py::entry_errors`, `negation.py:32–34` (E scope), `signals.py:51–69` (sentence/list disagreement), `score.py:18–21` (status shape), `score.py:80–112` (status/correctness/error results), and `rescore.py::read_rows` (strict offline statuses). The existing clarification register provides per-item test names; no competing register or speculative implementation was created.

If SC-06/07/08 behavior changes are approved, apply them as a separately identified next minor scorer release under WP5 §14.1, with exact source/annotation hashes and affected regression/flip review. Do not relabel modified rules as the existing 2.1.0 identity. If returned-key semantics change, follow the specification's major-version requirement instead.

## Regression examples and compatibility requirements

The following current controls were executed once for this finalization, using synthetic inputs only. They are observations, not proposed-policy execution:

| Synthetic control | Current result | Required regression after the recommended decision |
|---|---|---|
| Basic costs £4.99. Epistemic Visa sentence followed by `, but Visa is fine` | `correct=true` | False under approved SC-06 B; both occurrences judged separately. |
| The same answer separated with a semicolon | `correct=false` | Remains false. |
| Genuine epistemic Visa/Mastercard statement with no later affirmative claim | Existing SC-06 positive control | Remains true; `and`/`butterfly` must not become invented adversative boundaries. |
| `twenty-one months` / `twenty-two months` | Literal / `22 month` | Approved SC-07 B: `21 month` / `22 month`, each idempotent. |
| `one` / `one hundred and twenty days` | Both remain literal | Remain literal; G must still produce no number-word tokens. |
| Supported “30 days”, status `answered` / `partial` | Both correct in a fact case | Known statuses retain case-type rules; `partial` is not globally rejected. |
| Same supported fact, status unknown/empty/missing/null | All currently correct | Approved SC-08 B: each raises `ValueError` before scoring. |
| Same supported fact, integer/boolean status | `ValueError` | Remains `ValueError`; no truthiness coercion. |
| Same supported fact, status `error` | `correct=false`, canonical failure | Remains failure; official run validity is separately controlled by approved V-9. |

The existing full SC-08 matrix also covers abstention, partial and conflict cases. All 89 historical development rows have known status strings; this supports compatibility of a strict status proposal with those rows, but does not authenticate a policy decision or predict held-out results. Proposed SC-06/07 development lexical counts were zero in the existing decision package; that does not bound future richer-annotation impact.

No duplicate full regression suite was run by this workstream: the scorer was not edited. A single guarded Python probe called `score_case`, `M`, `contains`, `scorer_identity`, and hashed the existing manifest threshold section. It exited 0 and confirmed the rows above. Environment: `DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -`; `testsafe.require_scratch_db()` installed the guard, and no connection/provider was used. Existing exact regression sources remain `test_phase_e2_clarification_decisions.py`, `test_stage9_wp8_clarifications.py`, `test_phase_e2_gate_policy.py` and `test_stage9_wp8_adoption.py`.

## Threshold and source identity lock

Frozen values remain unchanged:

| V1 profile component | Required cases | Minimum correct |
|---|---:|---:|
| Development Tier 1 | 47 | 41 |
| Development Tier 2 | 42 | 28 |
| Held-out Tier 1 | 113 | 97 (85%, exact count) |
| Held-out Tier 2 | 106 | 69 (65%, exact count) |

`eval/framework/safety.py:31–35` and the frozen manifest contain these values. `threshold_result` returns `INCOMPLETE` unless evaluated count exactly matches the frozen denominator. The canonical SHA-256 of the existing manifest's threshold object is **`08aa6ece83dc46ed87f6f345993ab80e3843beecae525596166ed9e85c7925bb`**. This is a content digest of existing v1 settings, **not a newly approved profile ID and not a v2 threshold approval**. The freeze document separately permits a documented, independently reviewed pre-run dataset correction procedure; no denominator or minimum was recomputed here.

The proposed v2 threshold profile ID, metric selection/values and owner decision remain null in `gate_policy/decision_register.json`. **Recommendation:** bind any future profile to the complete scorer/annotation/dataset/tier identity, even if a reviewer ultimately approves numerically identical values. Unknown scorer hashes must not inherit v1 values. No v2 numbers are proposed by this document.

Current hardened scorer modules produce different valid development identities depending on annotation input:

| Annotation input | Annotation portable SHA-256 | Aggregate scorer SHA-256 |
|---|---|---|
| Historical c1bbcae literal annotations | `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a` | `0e9358638a94ce070e99b2db20aa3dcbfcdb85eb8670669690689d530ccabcdf` |
| Current package annotations | `d3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0` | `9648c71d1743a85a595db0175c89e5d38f8ccf3470f11c1f7145e753c369a237` |

Both labels are version 2.1.0; neither is an approved acceptance identity. The earlier pre-hardening aggregate `af81bae9df469cd880c8fec8a970a95bf5e0b275679111b783ee867d4e813a2c` identifies historical diagnostic source, not current modules. Module-level hashes and separate dataset pins are retained in `eval/acceptance_preparation/integration/candidate_manifest.json`; its validation is snapshot consistency only. Its nine decisions remain pending. Git HEAD alone does not attest to uncommitted scorer source bytes.

## Run validity and fallback decision

**Recommended explicit contract, pending approval:** a formal run cannot pass with missing/mismatched identity or provenance, unavailable/reconstructed-only required runtime context, page-superset fallback, final error/invalid rows, or an incomplete denominator. Preserve original rows and failed/interrupted artifacts; report invalid/incomplete separately from a score. Do not convert a failed v2 run into accepted v1 evidence by changing a label, reuse consumed approvals, or authorize an automatic rerun.

This does not prohibit an existing configured provider retry/fallback that succeeds within its approved total budget. Actual model identity and fallback use must be captured; a recovered transient attempt is distinct from a final error row. Live-provider evidence is owned by the separate integration workstream and is not inferred from these offline policy checks.

The current pure scorer deliberately allows unavailable context for diagnostic scoring (`numeric_grounded=null`); this is not permission to accept it. The WP7 exact-context preparation path refuses fallback/error rows and publishes only development bundles. The proposed gate policy keeps `official_acceptance=false` even for structurally consistent caller evidence. `adoption.assert_official_adoption_allowed` always refuses activation, and default/rollback selection returns exactly frozen v1. No active gate behavior was changed to implement these recommendations.

## Actionable external blockers

1. **Independent human review:** record actual judgments for the four flip occurrences, real-case annotation policy and the semantic `D-conflicting-01` question; do not substitute the separate AI technical review.
2. **Owner policy record:** decide SC-06 B, SC-07 B, SC-08 B; formally confirm SC-01–SC-05; record V-5 retention of v1 for the next run and V-9/error/incomplete/provenance validity policy. Recommendations here are not approvals.
3. **If v2 is selected later:** authorize the versioned semantic changes, exact identity-bound thresholds, frozen integration patch and lineage-aware re-freeze before any official result is observed. Preserve historical artifacts.
4. **Run-specific authority:** after review/policy/provenance readiness, supply authentic authorization in the exact existing runner format, bound to the actual manifest/tier/split/output. The sprint instruction is not that token. No held-out or full-split evaluation was executed by this workstream.

These are the remaining policy/review dependencies, not reasons to repeat completed engineering. Live Gemini verification and other independent technical work may continue under their own authorized scope.
