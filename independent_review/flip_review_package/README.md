# Independent flip-review package — development only

**No independent review has occurred.** All decisions, rationales and reviewer fields are blank.
Four case/tier records and eight historical artifact occurrences are distinct; none is an approved golden list.
V1 remains official. V2.1 remains experimental. Acceptance and re-freezing are not authorized here.

## Stage A: record your own judgment before AI analysis

The existing anti-anchoring policy is preserved: see `docs/remediation/dev_review/README.md`
“How to review” and `docs/remediation/phase_e2_engineering/PHASE_E2_REMAINING_DECISIONS.md`
§1 S-2. The owner must designate an independent reviewer. This package does not designate one.

1. Open only each `records/<case-tier>/stage_a_blind.json`: question, raw answer,
   citations, full reconstructed scoring context and relevant source pages/passages.
   These files intentionally omit scorer outcomes, gold labels, AI recommendations and mechanics.
2. Record an independent judgment and rationale in a **working copy** of
   `reviewer_decisions.csv`; keep the supplied template and evidence immutable.
   Record reviewer name, date and any prior exposure; do not backfill a sign-off.
3. A human review coordinator verifies that independent judgments have been recorded
   before providing the Stage B files. No review has been recorded by this builder.

## Stage B: compare the mechanics after the independent judgment

Only after Stage A is recorded, open `records/<case-tier>/after_independent_judgment.json`.
It contains full v1/v2 results, source/scorer hashes, applicable specification excerpts,
neutral mechanical explanations and both historical occurrences. It offers no recommended outcome.
Keep the original independent judgment, then separately record any post-analysis comment/change.
Do not open the historical WP8 AI flip ledger/analysis before Stage A.

This staging is an exposure instruction, **not filesystem access control or an authenticated
approval gate**. Do not treat editing a CSV cell as proof of independence or adoption authority.
The review-status index reports preparation state only; source identity is not a truth judgment.
D-conflicting-01 is listed first as the handoff's review-priority item; no judgment is suggested.

## Provenance and limits

Current scorer identity is pinned in each Stage B record. Historical ebc9/af81 identities
remain distinct from the hardened current identity; equal result dictionaries mean behavioral
parity, not execution of an unavailable old implementation. Contexts follow the historical
WP6 scoring-context contract. Historical original runtime configuration, row order and exact
prompt bytes are not proven by reconstruction. The seven unavailable `(1)` uploads are not
represented as byte-verified uploads; repository-retained snapshots are named explicitly.

No held-out case is scored. No provider, database, ingestion, adoption or official gate is invoked.
Use `package.build_payloads(repo_root)` and `test_phase_e2_flip_review.py` to verify deterministic
records, full contexts, source/scorer hashes and blank review state. Regeneration writes exclusively
to a new directory; existing packages must never be overwritten or silently marked reviewed.
