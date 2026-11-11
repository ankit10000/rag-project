# Phase 2.5 - Workstreams A, D, E: retrieval re-benchmark, stopwords, vector-hit-lost analysis

Scratch DB `rag_phase2_eval` only. No service code or default was changed. All alternatives were
evaluated via `hybrid_search_detailed(...)` parameters or by calling `reciprocal_rank_fusion(weights=...)`
inside `eval/phase25_ab.py`.

## Reproduce

```
.venv\Scripts\python.exe eval\phase25_ab.py main --seed 7            # A + D: 21 configs, latency (takes eval/results/.bench.lock), ~15 min
.venv\Scripts\python.exe eval\phase25_ab.py lost --seed 7            # E: lost-hit analysis + interventions, quality only, ~2 min
.venv\Scripts\python.exe eval\phase25_ab.py main --seed 99 --quick   # stability run: quality only, 1 repeat, no lock
.venv\Scripts\python.exe eval\phase25_ab.py lost --seed 99
```
Outputs: `eval/results/phase25_main_seed7.{log,json}`, `phase25_main_seed99_quick.{log,json}`,
`phase25_lost_seed{7,99}.{log,json}` (full per-query data, full intervention tables).

## Configuration

- Corpus: 24 real chunks + 120 filler docs (`make_distractors(120, seed=S)`), default chunking words 100/20,
  744 chunks (both seeds), 38 answerable queries, K=5. Seed 7 = the historical corpus; seed 99 = different distractors.
- Defaults untouched: vector_top_k=10, bm25_top_k=10 (Lucene positive-IDF BM25, no stopword removal), RRF k=60,
  rrf_top_k=10, rerank pool 10, cross-encoder ms-marco-MiniLM-L-6-v2.
- Latency (seed 7 only): 2 repeats per query, median per query then median/p95 across 38 queries, measured while holding the bench lock
  (lock released at the end of the phase). Other agents' processes not using the lock may still have loaded the CPU: the same pipeline
  config differs between rows (e.g. D 419 ms vs D k=10 263 ms, which are computationally identical), so
  treat latency as +/- 40% noisy and compare only coarse orders of magnitude. Seed-99 latency (`--quick`, no lock) is not meaningful and not reported.
- Bootstrap: 1000 resamples over the 38 queries, RNG seed 12345, percentile 95% CI. Paired CIs resample per-query differences.

## A. Main results (seed 7, CURRENT code) vs HISTORICAL pre-IDF-fix

"pre-IDF" columns are the historical figures supplied with the task (not re-measured). Delta = current - pre-IDF.

| Config | R@5 | P@5 | MRR | nDCG@5 | Hit@1 | med ms | p95 ms | rerank ms | pre-IDF R / MRR / nDCG | delta R / MRR / nDCG |
|---|---|---|---|---|---|---|---|---|---|---|
| A vector | 0.842 | 0.189 | 0.785 | 0.776 | 0.737 | 302 | 427 | - | 0.842 / 0.785 / 0.776 | 0 / 0 / 0 |
| B bm25 | 0.921 | 0.205 | 0.908 | 0.889 | 0.895 | 144 | 197 | - | 0.921 / 0.908 / 0.888 | 0 / 0 / +0.001 |
| C interleave | 0.974 | 0.216 | 0.922 | 0.914 | 0.895 | 409 | 525 | - | 0.974 / 0.922 / 0.914 | 0 / 0 / 0 |
| D RRF k=60 | 0.974 | 0.216 | 0.889 | 0.890 | 0.842 | 419 | 546 | - | 0.974 / 0.889 / 0.890 | 0 / 0 / 0 |
| E RRF+rerank pool 10 | 0.947 | 0.211 | 0.926 | 0.911 | 0.921 | 916 | 1256 | 566 | 0.947 / 0.926 / 0.911 | 0 / 0 / 0 |
| E pool=5 | 0.974 | 0.216 | 0.939 | 0.927 | 0.921 | 442 | 610 | 172 | 0.974 / 0.939 / 0.927 | 0 / 0 / 0 |
| E pool=20 (fused 20, lists 10) | 0.947 | 0.211 | 0.947 | 0.927 | 0.947 | 1015 | 1443 | 718 | n/a | n/a |
| E pool=20 (lists 20) | 0.947 | 0.211 | 0.947 | 0.927 | 0.947 | 1186 | 1471 | 893 | n/a | n/a |
| D k=10 / k=30 / k=100 | 0.974 | 0.216 | 0.889 | 0.890 | 0.842 | 263 / 293 / 297 | 328 / 465 / 414 | - | n/a | n/a |
| E k=10 / k=30 / k=100 | 0.947 | 0.211 | 0.926 | 0.911 | 0.921 | 685 / 729 / 707 | 1067 / 1051 / 904 | 398 / 417 / 423 | n/a | n/a |
| B2 Postgres FTS | 0.803 | 0.179 | 0.734 | 0.724 | 0.684 | 215 | 309 | - | 0.803 / 0.734 / 0.724 | 0 / 0 / 0 |
| D2 RRF + FTS | 0.868 | 0.195 | 0.831 | 0.820 | 0.816 | 350 | 501 | - | n/a | n/a |
| E2 RRF(FTS)+rerank | 0.895 | 0.200 | 0.895 | 0.874 | 0.895 | 741 | 911 | 367 | n/a | n/a |

Finding: **current quality is identical (to 3 decimals) to the pre-IDF-fix numbers** for every config that has a historical value.
The Lucene IDF fix does not move retrieval on this corpus (unscoped queries, IDF of query terms is positive anyway, and the
doc-filtered queries did not shift rank order enough to change any top-5). The fix is a correctness fix for scoped searches, not a benchmark gain here.

### Stability: seed 99 (different distractors, same 744 chunks), quality only

| Config | R@5 | MRR | nDCG@5 | Hit@1 | delta MRR vs seed 7 |
|---|---|---|---|---|---|
| A vector | 0.842 | 0.776 | 0.773 | 0.711 | -0.009 |
| B bm25 | 0.921 | 0.908 | 0.889 | 0.895 | 0 |
| C interleave | 0.974 | 0.925 | 0.917 | 0.895 | +0.003 |
| D RRF | 0.974 | 0.888 | 0.889 | 0.842 | -0.001 |
| E pool 10 | 0.947 | 0.934 | 0.917 | 0.921 | +0.008 |
| E pool=5 | 0.974 | 0.943 | 0.930 | 0.921 | +0.004 |
| E pool=20 | 0.974 | 0.954 | 0.938 | 0.947 | +0.007 |
| B2 FTS | 0.803 | 0.755 | 0.742 | 0.711 | +0.021 |
| D2 RRF+FTS | 0.895 | 0.830 | 0.826 | 0.789 | -0.001 |
| E2 FTS+rerank | 0.868 | 0.868 | 0.848 | 0.868 | -0.027 |

The ordering and recall are stable across distractor seeds. Differences of a few thousandths in MRR are distractor noise.
Two seed-dependent items: E pool=20 loses 1 query on seed 7 (`POL-HR-031` recall 0) but not on seed 99; the queries that fail are the same 2-3 on both seeds.

### Bootstrap 95% CIs (seed 7; seed 99 similar, see phase25_main_seed99_quick.json)

| Config | Recall@5 [CI] | MRR [CI] |
|---|---|---|
| A vector | 0.842 [0.711, 0.947] | 0.785 [0.658, 0.895] |
| B bm25 | 0.921 [0.816, 1.000] | 0.908 [0.803, 0.974] |
| C interleave | 0.974 [0.921, 1.000] | 0.922 [0.836, 0.987] |
| D RRF | 0.974 [0.921, 1.000] | 0.889 [0.789, 0.961] |
| E pool 10 | 0.947 [0.868, 1.000] | 0.926 [0.832, 1.000] |
| E pool=5 | 0.974 [0.921, 1.000] | 0.939 [0.860, 1.000] |
| E pool=20 | 0.947 [0.868, 1.000] | 0.947 [0.868, 1.000] |
| B2 FTS | 0.803 [0.671, 0.908] | 0.734 [0.605, 0.861] |
| D2 RRF+FTS | 0.868 [0.763, 0.974] | 0.831 [0.702, 0.930] |
| E2 | 0.895 [0.789, 0.974] | 0.895 [0.789, 0.974] |

All the BM25 / RRF / interleave / rerank variants have overlapping intervals. 1 query = 0.026 recall. Only these are statistically separable at 38 queries:
vector alone is worse than RRF (paired dRecall CI [+0.053, +0.237]; dMRR [+0.024, +0.200]), and FTS is worse than the in-memory BM25 (paired dMRR CI [-0.311, -0.047]).

### Recall@5 by query kind (seed 7; n: abbrev 8, keyword 8, metadata 4, multi 6, semantic 8, short 4)

| Config | abbrev | keyword | metadata | multi | semantic | short |
|---|---|---|---|---|---|---|
| A vector | 0.75 | 0.75 | 1.00 | 1.00 | 0.88 | 0.75 |
| B bm25 | 1.00 | 1.00 | 0.75 | 1.00 | 0.75 | 1.00 |
| C interleave | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| D RRF | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| E pool 10 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 1.00 |
| E pool=5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 |
| E pool=20 | 1.00 | 0.88 | 1.00 | 1.00 | 0.88 | 1.00 |
| B2 FTS | 0.88 | 0.50 | 1.00 | 0.92 | 0.75 | 1.00 |
| D2 RRF+FTS | 0.88 | 0.75 | 1.00 | 1.00 | 0.75 | 1.00 |

### Effect of RRF k and rerank pool

- **RRF k in {10, 30, 60, 100}: zero queries change** in D or E (both seeds). With two lists of 10 and unit weights the fused ordering barely depends on k here; k is not a lever on this data.
- **Rerank pool**: 5 vs 10 differ by 2 queries (seed 7: `callback ... platform` recall 0 -> 1, `POL-HR-031` MRR 0.20 -> 0.33; seed 99: only the `callback` query).
  Pool 5 recall 0.974 vs pool 10 0.947 is a 1-query difference (paired dRecall CI [0, +0.079], i.e. includes 0). Pool 20 adds latency (rerank ~718 ms vs 566 ms vs 172 ms at pool 5, noisy) and
  trades one query for another (gains `old row versions`, loses `POL-HR-031` on seed 7); MRR/Hit@1 up by ~0.02 (CI includes 0).
  The measured rerank cost scales roughly linearly with pool size.

### Per-query changes between configs (seed 7)

- B -> D (RRF): gains recall on `callback ... platform` (0->1, MRR 0.20) and `When is the interview?` (0->1, MRR 0.5); loses rank on keyword queries `POL-HR-031` (MRR 1.0 -> 0.25), `INC-2057` (1.0 -> 0.5) and `How can a server prove its identity...` (0.5 -> 0.33). Net recall +0.053, MRR -0.019 (dMRR CI [-0.081, +0.032]).
- A -> D: 8 queries change (recall gains on `POL-HR-031`, `INC-2057`, `What is HNSW?`, `MTTR`, `HNSW`; rank gains `PHD26052`).
- C -> D: only `POL-HR-031` and `INC-2057` lose rank (interleave puts the BM25 rank-1 exact-ID hit first; RRF averages it with a weak vector hit).
- D -> E: rerank rescues rank for 3 queries (`How can a server prove...`, `INC-2057`, `When is the interview?`: MRR up to 1.0) but **drops the `callback ... platform` gold chunk out of the top 5** (recall 1 -> 0). It is in the fused top 10 (rank 5 in D) and the cross-encoder scores it below five others.
- E pool 10 -> pool 5: `callback` recovered (the reranker never sees the competing chunks), `POL-HR-031` MRR 0.20 -> 0.33.
- Persistent failures: D/C: only `What happens to old row versions after an update in the database?` (gold phrase "leave dead tuples behind"; vector rank 6, absent from BM25 - no lexical overlap).
  E pool 10: that query plus `callback ...`.
- Seed 99 is the same set of changes with slightly different MRR values (e.g. `POL-HR-031` MRR 0.33 under D instead of 0.25).

## D. Stopword removal (BM25_DROP_STOPWORDS equivalent via `drop_stopwords=True`)

| Config | seed 7 R@5 / MRR / nDCG | seed 99 R@5 / MRR / nDCG |
|---|---|---|
| B bm25 | 0.921 / 0.908 / 0.889 | 0.921 / 0.908 / 0.889 |
| B3 bm25 no stopwords | 0.908 / 0.908 / 0.881 | 0.908 / 0.908 / 0.881 |
| D RRF | 0.974 / 0.889 / 0.890 | 0.974 / 0.888 / 0.889 |
| D3 RRF no stopwords | 0.947 / 0.884 / 0.879 | 0.974 / 0.888 / 0.889 |
| E rerank (pool 10) | 0.947 / 0.926 / 0.911 | 0.947 / 0.934 / 0.917 |
| E3 rerank no stopwords | 0.947 / 0.926 / 0.911 | 0.947 / 0.930 / 0.914 |
| E pool=5 | 0.974 / 0.939 / 0.927 | 0.974 / 0.943 / 0.930 |
| E3 pool=5 no stopwords | 0.947 / 0.930 / 0.914 | 0.974 / 0.939 / 0.927 |

By kind recall (seed 7): B -> B3 differs only on `multi` 1.00 -> 0.92 (the query `Compare HNSW and IVFFlat indexes and explain what pg_dump is used for.`: recall 1.00 -> 0.50; removing "and/is/used/for..." removed matches the second gold chunk).
D -> D3: `semantic` 0.88 -> 0.75 on seed 7 (the `callback` query, recall 1 -> 0, because without stopwords the BM25 rank of the gold chunk shifts down); on seed 99 D3 == D exactly. E -> E3: no change on seed 7; 1 MRR change on seed 99 (`POL-HR-031`).
E3 pool=5 vs E pool=5: on seed 7 stopword removal lowers recall (0.947 vs 0.974); on seed 99 they are equal.

Conclusion D: stopword removal is **never better and sometimes worse** (1 query lost in B3, 1 in D3 on seed 7), and the effect flips with the distractor seed. No evidence to enable it; leave `BM25_DROP_STOPWORDS=False`.

## E. Vector-only hits lost from the RRF top 5

Definition: gold chunk in vector top-10 (or top-5) but not in the fused top-5 (D, k=60, 10+10 lists).

- Seed 7: **1 occurrence in 38 queries**; seed 99: the same query. Vector top-5 and not fused top-5: **0 occurrences**.
- The one case: `What happens to old row versions after an update in the database?` (gold "leave dead tuples behind"). Vector rank 6, BM25 rank none (no lexical overlap), so its RRF score is 1/(60+6) = 0.01515.
  The two top-10 lists do not overlap for this query, so the fused list is 5 BM25-only chunks (ranks 1-5, scores 1/61..1/65) interleaved with 5 vector-only chunks (ranks 1-5, same scores): the fused top 5 is
  api_reference_v2 (BM25 rank 1), a filler doc (vector rank 1), incident_postmortems (BM25 rank 2), a filler doc (vector rank 2), api_reference_v2 (BM25 rank 3). The gold chunk is the 11th candidate, just outside the fused top 10, so it is also not in the default rerank pool. Only a pool of >= 11-20 (fused 20) recovers it, and then the reranker puts it first.
- Related but different loss: `callback ... platform` is lost by the **reranker**, not by RRF (gold is at fused rank 5 in pool 10).

### Interventions (all 38 queries; "improved/worsened" count queries by recall or MRR vs baseline; seed 7 unless noted)

D (fused top 5 without rerank):

| Variant | R@5 | MRR | improved | worsened | dMRR CI |
|---|---|---|---|---|---|
| baseline | 0.974 | 0.889 | - | - | - |
| weights [kw 1.0, vec 1.5] (also [1,2], [0.5,1]: identical) | 0.842 | 0.798 | 2 | 5 | [-0.187, -0.012] |
| stopwords removed | 0.947 | 0.884 | 0 | 1 | [-0.016, 0] |
| keyword score >= 0.3 x best | 0.974 | 0.889 | 0 (seed 99: 1) | 0 | [0, 0] (s99 [0, +0.053]) |
| keyword score >= 0.5 x best | 0.974 | 0.922 | 2 | 0 | [0, +0.086] |
| keyword score >= 0.7 x best | 0.974 | 0.926 | 3 | 0 | [0, +0.092] (s99: 3 improved, 0 worsened, MRR 0.928) |
| k=10 / 30 / 100 | 0.974 | 0.889 | 0 | 0 | [0, 0] |

E (cross-encoder rerank), seed 7 [seed 99 where it differs]:

| Variant | R@5 | MRR | improved | worsened |
|---|---|---|---|---|
| baseline pool 10 | 0.947 | 0.926 | - | - |
| pool 10 + weights [1,1.5] | 0.842 | 0.842 | 1 (`old row versions`) | 5 (the exact-ID/abbrev queries) |
| pool 10 + stopwords | 0.947 | 0.926 | 0 | 0 [s99: 1 MRR worse] |
| pool 10 + kw filter 0.7 | 0.974 | 0.954 | 2 (`old row versions`, `POL-HR-031` MRR) | 0 [s99: 1 / 1] |
| pool 5 baseline | 0.974 | 0.939 | 2 vs pool 10 | 0 |
| pool 5 + kw filter 0.3/0.5/0.7 | 0.974 | 0.939 / 0.939 / 0.943 | 2 vs pool 10 | 0 |
| pool 20 (fused 20) | 0.947 | 0.947 | 1 | 1 (`POL-HR-031` recall 0) |
| pool 20 + weights / stopwords / kw filter | 0.947 (kw 0.7: 0.974) | 0.947 (0.953) | 1 | 1 (kw 0.7: 0) |

Findings:
1. **Weighted RRF hurts.** Weighting the vector list higher (or BM25 lower) fixes 1-2 semantic queries but breaks 5 exact-ID / abbreviation queries (`POL-HR-031`, `INC-2057`, `What is HNSW?`, `MTTR`, `HNSW`) whose only signal is BM25 rank 1 in a list where the vector rank 1 is a wrong chunk. Reproduced identically on both seeds; recall -0.13, CI of the recall delta excludes 0. Do not change weights.
2. **Stopword removal does not fix** the lost query and loses another on seed 7.
3. **Larger pool/lists**: pool 20 recovers the `old row versions` query only when the reranker is applied (gold must enter the pool), but it also costs `POL-HR-031` on seed 7. Net zero. Pool 5 fixes `callback` (which pool 10 loses) with lower latency. The best recall/latency in the data is pool 5.
4. **Keyword score filter (>= 0.7 x best BM25 score before fusion)** is the only intervention that improves MRR/recall without a single worsened query in D on both seeds, and in E at pool 10 on seed 7 (recall 0.947 -> 0.974). Mechanism: it drops weak BM25 tail hits so strong vector hits are not pushed down by tail-noise rank-ties. But: (a) it was one threshold family tuned and evaluated on the same 38 queries, (b) all CIs include 0 (e.g. dRecall CI [0, +0.079]), (c) on seed 99 pool 10 + 0.7 improved 1 query and worsened 1 (net 0), (d) the effect is largest on exact-ID queries (`POL-HR-031`, `INC-2057`) whose rank was lowered by RRF rather than a lost hit. Treat as a hypothesis, not a result.

## Limitations

- 38 queries over a 24-chunk real core plus synthetic filler: 1 query = 0.026 recall; every CI above overlaps for the near-tied configs. The corpus is synthetic and small; the filler is template text that shares few words with gold, which favours BM25 (exact IDs) and understates hard lexical collisions.
- Only 2 distractor seeds; same 38 queries on both, so seeds test distractor variation only, not query variation. Interventions (filter threshold, weights) were chosen and scored on the same queries (no held-out split): optimistic.
- Gold judging is by substring match of a span inside the chunk; multi-gold queries count partial recall.
- Latency: seed 7 only, 2 repeats, other agents shared the CPU (the lock only protects against cooperating agents); sub-300 ms numbers are noisy. Seed 99 latency intentionally ignored. First-call cache effects (BM25 index build) are absorbed by warm-up. The in-memory BM25 builds an index per scope (per doc filter).
- "pre-IDF" numbers are the supplied historical values, not re-run on old code.
- The E-section "lost" filter uses vector/BM25 top-10 lists (defaults); lists of 20 were examined only in the pool-20 variants.

## RECOMMENDATION

- **RERANK_TOP_K (10)**: candidate to lower to 5. Evidence: +1 query recall (0.947 -> 0.974), MRR +0.013, rerank latency ~3x lower, reproduced on seed 99; but difference is 1 query and CI includes 0. Do not change on this evidence alone; confirm on a larger/real query set (and check recall on harder queries where the answer sits at fused rank 6-10, which pool 5 cannot reach).
- **RRF_K (60)**: no change; k in {10..100} is a no-op on this data.
- **BM25_DROP_STOPWORDS (False)**: keep off; no gain, one regression per seed on average.
- **Weights**: keep [1,1]; asymmetric weights clearly hurt exact-ID queries.
- **BM25 backend**: keep in-memory BM25 over Postgres FTS (FTS recall 0.80 vs 0.92; keyword-kind recall 0.50 vs 1.00).
- **New lead, not for adoption yet**: relative-score filter on keyword hits (>= ~0.7 x best) - improves MRR with no worsened queries on D in both seeds.
- Evidence still needed: a larger and independent labelled query set (>= 150 queries, held-out for tuning), real documents (not templated filler), a multi-seed latency run with exclusive CPU, and a test of the keyword-score filter and pool 5 on a held-out set including queries whose gold has no lexical overlap.
