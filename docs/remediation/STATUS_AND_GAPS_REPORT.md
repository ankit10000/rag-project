# Project status through Phase 5 and gap report

Date: 2026-11-11. Sources: the Stage-0 register (`MASTER_GAP_REGISTER.md`, as updated by the implementer), `docs/PROJECT_COMPLETION_AUDIT.md`, the P4-07 verification, and checks run in this session. Labels: VERIFIED = code + an executed test I or the runner observed; REPORTED = claimed by the implementer agent and **not independently re-verified** (the re-audit was stopped before it finished).

## 1. Where the project stands

| Phase | What it is | State now | Change since the audit |
|---|---|---|---|
| 1 Memory integrity & deletion safety | user-only evidence, deletion safety, cleanup | Implemented. Test coverage greatly extended (6 new/rewritten deterministic test files, 500 checks, all REPORTED passing). | P1-04, P1-07, P1-08 moved from "not verified" to REPORTED verified. P1-06 (positional pairing) and P1-09 (34 unsourced legacy memories) deferred to Phase 5 items. |
| 2 Retrieval | ingestion, vector+BM25+RRF+rerank | Implemented, same as audit. | No new work. PDF-ingestion test, sentence-chunking test, malformed-file tests still missing. |
| 2.5 Retrieval evaluation | benchmarks | Results exist; not re-run or re-derived. | No new work. |
| 3 Answer generation | grounded answers, citations | Implemented; 69 + 62 unit tests pass (ran earlier). | No new work. Adversarial-test mapping not done. |
| 3.5 Independent validation | dev/held-out evaluation | Partially complete: dev split only (tier 1 41/47, tier 2 28/42). | No new work. No failure analysis, no review sheet, no human review, no held-out run. |
| 4 Production readiness | logging, pooling, security, backup | Almost all not started. | **Test infrastructure (P4-07) done and verified**: guard, runner, network block, scratch DB. `backups/` now git-ignored. |
| 5 Memory source attribution | provenance links | Implemented and tested on a scratch DB. | Test fixed to be fully mocked. Remaining items are mostly design/approval gates. |

Counts from the register (49 rows; the register text says 47, the actual table has 49): **9 rows done** (P1-01, 02, 03, 04, 05, 07, 08, P1-10, P4-07 — the seven Phase 1 test rows are REPORTED), 2 deferred (P1-06, P1-09), 3 proposed not-applicable (P25-03, P4-10, P5-08), 3 blocked or approval-gated (P35-03, P35-05, P5-01), the rest pending. Excluding the 3 proposed not-applicable rows: 9 / 46 = **19.6 %** done. For comparison, the audit's coarser measure was 77 / 114 = 67.5 % (a different denominator; the two are not comparable).

## 2. Verified facts now (checked in this session)
- Default test run (unit + integration, network blocked, scratch DB `rag_test_scratch`): **18 / 18 passed** per the implementer's final run; the earlier 12 / 12 run of the same infrastructure was observed by me. 2 of the passes are smoke-only (no assertions).
- `rag_db` unchanged: 261 conversations, 1,340 messages, 127 memories, 93 links, 9 chunks (re-queried after all stops). The runner fingerprints it read-only before and after every run.
- Test inventory by category: unit 8, integration 10, live 10, manual 8 (36 scripts, all guarded and registered).
- No application code (`services/`, `main.py`) was changed by P4-07 or Cycle 1 per file-time checks run earlier; the implementer reports the same. The Phase 5 work (earlier turns) did change `services/` as designed.
- Nothing is running now (all background processes and agents stopped).

## 3. Gaps (prioritised)

### P0 — blocks trusting the current state
| # | Gap | Why it matters | Next action |
|---|---|---|---|
| 1 | **Cycle 1 results are not independently re-verified.** The re-audit was stopped. | The register says VERIFIED COMPLETE on the implementer's word for 7 rows. | Re-run the re-audit (or you review `cycle1_06_implementation.md` and `phase1_remediation.md`); then a clean `run_tests.py --clean`. |
| 2 | **7 candidate application defects found, none fixed** (details §4). | Two are user-visible (ordinary programming questions swallowed by the delete detector); one is a safety-relevant fall-through (unknown classifier status can delete). | Your decision per defect; each fix needs a test change and approval. |
| 3 | **Phase 3.5 quality gate not met.** | Only independent-ish evidence shows 87 % / 67 % correctness on the dev split; held-out never run; no human review. | Failure analysis → review sheet → you name a reviewer and approve thresholds → one held-out run. |
| 4 | **Git is in a mixed state and nothing is committed.** 19 staged adds, 1 staged-then-modified, 35 modified, 10 untracked. The pre-Phase-1 backup dump is already committed in HEAD. | Work could be lost; a database dump sits in history. | Approve a commit plan (logical groups, no dumps/secrets). |

### P1 — important for reliability and security (Phase 4)
| # | Gap | Files | Complexity |
|---|---|---|---|
| 5 | No structured logging, correlation IDs, stage timings or redaction (`print` only) | `services/*`, `main.py` | Medium |
| 6 | One DB connection per call (79–124 ms overhead); no pool, no timeouts, no shutdown handling. `psycopg_pool` is not installed (needs your approval; design + benchmark plan first) | `services/database.py` | Medium |
| 7 | PDF input unvalidated (type, size, pages, malformed) | `services/pdf_parser.py`, `ingestion_service.py` | Low |
| 8 | Backup restore never tested; the two dumps have never been restored into a scratch DB | docs, scratch DB | Low |
| 9 | No config/env validation at startup; no `--check` health command | `services/`, `main.py` | Low |
| 10 | No timeouts on LLM/DB/file operations beyond Gemini retry | `llm_service.py`, `gemini_retry_service.py` | Medium |
| 11 | No performance, memory or concurrency measurements | `eval/` | Medium |

### P1 — test coverage for earlier phases
| # | Gap | Register row |
|---|---|---|
| 12 | No end-to-end PDF ingestion test, no sentence-chunking tests, no malformed/empty document tests | P2-01..03 |
| 13 | Per-stage metadata-filter tests, BM25 cache invalidation, reranker-failure isolation, empty retrieval, RRF determinism, default-pinning test | P2-04..06 |
| 14 | Phase 2.5 benchmarks not re-run with seeds; metrics not re-derived from raw files; memory use not measured; synthetic vs real corpus not separated (real DB has 9 chunks) | P25-01..05 |
| 15 | Adversarial answer tests not mapped against the required list (fake page/filename, injection in history, malformed LLM, retry exhaustion, quota failure) | P3-01, P3-02 |

### Phase 5 remaining
| # | Gap | Status |
|---|---|---|
| 16 | Silent "last user message" fallback source can over-attribute provenance (`memory_service.py` ~l.290–312) | approved in principle; not implemented |
| 17 | 34 legacy memories with no source; 4 legacy links to assistant messages | approved for investigation and scratch-DB design only; migration 004 needs your review before touching `rag_db` |
| 18 | Live Gemini multi-source extraction never observed | BLOCKED until you confirm quota (use scratch DB) |
| 19 | Shared-source deletion hides context for sibling memories; positional user→assistant pairing; orphan lifecycle for deleted messages | propose designs first |
| 20 | `migrations/README.md` does not list migration 003 | docs, Low |
| 21 | `memory_revisions` | deferred (not needed now) |

### Housekeeping
- Scratch databases present (not dropped without approval): `rag_phase2_eval`, `_test`, `_emb`, `_scale`, `rag_phase35_eval`, `rag_phase5_mig`, `rag_phase5_test`, `rag_test_scratch`.
- `eval/` scripts still do not use the connection guard (name allow-list added to `eval/harness.py`).
- Smoke-only tests (`test_similarity.py`, `test_memory_storage.py`) assert nothing.
- Live/manual legacy scripts are guarded but unconverted; four of them hard-code conversation ids and stay manual.
- Stale `docs/phase2_report.md` "Not done" list.

## 4. Candidate application defects (found by Cycle 1 tests; REPORTED, not fixed)
1. Delete detector flags non-memory requests: "How do I clear memory in Python?", "remove the memory leak", "delete memory from the cache", "Don't save it as a PDF", "Forget all the tests I wrote". In `main.py` these skip document search, reply "I couldn't find any memories that clearly match…", and are saved as messages.
2. Detector raises on non-string input; `"delete " * 20000` takes ~28 s (quadratic backtracking).
3. `decide_memory_action`: `generate_answer` returning `None` raises `TypeError`; an exception from `generate_answer` propagates.
4. `decide_memories_to_delete`: an exception from `generate_answer` propagates; `[true]` → id 1, `[2.7]` → id 2.
5. `delete_matching_memories` deletes when the classifier status is unknown (e.g. "MAYBE") and the id is valid (latent: the real classifier maps unknown to UNCERTAIN).
6. `delete_memory("abc")` raises a raw database error.
7. In `main.py`, cleanup runs whenever `deleted_count > 0` regardless of status (latent).
Verified no orphan `memory_sources` rows after memory delete (REPORTED).

## 5. Decisions I need from you
1. Re-run the independent re-audit of Cycle 1? (recommended)
2. Which candidate defects (§4) to fix — I suggest #1, #5, #3/#4 first, each with a test change.
3. Commit plan: OK to prepare it (nothing committed until you approve)?
4. Next stage: Phase 2 test gaps (P2-01..06), or Phase 3.5 failure analysis + review sheet first?
5. Is Gemini quota available for the live Phase 5 check (P5-01)?
6. Phase 3.5: who will be the human reviewer, and what thresholds?
