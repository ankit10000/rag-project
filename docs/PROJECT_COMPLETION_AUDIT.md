# Project completion audit (read-only)

Scope: whole repository, Phases 1–5. Nothing in the application, config, dependencies, databases, scratch databases or data was changed by this audit; the only file created is this report. Secrets and `.env` contents are not reproduced.

## 0. How to read this report

- **Executed in this audit:** read-only file inspection, `psql` SELECT/`\dt`/`\di` queries on `rag_db`, a local re-computation of correctness counts from `eval/phase35/results/tier*_dev.jsonl`. **No test script was re-run for the audit**, because the test scripts write to a database (rule 10: do not modify databases, even scratch ones).
- **Executed earlier in this working session (before the audit), on scratch DB `rag_phase5_test`:** the test results quoted as "ran earlier". They were observed by the assistant in this conversation but are not re-verified here.
- **Documented only:** anything taken from `docs/*.md` or `eval/results/*` that I did not re-derive. Marked "documented".
- Labels: `VERIFIED COMPLETE`, `IMPLEMENTED, NOT VERIFIED`, `PARTIALLY COMPLETE`, `NOT STARTED`, `NOT VERIFIED`.
- "Verified" in the percentages = code exists **and** a test or saved result for it was actually executed/observed. It does not mean production-ready.

## 1. Dashboard

| Phase | Status | Verified / total requirements | % (numerator/denominator) | Main gap |
|---|---|---|---|---|
| 1 Memory integrity & deletion safety | VERIFIED COMPLETE (2 items not re-run) | 14 / 16 | 87.5 % | deletion-detector and memory-classifier tests are live-LLM and were not run; no Phase 1 report in `docs/` |
| 2 Retrieval pipeline | VERIFIED COMPLETE (2 items unverified) | 15 / 17 | 88.2 % | no repo test for the PDF-ingestion path or the chunker's sentence mode |
| 2.5 Retrieval evaluation | VERIFIED COMPLETE (existence-level) | 11 / 13 | 84.6 % | filtered-ANN test and memory measurement not found/verified; numbers not re-derived |
| 3 Answer generation | VERIFIED COMPLETE (structure) | 15 / 16 | 93.8 % | "genuinely grounded" is only checked structurally and on self-authored cases; see Phase 3.5 |
| 3.5 Independent validation | PARTIALLY COMPLETE | 7 / 12 | 58.3 % | no human review, held-out split never run, no final report |
| 4 Production readiness | NOT STARTED (a few incidental pieces) | 3 / 27 | 11.1 % | no logging, pooling, timeouts, health checks, shutdown handling, restore test |
| 5 Memory source attribution | VERIFIED COMPLETE for the deterministic layer | 12 / 13 | 92.3 % | live-LLM multi-id extraction not observed; 0 multi-source memories exist in `rag_db` yet |

**Overall:** pooled 77 / 114 requirements = **67.5 %** (every requirement counts equally, so the large Phase 4 list pulls the figure down). The unweighted mean of the seven phase percentages is 73.7 %. Neither number is a measure of production readiness (see §4).

Requirement lists used for the denominators are in Appendix A.

## 2. Phase-by-phase findings

### Phase 1 — Memory integrity & deletion safety
| Item | Evidence | Test | Status |
|---|---|---|---|
| Extraction sees only user messages; assistant text never a source | `services/memory_service.py::extract_memories` (filters `role == "user"`), `_parse_json_memories` keeps only batch user ids | `test_extraction_and_summary_guards.py` – ran earlier, ALL PASSED | VERIFIED |
| Automatic extraction cannot delete | `automatic_memory_service.process_memory` blocks `DELETE` unless `allow_delete`/`delete_only` | `test_deletion_scenarios.py` – ran earlier, 0 failures | VERIFIED |
| Ownership validation | `memory_storage_service.delete_memory` re-checks conversation; `delete_matching_memories` filters ids against the conversation's own memories | `test_memory_sources_regression.py` – ran earlier, ALL PASSED | VERIFIED |
| Conversation exclusion, paired assistant reply | `conversation_service.mark_messages_excluded`, `get_paired_assistant_ids` (positional: next message id) | `test_deletion_cleanup.py`, `test_phase5_provenance.py` – ran earlier, passed | VERIFIED (positional pairing is a heuristic) |
| Summary rewrite + semantic verification | `memory_cleanup_service.rewrite_summary_without`, `apply_deletion_cleanup` | `test_extraction_and_summary_guards.py`, `test_deleted_facts_regression.py` – ran earlier, passed (LLM mocked in guards) | VERIFIED |
| Explicit deletion detection | `services/memory_delete_service.py` | `test_memory_delete_detector.py`, `..._classifier.py`, `..._decision.py` exist; **not run** (live Gemini / quota) | IMPLEMENTED, NOT VERIFIED |
| Memory classification / decision | `services/memory_decision_service.py` | `test_memory_decision.py`, `test_memory_conflicts.py` exist; **not run** | IMPLEMENTED, NOT VERIFIED |
| Legacy memories | `rag_db`: 34 memories have no source and no links (query run in this audit); 4 links point at assistant messages (legacy, `NOT VALID` check) | covered by Phase 5 tests | HANDLED, NOT REPAIRABLE |

Normalized `memory_sources` provenance: **implemented** (Phase 5), see below.
Risk: the older tests `test_automatic_memory.py`, `test_duplicate_memory.py`, `test_memory_search.py`, `test_memory_update.py` contain hard-coded conversation UUIDs; they should not be run as-is.

### Phase 2 — Retrieval pipeline
- Config: `services/retrieval_config.py` — defaults read in this audit: `VECTOR_TOP_K=10`, `BM25_TOP_K=10`, `RRF_K=60`, `RRF_TOP_K=10`, `RERANK_ENABLED=True`, `RERANK_TOP_K=10`, `FINAL_TOP_K=5`, `RERANK_SCORE_MARGIN=2.0`, `RERANK_MIN_SCORE` off, `SIMILARITY_THRESHOLD` off, `BM25_BACKEND=memory`, `EMBEDDING_DIM=384`, `CHUNK_SIZE=100/OVERLAP=20`, strategy `words`. These match the defaults the Phase 2.5 report says were kept.
- Modules present: `ingestion_service.py` (dimension guard at l.71, `ON CONFLICT` duplicate prevention at l.95), `chunker.py`, `embedding_service.py`, `search_service.py` (pgvector, `build_scope_filter` for document/page), `bm25_service.py`, `fts_service.py`, `rrf_service.py`, `reranker_service.py` (lazy model load), `hybrid_search_service.py` (`hybrid_search_detailed` timings).
- Test: `test_retrieval_phase2.py` — ran earlier, ALL PHASE 2 RETRIEVAL TESTS PASSED.
- Database reality: `rag_db.document_chunks` holds **9 chunks** (one sample PDF in `data/documents`). The chunk table has only a primary key and a unique key; **no vector index** (consistent with the Phase 2.5 recommendation for small corpora).
- Not verified: end-to-end PDF → chunks → rows has no repo test; the BM25 index is in memory and rebuilt after any insert (documented bottleneck at scale).

### Phase 2.5 — Retrieval evaluation
- Scripts: `eval/run_benchmark.py`, `eval/phase25_ab.py`, `eval/scale_benchmark.py`, `eval/embedding_benchmark.py`, `eval/embedding_audit.py`, `eval/harness.py`, `eval/corpus.py`. Saved results exist in `eval/results/` (`phase25_AD_E.md`, `phase25_B_scale.md`, `phase25_C_embeddings.md/json`, seeds 7 and 99 logs, `phase25_lost_seed*.json`).
- Combined conclusions: `docs/phase25_report.md`. The report states no default changed; this audit confirms the defaults in `retrieval_config.py` are the ones it names (`RRF_K=60`, `RERANK_TOP_K=10`, `BM25_DROP_STOPWORDS=False`).
- Not verified: I did not re-derive Recall@K/MRR/nDCG figures from the raw JSON; I did not find a separate "filtered ANN" result or a memory-consumption measurement (latency yes, memory NOT VERIFIED). The benchmark corpus is 24 real + 720 filler chunks and 38 queries, so conclusions are limited to that size (documented caveat).
- Documentation inconsistency: `docs/phase2_report.md` still lists the scale/index/embedding benchmarks under "Not done"; they were done later in Phase 2.5. Its metric table is pre-IDF-fix (Phase 2.5 says it reproduced to 3 decimals).

### Phase 3 — Answer generation
- Modules: `context_assembly_service.py` (dedupe, char/chunk budgets, `[S#]` refs), `answer_prompt.py` (grounded prompt, explicit prompt-injection rule at l.78), `answer_service.py`, `citation_service.py` (parse/validate, fabricated citation handling), `rag_service.py`, `llm_service.py` + `gemini_retry_service.py` (retry, quota delay, model fallback).
- Tests (ran earlier): `test_answer_phase3.py` 69/69, `test_context_and_citations.py` 62/62, `test_answer_scoring.py` passed.
- Saved evaluation: `eval/results/answer_eval_new.md` shows 1.000 on every metric over the 33 hand-written cases in `eval/answer_cases.py`. **These cases were written by the same developer/assistant that built and tuned the pipeline; treat them as a regression set, not as quality evidence.**
- Groundedness is enforced structurally (citations must reference supplied chunks; uncited factual claims trigger retry/abstention). Whether answers are *semantically* supported is only measured by the automated scorers.

### Phase 3.5 — Independent answer-quality validation — PARTIALLY COMPLETE
Found:
- 160 authored cases (`eval/phase35/data_A..D.py`, 40 each), validator `validate.py`, runner `run_eval.py` (hash-based dev/held-out split, 30 % dev), scorer/summary `summarize.py`.
- **Dev split run only.** `eval/phase35/results/tier1_dev.jsonl` (47 cases) and `tier2_dev.jsonl` (42 cases) exist. No held-out file, no `REPORT.md`, no `review_sheet.csv`, no `docs/phase35_report.md`.
- Dev results computed in this audit from the saved JSONL (automated scorer's `score.correct`): **tier 1: 41/47 correct (87.2 %)**, median latency 2.12 s, 73,040 prompt tokens in total; **tier 2: 28/42 correct (66.7 %)**, median latency 3.92 s, 44,751 prompt tokens (tier 2 records retrieval fields, i.e. it appears to run the retrieval pipeline; tier 1 supplies chunks from the case data — inferred from `run_eval.py::tier1_context`, not exhaustively checked).
- These figures are well below the 100 % on the hand-written set and are the first independent-ish signal that Phase 3 quality is not yet established. Failures were not analysed in this audit.
- Requirement not met: ground truth is **author-written, not human-reviewed**; "unseen documents" are synthetic documents written by the assistant's helpers; the held-out set has never been run. `services/llm_service.py` gained a passive `usage_log` for token counting (a code change in an earlier step; no behavioural change intended).
- Do not count the 33 hand-written cases as independent validation: they are not.

### Phase 4 — Production readiness — NOT STARTED
Searched `services/` and `main.py` for logging, correlation ids, health checks, pools, signal handling, timeouts:
- No `logging` usage (only `print`), no correlation ids, no health endpoint, no graceful-shutdown handling, no connection pool. `services/database.py::get_connection` opens a **new connection per call** (32 call sites; documented cost 79–124 ms vs <0.3 ms reused). Awaiting approval, not implemented.
- No explicit timeouts on database or PDF operations; the only timeout/retry logic is Gemini quota/backoff in `gemini_retry_service.py` (test `test_model_fallback.py` exists, not run).
- The embedding model is loaded at import time (`embedding_service.py`), the reranker lazily; no memory/concurrency testing exists.
- Application is an interactive CLI (`main.py`, `input()` loop); there is no server, so deployment, health checks and concurrency are currently not applicable until a service layer exists.
- Incidental positives (the 3 verified items): parameterized SQL (a grep for f-string/format SQL in `services/*.py` returned nothing — static heuristic only), migration safety (idempotent `.sql` files with down scripts, rehearsed on a copy and applied after a backup), retrieval benchmarks.
- `.env` is git-ignored. Dependencies: `requirements.txt` exists; compatibility with Python 3.14 is only evidenced by the code running.
- Backups: two manual `pg_dump` files in `backups/` (pre-Phase 1, pre-Phase 5). **Restore of those dumps was never tested** (NOT VERIFIED). `backups/` is not git-ignored (the Phase 5 dump shows as untracked).
- PDF ingestion security: `pdf_parser.py` uses `pymupdf` directly with no size/page/type limits and `ingest_pdf` takes a path; nothing validates untrusted PDFs.

### Phase 5 — Deterministic memory source attribution
| Requirement | Evidence | Verified |
|---|---|---|
| `memory_sources` exists with FKs | `rag_db` (queried): constraints `memory_sources_memory_fk` (composite → `conversation_memories(conversation_id,id)`, cascade), `memory_sources_message_fk` (composite incl. role → `messages`, deferred), PK `(memory_id, source_message_id)`, checks `link_kind_ck` (valid) and `user_source_ck` (**not validated**, by design for 4 legacy rows), index `memory_sources_message_idx` | yes (schema read in audit) |
| Duplicate links prevented | PK + `ON CONFLICT DO NOTHING` | test ran earlier |
| Ownership validated | composite keys; `_validate_source_messages` | test ran earlier (assistant, foreign-conversation, unknown ids rejected) |
| Legacy backfill safe | migration 002 + 003; `rag_db`: 93 links, 0 memories whose legacy column lacks a link, 34 unsourced memories untouched | audit queries |
| New creation records every contributor | `save_memory(source_message_ids=…)`, `extract_memories` list parsing | **mocked LLM only**; real Gemini output not observed; `rag_db` has 0 multi-source memories |
| Update preserves old links | `update_memory` appends `update` links | test ran earlier |
| Multiple messages per memory | PK allows it | test ran earlier |
| Transactional | single connection block, validate-then-write | test ran earlier (nothing written on a bad id) |
| Deletion uses provenance | `get_memory_details` (links ∪ legacy column) → `apply_deletion_cleanup`; echo scan only as extra | test ran earlier |
| Cross-conversation cleanup | composite keys; conversation delete cascade | test ran earlier |
| Invalid legacy sources | tolerated, labelled `legacy` | audit query: 4 assistant links |
| Regression tests exist | `test_phase5_provenance.py` (25 checks, refuses to run unless DB name is `rag_phase5_test`), `test_memory_sources_regression.py` | ran earlier, all passed |
| Docs | `docs/phase5_*.md` | `migrations/README.md` was **not** updated for 003 (documentation gap) |

Design / implemented / tested / verified: designed ✔, implemented ✔, tested on scratch DB ✔, verified on live data and live LLM ✘.

## 3. Codebase-wide technical audit

- **Architecture:** `main.py` (CLI) → `services/*`. Service boundaries are reasonable; memory code is split across `memory_service`, `memory_storage_service`, `automatic_memory_service`, `memory_cleanup_service`, `memory_provenance_service`. No circular imports were observed at import time in the test runs. Possibly unused/stray: `add_memory.py` (root script), `search_service`/`rag_service` overlap not checked, table `vector_test` (2 rows) in `rag_db`.
- **Database:** tables `conversations`, `messages`, `conversation_memories`, `memory_sources`, `document_chunks`, `vector_test`. `rag_db` content: 261 conversations, 1,340 messages (many are leftovers from older test runs — test hygiene issue), 127 memories, 93 links, 9 chunks. Migrations 001–003 (+ down for 002, 003); README lists only 001–002.
- **Security:** parameterized queries; `.env` ignored; prompt-injection rule in the answer prompt and covered in test cases; no auth/authorization layer (single-user CLI; conversation ownership is a data-integrity check, not access control); logs are `print` and can include memory text and prompts; PDF input unvalidated.
- **Reliability:** Gemini retry/fallback exists; no timeouts elsewhere; no idempotent job layer; memory writes are transactional; no concurrency tests; no shutdown handling.
- **Performance:** documented only (Phase 2.5): rerank pool 10 ≈ 300+ ms on CPU, BM25 in-memory 156 ms at 3k chunks, new connection per query 79–124 ms. Dev eval latency from this audit: median 2.1 s (tier 1), 3.9 s (tier 2). Not measured: memory use, concurrent requests.
- **Testing:** 35 root-level `test_*.py` scripts, no pytest/CI/runner, no coverage figures (none invented). At least 14 scripts touch the database; most create their own conversations but write to whatever `DATABASE_URL` points at (i.e. `rag_db` by default) — `test_phase5_provenance.py` is the only one with a database-name guard. 4 scripts use hard-coded conversation ids. Several tests need live Gemini.
- **Source control:** `git status` shows modified `services/{automatic_memory,llm,memory,memory_storage}_service.py` and untracked Phase 3.5/5 files, migrations 003, docs and a dump. Only part of the work is committed.

## 4. Production-readiness assessment

| Area | Status | Evidence | Blocking issues | Next action |
|---|---|---|---|---|
| Core functionality | PARTIALLY COMPLETE | CLI works through all phases; tests above | CLI only | decide target interface |
| Retrieval quality | IMPLEMENTED, evidence limited | 38-query/744-chunk benchmark; real DB has 9 chunks | evaluated on a small synthetic corpus | re-benchmark on real documents |
| Answer quality | NOT VERIFIED independently | 100 % on own cases; 87 % / 67 % on dev split of new set | held-out not run, no human review, tier-2 failures unanalysed | finish Phase 3.5 |
| Memory safety | VERIFIED (scratch DB + mocks) | Phases 1 and 5 tests | 34 unsourced legacy memories; live-LLM paths unobserved | one controlled live run |
| Security | NOT STARTED as a review | see §3 | no PDF/input limits, no auth, `print` logging | Phase 4 security pass |
| Database reliability | PARTIAL | constraints good; per-call connections | no pooling, no timeouts | connection reuse |
| Observability | NOT STARTED | no logging/ids/health | — | structured logging |
| Performance | PARTIAL | benchmarks only | no load/concurrency/memory data | profile |
| Testing | PARTIAL | many scripts pass | no runner/CI; tests can write to `rag_db` | test runner + DB guard |
| Deployment | NOT STARTED | no service/container/config validation | — | only after a service layer exists |
| Backup & recovery | PARTIAL | manual dumps exist | restore never tested | restore drill |

**Can this project safely be used in production today? — ONLY FOR CONTROLLED TESTING.** Memory deletion safety and provenance are strong and tested, and retrieval/answer pipelines work on the sample data. But answer quality has not been validated independently (the only independent-style run scores 87 % and 67 % on its dev split), Phase 4 has effectively not been started (no logging, timeouts, pooling, health checks, restore test), and inputs such as PDFs are unvalidated.

## 5. Remaining work

### P0 — blockers
1. **Finish Phase 3.5.** Why: answer quality unproven; tier 2 only 66.7 % on dev. Files: `eval/phase35/*`. Do: analyse the dev failures (scorer vs. real defects), get a human to review the review sheet, then run the held-out split once and write the report. Dependency: human reviewer. Complexity: Medium.
2. **Test isolation.** Why: tests default to `rag_db` (261 leftover conversations). Files: `test_*.py`, `services/database.py`. Do: add the same DB-name guard as `test_phase5_provenance.py` to every DB-touching test, one runner script. Complexity: Low.
3. **Structured logging + timeouts.** Why: no diagnosability, hangs possible. Files: `services/*`, `main.py`. Do: stdlib `logging`, request id, timeouts on DB/LLM. Complexity: Medium.
4. **Connection reuse/pool.** Why: 79–124 ms per query overhead, no limits. File: `services/database.py` (needs your approval). Complexity: Low–Medium.
5. **PDF/input validation.** Why: untrusted file parsing. Files: `services/pdf_parser.py`, `ingestion_service.py`. Do: size/page/type limits. Complexity: Low.
6. **Backup restore drill and backup hygiene.** Why: dumps never restored; `backups/` not ignored. Complexity: Low.
7. **Commit the work.** Why: Phase 3.5 and 5 work is uncommitted. Complexity: Low.

### P1 — important
- Observe one live extraction with Gemini returning `source_message_ids` and check links in a scratch DB (Phase 5 live gap). Low.
- Update `migrations/README.md` (003), `docs/phase2_report.md` "Not done" section; write a Phase 1 report. Low.
- Re-run retrieval benchmarks on real documents; analyse `RERANK_TOP_K=5` candidate. Medium.
- Reduce reliance on the echo scan for the 34 unsourced legacy memories (manual review list). Medium.
- Auth/authorization model if it ever becomes multi-user. High.

### P2 — later
- HNSW index and BM25 backend change above ~20–50k chunks. Medium.
- `memory_revisions` for update history; messages-pairing beyond positional; remove `vector_test` table and stray root scripts (needs approval). Low–Medium.
- Replace standalone test scripts with pytest. Medium.

## Appendix A — requirement lists behind the percentages

- **Phase 1 (16):** extraction/storage, user-only evidence, assistant exclusion, automatic-extraction restriction, deletion detection (✘), ownership, conversation exclusion, paired assistant handling, summary rewrite, semantic verification, classification (✘), source attribution, multi-source, legacy handling, deletion safety, regression tests.
- **Phase 2 (17):** ingestion (✘ end-to-end), chunking (✘ no test of sentence mode), embeddings, pgvector search, BM25, hybrid, RRF, reranker, metadata filters, document/page filters, BM25 cache, FTS alternative, dedup, dimension validation, central config, ingestion duplicate prevention, timing diagnostics.
- **Phase 2.5 (13):** datasets/scripts, A–E coverage, metrics, rerank pool, RRF configs, BM25 vs FTS, embedding models, scaling, vector indexes, filtered ANN (✘), latency+memory (✘ memory), conclusions backed by saved results, defaults unchanged.
- **Phase 3 (16):** context assembly, dedup, budget, source refs, prompt, generation, citation parsing, validation, invalid-citation handling, retry, fallback/abstention, history, injection protection, output structure, eval scripts/results, groundedness (✘ independent).
- **Phase 3.5 (12):** dataset ≥150 ✔, correctness ✔ (dev), unsupported-claim ✔, citation correctness ✔, completeness ✔, abstention ✔, latency ✔; ✘ independent questions confirmed, ✘ unseen documents confirmed, ✘ human-reviewed answers, ✘ held-out run, ✘ reproducible final results.
- **Phase 4 (27):** only migration safety, SQL safety, performance benchmarks counted.
- **Phase 5 (13):** all but "creation with live LLM" counted.
