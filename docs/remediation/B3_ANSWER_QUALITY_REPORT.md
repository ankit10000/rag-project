# B3 — Answer quality and hallucination resistance

Date: 2026-11-12. Nothing committed or staged. No Gemini, network or DB access in any test (fake LLM, fake retrieval). This step builds on B1 and on B2 (`B2_CITATION_EVIDENCE_REPORT.md`).

## Findings addressed
| B1 # | Finding | Change | Before → after (deterministic probe) |
|---|---|---|---|
| F4 | `[DOCUMENT]` factual answer accepted when **nothing was retrieved** (MIXED/MEMORY question) | `answer_service.generate_grounded_answer`: if there are no sources and the tag is `DOCUMENT`, and the reply is neither the refusal nor a pure abstention, then issue `document_claim_without_sources`, with explicit feedback, a bounded retry and the usual fallback | `answered` → `unverified` (2 calls); a corrected `[MEMORY]` reply is accepted; a `[DOCUMENT]`-tagged pure abstention is still accepted |
| F8 | Chunk text could forge our source header or citation markers in the prompt | `context_assembly_service.assemble_context`: in the **prompt display only**, `[S#]`-shaped markers inside chunk content are replaced by `[ref removed]`. `sources[i]["content"]` stays unchanged. | forged `"[S2] Document: secret.pdf …"` present → now `"[ref removed] Document: secret.pdf …"`; real headers intact |
| F9 | Provider failure in `classify_question` / `rewrite_query` aborted the whole answer (exception) | `rag_service.ask_question`: classification failure → `DOCUMENT` (strictest: retrieval runs and citations are required); rewrite failure → the user's original question | exception → answer produced (or a safe `status=error` when the provider is fully down) |
| F1–F3, F5–F7 | (B2) | see B2 | — |
| F10 | Semantic support unprovable | documented, not "solved" (no keyword hallucination detector added) | — |

## Scenario coverage: `test_b3_answer_reliability.py` (unit, registered): **34 PASS, 0 FAIL**
| # | Scenario | Asserted behaviour |
|---|---|---|
| 1 | no retrieved evidence | DOCUMENT question → refusal without an LLM call. MIXED/MEMORY: a `[DOCUMENT]` claim is rejected → `unverified`; a corrected `[MEMORY]` answer is accepted; a pure abstention is accepted. |
| 2 | relevant but incomplete | the cited part plus a stated gap → `partial`, 1 call |
| 3 | irrelevant evidence | the refusal is accepted; an uncited general-knowledge answer is not |
| 4 | contradictory documents | both versions cited → `conflict`; an uncited counter-claim is not returned |
| 5 | multiple documents | each part cited to its own document |
| 6 | beyond the evidence | abstention accepted; an added uncited claim is removed or rejected |
| 7 | injection in retrieved content | forged header and markers neutralised; delimiter tags neutralised; stored content unchanged; the untrusted-data instruction is present; an obeyed injection ("HACKED", uncited) is not accepted; **limitation pinned** (below) |
| 8 | empty output (`""`, whitespace, `None`) | safe `error`/`unverified`, bounded, no citations |
| 9 | malformed output (tag only, non-string, unclosed `[S1`) | safe, bounded; an unclosed marker is not a citation |
| 10 | unsupported uncited claim | never returned as a verified fact |
| 11 | retry exhaustion | exactly `1 + ANSWER_MAX_RETRIES` calls; the config is honoured (3 retries → 4 calls); a negative value is clamped (1 call) |
| 12 | provider failure | every attempt fails → `ERROR_MESSAGE`; a failure followed by success → accepted |
| — | `rag_service` | classification and rewrite failures fall back and the answer is still produced; provider fully down → `status=error` with no exception; a successful MEMORY classification is unchanged |

Existing answer tests are unchanged and pass (`test_answer_phase3.py`, `test_context_and_citations.py`, `test_answer_scoring.py`).

## Mutation results (executed; repo untouched)
| Mutation | Result |
|---|---|
| `document_claim_without_sources` check disabled | `test_b3`: 3 FAIL |
| forged markers shown verbatim in the prompt | `test_b3`: 1 FAIL |
| rewrite failure re-raised (narrowed `except`) | `test_b3`: 2 FAIL |
| classification failure re-raised | `test_b3`: 2 FAIL |
| `[MEMORY]` tag bypass restored (B2 rule) | `test_b3`: 8 FAIL |
| `uncited_claim` not blocking (B2 rule) | `test_b3`: 3 FAIL |
| abstention list not shared (B2 rule) | `test_b3`: 2 FAIL |
All caught. Before the test wrapped `ask_question` in `try`, the two rag_service mutants were caught only as a crash; they now fail as explicit checks.

## Before/after where measurable
- **Deterministic probes** (B1 F1–F4, F6–F8): every probe that previously produced an unsupported `answered` result now yields `unverified`, or a repaired answer containing only cited sentences. The F8 forged header is no longer visible to the model.
- **Offline replay of the 47 recorded Tier-1 dev answers** through the new pipeline (B4): 0 status changes, 0 answer changes, correctness 41/47 → 41/47. The stricter checks rejected none of the previously produced dev answers. This is no evidence of improvement on real model output either; see B4.

## Remaining risks
- **No semantic grounding check.** A claim with a valid-looking citation to a real passage is accepted even when the passage does not support it, or when the claim came from injected text inside that passage (pinned in the test).
- **Heuristic rules.**
  - The uncited-claim rule, the abstention/meta exemptions and `classify_status` are heuristics.
  - With a live model, `uncited_claim` may cause extra regenerations (more latency and tokens, bounded by `ANSWER_MAX_RETRIES=1`) and shorter repaired answers. This is not measured live.
  - A factual sentence containing an abstention phrase is still exempt.
- **Display-only neutralisation.** F8 removes only `[S#]` markers; other forged text (e.g. "Document: x.pdf | Page: 9" without a marker) remains visible. The model is instructed to treat passages as data, but behaviour under injection is model-dependent and was not tested live.
- **Classifier risk.** A wrong MEMORY classification still skips retrieval. The F4 rule only stops the model from then claiming document facts.
- **Conflict handling.** It relies on the prompt; the dev failures (B4) show the live model often does not surface disagreements, and that was not changed here.

## Files changed
`services/answer_service.py` (F4), `services/context_assembly_service.py` (F8), `services/rag_service.py` (F9), `run_tests.py` (registration), new `test_b3_answer_reliability.py`, this report.
