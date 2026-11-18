# Tier 1 scorer v2.1 development validation

Date: 2026-11-18. Branch `main`, HEAD `690fcfbbf0abdf43b274161a5e6545f7ad11c325`. This focused investigation revalidates the three Tier 1 changes against actual archived inputs and the implementation present before this handoff's boundary-validation fixes. It preserves existing work and adds only this report. It does not approve a golden list, a scorer policy, an expected label, or adoption.

## Identity and complete Tier 1 replay

The handoff's seven named upload files were not present beside the request text. This work therefore used the byte-preserved WP8 **final** snapshots, whose provenance agrees with the described `af81…3a2c` comparison identity. It does not assert byte equality to an unavailable differently named upload. Snapshot inventory and original paths are preserved in `wp8_evidence/flip_inputs/index.json`.

| Evidence | Independently observed value |
|---|---|
| Comparison | `wp8_evidence/flip_inputs/final/tier1_dev.v2.jsonl` |
| Comparison raw SHA-256 | `cc075371eaeea6e9c73e3edab6af4f5f9799c02e3e782fdbba2df368c61f6fe0` |
| Sidecar raw SHA-256 | `820ed0d45b16e87d37d117016abac09afeaa87f1eba21d7a4c6c31ccddd4d557` |
| Scorer name/version/tables | `phase35-scorer` / `2.1.0` / `2.1.0` |
| Scorer aggregate SHA-256 | `af81bae9df469cd880c8fec8a970a95bf5e0b275679111b783ee867d4e813a2c` |
| Annotation raw and portable SHA-256 | `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a` |
| Dataset revision | `c1bbcae9a21e389c16c3f1587de5acc1b5209e37` |
| Dataset pin source | `operator_git_rev`; historical operator pin, not a run header |
| Frozen manifest identity recorded by the sidecar | `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97` |
| Original Tier 1 source-result raw SHA-256 | `4c1a6416f2603f7c0744533b6c3ee99570827aaefbdca003bbe346ea2bfd0988` |

All module hashes and the aggregate identity were compared with the sidecar **before** relying on the results; they matched at this investigation's pre-fix verification point. The parallel audit subsequently identified malformed-input boundary defects in direct annotation JSON and Tier 2 reference handling. Those fixes change source identity even when valid Tier 1 outputs are unchanged. The `af81…3a2c` identity in this report describes the archived/pre-fix replay, not the final post-fix implementation; the lead's new run/identity evidence governs the latter. The historical annotation file passed full validation against the Git-pinned dataset, including its dataset hash, and all four data-module hashes matched the pin. The three inspected cases have empty history and forbidden lists, with empty per-case literal baseline annotations; no richer annotation interpretation was inferred.

The independent Tier 1 pass reproduced:

- **47/47** ordered contexts and exact context hashes.
- **47/47** v1 scores, equal to both historical source scores and recorded `v1_stored`/`v1_current`.
- **47/47** full v2 result dictionaries at the matching `af81…3a2c` identity.
- **0** context mismatches, errors, fallbacks, v1 drift or v2 replay mismatches.
- Exactly **3** correctness changes: `B-comp-04`, `B-conf-04`, `D-conflicting-01`.

The older archived `ebc9…93d9` identity remains separately accounted for in the WP8 ledger; it is not represented as exact current-code replay. Both identities' historical outputs and sidecars remain unchanged. The sidecar's `acceptance_eligible` remains **false**.

## B-comp-04: a correct partial-answer classification

Question: “How many stations did each treatment get in the tile study, and what did one tile cost to produce?” The pinned case has `expect_partial=True`, `expect_conflict=False`, gold group `['12 stations', '12 per']`, and a gold source on page 2 of `calder_sound_tile_study_TR-2026-07.pdf`: “Stations were set in a grid of 12 stations per treatment.”

The raw model answer is:

> - Each treatment got 12 stations [S2].
> - The documents do not cover the production cost of one tile; the report did not record production costs [S3].

Exact Tier 1 reference mapping:

| Ref | Document/page | Gold |
|---|---|---|
| S1 | `velmoor_postgrad_handbook_v4.2.pdf`, p5 | No |
| S2 | `calder_sound_tile_study_TR-2026-07.pdf`, p2 | Yes |
| S3 | `calder_sound_tile_study_TR-2026-07.pdf`, p4 | No |

After citation stripping and bullet handling, sentence 0 matches group 0. Sentence 1 splits at the semicolon into two clauses containing no gold alternative. They are therefore eligible under WP5 §10.1. The first matches §10.2 family **A1**, “the documents do not cover,” span `[0,26]`, clause index 1; the second matches **A2**, “the report did not record,” span `[0,25]`, clause index 2. V1's fixed insufficiency phrases recognize neither wording.

| Signal | v1 | v2 |
|---|---:|---:|
| Fact recall | 1.0 | 1.0 |
| Partial OK | False | True |
| Abstain OK | None | None |
| Numeric grounded | Not reported | True |
| Citation correctness / completeness | 0.5 / 1.0 | 0.5 / 1.0 |
| Correct / correct lenient | False / False | True / True |

Neither scorer reports forbidden hits, ungrounded numbers or fabricated citations. This is **partial** success under the existing case contract: an available fact plus a genuine missing-part signal. It is not a claim that the answer supplies a tile-production price or completely answers both subquestions. The unchanged citation correctness 0.5 is an existing limitation: S3 is a context-present but non-gold citation under the pinned case. This investigation does not repair that label or apply the pending TA-D4 proposal.

Context SHA-256: `b01b51c3522e78f2f75fe88bd7422d7e0f1854edf9a0a02367cd4e526a1dabb3`.

Conclusion: the flip follows §10.2 A1/A2 and §10.3. No implementation defect was demonstrated. Missing-part adequacy, citation quality and any dataset-source correction remain independent review matters.

## B-conf-04: an actual contrast within one qualifying scope

Question: “For how many months did the tile monitoring run?” The pinned case sets `expect_conflict=True` and requires two groups: `['14 months']` and `['15 months']`. Its gold sources are the tile report page 1 (“Monitoring ran for 14 months.”) and page 4 (“Over the 15 months of monitoring”).

The raw answer is:

> The tile monitoring ran for 14 months [S2]. (Note: Although section 4 mentions monitoring over 15 months [S3], the executive summary explicitly states that monitoring ran for 14 months [S2].)

Exact references are S1 Kestrel vendor agreement p1 (non-gold), S2 tile report p1 (gold), S3 tile report p4 (gold), and S4 Kestrel fellowship call p2 (non-gold).

The splitter produces sentence 0 with group 0, then a parenthetical sentence 1 containing **both groups `[0,1]`**. That second sentence explicitly contrasts the body section and executive summary through “Although.” The word is in §11's closed `CONN` table; neither v1's seven global disagreement phrases nor the v2 lexicon supplies an alternative signal here. The v2 diagnostic is `sentence_index=1`, `groups=[0,1]`, `lexicon=[]`, `list_scope=False`.

Both required pages are cited. Fact recall is 1.0, citation correctness/completeness are both 1.0, numeric grounding is True, and forbidden/ungrounded/echo lists are empty. Only `conflict_ok`, `correct` and `correct_lenient` change, from False to True.

Context SHA-256: `84984c2dca7c09c178bdcc5802637cb9a3426b73b47618528b966906717467a4`.

Conclusion: this is not acceptance based merely on the presence of two numbers: the required groups, both cited sources and an explicit qualifying contrast all occur in one permitted sentence scope. It follows §11. Whether the report's differently located durations are substantively contradictory remains governed by the pinned `expect_conflict` label and independent review, not a new semantic inference by this scorer. Its Tier 2 occurrence uses a different answer and context; this report does not merge their hashes or scopes.

## D-conflicting-01: expected formal rejection, unresolved semantic concern

Question: “How often does pump P-204 need its bearing grease?” The pinned case sets `expect_conflict=True`, with group 0 `['500 h', '500 hours']` and group 1 `['750 h', '750 hours']`. Gold evidence:

- `Aquaflow_AF-Series_Maintenance_Manual_RevC.pdf`, p2: “Pump P-204 | bearing grease | 500 h | 35 Nm”.
- `Brannock_Ridge_Safety_SOP_Rev4.pdf`, p3: “Pump P-204 | bearing grease | 750 h”.

The raw answer is:

> Pump P-204 needs its bearing grease every 750 hours according to the Brannock_Ridge_Safety_SOP_Rev4.pdf document, which takes precedence over the OEM tables on site [S1]. However, the Aquaflow maintenance manual states an interval of 500 hours for clean water duty, which should be halved for glycol mixtures above 30% [S2].

S1 is the gold site SOP p3; S2 is the gold OEM manual p2. S3 is site SOP p5 and S4 is Kestrel Bay hospital policy p1, both non-gold distractors.

The splitter does **not** split inside the document filenames. It returns exactly two sentences:

| Scope | Matched groups | Contrast evidence |
|---|---|---|
| Sentence 0 | `[1]` — 750 hours | Site SOP attribution and site precedence |
| Sentence 1 | `[0]` — 500 hours | Starts “However”; includes clean-water/glycol qualifications |

V1 accepts a global “however” match anywhere in the answer with both pages cited. Under the formal WP5 §11 contract, no **single** sentence/list scope contains two groups; neither scope reaches the prerequisite for connective/lexicon acceptance. V2 consequently records no qualifying disagreement signal, while retaining `matched_groups=[0,1]` over the whole answer. Fact recall and both citation metrics remain 1.0; grounding is True, with no forbidden hits or history echo. `conflict_ok`, `correct` and `correct_lenient` change from True to False.

Context SHA-256: `ebdc0e9dc1f33b2e35bce8098e8a3fbf5b4e6254ea25f1954d701a58894203bd`.

Conclusion: the observed rejection follows the explicit same-sentence/list rule and is not caused by lost gold values, a malformed numeric token, missing citations or an unrecognized “However.” It does **not** establish that the answer is factually wrong. The answer provides an explicit adjacent-sentence contrast and qualifications about site precedence and fluid duty; it may be a semantic false negative under an overly strict scope rule, or a case needing review of how qualified/priority-resolved claims should be scored. Those are policy/label decisions. Joining arbitrary adjacent sentences, treating global “however” as sufficient, changing the case category or promoting the v1 answer is outside this implementation task's authority. No such change was made.

## Regression coverage and executed validation

Existing tests already supply substantive coverage, so this investigation adds no duplicate test or scoring code:

- `test_stage9_wp8_flips.py` reconstructs the archived real cases, compares complete v1/v2 dictionaries, verifies all eight occurrence records and the ledger's mechanical evidence, preserves separate old/final scorer identities and checks malformed/hash/context failure cases.
- `test_stage9_scoring_v2.py` executes the normative partial-answer example A-01 and disagreement examples D-01 through D-11. D-03/D-05 reject lexicon/connectives separated from a scope containing both groups; D-06 permits the specified list extension. These distinguish the formal D-conflicting-01 behavior from a blanket inability to recognize disagreement.

Commands executed from the repository root, with an unreachable scratch URL and network guard:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B test_stage9_scoring_v2.py

DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B test_stage9_wp8_flips.py
```

Results: **18 methods passed**, exit 0; **9 methods passed**, exit 0. The latter also reconstructs authorized Tier 2 development snapshots; it performs no held-out evaluation. No test was skipped. Local PyMuPDF/ONNX initialization emits a telemetry-persistence warning under the blocked-network guard; it is not a provider request or scoring failure.

An additional independent Tier 1-only pass invoked `load_pinned_dataset`, full annotation validation, module identity comparison, `verify_tier1`, v1 `score_generic` and explicit v2 `score_case` for the 47 source rows, then inspected sentence/clause-local gold matches for the three targets. It exited 0 and saved local diagnostic evidence at `/private/tmp/tier1-v21-investigation-evidence.json`. Persistent replay does not depend on that temporary file: the existing archive/ledger tests reproduce the underlying scores and contexts from repository snapshots.

No genuine implementation defect was demonstrated by these three changes. All raw answers, source results and historical scorer outputs remain preserved. Every flip remains pending independent review, and acceptance eligibility remains false. Any subsequent implementation change must receive its own new scorer-identity and replay evidence rather than being represented as the same archived run.
