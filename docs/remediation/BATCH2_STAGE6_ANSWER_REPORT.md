# Batch 2, Stage 6: Answer Generation & Grounding

**Date:** 2026-11-16. **Scope:** answer generation and grounding only.
**Not done:**
- No retrieval, ingestion, memory, schema, provider or embedding-model change.
- No held-out evaluation and no live LLM evaluation.
- Nothing committed or pushed.
- Stage 7 not started.

## A. Baseline

### Git and environment

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD | `09e6007` "Add Stage 5 retrieval tests and enhance retrieval pipeline error handling"; this is the Stage 5 implementation |
| Remote | `main` = `origin/main` = `09e6007` |
| Worktree at start | Only the expected H.1 artifacts (`BATCH2_STAGE5_RETRIEVAL_REPORT.md` modified, `eval/h1_relevance_gate.py`, `eval/results/h1_relevance_gate_dev.json`) plus an untracked `.vscode/` (editor setting only). All preserved unchanged |
| OS | macOS 27.0.1 (Apple silicon) |
| Python | 3.14.5 (`.venv`) |
| PostgreSQL | 18.7 (Homebrew), pgvector 0.8.7 |

### Database target
- **Tests:** `rag_test_scratch`. It was empty at preflight (0 chunks, conversations, messages, memories). `run_tests.py` points every test at it, and `testsafe` refuses any non-scratch name.
- **Offline replay:** reads `rag_phase35_eval`. Checked before use: it is the H.1 evaluation corpus, 135 chunks of synthetic evaluation documents. The replay only reads it.
- **`rag_db`:** on this Mac it is a fresh, empty schema (migrations 000–003), **not** the Windows application database. It was only read, through `run_tests.fingerprint`, a read-only transaction.
- No URL, password or key was printed.

### Baseline tests (before any change)
- **Command:** `.venv/bin/python run_tests.py` (unit + integration, scratch database).
- **Result:** **45 run, 43 passed, 2 failed.** The 2 failures are the known pre-existing `test_p1_process_memory.py` and `test_p1_delete_routing.py`.
- `rag_db` fingerprint unchanged. This matches the Windows Stage 5 regression result (43/45).

## B. Existing architecture

### Call sequence (one shared path; the CLI and the API both use `main.run_turn`)

| # | Step | Where |
|---|---|---|
| 1 | Query enters | CLI: `main.main` → `main.run_turn(conversation_id, query)`. API: `POST /api/v1/chat` (`backend/routers/chat.py`) → the same `main.run_turn` |
| – | Explicit memory deletion is routed first | `main.run_turn` (`is_explicit_memory_delete_request`); this returns early, with no RAG |
| 2 | Classification | `rag_service.classify_question` (LLM): MEMORY / DOCUMENT / MIXED. On a provider failure it falls back to DOCUMENT (B3) |
| 3 | Query rewriting | `llm_service.rewrite_query` (LLM; only when there is history or memory). On failure it uses the original question (B3) |
| 4 | Retrieval | `rag_service.ask_question` → `hybrid_search_service.hybrid_search_detailed` (**Stage 6**: previously the `hybrid_search` wrapper), then the margin / min-score gate on reranked results |
| 5 | Context assembly | `context_assembly_service.assemble_context`: dedupe, `CONTEXT_MAX_CHUNKS` / `CONTEXT_MAX_CHARS`, `[S#]` refs, display-only neutralisation of forged markers |
| 6 | Prompt construction | `answer_prompt.build_answer_prompt`: rules first, then `<retrieved_documents>`, memory, `<conversation_history>`, `<user_question>`; delimiters in untrusted text are neutralised |
| 7 | Provider selection | `llm_config` (environment > `.env` > default: `gemini-3.5-flash-lite`, fallbacks `gemini-3.1-flash-lite`, `gemini-2.5-flash`) → `llm_service.generate_answer` (model fallback, quota cooldown, 120 s timeout) → `gemini_retry_service.generate_with_retry` |
| 8 | Response parsing | `answer_service._parse` (tag + body); empty and non-string replies are rejected |
| 9 | Validation | `citation_service.validate_answer_citations` (refs, coverage, page and file mentions) + **Stage 6** `grounding_service.unsupported_numbers`; then bounded regeneration (`ANSWER_MAX_RETRIES=1`), then `answer_service._fallback` (repair / abstain / unverified) |
| 10 | Returned | `ask_question` → `run_turn` (saves messages, prints the answer and sources, then memory extraction and summary, each isolated) → CLI print or `ChatResponse` |

### Prompt and response contracts (existing; preserved)
- **Prompt:** evidence-only rules, the exact refusal sentence, "untrusted DATA" handling, an explicit list of allowed refs, and an output tag (`[DOCUMENT]` / `[MEMORY]` / `[MIXED]`). A rejected attempt adds a `CORRECTION REQUIRED` block.
- **`generate_grounded_answer`** returns `answer`, `status` (`answered | partial | conflict | abstained | unverified | error`), `tag`, `citations` (`ref`, `document`, `page`, `chunk_id`), `sources` (cited only), `validation`, `attempts`, `issues`.
- **`ask_question`** returns `answer`, `sources`, `citations`, `status`, `issues`, `retrieved`, and now **`retrieval_status`** (additive).
- **`run_turn`** returns `kind`, `answer`, `status`, `sources`, `citations`, `issues`, `memory_extraction`, `summary_update`, and now **`retrieval_status`** (additive). The deletion path is unchanged.
- **API `ChatResponse`** fields are unchanged (`request_id`, `conversation_id`, `kind`, `answer`, `status`, `citations`, `memory_extraction`, `summary_update`, `deleted_count`). By decision, `retrieval_status` is not exposed.

### Existing controls (B2/B3, verified by the probe below)

| Control | Result |
|---|---|
| Citation refs validated against the assembled sources; invalid refs removed | Yes |
| Every claim sentence (≥ 5 words) needs a citation | Yes |
| Page and file mentions checked against source metadata | Yes |
| Citation metadata built from the assembled source, never from model text | Yes |
| DOCUMENT question with nothing retrieved → refusal, no LLM call | Yes |
| `[DOCUMENT]` claim with nothing retrieved (MIXED / MEMORY) rejected | Yes |
| Bounded regeneration with specific feedback, then repair, abstention or `unverified` | Yes |
| Forged `[S#]` headers and delimiter tags neutralised in the prompt | Yes |
| **Semantic support of a cited claim** | **No.** Documented in B2/B3 as the main remaining gap |

### Probe of the existing code (before any change)
- **Setup:** fake LLM, 2-source context, script at `scratchpad/probe_stage6.py` (outside the repository).
- **Correct already:** citation cases 1–4 and 6–10, empty, `None`, non-string and tag-only replies, provider exceptions, and prompt separation.
- **Confirmed defects (all `answered` before the change):**
  - **G1–G3:** an invented amount, date or price with a *valid* citation, e.g. "within **60** days [S1]" when S1 says 30.
  - **C5:** a numeric fact cited to the **wrong** passage, e.g. "Opening hours are 9 to 17 [S1]" when the fact is in S2.
  - **G6:** a short uncited sentence with an invented number (`Fee: $12.`), which escapes the ≥ 5-word uncited-claim rule.
- **Semantic, not deterministically checkable (accepted, then and now):**
  - G4: an invented name with a valid citation.
  - G5: "may" turned into "will always".
  - C5b: a non-numeric fact cited to the wrong passage.

### Retrieval status before Stage 6
`rag_service` called the `hybrid_search()` wrapper, which returns only `["results"]` and **discards `rerank_status`**. The answer layer could not tell `ok`, `disabled`, `skipped` and `failed:<Type>` apart. A rerank failure looked like a normal result whose margin gate silently did not run.

## C. Changes

| File | Change | Reason | Tests |
|---|---|---|---|
| `services/grounding_service.py` (new, 89 lines) | `unsupported_numbers(answer, sources, question, check_uncited)` and `drop_unsupported_number_sentences(...)`. Every number in a **cited** sentence must appear in the **cited** passages (text + document name); an uncited sentence is checked against all retrieved passages when citations are required; numbers from the question are always allowed. Numbers are compared by value (`07`=`7`, `14.50`=`14.5`, `1,200`=`1200`). Page and file-name mentions are left to the existing metadata checks. Evidence numbers are extracted permissively (`v4.0`, `PR-7`, `A4`) | G1–G3, C5, G6: the smallest deterministic grounding check that fits the existing validate → regenerate → repair flow, with no extra LLM call | `test_stage6_answer.py` (grounding, citations, no-answer), `test_stage6_answer_integration.py` (wrong passage, fabricated number) |
| `services/answer_service.py` | (1) after citation validation, an `unsupported_number` issue makes the attempt invalid → the existing bounded regeneration, with feedback naming the numbers; (2) the repair fallback also drops sentences with unsupported numbers (`dropped_unsupported_number_sentences:N`); (3) a pure abstention is accepted in the fallback only if it introduces no unsupported number; (4) the fallback moved into `_fallback()` (no behaviour change; `generate_grounded_answer` 119 → 107 lines) | As above | Same; plus the existing `test_b2`, `test_b3`, `test_answer_phase3` |
| `services/rag_service.py` | Calls `hybrid_search_detailed(search_query, top_k=cfg.FINAL_TOP_K)`, the wrapper's exact call, and keeps `results`. Adds `retrieval_status` (= Stage 5 `rerank_status`, or `not_run` for MEMORY) to the result and prints it. **No answering behaviour depends on it** | Approved option "Call detailed API" (interface proposal answered before implementation) | `test_stage6_answer.py` (G), `test_stage6_answer_integration.py` |
| `main.py` | `run_turn` passes `retrieval_status` through (one additive key) | Same decision; the CLI path exposes it | `test_stage6_answer_integration.py` (`run_turn`) |
| `test_answer_phase3.py`, `test_b3_answer_reliability.py`, `test_stage5_retrieval.py`, `test_retrieval_phase2.py` | Mechanical: mocks of `rag_service.hybrid_search` now patch `rag_service.hybrid_search_detailed` with the same results wrapped as `{"results": …, "rerank_status": …}`. No assertion changed | Required by the approved interface change | Each passes with its previous check count |
| `test_b2_citation_evidence.py`, `test_b3_answer_reliability.py` | The two "LIMITATION pinned" checks used a **numeric** unsupported claim ("90 days", "9M"), which Stage 6 now rejects. Each is re-pinned with a non-numeric claim (still accepted, still documented), and a new check asserts the numeric version is rejected | The pinned behaviour intentionally changed; the limitation itself remains for non-numeric claims | `test_b2` 36/36, `test_b3` 35/35 |
| `test_stage6_answer.py` (new, unit, 66 checks) | Prompt construction, generation, grounding, the 10 citation cases, no-answer, provider failures through `ask_question`, retrieval status | Required coverage | — |
| `test_stage6_answer_integration.py` (new, integration, 13 checks) | Real ingestion + embeddings + cross-encoder on the scratch DB, fake LLM: `ask_question`, `run_turn` and `POST /api/v1/chat` | End-to-end and CLI/API compatibility | — |
| `run_tests.py` | Registers the two new tests (unit, integration) | Runner registry check | — |
| `eval/stage6_answer_replay.py` (new) | Offline replay of the recorded dev answers through HEAD vs working tree | Measure false positives on real model output without LLM calls | See H |

## D. Answer quality

**Supported claims:** a number present in the cited passage is accepted on the first attempt; one LLM call, as before.

**Unsupported claims:**

| Claim | Behaviour |
|---|---|
| Invented amount, date, price or derived total, with a valid citation | `unsupported_number` → one regeneration with feedback naming the numbers. If corrected: accepted. If not: repair drops the sentence, or the answer becomes `unverified`. Never returned as `answered` |
| Numeric fact cited to the wrong passage | Rejected the same way |
| Short uncited sentence with an invented number | Removed by the repair; the grounded part stays |
| Uncited claim of ≥ 5 words, or no citations | Rejected (B2, unchanged) |
| Invented **name**, hedging changed ("may" → "will always"), paraphrased wrong claim, non-numeric wrong source, spelled-out numbers ("thirty") | **Not detected** (accepted). Pinned in tests as limitations. Only the prompt addresses them |

**Insufficient context:**
- Cited part + stated gap → `partial`.
- Pure abstention → `abstained`.
- An abstention that introduces a number from neither the evidence nor the question is not accepted (`unverified`).

**No-answer:**

| Situation | Behaviour |
|---|---|
| Nothing retrieved (DOCUMENT) | Refusal with no LLM call |
| Irrelevant context + refusal | `abstained` |
| Irrelevant context + uncited general knowledge | Rejected |
| Irrelevant context + fabricated cited number | `unverified`. Unit test, and end-to-end with real retrieval |

**Known limitations:**
- Grounding is **numeric only**. It is not semantic: B2/B3's "no semantic grounding check" remains open for every non-numeric claim.
- Derived numbers (sums, conversions) are rejected even when correct. This is consistent with the dataset rule that gold facts are literal, but stricter than a human reader.
- The live model's response to the new feedback (extra regenerations, latency, tokens) is not measured (see H).

## E. Citation integrity

| Case | Result (`test_stage6_answer.py`) |
|---|---|
| 1 Correct citation | `answered`, `[S1]` |
| 2 Missing citation | `unverified` (`no_citation`, `uncited_claim`) |
| 3 Unknown id `[S9]` | `unverified` (`invalid_ref`) |
| 4 Id not in the supplied context `[S3]` | `unverified` (`invalid_ref`) |
| 5 Incorrect source | **numeric: `unverified` (new)**; non-numeric: accepted (limitation) |
| 6 Several sources, one claim | `answered`, `[S1][S2]` |
| 7 One source, several claims | `answered`, `[S1]` once |
| 8 No citations | `unverified` |
| 9 Empty context | Refusal, no LLM call |
| 10 Malformed (`[S1`, `(S1)`, `[Source 1]`) / duplicate `[S1][S1]` | Not a citation → `unverified` / de-duplicated → `answered` |

- **Metadata integrity:** citation `document`, `page` and `chunk_id` always come from the assembled source for that ref, never from model text. End to end, the cited `chunk_id` maps to the same document and page in the database. Invented page numbers and file names in prose are rejected.
- **Not confused with factual verification:** the citation checks validate the format and the existence of refs. The numeric check is a separate, factual (numbers-only) check. No citation is ever added automatically.

## F. Retrieval-status handling

| `retrieval_status` | Meaning (Stage 5 contract, unchanged) | Answer behaviour (Stage 6) |
|---|---|---|
| `ok` | Reranked; the margin / min-score gate applied | Normal validation; tested end to end |
| `disabled` | `RERANK_ENABLED=false`; RRF order, **no relevance gate** | Same validation; status returned; no fail-closed. Tested end to end |
| `skipped` | Nothing to rerank (empty fused list or `top_k=0`) | Empty context → DOCUMENT refusal without an LLM call |
| `failed:<ExceptionType>` | Reranker failed; RRF fallback, **no relevance gate** | Same validation; status returned (e.g. `failed:RuntimeError`); the answer is still produced from RRF. Tested end to end |
| `not_run` (new value, rag_service only) | MEMORY question; retrieval not called | Unchanged MEMORY path |

- The status is now **available** to `ask_question` and `run_turn` callers (CLI) but deliberately **not used** to change answers.
- The unreranked statuses (`disabled`, `failed:*`) do not have the reranker's relevance guarantee. The numeric check limits fabricated numbers in such contexts, but irrelevant non-numeric passages can still reach the model.
- **The H.1 no-rerank policy remains unresolved.** Fail-closed, a required reranker, and recalibration were **not** implemented. The API does not expose the status (decision: internal only).

## G. LLM failure handling

**Results through `ask_question`** (fake Gemini client, `MODEL_NAME=A`, one fallback `B`, `time.sleep` patched; `test_stage6_answer.py` F):

| Failure | Result | Requests per turn (no history) |
|---|---|---|
| Authentication (401) | `status=error`, `ERROR_MESSAGE`, no citations; not switched to another model | 3 (classify 1 + 2 answer attempts) |
| Rate limit (429) on all models | `status=error` | 18: each request tries A, B, waits, then up to 4 tries on A (`generate_with_retry` default `max_retries=3`) |
| Network timeout on all models | `status=error` | 6 (one per model, no same-model retry) |
| Unavailable (503) on all models | `status=error` | 12 (one same-model retry each) |
| Empty response from all models | `status=error` | 6 |
| Unexpected structure (`text` not a string) | `status=error` | 3 |
| Missing API key | `status=error` (not an exception, not an answer) | 0 sent |
| Retrieval failure (DB / embedding) | **Raises** (API → 500 `internal_error`), kept distinct from a generation failure | — |

- **Secrets:** a test key is set in the environment for every provider case. It never appears in printed output or in the result. Errors are logged by type or code only.
- **No fabricated answers:** every provider failure ends as `status=error` with the fixed `ERROR_MESSAGE`. It is never `answered`.
- **Retry behaviour:** unchanged (no defect demonstrated). The answer loop's second attempt after a provider exception is existing, tested behaviour (B3 #12).
- **Timeout:** 120 s per request (`REQUEST_TIMEOUT_MS`), unchanged.
- **Parsing:** empty, `None`, non-string and tag-only replies → `error` after `1 + ANSWER_MAX_RETRIES` calls.

## H. Evaluation

| Command | Dataset / split | Cases | Result | Real LLM calls |
|---|---|---|---|---|
| `.venv/bin/python -m eval.stage6_answer_replay --output eval/results/stage6_answer_replay_dev.json` | Recorded live Gemini answers, `eval/phase35/results/tier1_dev.jsonl` and `tier2_dev.jsonl`, **dev split only** (the script refuses non-dev ids) | Tier 1: 47; Tier 2: 42 | **0 of 89 answers or statuses changed.** Tier 1 correct 42/47 → 42/47; Tier 2 28/42 → 28/42. Transitions are all identities (answered 36 / 29, abstained 9 / 6, partial 1 / 6, conflict 1 / 1) | **None** (a fake model returns the recorded answer) |

**Method:** HEAD's `answer_service` (from `git show`) and the working tree are compared on identical inputs.
- Tier 1 contexts are rebuilt with `run_eval.tier1_context` (same seed).
- Tier 2 passages are read by chunk id from `rag_phase35_eval`, and each id is checked against the recorded document and page (all matched).
- Scoring uses `run_eval.score_generic`, loaded via `ast` because importing `run_eval` would switch databases. This is the B4 method.

**Two findings from the replay:**
1. **A false positive in my first version, found and fixed.**
   - In the first run (output kept outside the repository), Tier 2 `C-multi_page-03` changed. The recorded answer says "Under version **4.0** … £8.99 [S1]", and the passage writes `v4.0`.
   - The answer-side number pattern (shared with the evaluation metric) does not see digits glued to a letter, so a correct sentence was dropped.
   - Fix: evidence numbers are now extracted permissively. Regression test: "grounding: regression - 'version 4.0' is supported by 'v4.0'". Re-run: 0 changes.
   - A test then exposed a second false positive: a page number written in prose, "page 3 of report.pdf". Page and file mentions are now left to the metadata checks.
2. **B4's label for `C-multi_page-03` is a scoring artefact.** B4 listed the case as an "unsupported answer (ungrounded number `4.0`)". That flag comes from the same blind spot in `run_eval.norm_numbers`: the number is in the passage as `v4.0`. The frozen scorer and the B4 report were **not** modified; this note corrects the interpretation only. The replay's Tier 2 `unsupported` count (1 before, 1 after) is this artefact.

**Not equal to the recorded score:** Tier 1 `A-conflict-02` was recorded as incorrect (`conflict_ok=False`) but scores correct under today's HEAD pipeline as well. So the replay's 42/47 differs from the recorded 41/47 for both before and after; the difference predates Stage 6.

**Not run:**
- **Live Gemini dev evaluation.** `eval/phase35/run_eval.py` appends to the recorded `tier*_dev.jsonl` and skips cases already done. A fresh run would need `--fresh` (which deletes the recorded results, a frozen asset) or a runner change. The live effect of the new feedback (extra regenerations, tokens, latency, answers changed by the model) is therefore **unmeasured**.
  - Proposal: a separate approved run writing to a new results path.
  - Estimated cost: ≈ 47 + 42 cases × 2–4 calls (≈ 180–360 Gemini calls).
- **Held-out:** not run.

**Tests** (`run_tests.py`; scratch DB `rag_test_scratch`; models offline; network blocked):

| Command | Pass / fail / skip | Notes |
|---|---|---|
| `run_tests.py test_stage6_answer.py` | 1/0/0 files; **66/66 checks** | Unit, no DB |
| `run_tests.py test_stage6_answer_integration.py` | 1/0/0; **13/13 checks** | Writes: 2 `s6_*` PDFs (chunks), 2 conversations + 4 messages; all removed in `finally`; post-run 0 `s6_*` chunks, 0 conversations |
| Focused existing answer and retrieval tests (`test_b2` 36, `test_b3` 35, `test_answer_phase3` 69, `test_context_and_citations` 62, `test_stage5_retrieval` 47, `test_stage5_retrieval_integration` 33, `test_retrieval_phase2` 64, `test_model_fallback` 15, `test_llm_timeout` 19) | all pass, 0 failed checks | Stage 5 counts unchanged from the Stage 5 report |
| `run_tests.py` (full unit + integration) | **47 run / 45 passed / 2 failed**, 18 not run (live / manual) | The 2 failures are the known memory tests; see below. `rag_db` fingerprint unchanged |

**Regression investigated, not misclassified.** The first full run after the change failed `test_retrieval_phase2.py` (`rag_service` no longer has `hybrid_search`). That was a fourth mock site of the approved interface change, missed by my first search. It got the same mechanical fix and now passes, 64/64.

**Pre-existing failures, reported separately:**
- `test_p1_process_memory.py`: failed check `[5] whitespace-only memory -> SKIPPED, no row`; `AttributeError: 'NoneType' object has no attribute 'kwargs'`.
- `test_p1_delete_routing.py`: failed checks `[N2] memory_summary composition` (×2) and `[N3] 4 messages -> extraction`.
- Both were run on an untouched **HEAD** checkout (temporary `git worktree`, removed afterwards) and on the working tree. **The failed checks and errors are identical**, so they are not Stage 6 regressions.
- Memory code was not touched.

**Mutation check** (temporary in-place edits, restored; each run of `test_stage6_answer.py`):

| Mutation | Result |
|---|---|
| Numeric check disabled | 9 FAIL |
| Repair does not drop number sentences | 7 FAIL |
| Strict evidence extraction (`v4.0` false positive back) | 1 FAIL |
| Page/file mentions not stripped | 1 FAIL |
| Cited sentence checked against all sources | 1 FAIL |
| `retrieval_status` removed | Test exits 1 (`KeyError`) |

All caught.

## I. Database and frozen contracts

| Item | Status |
|---|---|
| `rag_db` unchanged | Yes. Fingerprint identical to the one taken before H.1 (all 5 tables, 0 rows); `run_tests` reported "unchanged" on every run |
| Writes performed | `rag_test_scratch` only (test fixtures, all cleaned up; see H). `rag_phase35_eval`: `harness.use_scratch_database` ran its idempotent `CREATE EXTENSION / CREATE TABLE IF NOT EXISTS` (no-op); data read only; still 135 chunks |
| Held-out evaluation | Not run; no held-out case was loaded into the replay |
| Datasets, splits | `eval/phase35/` unchanged (`git diff` empty) |
| Thresholds | `eval/framework/` (incl. `FROZEN_THRESHOLDS`) unchanged |
| BM25 fingerprint invalidation | `services/bm25_service.py` unchanged |
| Stage 4 ingestion | `ingestion_service.py`, `pdf_parser.py`, `embedding_service.py` unchanged; Stage 4 tests pass |
| Stage 5 retrieval | `hybrid_search_service.py`, `reranker_service.py`, `rrf_service.py`, `search_service.py`, `context_assembly_service.py`, `retrieval_config.py` unchanged; `rerank_status` values unchanged; Stage 5 tests pass (47, 33) |
| Provider configuration | `llm_service.py`, `llm_config.py`, `gemini_retry_service.py` unchanged |
| Migrations 000–003 | Unchanged |
| H.1 artifacts | Preserved; the Stage 5 report diff is still the H.1 section only (+189 lines) |
| `git diff --check` | Clean |
| Secret scan | No credential patterns in the diff or new files |
| Code limits (CLAUDE.md) | New files: ≤ 300 lines, functions ≤ 50 lines, no unused imports. Pre-existing over-limit items unchanged or improved (see J) |

## J. Remaining risks

### Blocking defects
None found.

### Non-blocking limitations
- **Semantic grounding:** names, paraphrases, hedging, non-numeric wrong-source citations and claims from injected text without numbers are not detected (pinned in `test_stage6_answer.py`, `test_b2`, `test_b3`).
- **Numeric check scope:**
  - Spelled-out numbers are not checked.
  - Correct derived numbers are rejected.
  - Evidence extraction is deliberately permissive (`A4` supports "4"), which allows rare false negatives.
- **Live behaviour unmeasured:** the model's response to the numeric feedback, and the frequency of extra regenerations, tokens and latency.
- **Worst-case provider latency** (existing behaviour):
  - With the default 3 models, all timing out: classify 3 × 120 s + 2 answer attempts × 3 × 120 s ≈ **18 min** (+ 6 min with a rewrite).
  - All rate-limited: ≈ 7 requests per LLM call plus server-directed waits (≤ 30 s each).
- **A generation failure is saved to history:** `run_turn` saves the `ERROR_MESSAGE` turn and runs memory work after it (existing behaviour).
- **Pre-existing code-limit violations** (unchanged by Stage 6 unless noted):
  - `generate_grounded_answer`: 107 lines (was 119).
  - `ask_question`: 124 lines (was 114; +10 for the status).
  - `run_turn`: 309 lines.
  - Unused imports `REFUSAL_MESSAGE` (`rag_service`) and `process_memory` (`main`).

### Decisions requiring approval
1. **H.1 no-rerank policy** (unchanged): fail closed, require the reranker, or recalibrate. `retrieval_status` now makes any of these implementable without another interface change.
2. **Live dev evaluation** of Stage 6 with a new results path (≈ 180–360 Gemini calls).
3. **Exposing `retrieval_status` in the API** (declined for now).

### Future proposals
- An optional, off-by-default semantic verifier (an LLM judge or an entailment model) for non-numeric claims. It needs a design decision, because of cost and an extra model or call.
- A bounded total time and request budget per turn for provider failures.
- Fix the evaluation metric `norm_numbers` blind spot (`v4.0`). This needs approval, because it changes a frozen scorer.

## K. Final status

**PASS WITH KNOWN ISSUES.**

- **What passed:**
  - The existing answer flow is traced, documented and validated.
  - Prompt separation is tested.
  - LLM responses and provider failures are handled and tested (no fabricated answers, no leaked secrets).
  - Numeric unsupported claims (invented or wrong-source numbers) are blocked by a deterministic, tested, mutation-checked safeguard with 0 false positives on 89 recorded dev answers.
  - Citation ids are validated against the supplied sources (all 10 cases).
  - Retrieval status reaches the answer layer (approved interface).
  - CLI and API contracts are preserved.
  - Focused tests pass; the regression is 45/47 with the 2 known memory failures shown identical at HEAD; `rag_db` and the frozen assets are unchanged.
- **Known issues** (non-blocking, listed in J): there is no semantic grounding beyond numbers, the live dev evaluation was not run, and the H.1 policy is undecided.
- **Ready for the next stage:** yes. Answers that pass validation are cited, use only supplied refs, and contain only numbers present in the cited evidence. Every failure mode ends in an explicit non-`answered` status.
  - Condition: before relying on unreranked retrieval (`disabled` / `failed:*`) in production, decide H.1.
  - Recommended before release: run the approved live dev evaluation to measure the new feedback loop.

Stage 7 was not started.
