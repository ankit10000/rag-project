# Executive Summary — backend development test

Result: **PASS for the six declared questions**, not a full application or formal evaluation acceptance.

Source: the requesting account's latest ready upload, `Executive Summary.pdf`, document `e3160c67-ee6d-4983-9029-8273bd35525a`, 18 pages / 76 chunks. PDF SHA256: `af9b4d20304baeaba3195cf3aed7e1465dd79ae1ad3724a5193994e10dc8df60`.

## Live results

Direct `services.rag_service.ask_question` calls used the real tenant context, cached local embeddings/reranker, and Gemini. No UI was used. Six questions were declared before the live run, with expected source facts. All citation IDs/pages were checked against owned source rows; factual coverage was checked against the PDF. Raw answers, question wording, timing, provider-call counts and hashes are in `after-context-fix-01.json`; expectations are in `after-context-fix-01-plan.json`.

| Question | Verified answer | Source | Result |
|---|---|---|---|
| Product and target exams | AI education portal; JEE/GATE/NEET | p. 1 | PASS |
| Summary development/team/budget estimates | 2–3 years; ~10–15 people; $1M–$5M over two years | pp. 1, 15 | PASS |
| Multilingual and offline/mobile access | Hindi/other regional languages; download videos/notes for offline study; mobile app | p. 2 | PASS |
| All four roadmap phases and ranges | Planning 0–6; MVP 6–15; Pilot 15–21; Launch 21–30 months | p. 15 | PASS |
| Quality and copyright mitigation | Human review/conservative generation/feedback; legal review/open data/rephrasing | p. 16 | PASS |
| Signed customer contract number | Abstained; no invented number or citations | Not established | PASS |

12 provider calls, all requested `gemini-3.5-flash-lite`, within the approved maximum of 24. Total measured case time: 68.67 seconds; individual cases 6.32–16.19 seconds, each below the normal 60-second request budget (harness ceiling 90 seconds). No provider errors or grounding issues occurred. The budget answer also reported personnel/hardware components from p. 15; these are scoped cost components, not interchangeable total-budget estimates. The source itself uses differing roadmap descriptions; the four enumerated phases were checked directly.

## Reproducible defect and fix

Provider-free baseline retrieval kept only chunk 194 for the “all four phases” question. It contains phases 1–2; the best-minus-2 rerank filter removed phase 3–4 chunks on the same page. This establishes missing context, not inability to reason by the LLM. No pre-fix live verdict was invented.

`services/v2_page_context.py` introduces explicit v2 policy `v2-enumeration-page-continuity/1`, called after the existing relevance filter. Enumeration questions can recover bounded neighboring passages from at most two retained anchor pages, only within owned ready documents and the existing eight-chunk / 12,000-character context limits. It preserves original IDs/pages, supplies no fabricated ranking scores, and leaves legacy v1 selection unchanged. The actual source check recovered chunks 195–197 on page 15; the live answer then supplied all four phases with correct citations. This does not guarantee completeness across arbitrary pages or oversized sections.

## Executed checks

Live: `.venv/bin/python -B /private/tmp/rag_exec_backend.py after-context-fix-01` — six cases PASS / 12 calls. The harness required explicit owner scope, refused any database other than `rag_test_scratch`, and verified `current_database()` on every service connection before source reads. No conversation/memory writes were performed.

Offline source retrieval: `.venv/bin/python -B /private/tmp/rag_exec_offline.py` and `.venv/bin/python -B /private/tmp/rag_exec_offline_after.py` — completed; preserved before/after bundles in `offline-baseline.json` and `offline-after-context-fix.json`.

Focused scripts, each executed with `.venv/bin/python -B FILE`:

- `test_v2_page_context.py`: 7 passed.
- `test_v2_routing_recovery.py`: 8 passed.
- `test_v2_qualification_focus.py`: 6 passed.
- `test_v2_tenure_calculation.py`: 11 passed, 1 optional separate DB test skipped.
- `test_assignment_flow.py`: 7 passed.

Additional provider-free regressions used `DATABASE_URL=postgresql:///rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 RAG_V2=0 .venv/bin/python -B FILE`:

- `test_stage8_p3_classification.py`: 20 assertions passed.
- `test_stage6_answer.py`: 66 assertions passed.
- `test_context_and_citations.py`: 62 assertions passed.
- `test_b3_answer_reliability.py`: 35 assertions passed.
- `test_local_v1_retrieval.py`: 13 tests passed.

All ten final script invocations exited 0: 52 unittest tests passed / 1 skipped, plus 183 script assertions passed. Five initial invocations exited 2 because the required scratch environment variable was absent; their logs are preserved, and corrected provider-blocked invocations passed. No test contract was changed to resolve those launch errors.

The local two-worker API was gracefully restarted with the restricted scratch role after a database identity preflight. `/api/v2/health` returned HTTP 200. No additional model requests were made through HTTP or UI.

## Integrity and limits

`git diff --check` passed. All 44 protected assets retain their manifest hashes; staged diff bytes remain unchanged. Among pre-existing files, only the intended insertion in `services/rag_service.py` changed during this task. New source/test/evidence files were added without staging. `rag_db`, frozen evaluations, historical failures, human review records, migrations, quarantine, commits and pushes were untouched.

This verifies the selected document's six development questions and the new context-selection fix. It does not certify all possible questions, HTTP/memory lifecycle behavior, or formal evaluation acceptance. Earlier documented application limitations remain in scope for separate confirmed failures.
