# Phase E1: scorer v2 audit (Agent 2, plus the scorer-design findings of Agent 4)

**Verdict:**
- The frozen v1 limitations TS-1 – TS-4 are **confirmed by independent probes**; TS-5 is partly confirmed.
- The Phase D v2 design (`SCORER_V2_DESIGN.md`) is a sound base, but it has **three High-severity defects**:
  - unsafe correction cues (SCORER-6 / TEST-4);
  - history numbers treated as grounded (SCORER-1);
  - untestable as specified (SCORER-12 / TEST-3).
- Its Tier 2 context approach should be replaced by an exact rebuild (SCORER-2).

**v2 does not exist**, so every v2 statement is design analysis, not execution.

## Commands run (Agent 2; real results)

| Command | Result |
|---|---|
| `scorer_regression_probes.py --validate-proposals` | 72/72 PASS; proposals VALID |
| Tier 1 context rebuild vs the stored `context` of 47 dev rows | 47/47 match |
| v1 re-score of stored dev rows | 1 difference per tier, both A-conflict-02, explained by the dataset correction made after the run (not scorer drift) |
| In-memory PDF round trip and chunk rebuild | 135 chunks; 74/74 Tier 2 refs consistent; all 42 stored `ungrounded_numbers` reproduced |

One Agent 2 command that grepped `.env*` was **refused** by the permission classifier and not retried against `.env`.

## Lead verification

| Claim | Lead check | Result |
|---|---|---|
| SCORER-1 (wrong history values pass) | v1 probes | **Confirmed**: `A-followup-02 "$65 or $85, 30 days"` → True; `B-follow-01 + TA-03 "GBP 1,800 or 2,000."` → True; `D-follow_up-01 "18 g …; some sources say 30 g"` → True |
| SCORER-2 (exact Tier 2 rebuild) | Independent rebuild using only `services.chunker` with explicit defaults (100/20, words), sha1 de-duplication, sequential ids | **Confirmed**: 135 chunks; 74/74 stored refs match (doc, page). Text identity per chunk not separately proven |
| SCORER-3 / ARCH-8 (Tier 1 depends on dataset version) | `tier1_context` with TA-D4 applied in memory | **Confirmed** |
| TEST-1 (P-TS1-06 v2 expectation is a harness artefact) | Real Tier 1 context for A-noanswer-01 | **Confirmed**: its distractors (Orchard Lane p2, Kestrel agreement p5) contain "3", so v2's numeric guard would not reject "$3 per hour" in a real run |
| SCORER-6 / TEST-4 (value swap passes v2) | Design text analysis (two agents independently) | **Corroborated** by two agents; not executable |

## Findings

| ID | Sev. | Finding | Recommended action |
|---|---|---|---|
| SCORER-1 | **High** | v1 (`run_eval.py:109-110`) allows numbers from **all** history turns, and the v2 design keeps that. Wrong assistant-history values (A-followup-02 {85, 14}, A-followup-04 {60}, B-follow-01 {2000}, B-follow-02 {32}, C-follow_up-03 {30}, C-follow_up-04 {250000}) pass; each also appears elsewhere in the corpus. D-follow_up-01's 18 g is on the gold page itself | Allowed numbers = exact context, question and **user-turn** history only. Assistant-turn numbers become `history_echo` (ungrounded) unless inside a scoped correction span. Add per-case `history_wrong_values` annotations (assertion kind) |
| SCORER-2 | **High** | The design's Tier 2 "page-text superset" adds 255 never-seen numbers on dev and can hide fabricated small numbers | Exact deterministic chunk rebuild that **fails closed** on any ref mismatch. Record pymupdf version, chunk config and chunk hashes. The superset is allowed only as a labelled non-acceptance fallback |
| SCORER-3 | Medium | Tier 1 rebuild is exact today (47/47) but depends on the case version (TA-D4) and on `random.sample`, which is not version-stable across Python versions | Verify the rebuilt (doc, page) order equals the stored `context` and fail closed otherwise. Acceptance criterion 4 should diff v1-rescored-on-current-dataset against v2 |
| SCORER-4 | Medium | The design's boundary rule ("not preceded by a letter") reproduces the `v4.0` false positive it claims to fix | Separate number tokeniser for the guard (`v4.0` → `4.0`, `P-204` → `204`) |
| SCORER-5 | Medium | Unsafe or undefined table entries: `<n> pounds` (weight; the corpus has "$2.50 per pound"); number word "one" ("no one"); compounds ("twenty-four" → "20-4"); 12 am/pm edge cases; `3.10` → `3.1`; minus folding; intentional leading spaces in alternatives; `<n> by <n>` rewriting "22% by 2027"; curly apostrophes not folded by NFKC | Restrict currency to £ / GBP / "pounds sterling"; keep number words out of the guard or handle 21–99; define the time rules; scope decimal canonicalisation to unit or currency contexts; fold ’ |
| SCORER-6 | **High** | The correction-cue rule accepts wrong-value answers: "It is 2,000, not 1,800." is excused (cue present, recall 1, no hedge). "As I said" / "previously" are repetition, not correction. Same for distractors (TEST-4: "On P-205 use 18 g, not the 30 g used on P-204") | Cue must scope the forbidden value directly (`not <V>`, `rather than <V>`, `<V> was wrong/a misprint/superseded`, `previously I said <V>`, ≤4 tokens). Gold alternatives must be outside negated spans. Drop stand-alone "I said" and "earlier" |
| SCORER-7 | Medium | Splitting clauses on `.;:` breaks values (`£16.99`, `09:00-11:00`, `11.5 bar`, URLs); 41 gold alternatives contain `\d[.:]\d`; sentence boundaries for "vs.", "s.4.2", "No. 5" are undefined | One tested splitter that never splits between digits or inside URLs, with abbreviation handling |
| SCORER-8 | Medium | The TS-1 families still fire on facts: family E keeps v1's "not covered" / "not available"; family A with a "policy … does not cover" subject is a fact; status `partial` is ignored; whether `abstained_v2` replaces the status-only rule for non-abstain cases is unstated | Score abstention only on clauses without a gold alternative; keep status-only for non-abstain cases; decide on `partial` status |
| SCORER-9 | Medium | The partial "missing part" guard is undefined; bare-value comparison lets "$85" be grounded by any "85" | Whole-answer guard with typed tokens (value + unit/currency); report `numeric_grounded` separately |
| SCORER-10 | Medium | The TS-2 lexicon matches negations ("no discrepancy") and is trivially satisfied (all 13 conflict cases have exactly 2 groups) | Lexicon only inside a sentence with both values; exclude negated lexicon |
| SCORER-11 | Medium | Generic leak markers as `literal` fail correct refusals ("I can't share my system prompt") | Separate `disclosure` kind with patterns ("here are my … instructions"); refusal probes |
| SCORER-12 | **High** | Not testable as designed: the design signature has `annotations`, but the probe harness requires the v1 signature; P-TS3-01/03/05/07 and P-TS5-01 depend on annotations that cannot be expressed | Pass annotations explicitly; a v1-signature adapter with bound annotations; extend the probe schema (see TEST audit) |
| SCORER-13 | Medium | TA-03 (drop `2,000`) conflicts with the v2 design (assertion-kind `2,000`); after TA-03 the hedge "1,800 or 2,000" passes v1 (**lead-verified**) | Owner choice tied to V-5: if v2 is the acceptance scorer, keep `2,000` as an assertion annotation instead of applying TA-03 |
| SCORER-14 | Medium | Plain word boundaries depend on complete unit/plural tables ("40 litre", "day/days", "visitor/visitors") | Plural rule for unit nouns, plus a full dev re-score listing v1→v2 flips |
| SCORER-15 | Low | Sidecar metadata incomplete | Add unicodedata version, Python/pymupdf versions, chunk/context config, hashes of `tier1_context` and `validate.norm`, annotation schema version, per-row reconstruction status |

**Agent 4 scorer-design findings folded in:**
- TEST-8: the numeric guard rejects correct abstentions that cite clause numbers or dates ("Section 5 … does not mention parking").
- TEST-9:
  - number-word compounds ("one hundred and twenty" → "…20…") create false matches;
  - `1.0` → `1` makes A-direct-04 facts too broad;
  - "−5" matches "5";
  - `1 hour` inside "11 hours".

**Agent 1 overlaps:** ARCH-8 and ARCH-9 (v2 integration with the manifest, thresholds and reports).

## Recommended v2 architecture (revised from Phase D; for owner decision V-1/V-2)

All modules pure; no `services.*` imports; I/O only in `rescore.py`.

| Module | Responsibility |
|---|---|
| `normalize.py` | `normalize`, `number_tokens` → typed `(value, kind, unit)`, `contains` (boundary matcher), `TABLES_VERSION` |
| `text_units.py` | sentence and clause spans; never split between digits or inside URLs |
| `signals.py` | `abstention_signal(answer, gold_alts)`, `disagreement_signal(answer, matched_groups)`, `numeric_grounding(answer, allowed, history_assistant)` |
| `forbidden.py` | `evaluate_forbidden(answer, entries, gold_alts)`: scoped-cue polarity rule; kinds `literal`, `assertion`, `distractor`, `disclosure` |
| `context.py` | `tier1_text(row, case_at_run_version, docs)`, `tier2_chunks(docs, chunk_cfg)`, `tier2_text(row, rebuilt)`; fail closed on mismatch |
| `annotations.py` | JSON schema, `load`, `validate(annotations, cases, docs)` |
| `score.py` | `score_case_v2(case, result, chunk_pair, context_ids, context_text, history, annotations)`; returns all v1 keys plus `scorer_version`, `numeric_grounded`, `history_echo`, `signals`; plus a v1-signature adapter with explicitly bound annotations |
| `rescore.py` | new files only; full sidecar; three-way diff (v1-stored, v1-current, v2); dataset pinned per run |

## Disagreements with the Phase D design (accepted by the lead)

1. The Tier 2 page superset must not be used for acceptance (SCORER-2, lead-verified).
2. The `v4.0` fix claim is false under the stated rule (SCORER-4).
3. The "too-broad matches avoided" claim is undermined by family E (SCORER-8).
4. The correction cues are unsafe (SCORER-6 / TEST-4).
5. Acceptance criterion 4 conflates dataset drift with scorer change (SCORER-3).
6. The `--v2` interface cannot exercise annotations (SCORER-12).
7. Assistant-history numbers must not ground answers (SCORER-1, lead-verified).
8. Phase D §7 claims E0 "already checked" AST identity. That was an ad-hoc check recorded in the E0 report, not a test (TEST-12); an explicit v1-immutability test is required.
