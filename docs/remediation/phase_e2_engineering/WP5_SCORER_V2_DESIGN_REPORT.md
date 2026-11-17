# WP5: scorer v2.1 design report (Stage 9 Phase E2)

**Deliverable:** `docs/remediation/phase_e2_engineering/wp5/SCORER_V2_1_SPEC.md`. It is a specification only.

**Scope respected:**
- Nothing was implemented. No `eval/scoring_v2/` exists.
- v1 (`eval/answer_scoring.py`, `eval/phase35/run_eval.py`), tests, `eval/phase35/*`, `eval/framework/*` and the Phase C/D/E1 documents are unchanged.
- No git command that changes state was run.
- No DB, network or LLM; `.env` was not read; `services.retrieval_config` was not imported (its constants were read as text).

## 1. Summary

The spec supersedes Phase D's `SCORER_V2_DESIGN.md` as **scorer v2.1** (`SCORER_VERSION = "2.1.0"`). It resolves every High finding:

| High finding | Resolution | Spec § |
|---|---|---|
| SCORER-1: history grounding | Assistant-turn numbers never enter the allowed set. `history_echo` fails `correct`. Scoped correction spans are exempt. Per-case `history_wrong_values` cover wrong values that also appear in the context | §8, §5.3, §13.2 |
| SCORER-2: Tier 2 context | Exact in-memory chunk rebuild (PyMuPDF → `get_text(sort=True)` → <10 words skipped → `chunk_page(100,20,'words')` → per-document sha1 dedupe → sequential ids). Fails closed on any `(chunk_id, document, page)` mismatch. Records versions, config, a chunk-table hash and per-chunk hashes. The page superset is allowed only as `NON_ACCEPTANCE` | §12.3 |
| SCORER-6 / TEST-4: value swap | Cue families scoped to the exact value: ≤ 4 FILLER tokens, prefix / from-to / stated-wrong / self-correction / epistemic. **Polarity rule:** a gold alternative inside a negated span does not count, so "It is 2,000, not 1,800" FAILS and "1,800, not 2,000" PASSES. Hedge and re-affirmation vetoes. "as I said", "earlier" and "separately" are dropped | §7, §9.2 – §9.3 |
| SCORER-12 / TEST-3: testability | `score_case(case, result, chunk_pair, context_ids, context_text, history, annotations)` with explicit annotations and history. v1-signature adapter `bind_v1_signature(annotations)` with explicit binding. Annotation JSON schema with validation rules AV-1 … AV-10. Aligned to the call **WP3's harness already makes** | §13 |
| ARCH-8: dataset pinning | Dataset loaded at the run-time revision (run header or `--dataset-rev`) and hash-checked. Ordered Tier 1 context verified; fail closed. Demonstrated: pinning the dev rows to `c1bbcae` reproduces 47/47; `HEAD` gives 46/47 | §12.1 – §12.2 |

**The 12 requirements:**

| # | Requirement | Spec § |
|---|---|---|
| 1 | Assistant-history numbers do not ground an answer | §8 |
| 2 | User and assistant turns treated differently | §8 |
| 3 | Scoped correction cues; value swaps fail | §7 |
| 4 | Tier 2 exact reconstruction | §12.3 |
| 5 | Tier 1 pinned reconstruction | §12.1 – §12.2 |
| 6 | Typed normalisation and guard tokeniser | §4 – §5 |
| 7 | Splitter | §6 |
| 8 | Abstention | §10 |
| 9 | Disagreement | §11 |
| 10 | Disclosure kind | §9.4 |
| 11 | API, adapter, schema, harness | §13 |
| 12 | Sidecar | §14.4 |

Also included:
- module layout (§2);
- versioning, the three-way diff and the CLI (§14);
- WP7 integration dependencies (§15, ARCH-9);
- acceptance criteria, including the v1-immutability test (§16, TEST-12);
- owner decisions (§17);
- traceability (§18);
- WP3 alignment (Appendix B).

Each requirement section gives the rule, its rationale (finding IDs), positive and negative tests (answer text and expected outcome; about 120 test rows in total) and the residual risks.

## 2. Traceability

| Finding | Sev. | Spec § | Status |
|---|---|---|---|
| SCORER-1 | High | §8, §5.3, §13.2 | Resolved |
| SCORER-2 | High | §12.3, §14.4 | Resolved |
| SCORER-3 | Med | §12.1 – §12.2, §14.3 | Resolved (ordered check; drift separated from v2 change) |
| SCORER-4 | Med | §5.1 | Resolved (`v4.0` and "version 4.0" → the same ref token) |
| SCORER-5 | Med | §4.1 – §4.4, §5.2 | Resolved |
| SCORER-6 | High | §7, §9 | Resolved |
| SCORER-7 | Med | §6 | Resolved |
| SCORER-8 | Med | §10 | Resolved (status `partial` → V-7) |
| SCORER-9 | Med | §5.2 – §5.3 | Resolved |
| SCORER-10 | Med | §11 | Resolved (residual D-10 pinned) |
| SCORER-11 | Med | §9.4 | Resolved |
| SCORER-12 | High | §13 | Resolved |
| SCORER-13 | Med | §17 | Owner decision, with a recommendation |
| SCORER-14 | Med | §4.1, §4.3 | Rules resolved; **the flip list is deferred to WP6** (needs the implementation) |
| SCORER-15 | Low | §14.4 | Resolved |
| TEST-1 | High | §10.4, §13.4, App. B | Spec side resolved; harness changes are WP3's |
| TEST-2 | High | §13.2, §13.4 | Keys defined; WP3 is asked to assert `v2_signals` |
| TEST-3 | High | §13, App. B | Resolved |
| TEST-4 | High | §7.4–§7.5 (C-01, C-11) | Resolved |
| TEST-5 | Med | §7.3 | Hedge veto; probes are WP3's |
| TEST-6 | Med | — | Deferred (dataset/probe) |
| TEST-7 | Med | §16 | WP3 owns it; it is an acceptance prerequisite |
| TEST-8 | Med | §5.2, §10.4 | Resolved (ref kind) |
| TEST-9 | Med | §4 | Resolved |
| TEST-10/11/13/14/15 | — | — | Out of WP5 scope |
| TEST-12 | Low–Med | §16.3 | Resolved (explicit immutability test) |
| ARCH-8 | High | §12.1 – §12.2 | Resolved |
| ARCH-9 | Med | §15 | WP7 dependency |

## 3. Commands run (real outputs)

All Python ran as:

```
cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B -c "..."
```

- Two longer evidence scripts were kept in the session scratchpad (outside the repository) and executed through `-c "exec(open(<scratch>/ev1.py).read())"` / `ev2.py`.
- They only read files, call `git show` (read-only) and render PDFs in memory (`tobytes()`, never saved).
- `git status` afterwards showed no change to any tracked file by WP5. Untracked `eval/probes/` is WP3's.

| ID | Command / check | Real output |
|---|---|---|
| E-1 | `git log -- eval/phase35/results/tier{1,2}_dev.jsonl`; `git diff --stat dfa10d7 c1bbcae -- data_*.py`; `… c1bbcae 4a5e090 …` | Results last changed `c1bbcae` (2026-11-12). Data identical `dfa10d7`→`c1bbcae`; changed at `4a5e090` (33 +/33 −; incl. A-conflict-01/02 reclassification). `c1bbcae` is an ancestor of HEAD |
| E-2 | Status counts in stored rows | Tier 1: answered 36, abstained 9, conflict 1, partial 1. Tier 2: answered 29, partial 6, abstained 6, conflict 1. Stored non-empty `ungrounded_numbers`: Tier 1 0, Tier 2 1 |
| E-3 | Corpus greps (56 pages, 12 documents) | `per pound`: 1 ("$2.50 per pound of cargo"); `pounds?`: 3 (2× "pounds sterling", 1× weight); am/pm: 3 ("8am-8pm" ×2, "2 pm"); noon/midnight: 1 ("crosses midnight"); "no one"/"one of": 0; minus before a digit: 0; tens-units word compounds: 0; "N% by YYYY": 0; `v\d.\d` / letter-hyphen codes: 59 (e.g. "v4.0 (June 2023)"); "No./Fig." before a digit: 3; URL: 1 (`http://data-sink.example.org/collect`); U+2019: 0 |
| E-4 | Gold alternatives (current dataset) | 349 alternatives; **41 contain `\d[.:]\d`**; padded: `'12 '` (B-direct-03); trailing-zero decimals: `1.0`, `3.0`, `$14.50`, `$2.50`, `97.0%`; containing "one": `one hour` (D-injection-03); with clause punctuation: **0**; 35 with currency, 14 with `%`; 66 forbidden entries in 46 cases (38 contain digits); 16 `prompt_injection` and 16 `follow_up` cases; all 16 history cases have assistant turns; A-multichunk-01 groups `[['65'], ['70'], ['same day', 'same visit', 'same appointment']]` |
| E-5 | Tier 1 rebuild vs stored `context` (`tier1_context`, current dataset) | ordered `(chunk_id, document, page)` equality **47/47** (also 47/47 as sets with gold flags, at both `c1bbcae` and current); max total context 4,500 chars (12,000 limit), max 4 items (8 limit), 0 duplicate-content rows; max over all 160 cases 4,848 chars; v1 re-score reproduces stored `ungrounded_numbers` 47/47 |
| E-6 | Tier 2 in-memory rebuild (`ev2.py`) | **135 chunks**; chunk-table sha256 `896cac77d2b03a3c51465e258b2fb96da300d92d2cc577e48d719ec2223e1493`; **58 distinct stored refs** (retrieved ∪ citations) → **0 mismatches**; v1 re-score on the rebuilt chunk text: `ungrounded_numbers` **42/42**, `correct` **42/42**; page superset adds **255** numbers absent from the exact chunks (row-summed). v1 `norm_numbers`: `v4.0`→[], `version 4.0`→['4.0'], `P-204`→['204'], `09:00-11:00`→['00','09','11'], `−5 °C`→['5'], `8am-8pm`→['8'], `1.000`→['1.000'] |
| E-7 | v1 re-score of the Tier 1 dev rows with the dataset at `c1bbcae` vs `HEAD` (data modules executed from `git show`) | `c1bbcae`: differences `[]`; `HEAD`: `['A-conflict-02']` |
| E-8 | v1 `score_generic` on the real Tier 1 context, history probes | A-followup-02 "$65 or $85…" v1 correct True, ungrounded without assistant turns `['85']`; B-follow-01 swap / correction / hedge v1 False (forbidden), assistant-only `['2000']`; D-follow_up-01 True, `[]`; C-follow_up-04 True, `['250000']`; A-followup-04 True, `[]`; B-follow-02 True, `['32']`; C-follow_up-03 True, `['30']` |
| E-9 | Versions and hashes | Python 3.14.5; unicodedata 16.0.0; PyMuPDF bind 2.0 / MuPDF 1.28.5; `answer_scoring.py` `c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af`; `run_eval.py` `9d4670ce…ace94`; `validate.py` `2f29ba0f…222ca`; frozen manifest `content_sha256` `1b73a208…bf97`, `dataset_version` `phase35-corrected-2026-11-12` |
| E-10 | A-noanswer-01 Tier 1 context | pages Orchard Lane p2, Kestrel agreement p5; bare "3": "3. Three missed…", "3 years after…"; currency 3: **none** |

**Also read as text:**
- `services/retrieval_config.py:73-79` (CHUNK 100/20/words; CONTEXT_MAX_CHARS 12000; CONTEXT_MAX_CHUNKS 8);
- `services/ingestion_service.py` (`build_chunks`, `chunk_dedupe_key`, `MIN_PAGE_WORDS`);
- `services/pdf_parser.py`;
- `services/context_assembly_service.py`;
- `services/chunker.py`;
- WP3's in-progress `eval/probes/{schema,scorer_regression,probes_phase_d,probes_e2}.py`.

**Note on E-6 vs the lead's figure:** the lead's "74 refs" counts differently, probably non-distinct retrieved entries or another grouping. WP5 counted 58 *distinct* `(chunk_id, document, page)` triples over the retrieved entries and citations of the 42 rows. All of them match.

## 4. Open owner decisions

| ID | Decision | WP5 recommendation |
|---|---|---|
| V-1 | Separate v2 package, v1 untouched | Yes |
| V-2 | Scope | TS-1 – TS-4 in full; TS-5 scorer side (disclosure kind) yes; dataset suite → V-4 |
| V-3 | Per-case annotations | Yes. Without them, SCORER-1's in-context cases (D-follow_up-01, A-followup-04), distractors and C-compound-03 stay residual |
| V-4 | Supplementary injection suite | Independent |
| V-5 | Acceptance scorer | Before any held-out result; v2 needs a threshold review (§15) |
| TA-03 vs assertion (SCORER-13) | — | If V-5 = v2: keep `2,000` as `assertion` and do **not** apply TA-03. If v1: TA-03 swaps a false rejection for a hedge false acceptance |
| V-6 | All `ungrounded_numbers` fail `correct` on fact cases? | No (v1 parity; only `history_echo`) |
| V-7 | Status `partial` = missing-part signal | Yes |
| V-8 | `ref`/`code` tokens in `numeric_grounded` | No |
| V-9 | Error-row policy (ARCH-10, SEC-3) | v2 mirrors v1 (counted as failures); recommend that a held-out run with any error row is invalid |
| V-10 | Status `conflict` as a disagreement signal | No |
| V-11 | Literal kind boundary-aware (differs from v1 substring) | Yes |

## 5. WP3 alignment

WP3's harness calls `score_case(case, result, chunk_pair, context_ids, context_text, case["history"], dict(probe["annotations"]))`. The spec adopts that call exactly, and also accepts WP3's annotation shapes:
- string `history_wrong_values`;
- `forbidden[]` without `source`;
- the text-form `disclosure`.

**Divergent v2 expectations** (Appendix B):

| Probe | WP3 | v2.1 |
|---|---|---|
| P-TS1-06 | True | **False** |
| P-TS1-08 | True | **False** |
| P-TS4-10 | True | **False** |
| P-E2-STAT-06 | None | **True** |

P-E2-HIST-07 relies on the new typed assertion match with unit propagation.

**Requested of WP3:**
- `v2_signals` asserts;
- in tier1 mode, `.strip()` the chunk text;
- annotation validation under `--v2`.

## 6. Uncertainties

- **Tier 2 chunk config of the historical run.** `.env` was not read, so the 100/20/words defaults are *assumed*. The evidence (58/58 refs, 42/42 `ungrounded_numbers` and `correct` reproduced) is strong but indirect. Per-chunk text identity is not proven directly. §12.4 asks WP7 to store context hashes.
- **The v2.1 test expectations are hand-derived** from the spec's rules, not executed (v2 does not exist). A few rows depend on context content not checked individually: G-08 and A-09 assume "5" may be absent (it is a ref, so this does not matter); P-TS1-05 assumes WP3's recorded v1 `ungrounded ['50']`, meaning no `usd 50` in its gold context.
- **The regexes are specified but not compiled or run.** WP6 must compile them and may find syntax slips. The behaviour stated in the test tables governs.
- **D-10** (positive lexicon "different" used non-contrastively) is a known residual of §11, pinned as a test.
- **Stability of `random.Random(str)` / `sample` across Python versions** is not guaranteed; the spec fails closed on any ordered mismatch rather than assuming stability.
- **WP3's files were read while still being written.** Their final probe values may differ from what Appendix B cites.
- **Executing data modules from `git show <rev>`** runs repository code from history. That is the same trust as importing it, but it is noted.
