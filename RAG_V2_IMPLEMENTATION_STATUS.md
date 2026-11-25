# RAG v2 implementation status

2026-11-20 · **CURRENT: GREY_WORKSPACE_UI_PASS.** The requested neutral grey/black frontend is implemented and verified against the production build, real scratch OCR/Gemini journeys, two-user isolation and actual PDF page rendering. Preview: **http://127.0.0.1:3000**, ordinary API http://127.0.0.1:8000/api/v2/docs, two API processes and two durable local workers on **rag_test_scratch**. This is local UI engineering acceptance; formal held-out/human acceptance is unchanged.

| Phase | Status | Actual gate evidence |
|---|---|---|
| Identity/isolation | PHASE_1_MULTIUSER_PASS | Real restricted-role PostgreSQL/API: two owners; vector/BM25/FTS, documents/PDFs, conversations/messages, memories/provenance/jobs; safe enumeration/deletion denial; admin/reset/disable/expiry/logout; cross-owner FK rejection and explicit unowned-legacy compatibility. |
| Frontend | PHASE_2_FRONTEND_PASS | Production Next/shadcn build/typecheck/lint;15 unit/security tests;10 provider-free desktop/mobile browser tests; genuine live browser core journey;24 actual OpenAPI route contracts. |
| OCR | PHASE_3_OCR_PASS | Native/scanned/mixed PDF tests and actual embedded-Tesseract OCR. Predeclared >=95%word recall plus both numeric facts and original page2; observed100%recall,2/2facts,page2. Real browser scan indexed and cited page1. |
| Multi-worker | PHASE_4_MULTIWORKER_PASS | Independent-process claim exclusivity, actual os._exit crash/recovery, lease expiry, stale/duplicate/cancel publication, advisory-lock ordering/no lost updates, versioned replacement and model metadata. Two real OCR/embedding worker processes and two API processes used in live integration. |
| Integration | PHASE_5_INTEGRATION_PASS | Actual browser login→image-only upload→job→OCR→local embeddings/hybrid retrieval/reranking→Gemini83/17→owned PDF page citation→memory extraction/user provenance→follow-up/recall→second-user404→document/conversation deletion/no resurrection.11 actual SDK calls under12cap, no retries. |
| Release | PHASE_6_RELEASE_PASS | Final affected API/security tests and provider-free browsers pass; nonempty consistent-snapshot backup/restore retains10table counts and8FORCERLSpolicies; startup with restricted role; failure/deadline/redaction/concurrency tests; preserved RAG behavior. Historical review-package mismatch is unrelated to runtime release behavior and remains untouched. |

No critical tenant-isolation, deletion, OCR, worker-consistency or browser journey failure remains in the defined workload. These are bounded local engineering gates, not general production certification or formal held-out acceptance.

## Source and contracts

Five specialists worked in bounded parallel waves, with lead ownership of migrations, schemas and integration. Existing RAG orchestration, generation, reranking, memory semantics and deletion services are reused.

- `backend/v2/{app,schemas,auth,tenant}.py`: separate session-authenticated API; registration/login/logout, audited admin reset/roles/status/bootstrap; typed resource contracts and safe errors. Salted scrypt, opaque hashed sessions, session-bound CSRF; no first-registrant admin or browser bearer. `run_v2_api.py` binds loopback; `scripts/v2_admin.py` reads passwords privately.
- `migrations/007_v2_identity_jobs.sql`: additive users/sessions/audit/documents/jobs/events, ownership indexes and foreign keys, model identity and8FORCERLS policies. Existing rows remain unassigned. No startup migration/backfill. Application authorization plus RLS; superuser/BYPASSRLS and rag_db are refused. Explicit `RAG_V2_COMPAT=1` permits only unowned legacy rows and is forbidden in the multi-user API.
- `services/tenant_context.py`, `database.py`, `search_service.py`, `bm25_service.py`, `v2_index.py`: transaction-local ownership, explicit retrieval scope, owner-partitioned BM25 cache, persisted model/dimension compatibility checks, and connection closure even after deferred commit failure.
- `services/ocr_service.py`, `requirements-ocr.txt`: bounded native/OCR page selection, original provenance, cancellation/timeout kill+reap, English local OCR with hash-pinned tessdata_fast4.1.0. Confidence is unavailable and represented as null; no cloud OCR. Model data is installed outside versioned sources at ignored `data/v2_models/tessdata`.
- `services/v2_{jobs,worker,coordination}.py`, `scripts/run_v2_worker.py`: SKIP LOCKED, token leases/heartbeat/recovery, bounded retries/backoff/terminal events, idempotency, fair active-owner scheduling and admission quotas, cancellation/version fences, atomic chunk publication. OCR/model work holds no database transaction; conversation mutations share cross-process advisory locks.
- `frontend/`: Next App Router/React/strict TypeScript/Tailwind/shadcn/ui/Lucide, generated actual OpenAPI bindings, all requested screen categories, upload/replacement, safe PDF previews/citations, history/search/rename/delete, supported memories, admin controls, polling jobs/retry/cancel, responsive/dark/keyboard/error states. Same-origin server gateway forwards only session/CSRF material. Final chat layout prevents composer overlap.

Final hardening fixes were driven by failing focused tests: total body deadlines now include slow-drip reads in API/BFF; unhandled private exceptions cannot escape to server traceback logging; deletion diagnostics hide private decision/error text during HTTP requests. No provider or retrieval-policy change was made to obtain a PASS.

## Executed verification

Exact interpreter/inline-runner commands, environments and outcomes are in `v2_evidence/verification_commands.json`; frontend commands are also in `frontend/evidence/final-ui-validation/verification.json`.

| Check | Outcome |
|---|---|
| Combined seven-module v2 suite |67/67 PASS,0skips,16.31s after stopping competing test schedulers. A prior fixture claim race was retained and diagnosed, not fixed by changing queue semantics. |
| Final middleware/security changes |3 focused negative tests PASS, then18 affected API/security/journey/release tests PASS14.278s; includes2 newly added regressions.69 unique v2 methods covered overall. |
| Prior abstention/policy/protected-runtime synthetic suites |73/73 PASS; no protected execution. |
| Existing registered RAG regression suite |91/92 scripts PASS in a separate fresh scratch container. Only `test_phase_e2_flip_review.py` fails its historical source_revision rebuild equality; see below. |
| Final frontend |Build, strict typecheck, lint,15 unit tests PASS;10 provider-free browser tests PASS26.7s, including actual desktop/mobile API sessions/upload/download/isolation/history/deletion. |
| Genuine live browser |1/1 PASS2.4min;11 SDK calls, all returned gemini-3.5-flash-lite. Two API processes/two worker processes; actual rendered answer/PDF navigation and memory recall. |
| Restore |Nonempty consistent exported snapshot restored into a new UUID scratch DB; all10table counts matched,8FORCERLSpolicies retained; only its seed and new restore DB removed afterwards. |
| Integrity/dependencies |git diff --check PASS; pip check reports no broken requirements;38 browser bundle files scanned against2configured secrets,0matches. |

Live browser identity: `v2-browser-aster-20261119T092730Z-466c2d`. Evidence: `frontend/evidence/v2-browser-aster-20261119T092730Z-466c2d/browser_result.json` and corresponding `v2_evidence/` SDK prompt/response-hash receipts. The successful browser JSON attachment was not persisted by the reporter: published evidence is explicitly an executed-assertion summary plus actual screenshots/SDK receipts, not reconstructed raw responses. Final layout screenshots are in `frontend/evidence/final-ui-validation/`.

The earlier API functional smoke used11actual Gemini calls and demonstrated three successful turns, real local models, user memory/recall and isolation. Its raw `live_smoke_retry1.json` remains FAIL25/26 because of two harness mistakes (the expected user_source label versus actual origin/user provenance, and a list-vs-array publication fixture); zero-provider `live_smoke_continuation.json` separately passes6/6 provenance/deletion checks. The first sandbox failure and two pre-provider browser failures remain preserved. No historical outcome was overwritten. **Total new actual Gemini calls:22**; no further calls after the browser PASS. Final transport/layout hardening was verified with focused/provider-free tests rather than a provider rerun.

## Historical limitation and integrity

`independent_review/flip_review_package` records source revision690fcfb; rebuilding embeds current HEAD. That stored revision already differed from this task's starting HEADdec09f6. The failure is confined to four source_revision values and their derived package-manifest hash. Frozen review evidence was deliberately not regenerated. Runtime RAG regression scripts pass; formal human-certified evaluation remains separately pending and its requirements unchanged.

Before edits,634 tracked/untracked file hashes and index bytes were captured. Only five pre-existing files changed intentionally: `.gitignore`, `services/database.py`, `services/search_service.py`, `services/bm25_service.py`, `services/automatic_memory_service.py`. All other baseline bytes and all44protected assets remain unchanged. Branch is main. HEAD advanced externally from dec09f6 to3bf3304 during the session; no agent staged, committed, pushed, reset, cleaned or stashed. Existing index bytes were preserved. See `v2_evidence/repository_integrity.json`.

No rag_db connection, production-memory/quarantine execution, protected held-out run, scorer/dataset/threshold/manifest/human-review change or production migration occurred. Only dedicated scratch migrations and disposable restore databases were written.

## Local setup and operating scope

Verified host: macOS27.0.1 arm64, Python3.14.5, Node25.9.0/npm11.12.1; PostgreSQL18.7/pgvector in the dedicated `rag-v2-scratch` container on127.0.0.1:55432. Existing Python pins are retained; frontend package-lock pins Next16.2.10/React19.2.8. The separate regression container on55433 is stopped after testing.

Fresh scratch schema: `.venv/bin/python -B scripts/v2_scratch.py` against that dedicated container. Configure a non-superuser/non-BYPASSRLS connection explicitly in process `DATABASE_URL`, and `RAG_OCR_TESSDATA` to the hash-verified model directory. `requirements-ocr.txt` gives the pinned data install command. Then start:

```sh
.venv/bin/python run_v2_api.py --workers 2
# Separate terminals, same explicit DATABASE_URL and RAG_OCR_TESSDATA:
.venv/bin/python scripts/run_v2_worker.py
.venv/bin/python scripts/run_v2_worker.py
cd frontend
npm ci
npm run build
RAG_BACKEND_ORIGIN=http://127.0.0.1:8000 npm start
```

The current preview is already running with this topology and persistent ignored OCR data. Initial admin: `.venv/bin/python scripts/v2_admin.py bootstrap --email <new-admin-address>`; passwords are prompted privately. Password resets are administrator-managed. Production/user-data migration is not activated. OCR is verified for English and the bounded fixtures, not arbitrary language/layout quality. Historical messages retain v1 text-only storage; structured citations/status render for new responses. Request feedback is incremental waiting state, not simulated token streaming.

**Remaining critical release blockers: none in the verified local scope. Next executable action: use the running preview.** Formal independent-human acceptance, broader OCR/language certification and network/cloud deployment remain separate from these engineering gates.

## Post-release correction: document routing (2026-11-19)

Observed a ready indexed resume falsely abstaining. Logs established a MEMORY classification skipped retrieval for a name question; a vague document-overview query also failed to rank the opening identity/summary chunk. V2 now uses `v2-memory-abstention-document-fallback/1`: only after a memory abstention, try the existing grounded document path once. Successful memory answers and legacy v1 routing retain their behavior. `v2-single-source-overview/1` resolves explicit broad document-overview requests using the sole ready owned filename as search terms; it never guesses between several sources. Citation validation, reranker thresholds and scorer policies are unchanged.

Changed `services/rag_service.py`; added `services/v2_routing.py` and `test_v2_routing_recovery.py`. Eight deterministic regressions PASS; five affected existing scripts PASS (`test_stage8_p3_classification.py`, `test_stage6_answer.py`, `test_local_v1_retrieval.py`, `test_context_and_citations.py`, `test_b3_answer_reliability.py`). Read-only local replay against the affected index selects its opening chunk/page1 for both reported queries; generation was a deterministic fixture, not a new live-provider result. No new Gemini calls, document/chat writes, migrations, protected asset changes or Git mutations occurred. API restarted with the fix; no re-upload is required. The earlier source-change count of five above describes initial v2 delivery; this follow-up additionally modifies rag_service.py.

## Post-release correction: academic qualifications (2026-11-19)

The personal qualifications question retrieved a name-rich career summary and the adaptive filter dropped the nameless education chunk. Added versioned v2-person-education-evidence/1: identify a unique person-bearing document from initial results, then search academic evidence within that same document. Do not guess across documents with the same name; do not substitute career experience when academic evidence is missing. V2-only answer guidance prioritizes degree, subject, institution and dates; explicit professional/role-requirement questions and legacy prompts are unchanged. No global rank thresholds, scorer assets or schemas changed.

Six qualification regressions and eight earlier routing regressions PASS; four affected existing scripts PASS (stage8 classification, stage6 answer, context/citations, B3 answer reliability). A bounded live check made two Gemini calls and returned the correct academic degree/institution/dates with the education chunk and original page1 citation. This read-only functional check did not write chat/document data. API restarted with the correction; previous messages are retained. Changed services/v2_routing.py, services/rag_service.py and services/answer_prompt.py; added test_v2_qualification_focus.py.

## Manual exploratory browser testing (2026-11-19)

Used cua_repl to sign into the existing synthetic account, upload a fictional mixed native/scanned two-page resume, submit seven live questions, open a PDF citation, verify stored preference/source and reopen conversation history. Actual outcomes and screenshots: frontend/evidence/manual-browser-20261119-morgan/result.json. Application source was not changed during this testing turn.

Upload/OCR, identity, project numbers, no fabricated telephone number, live PDF opening and preference storage/recall passed. Two education questions falsely abstained. A qualifications follow-up produced a UI timeout but reopening history showed its correct degree answer had already been saved. The project/telephone compound answer was incorrectly labelled answered rather than partial. Reopening history retained text but lost citation chips/status badges. Indexed OCR text on page2 was verified present; absence of source data is not the cause of the education failures.

Current readiness is blocked by these reproducible functional issues. The earlier six phase PASS entries remain their original scoped results, not a claim that these new cases pass. Test document and two test conversations are retained for review; deletion was not exercised. No personal document, production data, protected evaluation evidence, schema or Git history was modified. No further broad audit was performed.

## Additional uploaded document: manual questions (2026-11-19)

Asked four live browser questions about Executive Summary.pdf (18pages,76chunks). Product/target-exam answer passed with page1citation. Broad core-versus-additional-feature answer was incomplete, omitting multilingual and offline/mobile features onpage2. Timeline/team-size answer returned phase names but omitted the page1estimates of2–3years and approximately10–15people. A targeted multilingual/offline follow-up passed with page2citation. All displayed answered; no timeout observed in this run. Evidence: frontend/evidence/manual-executive-summary-20261119/result.json, chat screenshot and source-page2 screenshot. No application code, schema, document or protected evaluation edits; chat retained for review.

## Requested-account resume test (2026-11-19)

Signed into the owner-requested account through the UI and submitted four live resume questions. Credential values were not copied to artifacts. The original Metacube tenure question abstained. Explicit date extraction returned February2022–November2025 with a page1citation, but with a truncated opening sentence. A follow-up still refused to calculate the45-month (approximately3years9months) interval. Readibots was incorrectly described as not established under Metacube, despite the source hierarchy; the absence of separate Readibots project dates was correctly acknowledged. No code/document changes or deletion occurred; new chat retained. Evidence: frontend/evidence/manual-account-resume-20261119/result.json and chat screenshot. These cases remain failures, not a new PASS or fix claim.

## Verified employment-date arithmetic fix (2026-11-19)

The generic retriever can miss employer/date headers, and numeric grounding intentionally rejects numbers absent from cited passages; regeneration feedback explicitly forbids calculation. Added v2-verified-employment-months/1 in services/tenure_calculation.py: a bounded owner-scoped source lookup binds a unique company-header date range, verifies the source match, and computes elapsed months deterministically. The answer labels the result as calculated/approximate and cites the actual PDF chunk. Ordinary numeric validation, legacy v1 behavior and protected scorers remain unchanged. Missing/open-ended/reversed/ambiguous ranges and undated projects do not receive guessed durations. main.run_turn forwards optional calculation provenance.

Verified the exact reported question in the requested account through the browser: answered with February2022–November2025, approximately3years9months(45months), page1citation.11 deterministic tests PASS; one real guarded scratch/API test proves distinct results for two independent owners PASS; all nine focused regression scripts PASS. No new calculation LLM call is needed (ordinary memory lifecycle retains its existing behavior). Evidence frontend/evidence/tenure-fix-20261119/verification.json and browser-pass.png. Old failure evidence remains immutable; this resolves the closed employment-period calculation issue, not the other manual-browser issues. No migrations, rag_db, frozen assets, commits or pushes.

## Targeted evidence coverage and answer reliability (2026-11-19)

**PASS WITH LIMITATIONS for the selected development workload.** This does not replace the broader manual-browser failure status above or establish application-wide/formal evaluation acceptance. The original six-question Executive Summary result and its 12 provider-call receipts remain byte-for-byte unchanged.

### Diagnosed stages and bounded corrections

Source: the requesting tenant's ready 18-page/76-chunk Executive Summary upload. Provider-free before/after traces preceded live testing. Original hybrid retrieval, cross-encoder, thresholds, eight-chunk and 12,000-character limits remain in place.

| Reproduced case | Exact failing stage | Final evidence recovery |
|---|---|---|
| Account database + annual cloud budget | `RETRIEVAL_MISS`: database chunk188 was vector rank7 but lost from the RRF candidate pool | Scoped independent facets retain p9/cloud and p13/account-storage evidence; 2,213 characters |
| Roadmap stated count versus listed phases | `RERANK_FILTER_LOSS`: phase4 chunk196 was RRF rank10/reranker rank6, outside final top5 | Bounded section continuity retains chunks194–196/p15; 2,118 characters |
| All core and suggested additional features | `RERANK_FILTER_LOSS`: best5.232 produced margin cutoff3.232; complementary p2 chunks138/139 were discarded | Actual requested section headings outrank generic summary mentions; p1–2 evidence retained within eight chunks/6,020 characters |
| Public-cloud capital expenditure | `RERANK_FILTER_LOSS`: clear prose166 was vector/RRF rank1, rerank score−9.952 versus cutoff−9.485 | Version2 retains existing p9 prose, with **zero additional searches** for this case; 2,099 characters |
| Correct disagreement prose labelled answered | `ANSWER_VALIDATION_ERROR`: classifier missed the phrase “inconsistency between the stated phase count…” | Narrow v2 source-count disagreement classification |
| Correct first answer → uncited conclusion → false-abstention repair | `GENERATION_OMISSION` / `ANSWER_VALIDATION_ERROR`, not missing PDF data | Strict source-bound count fallback after the existing retry cap; unchanged citation/numeric validation |
| Complete paraphrased feature list labelled partial | `ANSWER_VALIDATION_ERROR`: exact full-heading checks were too strict | Accepted vocabulary alternatives; uncertain unmatched headings are diagnostic-only |

`SOURCE_INFORMATION_ABSENT` is retained for the signed customer contract number. A deterministic ambiguous-question diagnostic is tested; no general ambiguity resolver or full-document absence oracle is claimed. Comparison-table word ordering also produced one baseline literal-coverage gap, which is not proof that its underlying fact was semantically absent.

Implemented policies: `v2-bounded-complementary-evidence/2`, `v2-explicit-request-coverage/3`, and `v2-source-bound-phase-count-comparison/1`. Recovery uses at most three focused local searches, explicit owned/ready source identity, complementary anchors, exact deduplication and bounded adjacent sections. Unknown/unauthorized explicit filenames never fall back to an unfiltered search. The count fallback requires one source page, a unique positive stated count, unambiguous consecutive actual headings, and observed count **greater than** stated count. Equal/incomplete observations never prove agreement. Nothing forces an answer from insufficient evidence.

Development tracing requires both `RAG_DEVELOPMENT_TRACE=1` and an explicit context. Hooks capture vector/lexical/RRF/full rerank results, exact selection/removal reasons, final chunks/pages/characters, continuity recovery, actual prompts, generated answers, validation and coverage. Default traces fingerprint raw payloads, including nested rewritten queries/coverage; raw opt-in artifacts use private0700 directories, exclusive-create0600 files. Ordinary application logs retain identifiers/scores, not source text. A final diagnostics-only privacy correction followed live03 and passed final-tree tests; it changes neither raw-enabled live behavior nor answers.

### Separate development measurements — failures preserved

The 13 questions and literal source-review checks were frozen before live calls. Subset runs reuse original questions/checks without threshold or golden changes. These denominators differ; **they are not one combined pass rate**.

| Immutable run | Actual Gemini calls | Evidence coverage signals | Frozen final-answer completeness signals | Citation / declared-status correctness |
|---|---:|---:|---:|---:|
| `live-01`, all13 questions |28|12/12 (100%)|12/13 (92.31%)|11/13 (84.62%)|
| `live-02`, six focused cases |14|5/5 (100%)|4/6 (66.67%)|4/6 (66.67%)|
| `live-03`, four final cases |10|4/4 (100%)|3/4 (75%)|4/4 (100%)|

The unavailable-information case has no positive-evidence denominator. **52/52 provider calls used; stopped.** All returned `gemini-3.5-flash-lite`. Every request retained its original60-second budget; maximum observed case latency was30.9seconds. No timeout relaxation or mandatory second generation was introduced.

The final strict completeness FAIL remains: its upfront-cost question also requires an **unasked ongoing-cost detail** in the frozen check. The application correctly answers “no upfront cost / avoids CapEx” with authorized citations. This expectation was not changed after observing output. Separate source review supports the actual asked facts in all four final cases; it does not overwrite the strict3/4 metric. Literal signals/citation syntax are not a mathematical entailment proof.

The final conflict answer used the verified **deterministic source-count fallback** after Gemini's raw attempts failed citation validation; this is application correction, not a raw-Gemini PASS. The final long-section answer retained all requested facts after bounded citation repair and distinguished suggested narrative features from table priority. The PDF itself puts analytics in the suggested-additional narrative and marks it MVP in the table; “additional” is not silently equated with “later.”

Offline literal evidence coverage improved8/12→12/12; one of those four initial cue gaps reflects flattened-table ordering, as noted above. The original six live answers also pass unchanged through final-tree validation with zero new provider calls. Real read-only checks with two pre-existing users passed: source owner sees76chunks; the second owner sees neither the source nor its chunks.

### Executed commands and final code verification

```sh
.venv/bin/python -B scripts/v2_reliability_check.py --live --identity live-01
.venv/bin/python -B scripts/v2_reliability_check.py --live --identity live-02 --cases conflict,explicit_negative,comparison,partial,long_section,unsupported --max-provider-calls 16
.venv/bin/python -B scripts/v2_reliability_check.py --live --identity live-03 --cases conflict,long_section,explicit_negative,partial --max-provider-calls 10
```

Do not reuse these identities: the runner refuses overwrites and enforces the exhausted aggregate cap. Provider-free stage replays used `/private/tmp/rag_reliability_stage.py` with new identities `before-recovery`, `after-recovery-01`, `after-recovery-02`, `after-recovery-03`; their original outputs, including the unsuccessful intermediate recovery, remain intact.

**Final-tree verification:17 scripts exit0;158 unittest tests PASS,230 script assertions PASS, one optional separate DB test skipped.** Actual source/citation and two-user scratch checks were executed separately. Each final script command and log is recorded in `v2_evidence/reliability-20261119/final-verification-commands.json` and `final-verification/`; providers were blocked. This includes27 request-coverage,24 recovery/trace,19 completeness and12 runtime tests, plus affected v1/v2 routing, retrieval, citations, abstention, tenure and turn orchestration regressions. The local two-worker API was reloaded with final code; `/api/v2/health` returned200. No UI actions or chat/memory writes were used for this workload.

Evidence: `v2_evidence/reliability-20261119/` contains the predeclaration/frozen checks, stage traces, all three immutable run results, source-review notes, exact SDK receipts/runtime hashes, final regression logs and integrity record. At that initial closure, the two post-live runtime-file differences were the documented diagnostics-only privacy changes in `rag_service.py` and `evidence_trace.py`; the deterministic checks above covered those bytes. The subsequent current-tree revalidation and additional changes are recorded below.

All source DB operations used the restricted scratch role and verified `current_database() = rag_test_scratch` before data access. No rag_db access/write, production quarantine, backfill, migration, protected/held-out evaluation, human-review edit, staging, commit or push occurred. All44protected assets and pre-existing staged bytes remain unchanged; unrelated working-tree files were preserved.

Remaining limits: the frozen overstrict ongoing-cost expectation remains reported FAIL; this modest development set cannot certify arbitrary PDF layouts/paraphrases or overall answer quality. Existing broader browser education/timeout/history issues remain unclosed by this task. Formal evaluation/human acceptance and frozen v1 policies are unchanged.

### Execute-now A–E acceptance revalidation (2026-11-19)

**Selected-workload functional gates A–E PASS; the strict frozen metric limitation remains unchanged.** The existing A–E implementation was inspected and exercised rather than rebuilt. This is not broader application or formal evaluation acceptance.

Phase A began with current orchestration, page recovery, answer semantics/citations, retrieval, fusion, reranker and context-assembly inspection. The original real roadmap candidate/source snapshots reproduce loss of chunks195/196 below the adaptive threshold0.2985; current orchestration retains the same original source/page identities and recovers chunks194–197, four chunks/2,548characters. This replay uses no model or DB network call. The earlier before/after coverage and three live outcomes above remain separate and immutable.

Two additional genuine gaps were reproduced and corrected:

- **Deadline enforcement at the answer stage:** a deterministic generator returning after the original budget expired could trigger a second repair invocation. `services/answer_service.py` now checks the original deadline before each attempt, immediately after generation and before fallback. The new clock-controlled regression in `test_v2_answer_completeness.py` observes one invocation and a propagated deadline instead of a post-deadline repair. Production provider wrappers already checked deadlines; this closes the orchestration boundary as well. Prompts, retry count, numeric grounding and citation policies are unchanged.
- **Exact fusion rejection attribution:** `hybrid_search_service.py` previously labelled every missing candidate `rrf_pool_limit`, including exact-content deduplication before the pool filled. `services/rrf_service.py` now records full fusion rankings and authoritative `rrf_selection` decisions, distinguishing `duplicate_content` from actual pool-limit losses. Hybrid tracing references that decision stage and labels interleave caps separately. Ranking scores, selected chunks and original citation identities remain unchanged. Five focused regressions in `test_v2_fusion_trace.py` verify both reasons and output equivalence with tracing enabled/disabled.

| Gate | Current evidence |
|---|---|
| A — Traceability | Original roadmap loss reproduced; fusion dedup/cap attribution corrected; actual rankings, filter thresholds, source identities and recovery are recorded privately. |
| B — Evidence coverage | Same-page recovery preserved; explicit owner/ready-source scope and eight-chunk/12,000-character budgets pass. All13 saved source bundles match current owned scratch DB rows by ID, page and content. |
| C — Answer completeness | Coverage policy3 passes27 tests, including the exact paraphrase failure and missing multilingual/offline cases. All13 latest recorded application answers replay unchanged through the current contract; keyword signals are not treated as entailment proof. |
| D — Grounding and safety | Current explicit-negative, partial, abstention, conflict, citation/numeric, deadline and deletion-fencing regressions pass. Actual two-user scratch read isolation passes: owner76source chunks, other user0. |
| E — Real verification | Current focused suites pass; prior bounded actual Gemini outcomes remain verified and preserved. No additional provider run is needed for the deadline/trace-only changes. |

Current-tree focused verification: **19 unique scripts PASS;154 unittest tests and304 script assertions PASS.** Counts are deduplicated by script, not summed across repeated agent checks. Specific current results include recovery/trace24, page continuity7, coverage27, answer completeness20, runtime12, fusion trace5, recorded-case acceptance3 (all13bundles), turn flow7, provenance12, abstention17, abstention policy7, deadlines6 and budget7. Existing retrieval/answer/citation/reliability and delete-decision/error/ID scripts account for304 additional assertions. Child argv, counts, logs and source digests are recorded in `v2_evidence/reliability-20261119/execute-now-verification/combined-test-results.json`, `lead-tests.json`, `agent1-gate-summary-01.json` and `agent4/focused-commands.json` / `summary.json`. Deterministic suites block provider/network I/O or use mocks; the separate actual DB checks verify `current_database() = rag_test_scratch` before source access and perform no writes.

The current **offline recorded-response replay**, not a new live evaluation, measures evidence12/12, strict factual cues12/13, citation/status13/13. The lone strict cue failure is still the unasked ongoing-cost expectation; neither its golden check nor any historical verdict was changed. Latest recorded source-count answers include the explicitly disclosed deterministic fallback above. Existing real-provider total stays **52; new calls0**. The previous13-/6-/4-case live denominators and results must not be replaced by this offline replay.

The API was gracefully reloaded with these source changes; localhost health returned200. No UI actions, DB writes, migrations, protected/held-out execution, human-review edits, staging, commits or pushes occurred. Ninety-three historical evaluation files and all44protected assets retain their hashes. Pre-existing staged bytes and unrelated tracked/untracked work remain intact; `git diff --check` passes. Final current-task integrity/source hashes are in `execute-now-verification/final-integrity.json`.

No new verified application defect remains in this selected workload. Remaining limitations are the preserved strict development-oracle mismatch, the lack of general semantic-entailment certification, and the previously documented broader education/timeout/history issues outside these selected cases. No project-wide readiness claim is made.


## Targeted browser reliability closure (2026-11-20)

**PASS for all four retained defects.** The completed A–E workload was not reopened. Original manual failures, original six-question Executive Summary evidence, all 52 historical reliability provider receipts and failed experiments remain unchanged.

| Defect and exact retained regression | Actual before / root cause | Verified after |
|---|---|---|
| `What is the qualifications of Morgan Vale?` | Historical fresh-chat abstention. Existing academic recovery now retrieved chunk128/page2, but discarded the name-bearing chunk127/page1; live generation explicitly disputed the identity association. | Same-document identity continuity retains the actual name passage alongside the degree, within existing packing limits. Live answer: Bachelor of Engineering in Computer Engineering, Sample Institute of Technology, 2016–2020; `answered`, original page2/S1. |
| `In Browser_Check_Morgan_Vale.pdf, what is listed under EDUCATION? Please give the degree, institute and study dates.` | Recovery was not invoked for this explicit-section shape. Real offline trace: chunk128/page2 score−7.355 dropped below−4.075 threshold, leaving career chunk127/page1. After recovery, real Gemini still abstained because the prompt identified the requested filename only by a UUID. | Unique owned filename scope invokes academic recovery; prompt headers include the authorized filename as quoted data while citation UUID/chunk/page identities stay unchanged. Exact live answer contains the degree, institute and 2016–2020, `answered`, page2/S1. |
| Timeout while answer already committed | Two independently committed message inserts, then synchronous extraction/summary before HTTP return; no stable turn identity or recovery endpoint. BFF120s/API60s do not imply rollback of an already committed answer. | UUID turn IDs; atomic user/assistant pair plus metadata and content-free retry receipt; existing cross-process conversation lock; owner-scoped read reconciliation. A real browser POST was aborted **after** GET recovered the committed result, while a controlled5s post-commit delay kept POST unfinished. Reopening/refresh recovered it; retry returned the same answer with exactly2 messages, no new generation. Deadline values unchanged; the180s client window performs reconciliation reads, not extra generation. |
| Exact project-plus-phone question: `According to Morgan Vale’s resume, how did the Atlas project change report preparation time? Also, what telephone number is listed for Morgan?` | Page1 supports40→12minutes; source has no telephone number. Existing prefaced-gap regression passed, but new live wording “telephone number listed for Morgan” was misparsed as an uncited fact. At the experiment's finite call cap, safe fallback dropped that clause and incorrectly returned `answered`; this FAIL is preserved. | Narrow v2 informational-head parsing recognizes the reporting participle without treating excluded services as gaps. Exact raw-answer regression retains the uncited gap in one attempt; fresh live response is `partial`, states40→12minutes, does not invent a phone, and retains page1/S1 citation. Explicit negative-service regressions pass. |
| Reopened history | API only serialized id/role/content; browser badges/citations existed only in a temporary response map. | `messages.answer_metadata` and turn identity persist atomically. History/recovery validate each citation against tenant-visible ready documents and its original chunk/page. Browser refresh preserves answer text, status badges, source IDs, page2/page1 chips and same-origin PDF links. All three actual citation-click navigation requests and PDF responses verified200; headless PDF plugin rendering is not claimed. |

Source changes: `services/v2_routing.py`, `services/v2_source_labels.py`, `services/rag_service.py`, `services/answer_semantics.py`; `services/v2_turn_results.py`, `main.py`, `backend/v2/app.py`, `backend/v2/schemas.py`; frontend chat hydration, API bindings and `chat-reconciliation.ts`. Additive migration008 is necessary because the original schema had neither durable metadata nor retry identity; applied **only** after actual `current_database()='rag_test_scratch'`. New receipt-table RLS is forced; all existing ownership/RLS policies are preserved. Receipts contain question hashes/IDs, not deleted text; physically removed turns return410 rather than regenerate. No automatic startup migration, production migration or legacy backfill.

Final executed checks (logs and machine-readable commands in `v2_evidence/browser-closure-20261120/test-summary.json`):

- Deterministic unit command: `DATABASE_URL=postgresql:///rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 RAG_V2=0 .venv/bin/python -B -m unittest test_v2_qualification_focus test_v2_source_labels test_v2_answer_completeness test_abstention_contract test_abstention_policy test_v2_routing_recovery test_v2_request_coverage test_assignment_flow test_assignment_provenance test_local_v1_deadlines test_local_v1_budget -q` — **125/125 PASS**.
- `RAG_V2_DB_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m unittest test_v2_browser_contract test_v2_integration -q` — **12/12 PASS**, real guarded scratch: atomic rollback, retry identity/conflicts, history, two-owner denial, excluded/physically removed-turn fencing and wrong-page suppression.
- Guarded `app_url()` launcher with `RAG_V2_DB_TESTS=1 RAG_OCR_REAL=1 RAG_OCR_TESSDATA=data/v2_models/tessdata`, running `test_v2_workers` and `test_v2_ocr` — **32/32 PASS**, including independent-process queue claims/crash recovery and actual offline OCR word recall1.000, numeric facts2/2, original page2. **169 unique Python tests PASS, zero skips** across these final groups.
- Same offline environment, `.venv/bin/python -B` for `test_context_and_citations.py`, `test_stage6_answer.py`, `test_p1_d4_delete_decision_errors.py`, `test_p1_d5_delete_ids.py` — **62+66+54+40 =222 checks PASS**. All four were rerun after the final reporting-participle edit.
- `npm --prefix frontend test` — **19/19 PASS**; `npm --prefix frontend run typecheck` and `npm --prefix frontend run lint` — PASS.
- From frontend: `RAG_BROWSER_CLOSURE=1 RAG_E2E_EXTERNAL=1 node_modules/.bin/playwright test tests/browser/reliability-closure.spec.ts --project=desktop-chromium` — **1 suite PASS, all3 exact question journeys verified**, including refresh, PDF navigation and duplicate retry. Final explicit education generations are in `browser-confirmation-20261120/live-01`; final partial generation is in `browser-final-20261120/live-01`. The final suite reopens the two already verified education answers rather than spending new provider calls.
- After removing test-only provider/owner restrictions and delay, the ordinary API was restored with2 workers. `RAG_BROWSER_READONLY=1 RAG_E2E_EXTERNAL=1 node_modules/.bin/playwright test tests/browser/reliability-closure.spec.ts --project=desktop-chromium --grep 'ordinary two-worker'` verifies all3 reopened/refreshed turns against this ordinary preview, with **zero chat POSTs/new generation**. Two durable index/OCR workers restored.

New live provider accounting: **17 actual SDK calls**, all returned `gemini-3.5-flash-lite`: initial closure family9/12 (including interrupted PDF-viewer test-harness failures and genuine filename abstention), separately predeclared education confirmation6/6 (two education PASS, preserved partial FAIL), separately predeclared partial confirmation2/3 (PASS). No identity or original outcome was overwritten; no official/frozen evaluation policy changed. Raw synthetic traces/screenshots and call receipts are restricted scratch artifacts under the three new `v2_evidence/browser-*20261120` directories. The original52 receipts are historical and are not part of these17 calls.

Remaining limits: messages written before migration008 have no authoritative structured metadata; their old text is preserved and citations are **not** inferred from prose. The historical failed messages remain failed; new corrected turns carry verified metadata. The observed post-commit disconnect class was reproduced with controlled delayed summary work, rather than waiting120seconds for a fresh provider stall. No new verified defect remains in these four selected contracts. General model quality, unrelated previously recorded manual findings and formal human/evaluation acceptance are not certified by this closure.


## Grey & black AI workspace implementation (2026-11-20)

**PASS — implemented in the existing Next.js frontend, not a mockup.** Five engineering agents used separate shell, chat, document, management and integration-test ownership; the lead integrated shared primitives, dependencies and real verification. The existing RAG pipeline, typed backend contracts, tenant/RLS rules, employment calculation, evidence coverage, stable-turn persistence and historical evaluation records were preserved.

### Screens and source changes

- **Shell, overview and authentication:** exact requested dark palette (`#171717/#202020/#262626/#303030/#404040`, light primary button, neutral text/border tokens), coherent persisted light appearance, system typography; collapsible desktop sidebar, focus-trapped mobile Sheet, new chat, searchable recent conversations, real rename/delete menus, account/logout and role-gated administration. Dark is the default. Files: `frontend/app/globals.css`, `app/layout.tsx`, `app/page.tsx`, `app/(workspace)/dashboard/page.tsx`, `components/workspace.tsx`, `components/auth-form.tsx`.
- **Chat:** restrained assistant layout and subtle user bubbles; safe Markdown/GFM, code and response copying; responsive bottom composer, auto-resize, Enter/Shift+Enter/IME behavior, honest pending states, attachment upload/index-status polling, owned-source library and explicit filename prompt insertion. No fake token streaming or document-ID filter unsupported by the API. Original answer status, citation identities and authorized page navigation persist through authoritative history hydration. Existing retry reconciliation/UUID behavior is retained. Files: `components/chat-workspace.tsx`, new `components/chat-markdown.tsx`.
- **Documents, source pages and activity:** compact searchable/filterable tables, validated drag/drop upload, actual native/OCR metadata and job progress, confirmed delete/replace/cancel and supported retry controls, original-page navigation. Unsupported document rename is not presented. New local PDF.js canvas renderer replaces browser-plugin-dependent embedding: credentialed same-origin source bytes, bundled local worker, original pages, responsive aspect ratio, bounded25MB input/6million canvas pixels, cancellation and sanitized loading/error fallback. No CDN or executable PDF annotation/form layer. Files: document routes, `components/document-detail.tsx`, new `components/pdf-preview.tsx`, `components/document-status.tsx`, `lib/document-ui.ts`, activity route.
- **Memories, settings, conversations and admin:** saved-memory search, actual provenance/source details and confirmed delete-and-forget; profile/session/appearance/privacy; compact conversation search and accessible rename/delete; real user-role/status/reset controls with confirmations. Provider/model configuration is truthfully server-managed; no fake selector, account-self-deletion or audit viewer without a backend contract. Files: the four corresponding pages under `frontend/app/(workspace)/`.
- **Shared components and dependencies:** accessible shadcn-style Radix Dialog, AlertDialog, Sheet, DropdownMenu and Tabs, plus Table, Skeleton, Progress and contrast-correct Button. Added React Markdown/GFM and local PDF.js. Npm audit exposed existing Next.js vulnerabilities; upgraded Next.js and its ESLint config together from16.2.10 to16.4.6, with lockfile and generated `next-env.d.ts` updated. Next dev also generated `frontend/AGENTS.md`; it is retained, and its bundled client/server, lazy-loading and router guides were checked. Final audit: **0 vulnerabilities**. No competing UI framework.

### Actual findings and before/after verification

| Finding | Before | Final evidence |
|---|---|---|
| CSS overrides and long-chat geometry | Unlayered global styles forced30px chat headings and1px textarea borders; absolute screen-reader status text stretched a720px viewport to918–925px. | Base defaults are layered; explicit utilities win. Desktop heading18px/mobile16px, textarea border0/transparent. Positioned message log clips its own absolute descendants: document/body height720/720 desktop and851/851 mobile, while messages remain scrollable and the composer remains separate. Measured receipts retained. |
| Native PDF embedding | First real journey passed HTTP/source-link checks, but visual inspection showed a blank native PDF object. Its original run/result/screenshots remain unchanged. | Local canvas renderer paints original page2→1→2 and mobile page2, with actual nonblank pixel checks. Desktop930×1116; resized mobile324×388 with preserved aspect ratio. **Zero remote requests/provider calls** for this check. A fresh final live journey also waits for rendered PDF completion. |
| Two education abstentions | Historical failure records preserved; earlier backend correction remains in place. | New UI actually reopens both retained real-Gemini answers: degree, Computer Engineering, Sample Institute of Technology and2016–2020; `answered`, original document/chunk/page2 citations. No regeneration of historical answers. |
| Timeout after commit | Previously closed real post-commit-disconnect evidence remains unchanged. | New UI browser fixtures reject the POST transport, recover the already committed authoritative result via the **same UUID**, render it once and preserve history. Twelve actual scratch API contracts verify committed-turn replay/conflicts/rollback/isolation/deletion fencing. The prior real disconnect receipt is not relabelled as a newly induced provider stall. |
| Compound project/phone status | Historical `answered` failure preserved. | Actual retained source-supported40→12minutes plus unavailable-phone answer reopens as `partial` with page1 citation in the new UI. No phone fabricated and no model call for this verification. |
| History metadata | Previous missing-chip/status bug remains closed. | Real fresh Gemini answer and all3 retained results survive reopen/refresh with status, citation IDs, document identity and original pages. No metadata manufactured from prose. |
| Initial regression harness failures | Global link selectors matched sidebar+main duplicates; modal `aria-hidden` made a zero-link assertion succeed before DELETE committed. A running queue worker also took the deterministic API test's fixture lease. | Tests now scope the intended main content and wait for the actual DELETE response before404 checks; deterministic lease tests ran with background workers temporarily paused, then both workers were restored. Original failing logs/traces remain private. No backend or deletion contract was weakened. |

### Executed results

Exact commands and totals: `v2_evidence/ui-grey-20261120/acceptance-summary.json`.

- `npm --prefix frontend run build` — **PASS**, final production build including PDF worker (`production-build-pdf-final.log`).
- `npm --prefix frontend run typecheck`, `npm --prefix frontend run lint` — **PASS**.
- `npm --prefix frontend test` — **22/22 PASS**, including all existing frontend API/CSRF/body-budget/gateway/reconciliation security tests and3 document-helper checks.
- `cd frontend && npm audit --json` — **0 vulnerabilities** (`npm-audit-pdf-final.json`).
- `RAG_V2_DB_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m unittest test_v2_browser_contract test_v2_integration -q` — **12/12 PASS**, guarded scratch; deterministic queue-claim test isolated from background workers.
- Production Playwright desktop/mobile: workspace, chat composer, management, history-reliability and existing real-api specs — **38/38 PASS**:36 contract/UI fixtures and2 actual scratch login/upload/isolation/history/delete journeys. Tablet widths, mobile drawer focus/Escape, keyboard input, Markdown/code copying, dialogs, contrast states, light-mode persistence, failed/partial/abstained badges, errors and long conversations covered. `production-browser-tests-pdf-final.log`.
- Actual original-page PDF pixel/mobile-resize verification — **1/1 PASS**, original pages2→1→2, authenticated source, no remote requests (`pdf-browser-tests-verified.log`, `pdf-render-result-verified.json`).
- New UI actual read-only retained education/partial/history verification — **1/1 PASS**,3 retained real results, original pages2/2/1, zero new chat POSTs (`retained-browser-result.json`).
- Final production **login → scanned PDF upload → actual local OCR/indexing → real Gemini → citation/PDF → reopen/refresh → second-user404 isolation → document/conversation deletion** — **1/1 PASS** under fresh identity `rag-grey-ui-20261120-live-02` (`real-live-browser-tests-final.log`). Actual OCR method `pymupdf-tesseract-fast-4.1.0`; Gemini returned83credits/17days, `answered`, owned original page1 citation; resources subsequently404. **41 unique selected Playwright cases passed** across these groups.

Provider accounting: initial identity live-01 used2 calls; fresh final identity live-02 used2 calls. **4 actual SDK calls total / aggregate cap6**, all returned `gemini-3.5-flash-lite`. Both receipts and outcomes preserved separately. Initial native-preview limitation and its fix are recorded separately in `native-preview-assessment.json`. The historical52 reliability receipts, original six-question Executive Summary records and all earlier failures remain unchanged. No held-out evaluation executed.

### Real browser screenshots

These use real scratch data/provider responses, not intercepted chat responses:

- [Desktop chat](frontend/evidence/rag-grey-ui-20261120-live-02/chat-desktop.png)
- [Mobile chat](frontend/evidence/rag-grey-ui-20261120-live-02/chat-mobile.png)
- [Tablet chat](frontend/evidence/rag-grey-ui-20261120-live-02/chat-tablet.png)
- [Mobile navigation drawer](frontend/evidence/rag-grey-ui-20261120-live-02/mobile-sidebar.png)
- [Document library](frontend/evidence/rag-grey-ui-20261120-live-02/documents-desktop.png)
- [Rendered PDF source](frontend/evidence/rag-grey-ui-20261120-live-02/pdf-preview-desktop.png)
- [Original resume page2, desktop](frontend/evidence/rag-grey-ui-20261120-live-01/pdf-rendered-page2-desktop-verified.png)
- [Original resume page2, mobile](frontend/evidence/rag-grey-ui-20261120-live-01/pdf-rendered-page2-mobile-verified.png)
- [Other-user source denied](frontend/evidence/rag-grey-ui-20261120-live-02/isolated-source-denied.png)

### Integrity and remaining scope

Normal production preview restored at127.0.0.1:3000 against the ordinary two-worker API8000; temporary API8001 stopped and temporary read-test session removed. Two independent durable workers remain available, with actual scratch-identity checks. Existing user data preserved; exact new synthetic resources left by early test failures were cleaned through their owner/API, while failure records were retained. Git index/HEAD and all44 protected assets preserved; no backend source changes, RLS/authentication weakening, schema migration, `rag_db` access, staging, commit, push or frozen/human-review/evaluation edits.

**No remaining verified blocker for this requested local UI scope.** Backend-unsupported controls remain absent or read-only as described. Old pre-metadata messages remain text-only; citations are not invented for them. Synthetic test accounts remain as test fixtures after their document/conversation resources are deleted. This is not a claim of formal evaluation acceptance, universal PDF compatibility or cloud/production readiness.

## Deployed request resolution and answer completion · 25 November 2026

Compared nine live backend file hashes with clean checkout `5230d79d` before editing. Release `20261125-03` was the baseline. The authenticated development journey uses the synthetic two-page employee record that was already indexed. Its four questions and expected facts, pages and statuses were frozen before submission. [Development policy](deploy/aws/tests/request-reliability-policy.json)

| Reproduced behavior | Cause and change | Verification on the corrected code |
| --- | --- | --- |
| A joining answer followed by “How many months?” abstained. A challenge could repeat stale dates from an earlier assistant turn. | Routing lost the prior user’s requested operation. The request contract resolves the subject, units, document and recent user turns, then rechecks the current authorized evidence. A named employee must match the record or a heading in the same document. | The synthetic July 2023–October 2024 record gives 15 months. After replacement with a November end date, a challenge gives 16 months and cites the replacement chunk. An unrelated employee’s dates are withheld. |
| A rewrite dropped an explicit filename and allowed a memory answer. A scoped first search with zero retained chunks missed separately retrievable fields. | Scope now comes from the original or explicitly inherited user selection, before rewriting. Missing files stay closed. An owned file still processing returns a readiness error. An authorized compound request can use the existing bounded facet searches after an empty first pass. | The missing-file case made zero search or generation calls. The two-page budget and headcount fixture recovered and cited chunks 5 and 7 with one initial search and two scoped searches. |
| A citation and three field labels passed as a complete answer. A number supplied in a question or present with another unit could also pass. | The answer stage checks explicit field/value bindings, source units and the requested operation. Verified tenure still uses policy `v2-verified-employment-months/3`. Its proof now includes date character offsets. One shared repair allowance remains. Unresolved fields are named. | Unsupported employment arithmetic and component-as-total claims were rejected. A supported negative remains answered. A mixed request retains its grounded portion and reports partial. |
| A superseded 14-credit allowance was accepted even with its 19-credit official correction in context. | A narrowly matched current-amount lookup checks the named subject, original amount, replacement, unit and explicit supersession. Competing or unrelated amendments do not select a winner by rank. | The synthetic amended allowance returned 19 credits with the correction’s original reference. Comparisons between independent values and unresolved source conflicts have separate tests. |
| A failed reranker produced an evidence abstention. A timed-out repair could return a previous incomplete answer. Reopening could retain derivation metadata after a source disappeared. | V2 preserves operational errors and the original deadline. History filters derivations against both the live operand citation and any separate person-identification citation. | Injected search/provider failures produced an error or exception. Expired rewriting stopped before classification. Removing either required source invalidated the stored proof on read. |

The predeclared offline matrix covers 26 dimensions through 24 distinct tests. On the baseline, 19 passed. Four failures reproduced application behavior and one reflected the newly specified document-readiness SQL contract. All 24 passed on the corrected backend. Two supplemental tests also passed and use a real page boundary in the synthetic retrieval fixture and a comparison with only one entity delivered. The larger final offline run passed 247 tests. Six affected legacy scripts reported 287 passing checks in total. The native Linux image passed 87 focused tests with networking disabled. These test groups overlap.

Reproduce the offline results on a scratch-only process configuration:

```sh
export DATABASE_URL=postgresql://none@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
.venv/bin/python -B -m unittest test_v2_request_contract test_v2_request_orchestration test_v2_request_journey test_v2_verified_task_completion test_v2_present_tenure test_v2_tenure_calculation.TenureTests test_v2_answer_reliability_hotfix test_v2_routing_recovery test_v2_evidence_recovery test_v2_request_coverage test_v2_answer_completeness test_v2_page_context test_v2_qualification_focus test_v2_reliability_runtime test_v2_auth test_abstention_contract test_abstention_policy deploy.aws.tests.test_provider_guard -q
for suite in test_stage6_answer.py test_answer_phase3.py test_b3_answer_reliability.py test_b2_citation_evidence.py test_llm_timeout.py test_context_and_citations.py; do .venv/bin/python -B "$suite" || exit 1; done
.venv/bin/python -B -m unittest test_stage9_v2_integrity.EvaluationIntegrity.test_protected_assets_are_byte_identical -q
```

**Authenticated Chromium results on AWS**

| Frozen question | Result rendered in chat | Status | Cited page | Time to visible answer | Metered SDK attempts during turn |
| --- | --- | --- | ---: | ---: | ---: |
| When did Mira join Cedarbridge Labs? | February 2022 | answered | 1 | 23.967 s | 0 |
| How many months? | Approximately 45 months from February 2022 to November 2025 | answered | 1 | 2.650 s | 1 |
| Are you sure? | The application re-read the employment record and recalculated 45 months | answered | 1 | 0.610 s | 0 |
| Using only RAG_E2E_Check_20261125.pdf, what are the total project budget and the project team size? | “Total project budget: 83,000 credits [S1]. I couldn't establish the following requested information from the available evidence: team size / staffing.” | partial | 2 | 4.647 s | 3 |

Required source page recovered **4/4**. Requested task fulfilled **4/4**. Citation and calculation checks passed **4/4**. Final status matched **4/4**. The browser submitted four unique turns and reopened all eight messages. The citation chips and badges survived reload, a chip opened the authenticated original PDF, and both cited pages rendered. A second signed-in test account’s document and conversation lists contained neither test object. [Verified conversation](https://rag-demo.3-109-17-151.sslip.io/chat?conversation=1e0d1b40-6583-4b5a-9d51-ede0b248394f)

Run `aws-demo-20261125-live-01` used **4 of 12** exclusive SDK slots. All four receipts succeeded on `gemini-3.5-flash-lite`, totaling **3,662 provider-reported tokens**. Turn counts use receipt timestamps from the isolated conversation and include memory housekeeping. No new upload, model download, AWS resource, instance upgrade or migration was needed.

Release `20261125-04` is active. Its backend image ID is `sha256:87021e0f65562ccb7c5c1b46f4a0f164fdf4b721072d1788128fe587a355c7cc`. Ten runtime module hashes matched the final local files both during the browser test and after restoring the ordinary API entry point. All five services were healthy. After the test guard was removed, a second authenticated Chromium readback verified the same four saved answers, citations and badges on the ordinary service with zero new chat submissions. The public login and health endpoints returned HTTP 200. Release `20261125-03` and its configuration remain available for rollback. Two initial native test harness attempts stopped before rollout because the test mount lacked read permissions and then the shared test-safety module. Both logs were preserved. The successful native run used the same image.

Evidence is in the restricted `deploy/aws/private/request-journey-20261125-01/` directory. All 44 protected file hashes passed the existing integrity test. The local scratch PostgreSQL instance was unavailable, so its optional two-owner SQL suite was not repeated. Two-owner visibility was exercised on AWS. General paraphrases, unstructured contradictions and arbitrary arithmetic remain outside the deterministic checks. Formal held-out acceptance remains separate.
