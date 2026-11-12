# B2 — Citation correctness and evidence coverage

Date: 2026-11-12. Nothing committed or staged. No Gemini, network or DB writes; all tests use fake LLM replies. This step builds on the B1 findings (`B1_ANSWER_QUALITY_GROUNDING_AUDIT.md`).

## Confirmed defects addressed (all reproduced in B1 before the change, all fixed and re-probed after)
| B1 # | Defect | Before | After |
|---|---|---|---|
| F1 | A `[MEMORY]` tag bypassed citations on a DOCUMENT question with sources | `answered`, uncited "90 days" claim accepted | citations are required for every DOCUMENT question with sources, whatever the tag. Probe → `unverified`, issues `no_citation, uncited_claim`, 2 calls. A pure abstention tagged `[MEMORY]` is still accepted. MEMORY questions are unchanged. |
| F2 | An uncited claim next to a cited one was accepted | `answered`, invented sentence kept | new blocking issue `uncited_claim` when citations are required. The model is asked to correct (bounded retry). If the claim persists, the repair fallback drops it (see F3). |
| F3 | Repair kept a claim whose only citation was fabricated | `answered` with the fabricated claim as uncited prose | repair = remove invalid refs → **drop every uncited claim sentence** → re-validate. Probe → `answered` with only "Refunds take 30 days [S1]." and issues `repaired:invalid_ref, dropped_uncited_sentences:1`. If nothing cited is left → `unverified`. |
| F5 | Two different abstention phrase lists | "X is not mentioned" counted as an uncited claim | one shared `citation_service.ABSTAIN_PHRASES`, used by both modules (adds "do/does not mention", "no mention"). |
| F6 | File mention accepted by suffix (`data.pdf` ⇒ `a.pdf` OK) | valid | exact, case-insensitive file-name match → `unknown_document_mention` |
| F7 | Page mention checked against any source | valid | a sentence that cites sources may only mention pages of **those** sources. Uncited sentences, and the old global check, still apply. |

## Implementation (exact changes)
`services/citation_service.py`:
- **Shared phrases:** `ABSTAIN_PHRASES` (shared); `_REFUSAL` is now an alias of it.
- **`split_sentences(text)`:** a marker written after the full stop (`"Fact. [S1] Next."`) is attached to the preceding sentence. Before this, it silently counted toward the next sentence.
- **`uncited_claim_sentences(text)`, `count_uncited_sentences(text)`** (same API, same ≥5-word rule). Sentences exempt from the claim check:
  - abstention sentences;
  - list or section intros ending with `:`;
  - meta statements that combine a disagreement word (disagree/conflict/differ/inconsistent/contradict) with a source word (source/passage/document/report/file).
- **`drop_uncited_claims(text)`:** used only by the repair fallback.
- **`validate_answer_citations`:**
  - new issue `uncited_claim` (only when `require_citations=True`);
  - per-sentence page pairing in addition to the existing global page check;
  - exact file-name match.

`services/answer_service.py`:
- **Phrase list:** `_ABSTAIN_PHRASES = ABSTAIN_PHRASES`.
- **Citation requirement:** `needs_citations` also requires citations when `question_type == "DOCUMENT"`, whatever the tag. Exact refusal text and pure abstentions are still exempt, as before.
- **Repair fallback:** drops uncited claims after removing invalid refs, and records `dropped_uncited_sentences:N` in `issues`.

No change to: the public function signatures, the result shape (`answer, status, tag, citations, sources, validation, attempts, issues`), `ANSWER_MAX_RETRIES`, the prompt rules, or retrieval.

## Regression tests (executed)
New `test_b2_citation_evidence.py` (unit, registered in `run_tests.py`): **35 PASS, 0 FAIL**. It covers:
- valid citations, with structured metadata coming from the source, not the model;
- a marker written after the full stop;
- multiple refs and `[S1, S2]`;
- fabricated refs S9, S0 and S3 (never emitted; `unverified` after bounded retries);
- the wrong page for the cited document and the wrong document by suffix, plus their accepted correct forms;
- missing citations and the uncited-claim rule, with the abstention, list-intro, meta-statement and short-sentence exemptions;
- regeneration on `uncited_claim`;
- repair (drops the fabricated-ref claim, keeps the valid ref, falls back to `unverified` when nothing valid is left);
- the tag bypass, previous-turn leakage (old `[S3]` is stripped from history and rejected if reused), and conflicting evidence;
- the **semantic limitation pinned**: a wrong claim with a syntactically valid citation is accepted.

Existing tests still pass unchanged: `test_answer_phase3.py`, `test_context_and_citations.py` (62/62), `test_answer_scoring.py`. One intermediate regression ("`see p. 5 [S1]`" no longer flagged, because the sentence splitter cut after "p.") was found by the existing test and fixed by keeping the global page check; the test itself was not changed.

## Mutation results (executed; repo files untouched, modules loaded from modified source)
| Mutation | `test_b2` | `test_b3` |
|---|---|---|
| `uncited_claim` not blocking | 3 FAIL | 3 FAIL |
| `[MEMORY]` tag bypass restored | 3 FAIL | 8 FAIL |
| repair keeps uncited sentences | 2 FAIL | 0 |
| marker re-attachment removed | 1 FAIL | 0 |
| suffix document match restored | 1 FAIL | 0 |
| page check against any source | 1 FAIL | 0 |
| invalid refs accepted | 4 FAIL | 0 |
| abstention list not shared (old short list) | 2 FAIL | 2 FAIL |
All mutants are caught by at least one test.

## Remaining semantic verification limitations (not solved, by design)
- **No semantic check.** A citation shows only that the sentence points at a retrieved passage, not that the passage supports the sentence. "Refunds within 90 days [S1]", where S1 says 30, is **accepted** (pinned in the test). Deterministic code cannot prove semantic support, and no model-based verifier was added (none verified, no live dependency allowed).
- **Heuristic coverage.** The uncited-claim rule is a heuristic: sentence splitting on `.!?`, a 5-word minimum, and phrase lists for abstention and meta statements.
  - It can miss claims inside short sentences, and it can let through a factual sentence that happens to contain an abstention phrase (e.g. "Parking is not available on site.").
  - It can also reject a legitimate uncited transitional sentence; that is safe (the sentence is dropped or retried) but may shorten answers.
- **Previous-turn reuse.** A previous-turn ref that is also a valid current ref points at the current chunk. That cannot be distinguished.

## Files changed
`services/citation_service.py`, `services/answer_service.py`, `run_tests.py` (registration), new `test_b2_citation_evidence.py`, this report.
