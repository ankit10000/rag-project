# WP8 development scorer-flip analysis

Date: 2026-11-17. Status: **engineering evidence complete; every flip PENDING_INDEPENDENT_REVIEW**. This is not a human-approved golden list, a scorer-adoption decision, or an acceptance report. No scorer, annotation, dataset, threshold, historical result, frozen runner or gate was changed.

## Inventory and accounting

All four available development comparisons cited by the WP6 work were inspected, including their sidecars, Markdown differences and historical literal annotations. Their byte-identical snapshots are archived under `wp8_evidence/flip_inputs/`; `index.json` records original paths, archived paths, raw hashes, scorer hashes, source-result identities and dataset pins. These snapshots preserve historical evidence; they are **not newly executed evaluation results**. The original files remain unchanged. WP7 integration tests use temporary comparison bundles that are removed on test cleanup; its report cites no additional persistent comparison-result paths.

| Original comparison directory | Tier | Row occurrences | Flip occurrences | Recorded scorer identity | Exact current v2 replay |
|---|---:|---:|---:|---|---|
| `/private/tmp/wp6-dev-rescore-9ljt095p` | 1 | 47 | 3 | `ebc9a15b6706180486f8f813b93bc75383bcac29cecce226b8a143f9b8cc93d9` | Not claimed: old source identity |
| `/private/tmp/wp6-dev-rescore-9ljt095p` | 2 | 42 | 1 | Same `ebc9…93d9` | Not claimed: old source identity |
| `/private/tmp/wp6-final-dev-hnuo27v0` | 1 | 47 | 3 | `af81bae9df469cd880c8fec8a970a95bf5e0b275679111b783ee867d4e813a2c` | 47/47 exact |
| `/private/tmp/wp6-final-dev-hnuo27v0` | 2 | 42 | 1 | Same `af81…3a2c` | 42/42 exact |

Totals: **178 row occurrences, 8 flip occurrences, 4 unique tier/case/source-result identities**. The two scorer identities share version `2.1.0` but differ in the recorded `score.py` source hash. They are retained separately; a version string is not treated as a source-identity proof. Initial and final comparison JSONL payloads happen to be byte-identical for each tier, but their sidecars record different code identities, so neither occurrence is discarded.

All 178 contexts were reconstructed using unchanged WP6 functions and the pinned revision `c1bbcae9a21e389c16c3f1587de5acc1b5209e37`. All context hashes match the corresponding sidecar; all 178 v1 stored/current scores reproduce, with **zero v1 drift**. Tier 2 reconstruction has 135 chunks and reproduces chunk-table hash `29643967a4e3b0e453efa8f44c34cddf7528b4edf3da977140008a2e199b914a`. Only the final 89 rows have matching current scorer identity and receive exact full-result v2 replay. The initial 89 v2 results are validated as recorded historical results; their old implementation is unavailable and is **not** falsely replayed with current code.

Source-result raw hashes remain:

- Tier 1: `4c1a6416f2603f7c0744533b6c3ee99570827aaefbdca003bbe346ea2bfd0988`.
- Tier 2: `b2c92e582c8e9ddb75e6adc6661a200ab294bc4956002c54f2c6258fb63f4962`.
- Historical annotations portable SHA-256: `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a`; raw hash and full pinned data-file hashes are preserved in the ledger/index.

Historical pins are operator-supplied rather than run-header-bound, and all four sidecars have `acceptance_eligible: false`. Exact replay is diagnostic evidence, not an upgrade to historical acceptance eligibility or a proof of originally unrecorded prompt bytes.

## Mechanical explanations and separate review hypotheses

All four unique flips are supported by the formal WP5 rules. No rule was optimized to reduce the flip count. The separate engineering assessments below are proposals, not adjudicated truth labels.

| Unique flip | v1 → v2 | Formal explanation | Engineering hypothesis requiring review |
|---|---|---|---|
| Tier 1 `B-comp-04` | False → True | `partial_ok` False → True; §10.2 A1/A2 and §10.3 partial rule | Expected signal expansion; pre-existing citation correctness 0.5 warrants review, without silently applying TA-D4 |
| Tier 1 `B-conf-04` | False → True | `conflict_ok` False → True; §11 sentence-scoped `although` connective | Expected contrast detection; independently confirm answer/source interpretation |
| Tier 1 `D-conflicting-01` | True → False | `conflict_ok` True → False; §11 requires both groups in the same sentence/list scope | **Possible v2 false negative**: a clear cross-sentence “However” contrast is rejected by the formal scope rule |
| Tier 2 `B-conf-04` | False → True | `conflict_ok` False → True; §11 sentence-scoped `though` connective | Expected contrast detection; independently confirm answer/source interpretation |

By rule: one unique partial-answer flip (two occurrences) and three unique disagreement flips (six occurrences). By impact: three unique False→True changes (six occurrences) and one unique True→False change (two occurrences). Mechanical explanation confidence is high; independent correctness judgments remain unreviewed. No implementation-versus-formal-spec regression was identified in these four cases. One possible semantic false negative is explicitly flagged; no new-rule false positive was established mechanically. Neither statement substitutes for human review.

### Tier 1 B-comp-04 — missing-cost signal

Question: “How many stations did each treatment get in the tile study, and what did one tile cost to produce?”

Stored answer:

> - Each treatment got 12 stations [S2].
> - The documents do not cover the production cost of one tile; the report did not record production costs [S3].

The pinned source `calder_sound_tile_study_TR-2026-07.pdf`, page 2, states “Stations were set in a grid of 12 stations per treatment.” Gold alternatives are `12 stations` / `12 per`. Both scorers have fact recall 1, no forbidden hits, no ungrounded numbers and unchanged citation arithmetic. V1's 22 fixed insufficiency phrases do not match “documents do not cover” or “report did not record.” V2 records A1 and A2 signals in eligible clauses and sets `partial_ok=True`. Its numeric guard is True.

Both scores retain `citation_correctness=0.5` and completeness 1; v2 did not repair citation quality or change the v1 citation policy. Source absence and citation adequacy must be reviewed separately. TA-D4 remains a pending proposal, not a correction applied here.

Exact reconstructed context SHA-256: `b01b51c3522e78f2f75fe88bd7422d7e0f1854edf9a0a02367cd4e526a1dabb3`.

### Tier 1 B-conf-04 — “Although” in a qualifying sentence

Stored answer:

> The tile monitoring ran for 14 months [S2]. (Note: Although section 4 mentions monitoring over 15 months [S3], the executive summary explicitly states that monitoring ran for 14 months [S2].)

Gold sources are the tile report page 1 (“Monitoring ran for 14 months.”) and page 4 (“Over the 15 months of monitoring”). Both required groups and pages are present/cited. V1's seven global disagreement phrases omit “although.” V2's §11 connective table includes it, and its second sentence contains both groups; `conflict_ok` becomes True. The reported disagreement scope is sentence index 1, groups `[0,1]`, not a list extension. Fact recall, grounding and citation scores are unchanged.

Exact reconstructed context SHA-256: `84984c2dca7c09c178bdcc5802637cb9a3426b73b47618528b966906717467a4`.

### Tier 1 D-conflicting-01 — formal scope narrowing, possible false negative

Stored answer:

> Pump P-204 needs its bearing grease every 750 hours according to the Brannock_Ridge_Safety_SOP_Rev4.pdf document, which takes precedence over the OEM tables on site [S1]. However, the Aquaflow maintenance manual states an interval of 500 hours for clean water duty, which should be halved for glycol mixtures above 30% [S2].

Gold evidence is the OEM manual page 2 (“Pump P-204 | bearing grease | 500 h | 35 Nm”) and the site SOP page 3 (“Pump P-204 | bearing grease | 750 h”). Both groups match, both required pages are cited, numeric grounding is True and neither scorer has forbidden hits.

V1 accepts the global “however” phrase. V2 §11 requires one sentence/list scope to contain both groups and a qualifying disagreement signal. Here 750 hours occurs in the first sentence and 500 hours in the second; neither scope contains both. V2 therefore reports no qualifying disagreement and `conflict_ok=False`. This is the specified behavior, not proof that the answer is substantively wrong. Engineering hypothesis: it may be an over-strict semantic false negative because the adjacent sentences explicitly contrast the documents. Independent review should prioritize this case. Any subsequent scope-rule change requires explicit contract/version review; this package changes no scoring rule.

Exact reconstructed context SHA-256: `ebdc0e9dc1f33b2e35bce8098e8a3fbf5b4e6254ea25f1954d701a58894203bd`.

### Tier 2 B-conf-04 — parenthetical “though” contrast

Stored answer:

> The tile monitoring ran for 14 months [S1] (though another section mentions 15 months of monitoring) [S2].

The gold report pages and groups are the same as the Tier 1 case. Both occur in one sentence; parenthetical clauses remain part of its disagreement scope. V1 does not recognize “though.” V2 §11 does, yielding a scope at sentence index 0 with groups `[0,1]`, full citation completeness and `conflict_ok=True`. Other common score fields are unchanged.

Exact reconstructed context SHA-256: `f7a823a4694606bfe8dbf08df2f90c1e6458a82692cdefd4322b30287ef09e26`.

## Reproduction and review workflow

`eval/acceptance_preparation/flips.py` is a pure byte-input validator/analyzer. It rejects malformed/duplicate/non-finite JSON, mislabeled/non-dev rows, incomplete coverage, invalid scorer aggregates, source/annotation/context hash mismatches, missing pins, annotation linkage failures, v1 drift, current-identity v2 replay mismatches, and missing rule codes. `group_occurrences` groups by tier/case/source hash while retaining every artifact occurrence. `ledger_rows` serializes deterministic mechanical evidence and explicitly separate proposed engineering assessments; it cannot supply approval.

Run from the repository root:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B test_stage9_wp8_flips.py
```

Result: **9 unittest methods passed, exit 0**. Tests replay all archived contexts/v1 results and current-identity v2 results, verify the CSV's deterministic mechanical evidence against the archives, exercise malformed metadata/hashes and preserve input bytes. The environment URL is unreachable; no database access, provider call, held-out scoring or full-split evaluation is performed. Local PyMuPDF/ONNX initialization may emit a telemetry-persistence warning; network operations are blocked by the shared test guard.

`actual_analyses()` in the test file performs reproducible local Git-pinned reconstruction with unchanged WP6 helpers; it reads repository snapshots rather than depending on volatile `/private/tmp` originals. The ledger preserves the originals' paths as historical provenance and adds archived paths for reproduction. Original result files are still verified by raw hash. The pure analyzer receives reconstructed evidence explicitly instead of manufacturing missing provenance.

Every ledger row remains `PENDING_INDEPENDENT_REVIEW` with `human_approved=False`. Required next steps: independently review all four unique flips and their eight identity-specific occurrences; decide the cross-sentence contrast concern; complete annotation and specification review; and separately authorize any adoption, gate change or re-freeze. No such approval is inferred here.
