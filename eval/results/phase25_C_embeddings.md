# Phase 2.5 / Workstream C - Embedding model comparison

Scratch database `rag_phase2_emb` only (never `rag_db`). No file under `services/`, no retrieval default and no
`vector(384)` column was changed. The query-side embedder is monkey-patched inside the benchmark process only.

## Reproduction

```
.venv\Scripts\python.exe eval\embedding_benchmark.py            # add --fresh to ignore cached per-model json
```

Outputs: `eval/results/phase25_C_embeddings.json` (all raw per-query numbers), `eval/results/phase25_C_cache/*.json`
(per model), `eval/results/phase25_C_tables.md` (the raw printed tables, including the full per-query difference
tables), logs `phase25_C_run.log` / `phase25_C_run2.log`.

The run was done in two invocations (the first was killed during `gte-small` because that checkpoint ships fp16
weights and ran for >10 min on CPU; the script now forces `float32` for all models and the first five models'
cached quality results, which were already float32, were reused). Quality metrics for each model come from a single
run; the latency pass (second phase of the script) re-loads each model and re-embeds the corpus, then measures
under `eval/results/.bench.lock`.

## Configuration

- Corpus: 24 real synthetic pages + 120 filler documents (`make_distractors(120)`, seed 7), chunked 100 words / 20 overlap
  (`CHUNK_SIZE`/`CHUNK_OVERLAP` defaults) = 744 chunks (identical text for every model; BM25 index is identical).
- Queries: the 38 answerable queries of `eval/corpus.py` (semantic 8, keyword 8, abbrev 8, multi 6, metadata 4, short 4).
  The 4 no-answer queries are not used here.
- Metrics: harness `score_query`, K = 5, chunk-level binary relevance (document + gold span). Recall = fraction of gold
  items covered in top 5.
- Modes: "vector" = pgvector cosine only; "hybrid" = BM25 (memory backend) + vector fused by RRF (k=60, pool 10), no
  reranker; "hybrid_rerank" = same plus the production cross-encoder (`ms-marco-MiniLM-L-6-v2`, top 10 candidates);
  "vector_rerank" = vector only plus reranker. Reranker was run for all six models (cheap), not only the top two.
- All embeddings are L2-normalised in the benchmark (`normalize_embeddings=True`) both for documents and queries, so
  `<=>` is cosine distance. Raw (un-normalised) model output already had norm 1.000 (min/max 0.99999988-1.0000001)
  for every model (the sentence-transformers pipelines contain a Normalize layer or equivalent), so no extra
  normalisation was hidden anywhere.
- Prefixes: bge-small query = `Represent this sentence for searching relevant passages: ` (documents none);
  e5-small-v2 query = `query: `, document = `passage: `; others none (gte-small, MiniLM variants, multi-qa need none).
  The same model embeds documents and queries in every run.
- Ablation "noprefix": bge / e5 queries embedded without their query prefix against the correctly embedded documents.

## Model facts

| Model | dim | max_seq (tokens) | chunk tokens median / max | chunks > max_seq | corpus encode s (744 chunks, CPU) | query embed ms (median of 30) | pgvector search ms (median of 30) | weights on disk (HF cache) |
|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 (baseline) | 384 | 256 | 80 / 141 | 0 | 27.3 | 15.5 | 155 | 91 MB |
| multi-qa-MiniLM-L6-cos-v1 | 384 | 512 | 80 / 141 | 0 | 25.7 | 16.2 | 89 | 91 MB |
| bge-small-en-v1.5 | 384 | 512 | 80 / 141 | 0 | 72.4 | 21.4 | 71 | 133 MB |
| e5-small-v2 | 384 | 512 | 82 / 143 | 0 | 82.8 | 25.9 | 76 | 133 MB |
| all-MiniLM-L12-v2 | 384 | **128** | 80 / 141 | **32** | 70.2 | 30.0 | 88 | 133 MB |
| gte-small (thenlper) | 384 | 512 | 80 / 141 | 0 | 42.8 | 32.3 | 89 | 67 MB (fp16 file, loaded as fp32) |

Notes on these numbers:
- Truncation pitfall: all-MiniLM-L12-v2 loads with `max_seq_length=128`, so 32 of 744 chunks (4.3%) are silently
  truncated (max 141 tokens). No other model truncates anything at 100-word chunks. The baseline's 256 limit is
  fine for the current chunk size (it would not be at ~200+ words).
- Corpus encode time and latency were measured on a shared 8-core Windows machine while two other benchmark agents
  were running CPU-heavy jobs that do not take the lock. Treat them as order-of-magnitude: 12-layer models
  (bge, e5, L12) are roughly 2.5-3x slower to embed than the 6-layer MiniLMs; query embedding is 15-32 ms for all
  of them. The "pgvector search ms" column includes opening a new connection on each call and is dominated by
  that and by machine noise (baseline = 155 ms was measured first, during heavy contention); it is NOT a
  meaningful differentiator (all models have the same 744 x 384 sequential scan, no index).
- gte-small is 67 MB only because its checkpoint is fp16; in memory it is the same size as the others.

## Quality (38 answerable queries, K = 5)

Vector only:

| Model | Recall@5 | Precision@5 | MRR | nDCG@5 | semantic | keyword | abbrev | multi | metadata | short |
|---|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 (baseline) | 0.842 | 0.189 | 0.785 | 0.776 | 0.88 | 0.75 | 0.75 | 1.00 | 1.00 | 0.75 |
| multi-qa-MiniLM-L6-cos-v1 | 0.776 | 0.174 | 0.708 | 0.702 | 0.88 | 0.62 | 0.62 | 0.92 | 1.00 | 0.75 |
| bge-small-en-v1.5 | 0.816 | 0.179 | 0.794 | 0.765 | 0.62 | 0.75 | 1.00 | 0.83 | 1.00 | 0.75 |
| e5-small-v2 | 0.895 | 0.200 | 0.868 | 0.855 | 0.62 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |
| all-MiniLM-L12-v2 | 0.816 | 0.179 | 0.741 | 0.727 | 1.00 | 0.75 | 0.75 | 0.83 | 1.00 | 0.50 |
| gte-small | 0.895 | 0.200 | 0.830 | 0.826 | 0.88 | 0.75 | 1.00 | 1.00 | 1.00 | 0.75 |

Hybrid (BM25 + vector, RRF, no reranker) - the production retrieval path before reranking:

| Model | Recall@5 | Precision@5 | MRR | nDCG@5 | semantic | keyword | abbrev | multi | metadata | short |
|---|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 (baseline) | 0.974 | 0.216 | 0.889 | 0.890 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi-qa-MiniLM-L6-cos-v1 | 0.974 | 0.216 | 0.869 | 0.875 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| bge-small-en-v1.5 | 0.947 | 0.211 | 0.864 | 0.864 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| e5-small-v2 | 0.947 | 0.211 | 0.908 | 0.898 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| all-MiniLM-L12-v2 | 0.974 | 0.216 | 0.893 | 0.893 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| gte-small | 0.921 | 0.205 | 0.862 | 0.857 | 0.75 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |

Hybrid + cross-encoder reranker (E):

| Model | Recall@5 | Precision@5 | MRR | nDCG@5 | semantic | keyword | abbrev | multi | metadata | short |
|---|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 (baseline) | 0.947 | 0.211 | 0.926 | 0.911 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| multi-qa-MiniLM-L6-cos-v1 | 0.947 | 0.211 | 0.926 | 0.911 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| bge-small-en-v1.5 | 0.921 | 0.205 | 0.921 | 0.901 | 0.75 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |
| e5-small-v2 | 0.947 | 0.211 | 0.926 | 0.911 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| all-MiniLM-L12-v2 | 0.947 | 0.211 | 0.947 | 0.927 | 0.88 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |
| gte-small | 0.947 | 0.211 | 0.947 | 0.927 | 0.88 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |

(Vector + reranker table and the prefix ablation are in `phase25_C_tables.md`.) Prefix ablation, vector only
(recall / MRR with vs without query prefix): bge 0.816 / 0.794 with prefix, 0.842 / 0.825 without; e5 0.895 / 0.868
with, 0.908 / 0.857 without. So on this set the documented prefixes did not help; the differences are 1-2 queries and
are noise. Hybrid values are essentially unchanged. The prefixes were nevertheless used in the headline numbers as the
model cards prescribe; omitting them is not a catastrophic failure on this data, but we cannot claim they are useless
on real data.

## Confidence intervals (paired bootstrap over the 38 queries, 1000 resamples, seed 7; difference vs baseline, 95% CI)

Hybrid (no reranker):

| Model | d Recall@5 | d MRR | d nDCG@5 | queries better / worse (recall) | better / worse (MRR) |
|---|---|---|---|---|---|
| multi-qa-MiniLM-L6-cos-v1 | +0.000 [0.000, 0.000] | -0.020 [-0.079, +0.033] | -0.014 [-0.058, +0.026] | 0 / 0 | 2 / 3 |
| bge-small-en-v1.5 | -0.026 [-0.079, 0.000] | -0.025 [-0.058, 0.000] | -0.025 [-0.056, 0.000] | 0 / 1 | 0 / 3 |
| e5-small-v2 | -0.026 [-0.079, 0.000] | +0.019 [-0.011, +0.055] | +0.008 [-0.027, +0.039] | 0 / 1 | 3 / 1 |
| all-MiniLM-L12-v2 | +0.000 [-0.079, +0.079] | +0.004 [-0.045, +0.056] | +0.003 [-0.044, +0.056] | 1 / 1 | 2 / 2 |
| gte-small | -0.053 [-0.132, 0.000] | -0.027 [-0.063, +0.004] | -0.033 [-0.074, -0.002] | 0 / 2 | 1 / 4 |

Vector only:

| Model | d Recall@5 | d MRR | d nDCG@5 | better / worse (recall) | better / worse (MRR) |
|---|---|---|---|---|---|
| multi-qa-MiniLM-L6-cos-v1 | -0.066 [-0.145, 0.000] | -0.077 [-0.178, +0.013] | -0.074 [-0.171, +0.004] | 0 / 3 | 2 / 6 |
| bge-small-en-v1.5 | -0.026 [-0.145, +0.092] | +0.009 [-0.101, +0.118] | -0.011 [-0.120, +0.105] | 3 / 5 | 3 / 5 |
| e5-small-v2 | +0.053 [-0.079, +0.184] | +0.083 [-0.031, +0.211] | +0.079 [-0.033, +0.200] | 4 / 2 | 6 / 3 |
| all-MiniLM-L12-v2 | -0.026 [-0.132, +0.079] | -0.044 [-0.136, +0.048] | -0.050 [-0.139, +0.049] | 2 / 4 | 2 / 6 |
| gte-small | +0.053 [-0.053, +0.184] | +0.045 [-0.061, +0.147] | +0.049 [-0.059, +0.151] | 4 / 2 | 5 / 4 |

Hybrid + reranker: every difference has a CI that includes 0 (multi-qa and e5 are identical to baseline on every
query; bge -0.026 recall [-0.079, 0.000]; L12 and gte +0.021 MRR [-0.016, +0.079]).

Only one hybrid interval excludes zero (gte-small nDCG, upper bound -0.002), and with ~5 models x 3 modes x 3 metrics
compared and no multiplicity correction that is not evidence of a real difference.

## Per-query findings (full tables in `phase25_C_tables.md`)

- Hybrid: the nine queries where any model differs from the baseline. The baseline's own hybrid misses are
  #1 ("old row versions...", semantic; found only by L12), and the 0.2 MRR on #6 ("callback request ... came from the
  platform"), a query that 4 of 5 alternatives fail completely (bge, e5, L12, gte all drop the gold HMAC chunk from the
  top 5; only multi-qa keeps it). The recall loss of bge / e5 in hybrid is exactly this one query; gte loses #6 and
  #9 (POL-HR-031, an identifier query where the dense side matters little).
- Vector only: no model is uniformly better. e5 and gte-small fix the abbreviation / short-term queries the baseline
  misses ("What is HNSW?", "HNSW", "MTTR" - recall 0 -> 1 for e5, gte and bge), but bge, e5 and gte all lose some
  paraphrase queries ("server prove identity", "callback request", "online shop stopped" for e5) and bge / gte lose
  "probation". L12 (truncated to 128 tokens) is the best on semantic paraphrase (1.00) but worst on short queries.
  multi-qa is strictly worse than baseline in vector mode (never better on recall, worse on 3 queries).
- These gains in vector-only mode are mostly absorbed by the hybrid BM25 leg: the abbreviation, keyword and short
  query kinds all reach 1.00 in hybrid for the baseline, so the places where other models help (acronyms) are
  already covered by BM25, and the only remaining hybrid headroom is the semantic kind (baseline 0.88, 7/8
  queries), where no alternative improves on it except L12 on a single query.
- The reranker narrows everything (0.92-0.95 recall for all six); its effect (+0.04 to +0.09 MRR over hybrid without it) is larger than any
  embedding-model effect.

## Pitfalls checked

- Dimension: all six are 384 and fit the existing column; no schema change needed for any of them.
- Normalisation: raw norms are 1.0 for all six; stored vectors are unit length.
- Prefixes: used as prescribed for bge and e5, documents and queries embedded by the same model; an ablation without
  prefixes is reported above (prefix omission cost little here).
- Truncation: only all-MiniLM-L12-v2 (max_seq 128) truncates (32/744 chunks, 4.3%). This is a configuration trap -
  its quality figures above include that handicap. multi-qa / bge / e5 / gte accept 512 tokens.
- fp16 trap: gte-small's checkpoint is fp16; on CPU it must be loaded as float32 (done), otherwise encoding is
  dramatically slower.

## Migration / re-embedding strategy that would be required to adopt a different model (NOT implemented)

Embeddings from different models live in different vector spaces, so mixing them in one column silently destroys
retrieval (cosine between spaces is meaningless even when both are 384-d). A safe adoption path:

1. Never overwrite existing embeddings. Add a new nullable column (e.g. `embedding_v2 vector(384)`, or a separate
   table `document_chunk_embeddings(chunk_id, model, dim, embedding)`, which also supports other dimensions) plus a
   `embedding_model` identifier per row; keep `embedding` untouched.
2. Dual-write: ingestion computes both embeddings (old and new model) so new uploads are queryable under either.
3. Backfill in batches from the stored `content` (no re-parsing of PDFs needed), idempotently (`WHERE embedding_v2 IS NULL`),
   with the document prefix for models that need one; verify row counts, dimension and unit norm; build the new ANN
   index (HNSW) concurrently only after the backfill.
4. Select the model with the `EMBEDDING_MODEL` (and `EMBEDDING_DIM`, prefix settings) config. The query-side
   embedding, `semantic_search` column / table, and BM25-independent code must all follow the same switch; a
   query model that disagrees with the column's model must fail loudly (check `embedding_model` at startup).
5. `conversation_memories` embeddings use the same model: they must be dual-written and backfilled in the same
   release, and memory recall must use the same model/column as chunk retrieval at all times; otherwise the memory
   query vector and stored memory vectors would live in different spaces.
6. Shadow-evaluate (run old and new retrieval side by side on real queries, compare using this harness plus
   production logs), then flip the config; keep the old column for a rollback window; drop it only after a full
   release cycle. Rollback = flip the config back, no data loss.
7. A model with a different dimension (e.g. bge-base-en-v1.5 / e5-base-v2 / all-mpnet-base-v2 at 768, bge-large at
   1024) additionally requires a new `vector(N)` column or table and a new index; it cannot reuse `vector(384)`,
   and increases storage and query cost roughly linearly with N. Those models were not benchmarked here.

## Limitations

- 38 queries: one query = 2.6 points of recall; most differences between models are 1-3 queries. All hybrid CIs are
  consistent with no difference (and the one interval that barely excludes zero is multiplicity-affected).
- The corpus is synthetic, English, and the 120 filler documents are template text; there is no real domain data,
  OCR noise, tables, other languages, or long chunks. Queries were authored by the same project as the corpus.
- The vector-only gains for e5 / gte / bge on acronym queries are real in this data but are covered by BM25 in the
  hybrid system actually used.
- Gold relevance is span-based and only a single chunk usually qualifies; there are no graded judgements.
- Latency and encode times were measured on a shared, CPU-contended machine (other agents' non-lock jobs
  were running), single run, CPU only; query embedding latency medians of 30 queries are reasonable but not
  precise. The lock fairness only prevented overlap with other lock-using benchmarks.
- Quality figures are from a single deterministic run per model (no run-to-run variance expected beyond float
  noise); the first five models were scored in the first process and gte-small in the second.

## RECOMMENDATION

Keep `all-MiniLM-L6-v2`. No candidate beats it in the production configuration (hybrid + reranker): recall 0.947 vs
0.947 / 0.947 / 0.921 / 0.947 / 0.947 and MRR 0.926 vs 0.926 / 0.921 / 0.926 / 0.947 / 0.947, all within the
bootstrap noise (CIs include 0). In hybrid without the reranker, the baseline has the best recall (0.974, tied with
multi-qa and L12) and the others are lower or within noise on MRR. The models that look better in vector-only mode
(e5-small-v2: +0.053 recall / +0.083 MRR; gte-small +0.053 recall) are not significant even there (CIs include 0) and
the advantage disappears once BM25 is added. The baseline is also the fastest to embed (2.5-3x faster than the
12-layer alternatives) and needs no prefixes, so adopting another model would cost a full re-embedding (see
strategy) and a prefix-handling code path for no measurable gain.

Evidence that would still be needed to change this: (1) a larger, real, in-domain query set (hundreds of queries
from actual user logs with graded relevance) and real documents with OCR noise / tables; (2) a re-run of
semantic-paraphrase queries specifically, where hybrid headroom exists (baseline 0.88 -> ceiling 1.00) and e5 / bge
actually did worse, so the candidate worth re-testing first on real data is e5-small-v2 (best vector-only) with
properly prefixed passages; (3) end-to-end answer quality (Phase 3 answer eval), not only retrieval metrics; (4)
if multilingual or longer-chunk usage is expected, a 768-d / multilingual model (bge-m3, multilingual-e5) would
need to be tested together with the schema migration described above; (5) latency measured on the deployment
hardware without contention.
