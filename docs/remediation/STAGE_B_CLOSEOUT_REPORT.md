# Stage B closeout report (B1–B4)

Date: 2026-11-12. Stages C and D were not started. No live Gemini evaluation was run. No migration was applied. Claude did not stage, commit or push anything (see §12 for repository events not caused by Claude).

## 1. B1 audit summary (`B1_ANSWER_QUALITY_GROUNDING_AUDIT.md`)
B1 traced the query→answer flow end to end, including `services/rag_service.py`, context assembly, the prompt, generation with retries, citations and fallback. It recorded 12 findings with file and line references and deterministic offline probes. The confirmed defects:
- **F1 (H):** a `[MEMORY]` tag bypassed citations on DOCUMENT questions.
- **F2 (H):** an uncited claim was accepted next to a cited one.
- **F3 (H):** repair kept a claim whose only citation was fabricated.
- **F4 (M):** a `[DOCUMENT]` claim was accepted when nothing had been retrieved.
- **F6 (L):** file mentions matched by suffix.
- **F7 (L):** page mentions were not paired with the cited document.
- **F8 (M):** chunk text could forge source headers in the prompt.

Gaps found: F5 (two abstention phrase lists), F9 (a classify/rewrite provider failure aborted the answer). Limitations: F10 (no semantic support check), F11 and F12.

## 2. B2 implementation summary (`B2_CITATION_EVIDENCE_REPORT.md`)
- **Claim coverage:** a new blocking issue, `uncited_claim`.
- **Repair:** drops uncited claim sentences after removing invalid refs.
- **Citations required:** a DOCUMENT question with sources always needs citations, whatever the tag.
- **Abstention phrases:** one shared `ABSTAIN_PHRASES` list.
- **Markers after a full stop:** attached to the preceding sentence.
- **Mentions:** exact file-name match; page mentions paired with the sources cited in the same sentence.

Files: `services/citation_service.py`, `services/answer_service.py`.

## 3. B3 implementation summary (`B3_ANSWER_QUALITY_REPORT.md`)
- **F4:** `document_claim_without_sources` rejection, with feedback and a bounded retry.
- **F8:** display-only neutralisation of `[S#]` markers inside chunk content (`context_assembly_service.py`).
- **F9:** `rag_service.ask_question` falls back to type DOCUMENT if classification fails and to the original query if rewriting fails.
- The 12 required scenarios are covered with fake LLM and fake retrieval.

## 4. B4 evaluation summary (`B4_ANSWER_QUALITY_EVALUATION_REPORT.md`)
- **Offline only.** `validate.py` → VALID (160 cases).
- **Previous dev baseline (live, before Stage B):** Tier 1 41/47 (87.2%), Tier 2 28/42 (66.7%). This is development data, not independent validation.
- **Replay:** the 47 recorded Tier-1 dev answers, replayed through the Stage B pipeline, gave **0 changes** (41/47 → 41/47). That means no measured regression and no measured improvement.
- **Failure analysis:** Tier 1 failures are mostly conflict handling; Tier 2 failures are mostly retrieval (10/14 have gold page recall below 1).
- **Not done yet:** the held-out split has not been run and nothing has been human-reviewed. A live procedure is documented but **not executed**.

## 5. Files changed in Stage B (all uncommitted)
- **Modified:** `services/citation_service.py`, `services/answer_service.py`, `services/context_assembly_service.py`, `services/rag_service.py`, `run_tests.py` (registered 2 unit tests).
- **New:** `test_b2_citation_evidence.py`, `test_b3_answer_reliability.py`, and the reports `B1_ANSWER_QUALITY_GROUNDING_AUDIT.md`, `B2_CITATION_EVIDENCE_REPORT.md`, `B3_ANSWER_QUALITY_REPORT.md`, `B4_ANSWER_QUALITY_EVALUATION_REPORT.md` and this report.
- **Untouched:** datasets (`eval/phase35/data_*.py`), recorded results, thresholds and the database. Earlier work was preserved; no existing test was weakened, and the three existing answer tests pass unchanged.
- **Outside the repo:** probe, replay and mutation scripts and logs live in the job's temp directory, outside the repo.

## 6. Tests added and executed
- `test_b2_citation_evidence.py`: 35 PASS. `test_b3_answer_reliability.py`: 34 PASS. Both are unit tests and registered.
- Focused runs during development: `test_answer_phase3.py`, `test_context_and_citations.py` (62/62) and `test_answer_scoring.py` all pass.
- `validate.py` VALID.
- Offline replay: 47/47 unchanged.

## 7. Mutation results (executed; repo untouched)
B2 rules, as `test_b2` / `test_b3` FAIL counts:

| Mutation | `test_b2` | `test_b3` |
|---|---|---|
| `uncited_claim` not blocking | 3 | 3 |
| tag bypass restored | 3 | 8 |
| repair keeps uncited sentences | 2 | — |
| marker re-attachment removed | 1 | — |
| suffix document match restored | 1 | — |
| page check against any source | 1 | — |
| invalid refs accepted | 4 | — |
| abstention list not shared | 2 | 2 |

B3 rules, as `test_b3` FAIL counts:

| Mutation | `test_b3` |
|---|---|
| `document_claim_without_sources` disabled | 3 |
| forged markers shown | 1 |
| rewrite failure re-raised | 2 |
| classification failure re-raised | 2 |

All 12 mutants are caught.

## 8. Full-suite result (single run)
Command: `.venv/Scripts/python.exe run_tests.py --clean` (the documented default: unit + integration). It was run **exactly once**.
- **34 run / 34 passed / 0 failed**, exit code **0**: 15 unit and 19 integration tests, including `test_b2_citation_evidence.py` and `test_b3_answer_reliability.py`.
- Smoke-only passes: 2 (`test_similarity.py`, `test_memory_storage.py`).
- Not run by category: 18 (live/manual), so there were no Gemini or network calls.

## 9. `rag_db` fingerprint (established read-only procedure `run_tests.fingerprint`)
| Table | Before | After |
|---|---|---|
| conversations | 261, `7f4fb6de…70d5` | same |
| messages | 1340, `502d43b7…15c8` | same |
| conversation_memories | 127, `88d8b76a…0f38` | same |
| memory_sources | 93, `7d877c75…6a36` | same |
| document_chunks | 9, `711aa64f…5cb` | same |

The separate pre/post captures are identical, and the runner also reported `fingerprint unchanged : True`. There is no evidence of any `rag_db` modification.

## 10. Remaining findings
- **No semantic support check (F10).** A wrong claim with a valid-looking citation, or a claim taken from injected text inside a real passage, is accepted. This is pinned in the tests.
- **Heuristic rules.** The uncited-claim rule, the abstention and meta exemptions, and `classify_status` are heuristics. With a live model they may add bounded regenerations and shorten repaired answers; this is unmeasured.
- **F8 is partial.** Only `[S#]` markers are neutralised; other forged text remains visible to the model.
- **F12 still open.** A wrong MEMORY classification still skips retrieval.
- **Conflict handling** (the main Tier-1 failure) and **retrieval misses** (the main Tier-2 failure) are not addressed in Stage B.
- **Carried over from Stage A:** no total-chunk limit; unspaced CJK; P2-04 random-byte flakiness risk; embedding model identity is not stored; negative `top_k` on the direct retrievers.

## 11. Human review and live evaluation still required
- **Human review:** a named reviewer, not the dataset author, reviews and freezes the held-out cases, then labels failures and a sample of passes.
- **Live dev re-run with the Stage B code:** copy the baseline result files first, because `--fresh` deletes them.
- **Live held-out run:** once, for Tier 1 and Tier 2.
- **Cost:** about 465 Gemini calls for held-out. The full procedure is in B4.
- **Approval:** none of this runs without your explicit approval.

## 12. Git status
- **At Stage B start:** HEAD was `2a0e06f`. 21 Stage A and earlier files were already **staged in the index**. At Stage A closeout the index had been empty, and **Claude did not run `git add`**.
- **During the single full-suite run:** a new commit **`67aa30a` "Add comprehensive tests for PDF ingestion and retrieval functionality"** appeared, authored as the repository owner (2026-11-12 15:23:46 +0530). It contains exactly those 21 staged files: the A1–A4 and P2-04/P2-05 code, tests and reports, and `STAGE_A_CLOSEOUT_REPORT.md`. **Claude did not create this commit.** It appears to have been made by the user outside this session.
- **Now:** HEAD is `67aa30a` and the index is empty. Stage B changes are **unstaged and uncommitted**:
  - modified: `run_tests.py`, `services/answer_service.py`, `services/citation_service.py`, `services/context_assembly_service.py`, `services/rag_service.py`;
  - untracked: `test_b2_citation_evidence.py`, `test_b3_answer_reliability.py`, the B1–B4 reports and this report.

## 13. Staging and commit confirmation
Claude ran no `git add`, `git commit` or `git push` during Stage B, and applied no migration. The external staging and commit described in §12 were not performed by Claude.

## 14. Final status: **PASS**
- B1–B4 are complete within their offline scope.
- The single full suite passed 34/34, and the `rag_db` fingerprint is identical.
- All defects that B1 confirmed were fixed with regression tests and caught mutants.
- **This is not a production-readiness claim.**
  - Semantic grounding is not verified.
  - Answer quality with the Stage B code has not been measured live.
  - The held-out evaluation and human review are outstanding.

Waiting for explicit approval for the live evaluation or for the next stage.
