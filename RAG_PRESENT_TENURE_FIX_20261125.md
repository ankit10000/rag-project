# Present-date and conversational tenure fix — 25 November 2026

**PASS — deployed.** The actual owned resume states
`GOC Productions | Apr 2026 – Present` on page 1. Treating its explicit `Present`
as **25 November 2026**, the month-level duration is **0 years, 7 months**.
The joining day is absent, so the answer correctly describes this as approximate.

The previous `/2` tool accepted only closed ranges and missed the supplied
informal experience question, joining-date grammar and bare calculation follow-up.
All four failures were reproduced offline using the actual source header and
retained deployed source code, without another Gemini experiment.

`services/tenure_calculation.py` now implements versioned
`v2-verified-employment-months/3`:

- Explicit `Present`/`Current` uses the application clock, reports its as-of date
  and preserves month precision. Source/question/history dates cannot replace
  that clock. Missing, reverse, future-start and ambiguous records are not guessed.
- Joining-date questions return the source-supported month directly.
- Informal experience/month questions and bare calculation follow-ups retain
  the recent user-referenced employer; historical assistant dates are not facts.
- A unique one-character acronym typo in a pronoun follow-up can use recent user
  context, including a subsequent bare follow-up after that typo. A literal
  employer in the actual source always wins, even if its dates are missing.
- Existing owner/document scope, bounded lookup, original citation identities,
  closed-range arithmetic and ordinary generated-number validation are retained.

Only this existing production source file changed in this task. Added
`test_v2_present_tenure.py` covers 18 focused methods; the source-only Dockerfile
adds no packages or models. Previous partial-status/compound-answer fixes and
historical evaluation outcomes remain intact.

## Executed evidence

Final offline command, with an unreachable `rag_test_scratch` DSN,
`TESTSAFE_BLOCK_NETWORK=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`:

`.venv/bin/python -B -m unittest test_v2_present_tenure test_v2_tenure_calculation.TenureTests test_v2_answer_reliability_hotfix test_abstention_contract test_abstention_policy test_v2_answer_completeness test_v2_request_coverage test_v2_routing_recovery test_v2_evidence_recovery test_v2_page_context -q`

**154 tests PASS**. `.venv/bin/python -B test_stage6_answer.py` passed **66 checks**
again on the final source. Final built Linux image ran
`python -B -m unittest test_v2_present_tenure test_v2_answer_reliability_hotfix test_v2_tenure_calculation.TenureTests -q`
with no network, secrets or user-data mounts, read-only root and bounded CPU/RAM:
**42 tests PASS**. Linux tests overlap the offline test set.

Live deployed API results, with the original PDF reused:

| Case | Actual result |
|---|---|
| `when Ankit joined the Goc Productions company` | April 2026, `answered`, original page-1 citation |
| `how much experience to Ankit in GOC Productions` | Approximately 7 months as of 25 November 2026, `answered`, page 1 |
| `can you calculate exact year and months` | Same verified calculation using the prior user employer reference |
| `how much months he spended in GO Productions?` | Source-verified GOC interpretation, same calculation and page |
| Bare calculation after the saved GO typo | Same verified 7-month result, correct reference, no duplicate turn |

The first four checks passed on release `20261125-02`. Replaying the original
saved conversation exposed the final after-typo context gap offline; two more
regression methods were added. Final release `20261125-03` passed 154 offline and
42 Linux tests, followed by the one additional live after-typo check. The original
four live requests were not repeated and their receipts were not overwritten.
These are API/history checks; no new browser-render certification is claimed.

## Deployment, spend and preservation

Final release: `/srv/rag/releases/20261125-03`.
Image: `rag-v2-backend:aws-20261125-03`;
image ID `sha256:35d7ba5713bca98b87be41c075c0f83acbb0cea1d30fb7e687ebb7e76fafdbd5`.
Running source hash matches the final tree. All five services healthy, no OOM;
prior releases and configuration retained for rollback. Only API/worker image
configuration changed; no migrations, infrastructure resize or paid resources.

**Five live chat POSTs total**, no resends, no new PDF upload or direct Gemini
experiment. All returned `retrieval_status: source_lookup`: answering/routing
used the deterministic branch rather than Gemini generation. Ordinary post-turn
memory housekeeping may call Gemini; exact total SDK usage/cost is not exposed
by this API and is not inferred from question count.

The original 14-message user conversation, original PDF, earlier fix report,
Git index, HEAD and all other 1,446 tracked files retain their initial content.
No `rag_db` access, protected evaluation/human-review changes, staging, commit,
push, reset, clean or stash. `git diff --check` passes.

Private source excerpt, before/after reproductions, policies, exact requests,
responses, runtime hashes, test/deployment logs and integrity receipt are under
ignored `deploy/aws/private/present-tenure-20261125-01/`. Verified test chat:
`94592cc8-b4fc-4dc2-a2dc-b39f1355ad56`.
