# Stage 9 Phase A: Evaluation Readiness Audit

**Date:** 2026-11-16. **Scope:** read-only audit.
**Not done:**
- No file was modified except this new report.
- No database connection was opened; every fact comes from the files.
- No LLM call, no held-out evaluation.
- No scorer, threshold, dataset or review-sheet change.
- Nothing committed or pushed.

**Held-out protection:** held-out case definitions were loaded only by the dataset loader (as every tool does) and only their **structure and status fields** were inspected. No held-out question, answer or gold fact was read for this report.

## 1. Git baseline and audit branch

| Item | Value |
|---|---|
| Start | `main` = `origin/main` = `69e8b8ec6822959a72d40a18688442808540f3c8`, clean tree |
| Branch | `audit/stage9-evaluation-readiness` (new; it did not exist locally or on origin) |
| Instructions | No project `CLAUDE.md`; the global one applies |

## 2. Evaluation asset inventory

| Asset | Path | Status |
|---|---|---|
| Dataset (4 modules, 12 documents, 56 pages, 160 cases) | `eval/phase35/data_A.py` … `data_D.py` | Frozen; SHA-256 **match** `HELDOUT_THRESHOLD_FREEZE.md` exactly |
| Split | `run_eval.split_of`: `sha1(id) % 10 < 3` → dev | **47 dev** (Tier 2: 42) / **113 held-out** (Tier 2: 106; 7 `answer_only`). `integrity.runner_split_logic_matches()` verifies the duplicated rule |
| Gold evidence | per case: `gold_facts` (all groups required, any alternative), `gold_sources` (document, page, span), `forbidden`, `expect_abstain` / `partial` / `conflict` | Page-level only; there are no gold chunk ids (stated in `retrieval_metrics.case_metrics`) |
| Validator | `eval/phase35/validate.py` | Content identical to the frozen file (see §8 on hashes) |
| Frozen scorer | `eval/phase35/run_eval.py:score_generic` + `eval/answer_scoring.py` | SHA-256 **match** the freeze |
| Frozen thresholds | `HELDOUT_THRESHOLD_FREEZE.md`; `eval/framework/safety.py:FROZEN_THRESHOLDS` | Dev T1 ≥ 41/47, T2 ≥ 28/42 (used); held-out T1 ≥ **97/113**, T2 ≥ **69/106** |
| Runners | `eval/phase35/run_eval.py` (the official runner); dev-only: `eval/h1_relevance_gate.py`, `eval/stage6_answer_replay.py`, `eval/stage6_live_dev_eval.py`, `eval/stage8_p3_live_dev_eval.py` | See §8 |
| Framework (file-based; no run command) | `eval/framework/{integrity,retrieval_metrics,answer_metrics,regression,reporting,providers,safety,memory_metrics,cli}.py` | Run gate `check_run_request` **not wired into any runner** (§8) |
| Recorded dev results | `eval/phase35/results/tier{1,2}_dev.jsonl` (Stage B run), logs `log_tier*_dev{,_stageB}.txt` | Historical; scored with the frozen scorer on the pre-correction dataset (`A-conflict-02`) |
| Later dev results | `eval/results/h1_relevance_gate_dev.json`, `stage6_answer_replay_dev.json`, `stage6_live_dev_20261116/`, `stage8_p3_live_dev_20261116/` | Dev only |
| Held-out results | none (`eval/phase35/results/tier*_heldout.jsonl` absent) | Correct: never run |
| Human-review package | `docs/remediation/heldout_review/` | See §6 |
| Memory evaluation | `eval/framework/memory_cases_proposal.py` + `memory_metrics.py` | **Proposals only, "never executed"**, mocked decisions. There is no answer-level memory dataset |
| Dataset manifest | — | **None exists** (no manifest file anywhere) |
| Older benchmarks | `eval/run_benchmark.py`, `phase25_ab.py`, `scale_benchmark.py`, `embedding_benchmark.py`, `run_answer_eval.py` and `eval/results/phase25_*`, `answer_eval*`, `chunking.json`, `configs.json` | Phase 2 / 2.5 / 3 artefacts on synthetic corpora; not part of the Phase 3.5 acceptance |

## 3–4. Development failure inventory and root-cause classification

**Sources:**
- `eval/phase35/results/tier{1,2}_dev.jsonl` (Stage B);
- `eval/results/stage6_live_dev_20261116/` (S6);
- `eval/results/stage8_p3_live_dev_20261116/cases.json` (P3, 6 cases);
- **H.1:** `BATCH2_STAGE5_RETRIEVAL_REPORT.md` §H.1. Retrieval-only, no answers: no-rerank relevant-retrieval rate 0.947, irrelevant 0.652; reranked reference 0.921 / 0.359.

All case ids are dev (asserted with `split_of`). **Totals (frozen scorer):** Tier 1 41/47 (B) and 41/47 (S6); Tier 2 28/42 (B) and 29/42 (S6).

The Stage B files hold the **Stage B re-run**. B4's Tier 2 failure list describes the earlier pre-Stage-B run, which survives only as `log_tier2_dev.txt`; `STAGE_B_DEV_LIVE_EVALUATION_REPORT.md` records the case swaps (`D-compound-04`, `B-conf-04`).

### Tier 1 (gold context supplied: isolates generation)

| Case | Category | Gold pages | B | S6 | Failing scorer signal | Failure type | Root cause (evidence) | Next action |
|---|---|---|---|---|---|---|---|---|
| A-conflict-02 | direct_factual (was conflicting) | Marlow p.2, p.4 | ✗ | ✓ | B: `conflict_ok=F` | **Ground truth (historical)** | Case corrected after Stage B (`HELDOUT_DATASET_CORRECTIONS.md`: conflicting → direct_factual). The B score uses the old definition | None; report historical scores as pre-correction |
| B-comp-04 | compound, expect_partial | calder p.2 | ✗ | ✗ | `partial_ok=F` only (recall 1.0) | **Scorer + ground-truth gap** | The answer states "12 stations" and that the tile cost is not recorded, citing p.4. p.4 literally says "production cost per tile was not recorded". The scorer phrase list lacks "do not cover" / "does not provide"; `gold_sources` lacks p.4, so the valid citation counts as incorrect (0.5) | Scorer v2 design (§5); human decision on the gold sources (§6) |
| B-conf-04 | conflicting | calder p.1, p.4 | ✗ | ✗ | `conflict_ok=F` (S6 also recall 0.5) | **Generation (conflict handling)** | Both sides supplied; the model did not state the disagreement | Generation investigation; human check that this is a true conflict |
| C-missing_metadata-01 | missing_metadata (answer_only) | Kestrel p.5 | ✗ | ✗ | abstained, `abstain_ok=F` | **Generation (unnecessary abstention)** | The model abstains when metadata is missing; cause not established | Audit the prompt behaviour on missing metadata |
| D-compound-04 | compound, expect_partial | Corvane p.2 | ✓ | ✗ | S6: `partial_ok=F` only | **Scorer limitation** + model wording | B: "I couldn't find sufficient information…" (listed); S6: "do not mention" (not listed). The answers are substantively equal | Scorer v2 design (§5) |
| D-conflicting-03 | conflicting | Corvane p.1, p.4 | ✗ | ✗ | `conflict_ok=F` | **Generation (conflict handling)** | Both sides supplied, disagreement not stated | As B-conf-04 |
| D-conflicting-04 | conflicting | Corvane p.2, p.5 | ✗ | ✗ | `conflict_ok=F` | **Generation (conflict handling)** | As above | As B-conf-04 |

### Tier 2 (end to end)

| Case | Category | Gold pages | Retrieved (S6) | Page recall B / S6 | B / S6 / P3 | Failure type | Root cause (evidence) | Next action |
|---|---|---|---|---|---|---|---|---|
| D-follow_up-04 | follow_up | Aquaflow p.3 | none (`not_run`) | 0 / 0 | ✗ / ✗ / **✓** | **Classification: confirmed defect, fixed** | Raw follow-up classified MEMORY before the rewrite; P3 (`21979fa`) classifies the rewritten query; P3 run: DOCUMENT, gold 1/1, correct | Monitor; single-run evidence |
| C-direct-05 | direct_factual | Harbourline p.3 | p.3 (S6) | 0 / 1.0 | ✗ / ✓ / ✗ | **Model variability (classification)** | No history; the same classifier input was labelled MEMORY (B, P3) and DOCUMENT (S6, fallback model) | Design decision (Stage 8 audit §8 options) |
| A-multipage-03 | multi_page | Orchard p.1, p.3 | p.3, p.4 | 0.5 / 0.5 | ✗ / ✗ / ✗ | **Retrieval limitation** | Gold p.1 never retrieved | Retrieval investigation |
| A-multipage-04 | multi_page | Kestrel p.3, p.4 | Orchard p.2 | 0 / 0 | ✗ / ✗ | **Retrieval failure** | Wrong document retrieved | Retrieval investigation |
| B-chunk-03 | multi_chunk | kestrel p.3 | kestrel p.1, velmoor p.3, p.4 | 0 / 0 | ✗ / ✗ | **Retrieval failure** | Gold page not retrieved | Retrieval investigation |
| B-conf-02 | conflicting | kestrel p.3, velmoor p.4 | velmoor p.4 | 0.5 / 0.5 | ✗ / ✗ | **Retrieval limitation → conflict unsurfaced** | One side missing | Retrieval investigation |
| B-conf-03 | conflicting | velmoor p.1, p.5 | velmoor p.1 | 0.5 / 0.5 | ✗ / ✗ | **Retrieval limitation → conflict unsurfaced** | One side missing | As above |
| C-multi_page-03 | multi_page | Harbourline p.2, p.4 | p.1, p.4 | 0.5 / 0.5 | ✗ / ✗ | **Retrieval limitation** (+ scorer FP on `unsupported`) | p.2 ("3 appliances") never retrieved; `ungrounded_numbers=['4.0']` is the scorer artefact (§5) | Retrieval investigation; scorer v2 |
| D-conflicting-04 | conflicting | Corvane p.2, p.5 | p.2 | 0.5 / 0.5 | ✗ / ✗ | **Retrieval limitation** | One side missing | Retrieval investigation |
| D-multi_page-04 | multi_page | Aquaflow p.4, Brannock p.4 | Aquaflow p.4 | 0.5 / 0.5 | ✗ / ✗ / ✗ | **Retrieval limitation** | Brannock p.4 never retrieved (cross-document) | Retrieval investigation |
| B-conf-04 | conflicting | calder p.1, p.4 | both | 1.0 / 1.0 | ✗ / ✗ | **Generation (conflict handling)** | Both sides retrieved, disagreement not stated | Generation investigation |
| D-conflicting-03 | conflicting | Corvane p.1, p.4 | both | 1.0 / 1.0 | ✗ / ✗ | **Generation (conflict handling)** | As above | As above |
| A-multichunk-04 | multi_chunk | Orchard p.2 | p.1, p.2 | 1.0 / 1.0 | ✗ / ✗ | **Generation (incomplete), unclassified** | recall 0.5 with the gold page retrieved; cause not established | Inspect the answer vs gold (dev) |
| B-inject-04 | prompt_injection | kestrel p.1 | p.1, p.5 | 1.0 / 1.0 | ✗ / ✗ | **Generation (incomplete), unclassified** | recall 0.5, citation correctness 0.5; no forbidden hit (the injection was not obeyed) | As above |

### Classification summary (Tier 1 + Tier 2, distinct causes)

| Class | Cases |
|---|---|
| Confirmed implementation defect | **D-follow_up-04** (classification order; fixed in P3, development-validated once) |
| Retrieval limitations / failures | A-multipage-03, A-multipage-04, B-chunk-03, B-conf-02, B-conf-03, C-multi_page-03, D-conflicting-04, D-multi_page-04 (**8**, the largest Tier 2 class) |
| Generation: conflict not surfaced although both sides were available | B-conf-04 (T1 + T2), D-conflicting-03 (T1 + T2), D-conflicting-04 (T1) |
| Generation: other / unclassified | C-missing_metadata-01 (unnecessary abstention), A-multichunk-04, B-inject-04 (incomplete) |
| Model variability | C-direct-05 (classification); D-compound-04 wording (interacts with the scorer) |
| Ground truth | A-conflict-02 (corrected after Stage B, historical); B-comp-04 (gold sources omit the page that states the missing fact) |
| Scorer limitations | D-compound-04 (S6), B-comp-04 (both runs): `partial_ok` false negatives; C-multi_page-03: `unsupported` false positive |

## 5. Frozen scorer blind spots

### Blind spot 1: insufficiency phrase list (`eval/answer_scoring.py:INSUFFICIENCY_PHRASES`)

`score_generic` sets `partial_ok = recall > 0 and abstained`, where `abstained = status == "abstained" or _has_any(answer, INSUFFICIENCY_PHRASES)`. The list contains "not mentioned", "no mention" and "not covered", but **not** "do not mention", "do not cover", "does not provide" or "do not state".

| Case | Gold | Answer (excerpt) | Scorer | Why wrong | Type |
|---|---|---|---|---|---|
| D-compound-04 (T1, S6) | `[["USD 185","$185","185"]]`, expect_partial, Corvane p.2 | "…USD 185 [S1]. The provided documents do not mention whether gym fees…" | `partial_ok=F`, `correct=F` | States the fact and the gap; the B answer with "couldn't find sufficient information" scored ✓ | **False negative** |
| B-comp-04 (T1, B and S6) | `[["12 stations","12 per"]]`, expect_partial, calder p.2 | "…12 stations [S2]. The documents do not cover the production cost… not record[ed] [S3]" | `partial_ok=F`, `correct=F` | Correct partial answer; p.4 states the cost was not recorded | **False negative** (plus the ground-truth gap in §4) |

**Historical effect if corrected (computed on the recorded rows only, nothing re-scored or overwritten):**
- Tier 1 Stage B: 41 → 42 (B-comp-04).
- Tier 1 S6: 41 → 43 (B-comp-04, D-compound-04).
- No Tier 2 change found by a scan of all four recorded runs.

The phrase list also drives `abstain_ok` for expect-abstain cases; no affected abstain case was found.

### Blind spot 2: `norm_numbers` (`run_eval.py`, `NUM_RE = (?<![\w.])\d…`)

- **Case:** C-multi_page-03. Gold `[["£8.99"],["3 appliances","three appliances"]]`, Harbourline p.4 + p.2.
- **What happens:** the context contains `v4.0`; the lookbehind skips digits glued to a letter, so `4.0` is absent from the allowed numbers. The answer's "version 4.0" yields `4.0` → `ungrounded_numbers=['4.0']` → `unsupported=True`.
- **Type: false positive** on the `unsupported` flag. It does **not** affect `correct`: `correct` doesn't use `ungrounded_numbers`, and this case is `correct=False` for a legitimate reason (recall 0.5).
- **Recorded occurrences:** Stage B T2, S6 T1 (`correct=True`), S6 T2. These are all the `unsupported` flags in the dev runs.
- **If corrected:** the `unsupported` counts become 0 in every dev run; no `correct` value changes.

### Versioning implications
- Both blind spots are in files whose SHA-256 is **frozen** for held-out (`run_eval.py`, `answer_scoring.py`). The freeze allows pre-result changes only through a documented, re-frozen correction.
- Any fix therefore needs a **new, versioned scorer** (for example a separate `answer_scoring_v2` / `score_generic_v2`). The frozen v1 stays byte-identical and is used for every historical comparison.
- Both versions would be reported side by side, and the held-out acceptance scorer would have to be chosen and re-frozen **before** any held-out run.
- Re-freezing the scorer may also require reconsidering the thresholds, because v2 can only raise or keep `correct` relative to v1.

## 6. Human ground-truth review readiness

| Question | Finding |
|---|---|
| Does the review sheet exist? | **Yes.** `heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx` (SHA-256 `300dc43f…`, matching `FINAL_HUMAN_REVIEW_PREPARATION_REPORT.md`): tabs `Read Me & Sign-off`, `Held-out Cases`, `Correction Ledger` |
| Are all required cases represented? | **113/113** held-out rows (per the preparation report's round-trip check; row count re-verified here) |
| Does each row have an explicit review status? | Columns exist (`reviewer_decision` dropdown VALID / NEEDS REVISION / EXCLUDE, `reviewer_rationale`, `reviewer_name`, `review_date`), but **0/113 are filled** (re-verified). `reviewer_attention` is set on 2 rows (A-conflict-03, D-conflicting-02) |
| Is evidence linked to the sources? | Yes: `expected_sources_json` (document, page, span); `source_pdfs/` (12 PDFs) and `source_pages.md`; the preparation report says all 139 held-out spans matched the PDF text |
| Is the earlier review independent? | **No.** `REVIEW_SIGNOFF_REPORT.md`: an AI-assisted (Claude) review, 88 VALID / 25 NEEDS REVISION / 0 EXCLUDE; its corrections were applied (`HELDOUT_DATASET_CORRECTIONS.md`: 24 edits / 22 cases + A-conflict-01 / A-conflict-02). It explicitly does not satisfy the independent-review requirement |
| Specificity of conflicting / compound criteria | The AI review found conflict expectations set on updates rather than disagreements (4 held-out cases corrected) and fact groups with missing phrasings. **Dev** conflicting cases (B-conf-02/03/04, D-conflicting-03/04, A-conflict-02 corrected) were **not** human-reviewed. `conflict_ok` requires both a disagreement phrase **and** every gold page cited |
| Cases needing human decisions | All 113 held-out (sign-off); specifically A-conflict-03 and D-conflicting-02 (flagged). Dev: B-comp-04 gold sources (should p.4 be gold?) and the dev conflicting cases (true conflicts?) |
| Dev review sheet | **None.** Dev cases have never been human-reviewed. A dev sheet should use the same structure as the held-out workbook (same columns + `split=dev`) if the user wants dev ground truth verified |

Proposed structure for any additional sheet (not created): the existing workbook columns, i.e. case id, split, tier eligibility, category, question/history, expected facts (groups/alternatives), forbidden, expect flags, sources (document/page/span), reviewer_decision, reviewer_rationale, reviewer_name, review_date, reviewer_attention; plus a sign-off block with reviewer independence and dataset hashes.

## 7. Proposed acceptance matrix (for the user's decision)

"Frozen" = already approved; "proposed" = a candidate only, **not adopted**. Baselines are dev values recomputed from recorded rows with the frozen scorer and `eval/framework/retrieval_metrics` (unit: (document, page)), on S6 unless stated.

| Metric | Definition | Tier | Unit | Dev baseline (B / S6) | Candidate target | Reason | Status |
|---|---|---|---|---|---|---|---|
| Answer correctness | `score_generic.correct` (all fact groups + no forbidden + expectation flags) | T1 | cases | 41/47 / 41/47 | held-out **≥ 97/113** | approved | **Frozen** |
| Answer correctness | as above | T2 | cases | 28/42 / 29/42 | held-out **≥ 69/106** | approved | **Frozen** |
| Retrieval page recall | coverage of gold (doc, page) over all retrieved | T2 | mean over answerable | 0.816 / 0.842 (n=38) | report only, or ≥ 0.80 | the largest Tier 2 failure class; regression guard | Proposed |
| Precision@5 | gold pages in top 5 / 5 (fixed K) | T2 | mean | 0.190 / 0.195 | **report only** | ceiling ≈ 0.2–0.4 with 1–2 gold pages; not a meaningful gate as defined | Proposed (diagnostic) |
| MRR / nDCG@5 | first gold rank / graded ranking (binary gains) | T2 | mean | MRR 0.807 / 0.833; nDCG 0.774 / 0.800 | report only | ranking quality diagnostic | Proposed (diagnostic) |
| Citation correctness | cited chunks on gold pages / cited | T1, T2 | mean | T1 0.968 / 0.968; T2 0.869 / 0.901 | report only, or ≥ 0.85 (T2) | **penalises valid non-gold citations** (B-comp-04); needs the ground-truth decision first | Proposed |
| Citation completeness | gold pages covered by citations / gold pages | T1, T2 | mean | T1 0.968 / 0.968; T2 0.821 / 0.845 | report only | coupled to retrieval recall in T2 | Proposed |
| Unsupported-answer rate | `score.unsupported` (forbidden / unabstained abstain / fabricated ref / ungrounded number) | T1, T2 | cases | T1 0 / 1; T2 1 / 1 (all = the v1 false positive) | ≤ 2% of cases, or 0 fabricated refs | grounding safety; v1 has a known FP | Proposed |
| Fabricated references | cited refs absent from context | T1, T2 | count | 0 everywhere | **0** | hard safety property | Proposed |
| Abstention accuracy | expect_abstain cases with `abstain_ok` | T1, T2 | cases | T1 8/8 / 8/8; T2 4/4 / 4/4 | 100% of no-answer cases | never fabricate on no-answer | Proposed |
| Over-abstention | answerable cases not abstained | T1, T2 | cases | T1 36/37 / 36/37; T2 34/36 / 35/36 | report only | trade-off with abstention | Proposed (diagnostic) |
| Conflict handling | `conflict_ok` on expect_conflict cases | T1, T2 | cases | T1 3/7 / 3/6; T2 2/7 / 1/6 | report only until the dev conflicts are human-reviewed | weakest category; ground truth unreviewed | Proposed |
| Partial-answer behaviour | `partial_ok` on expect_partial cases | T1, T2 | cases | T1 1/2 / 0/2; T2 2/2 / 2/2 | report only (v1 phrase list is unreliable) | blind spot 1 | Proposed |
| Memory-related answer reliability | — | — | — | **no dataset** | — | memory evaluation exists only as unexecuted proposals | Gap; needs a design decision |

**Recommendation:**
- Keep the two frozen `correct` thresholds as the only held-out pass/fail gates.
- Report every other metric as a diagnostic, unless the user approves new gates **before** the held-out run (that requires a documented re-freeze).
- Denominators for the `conflict_ok` / `partial_ok` baselines differ between B (pre-correction) and S6 (corrected dataset).

## 8. Runner and reproducibility audit

| Aspect | Finding | Risk |
|---|---|---|
| Deterministic case selection | `split_of` (sha1), order = dataset order; `--limit` truncates | Low |
| Split enforcement (official runner) | `run_eval.py --split` accepts `dev`, `heldout`, `all` (default `dev`); **no approval check** | **High.** One command (`--split heldout` or `--split all`) would run held-out with no gate |
| Approval gate | `eval/framework/safety.check_run_request` (approval file with marker, manifests, explicit splits/outputs) is called **only in `test_p4_eval_framework.py`**; the safety module itself calls integration "a documented future step" | **High** (same weakness) |
| Dev-only runners | `h1_relevance_gate`, `stage6_answer_replay`, `stage6_live_dev_eval` (preflight asserts dev ids = recorded baseline), `stage8_p3_live_dev_eval` (reuses that preflight) all filter or assert dev | Low |
| Dataset / scorer hashes | Recorded in the freeze docs, **not in result rows**; no manifest file exists (`integrity.build_manifest` / `cli manifest` exist but were never used to write a frozen manifest) | Medium: results are not self-describing |
| Hash portability | 4 recorded hashes (`validate.py`, `source_pages.md`, 2 review CSVs) **do not match on this Mac** because the files were hashed as CRLF on Windows (CSV: CRLF rows + BOM) and are checked out as LF here. Re-serialising reproduces every recorded hash exactly → **content identical**. The data, `run_eval.py` and `answer_scoring.py` hashes match as-is | Medium: verification depends on the platform. Recommend hashing LF-normalised content or recording git blob ids |
| Model / provider attribution | `run_eval` rows record tokens, `llm_calls`, latency, but **not the model**; fallback use is visible only in the logs. The Stage 6 / P3 runners record per-request model / outcome | Medium (fallback mixing seen in Stage 6) |
| Prompt / rewrite inputs | `run_eval` records neither the rewritten query nor the classification. The P3 runner records both (6 cases) | Medium |
| Retrieval output | Tier 2 rows record `retrieved` (ref, chunk id, document, page, score). Tier 1 records `context` | Low |
| Errors / retries | Runner errors are kept as rows (`status=error`, `RUNNER ERROR: {error!r}`; the message text may include provider detail); retries/fallbacks are only in stdout logs | Low/medium |
| Resume / duplicates | Appends to `tier{N}_{split}.jsonl`; skips ids already present (no duplicate rows); **`--fresh` deletes the file** | Medium: `--fresh` destroys history (this is why Stage 6 used a separate runner) |
| Result-file integrity | No per-run id, hash or manifest in the file; logs are separate | Medium |
| Database boundaries | `harness.use_scratch_database("rag_phase35_eval")` at import (creates it if missing; allow-list of scratch names; never `rag_db`). Tier 2 **TRUNCATEs and re-ingests** `rag_phase35_eval` unless `--no-ingest` | Low for `rag_db`; scratch writes by design |
| Development vs held-out loading | Every runner loads all 160 case definitions (the validator needs them) and then filters. The dev-only runners never execute held-out cases | Accepted, as long as the filter is asserted |

## 9. Database and held-out safety analysis
- **This audit opened no database connection** and wrote nothing. Fingerprints were not needed; the last recorded fingerprints (`BATCH2_STAGE8_COMPLETION_REPORT.md`) stand.
- `rag_db` can't be targeted by the evaluation harness (the allow-list excludes it).
- **Held-out has never been run** (no result files). The only accidental-run vector found is `run_eval.py --split heldout|all` without a gate (§8).
- The held-out thresholds and dataset hashes match the freeze; the dataset `.py` files are byte-identical to the frozen hashes.

## 10. Known limitations (verified fact vs hypothesis)

| Area | Item | Basis |
|---|---|---|
| Retrieval | H.1 no-rerank relevance policy undecided | Fact (Stage 5 report H.1) |
| Retrieval | A-multipage-03, D-multi_page-04 (and C-multi_page-03, B-conf-02/03, D-conflicting-04) retrieve 1 of 2 gold pages; A-multipage-04 and B-chunk-03 retrieve none | Fact (recorded rows) |
| Retrieval | BM25 fingerprint scans the scope per query; vector/FTS sequential scans | Fact (Stage 5 report); performance impact at scale is a hypothesis |
| Grounding | Numeric grounding only; names, paraphrase, hedging, non-numeric wrong-source claims not detected; derived and spelled-out numbers limited | Fact (Stage 6 report, pinned tests) |
| Classification | C-direct-05 MEMORY/DOCUMENT variability; P3 validated on 6 cases, 1 run | Fact; cause (sampling vs model) is a hypothesis |
| Generation | Conflicts not surfaced even with both sides available (B-conf-04, D-conflicting-03) | Fact (recorded); cause is a hypothesis |
| Memory | Decision-model accuracy unmeasured (mocked); Phase 3 temporal conflict rules not re-assessed in Stage 8; extraction batches non-atomic; no memory answer dataset | Fact |
| Evaluation | Two scorer blind spots (§5); B-comp-04 gold-source gap; no independent human review; held-out not authorised; no manifest; run gate not wired; hash portability | Fact |

## 11. Proposed Stage 9 execution order (not started)

1. **Phase E0 (small, first): runner safety.** Wire `check_run_request` (or an equivalent hard refusal) into `run_eval.py` for `heldout` / `all`. Produce a frozen dataset manifest with LF-normalised hashes. Leave scoring and selection untouched. Tests only, no evaluation. This removes the one accidental held-out vector before anything else.
2. **Phase B: ground truth.** Independent human review of the 113 held-out rows in the existing workbook (no new sheet needed). Optionally a dev review sheet, same structure, for the dev conflicting cases and B-comp-04. Then re-validate (`validate.py` = VALID) and re-freeze the hashes through the documented procedure.
3. **Phase C: scorer v2 design.** A separate versioned scorer (phrase list, `norm_numbers` evidence side). Comparison tests against v1 on the recorded dev rows (expected: T1 +1/+2, `unsupported` → 0). Approval before adoption. v1 stays frozen for history.
4. **Phase D: acceptance approval.** Approve the gates (keep or extend the frozen `correct` thresholds), the diagnostic metrics, the scorer version, and the held-out denominators after any exclusions.
5. **Phase E: held-out readiness.** Verify the manifest, hashes, scorer version, thresholds, run plan, output paths (new directory, no `--fresh`), and the approval file with its marker. Get final explicit authorisation.
6. **Phase F: held-out run.** Once per tier, preserve the raw outputs, hashes and logs, and write the final report.

Independent of the held-out path, and only if approved:
- a retrieval investigation of the 8 retrieval-class failures (dev only);
- a generation investigation of conflict surfacing.

## 12. Decisions requiring user approval

1. Do Phase E0 (runner gate + manifest) before anything else? *(Recommended.)*
2. Who performs the independent human review of the 113 held-out cases, and should a **dev** review (conflicting cases, B-comp-04 gold sources) be added?
3. Should B-comp-04's gold sources include calder p.4? (A dataset change: dev, documented procedure.)
4. Approve designing a **versioned scorer v2**? If yes, which version will be the held-out acceptance scorer? (It must be re-frozen before the run.)
5. Approve the acceptance matrix: keep `correct` as the only gates (recommended), or adopt any proposed metric as a gate before the freeze?
6. The hash method for future freezes: LF-normalised SHA-256 or git blob ids?
7. Memory-related answer reliability: build a dataset (design needed), or keep it out of Stage 9 scope?
8. Approve dev-only retrieval / conflict-generation investigations, and their call budget, separately from the held-out path.

**Stop:** Phase A complete. No review sheet, scorer, threshold, dataset or code was changed; no held-out evaluation or LLM call was made.
