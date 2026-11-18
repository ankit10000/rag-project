# Tier 2 scorer v2.1 development reconstruction validation

Date: 2026-11-18. Dataset revision: `c1bbcae9a21e389c16c3f1587de5acc1b5209e37`. **Engineering validation reproduced; acceptance remains ineligible.** No defaults, policy tables, frozen datasets, annotations, manifest or historical results were changed.

## Artifact scope and identities

The handoff names seven files with `(1)` suffixes, but those physical attachments were not present in the available attachments directory. This work independently checked the repository-retained final counterparts under `docs/remediation/phase_e2_engineering/wp8_evidence/flip_inputs/final/`. Their metadata matches the handoff's revision, annotation identity and reported results. This establishes reproduction of those retained counterparts; it does not establish byte identity to unavailable external attachments.

| Retained input | Raw SHA-256 |
|---|---|
| `literal-annotations.c1bbcae.json` | `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a` |
| `tier2_dev.v2.jsonl` | `fe875b55933b0a98292d247a11ef2d9737e792fee3aea01a6985a543808f2443` |
| `tier2_dev.v2.jsonl.scoring.json` | `86ac6fd3e03c04d7328502c6da62dd73a78f4ce10a595a9bfe77b0b90daa8ce3` |
| `tier2_dev.v2.diff.md` | `d974eaff8b76c9a127318982325d5937968c3ae93a3a760a6f95468b023cd38a` |

The retained sidecar records scorer identity `af81bae9df469cd880c8fec8a970a95bf5e0b275679111b783ee867d4e813a2c`, scorer/tables version `2.1.0`, Python `3.14.5`, Unicode `16.0.0`, PyMuPDF binding `2.0` and MuPDF `1.28.5`. That is the historical comparison identity, not a claim that later audit fixes retain the same source hash. The lead's package-level hash report distinguishes original identity from any subsequently changed implementation. Scoring behavior in this suite reproduced the retained v2 signal dictionaries for all 42 rows.

## Configuration: supported defaults versus unproven runtime settings

| Item | Independently verified evidence | Remaining limit |
|---|---|---|
| Size 100, overlap 20, `words` strategy | The actual `services/retrieval_config.py` source at the pinned revision sets those defaults. AST checks inspect the literal defaults without importing the configuration module. | The same module calls `load_dotenv()` and reads environment overrides. No original resolved-config header proves what values were active during evaluation. The current `.env` is neither read nor treated as historical evidence. |
| Minimum 10 page words | The pinned `ingest_pdf` inline chunk stage explicitly skips pages with fewer than 10 words. Synthetic tests prove the 9/10 boundary. | No actual pinned page falls below 10 words, so the corpus result alone cannot validate this branch. |
| Extractor | Pinned `extract_text` calls `page.get_text(sort=True)`, preserves page numbers, skips blank text and applies the page-count limit. | Interpreter/PyMuPDF behavior is environment-sensitive; original rendered PDFs and extracted chunk text were not hashed at runtime. |
| Rendering | Pinned `build_scratch_corpus` iterates documents/pages in their dataset order, inserts text with `Rect(36,36,559,806)`, font size 9, and restarts table identities before ingestion. Reconstruction renders/extracts in memory using the same parameters. | This is a reproduction of the documented synthetic corpus generation, not a production PDF/configuration attestation. |
| Chunking and deduplication | The pinned pure `services/chunker.py` is byte-equivalent under portable hashing to the current pure chunker. The historical ingestion AST uses SHA-1 of whitespace-collapsed lowercase chunk text, with a fresh seen set per document. | Current `build_chunks` is a later refactor; its current AST hash must not be presented as a hash of a historical helper that did not yet exist. |
| Chunk ID order | Pinned insertion loops follow document, page and chunk order after `TRUNCATE ... RESTART IDENTITY`. The reconstruction uses sequential global IDs and reproduces all recorded references. | Original database rows were not queried. No database or provider operation was needed or performed. |

The sidecar correctly retains `chunk_config_source="assumed_default"`. Its `assumption_checked=false` lives in `context_config.tier1`; it is not a Tier 2 runtime attestation. Matching pinned source defaults supports the assumption, but does not justify changing it to `run_header` or claiming authoritative historical/production configuration.

Portable SHA-256 of source files **at the actual historical pin**:

| Pinned source | SHA-256 |
|---|---|
| `services/retrieval_config.py` | `58164b6068cd97acfa4183c71b268d996c393b879dbe3ad37649f0f402e2f9c1` |
| `services/ingestion_service.py` | `8c3b359356a303b46fc2c6a8c92d710bf666892b7e1b5954b8acb9bd36c71aa4` |
| `services/pdf_parser.py` | `a26738837040a0b1d43f9368a274ba1e9a4267835d777a82342d29742cee981f` |
| `services/chunker.py` | `0a002515c7a2fa624d46c2d0375f6fbceac682fab001272a2091d4da481b3554` |
| `eval/phase35/run_eval.py` | `3b066a5b3b4c1de908cb5a555db17762af2bd70606f0854d5f2ba0ce7106e989` |

## Independent reconstruction result

New focused test: `test_tier2_v21_reconstruction_validation.py`.

The test does not import or execute the ingestion service. It extracts only the inline page-filter/chunk/dedup AST from historical `ingest_pdf`, stopping before embedding generation or storage, and supplies extracted text and explicit settings. It executes the historical pure chunker, which imports only `re`. The resulting ordered chunk dictionaries are compared byte-for-byte with the existing reconstruction table.

| Check | Result |
|---|---:|
| Documents / rendered pages | 12 / 56 |
| Pages below the 10-word filter | 0 |
| Raw chunks / retained chunks | 135 / 135 |
| Chunks removed by actual-corpus deduplication | 0; document-scoped dedup independently tested with synthetic duplicates |
| Independent historical inline chunk stage versus reconstructed table | All 135 records equal, including text, IDs, document/page and text hashes |
| Chunk-table SHA-256, recorded and reproduced | `29643967a4e3b0e453efa8f44c34cddf7528b4edf3da977140008a2e199b914a` |
| Development rows / exact reconstructed contexts | 42 / 42 |
| Distinct retrieved/cited references verified | 58 / 58 |
| Per-row reconstructed context hashes and per-used-chunk hashes | 42/42 equal to retained sidecar |
| v1 scoring signals versus original stored v1 signals | 42/42 equal; zero drift |
| v2 complete scoring dictionaries versus retained v2 results | 42/42 equal |
| Error / mismatch / fallback rows | 0 / 0 / 0 |
| Correctness changes | One: `B-conf-04`, false to true |

Using 120-word chunks instead of 100 causes reference mismatches; a wrong declared table hash produces `mismatch:chunk_table_sha256` with unavailable context. These are negative regression checks, not proposed new defaults.

## `B-conf-04`: separate Tier 2 evidence

The exact Tier 2 answer is:

> The tile monitoring ran for 14 months [S1] (though another section mentions 15 months of monitoring) [S2].

Its retrieval order is chunk **48**, `calder_sound_tile_study_TR-2026-07.pdf`, page **1**, then chunk **55** of the same document, page **4**. Both are cited. Its reconstructed context SHA-256 is `f7a823a4694606bfe8dbf08df2f90c1e6458a82692cdefd4322b30287ef09e26`. Tier 1 has different context and answer wording and is not substituted for this evidence.

Both gold groups (`14 months`, `15 months`) match without negation; recall is 1. Citation correctness/completeness are 1, no numeric token is ungrounded, and there are no forbidden hits. V1's fixed disagreement phrases omit the connective `though`, so `conflict_ok=false` and `correct=false`. WP5 §11 explicitly includes `though` in `CONN`, and both groups occur in the same sentence. V2 records `groups=[0,1]`, `sentence_index=0`, `list_scope=false`, `lexicon=[]`; `conflict_ok=true` and `correct=true` follow the closed rule.

Mechanically this is a justified rule difference. Whether the qualified answer adequately reports the source disagreement is an independent human correctness judgment; the test does not approve a golden list or alter the dataset/conflict policy.

## Reproducibility limits and future use

The 42 exact results prove consistency with this deterministic reconstruction and the retained comparison artifacts. They do not prove the original environment overrides, original extracted text or exact original model prompt. The historical Tier 2 scorer fetched full chunk content from a database query without an explicit order; current reconstruction deterministically joins retrieved-rank chunks. Numeric grounding is order-insensitive, so zero v1 drift alone cannot attest to historical context byte order. Likewise, full chunk text used for scoring differs conceptually from any truncated prompt context produced by context assembly.

For future independently reproducible runs, capture the resolved chunk configuration and environment/model versions, document/source identities, ordered chunk table and text hashes, exact scoring-context hash, and the separately identified prompt context/hash at runtime. Bind them to the run header and dataset/manifest/scorer identity. Existing WP7 capture/preparation components support this direction; installing them in frozen live paths remains owner-controlled. Historical operator pinning remains non-acceptance evidence.

Validation command:

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
.venv/bin/python -B -m unittest test_tier2_v21_reconstruction_validation
```

**7 tests passed, exit 0** (0.859 seconds in the focused validation). A supplementary local evidence JSON is `/private/tmp/tier2-v21-reconstruction-evidence.json`; the tests recreate evidence and do not depend on that temporary file. No held-out case was scored. Loading the four pinned data modules supplies the shared synthetic document corpus and annotations validation context; only the 42 existing development result rows were evaluated. No API, embedding, ingestion, database, migration, production-memory operation, staging, commit or push was performed.
