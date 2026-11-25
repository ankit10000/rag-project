# Deployed answer-reliability fix — 25 November 2026

**PASS: both targeted defects fixed and deployed; original three questions pass
3/3 through the live deployed API.** Historical browser FAIL evidence remains
unchanged. This establishes the targeted fixes, not general production readiness.

Application: https://rag-demo.3-109-17-151.sslip.io

| Original question | Before | After deployment |
|---|---|---|
| Employment dates, duration, degree and institution | Dates/education correct; calculation refused; `answered` | February 2022–November 2025; approximately **3 years 9 months (45 months)**; degree/institution retained; `answered`; original page-1 citation |
| Three roadmap milestones, dates, budget, fax and telephone | Supported facts correct and phone unavailable, but incorrect `answered` | All milestones/dates, 83,000-credit budget and explicit no-fax fact retained; phone explicitly unavailable; **`partial`**; original page-2/page-1 citations |
| Unavailable annual salary | Correct `abstained` | Correct **`abstained`**, no invented salary; original page-1 citation |

## Implemented correction

- `services/tenure_calculation.py`: versioned `v2-verified-employment-months/2`
  recognizes an immediately adjacent `Employment:` field without crossing other
  employers, employees, projects or blank sections. Explicit document scope is
  enforced for direct lookup. Closed month/year arithmetic remains deterministic.
- `services/rag_service.py`: compound requests retain normal retrieval/generation
  rather than returning a duration-only answer; calculation metadata reaches the
  final response and saved history.
- `services/answer_service.py` and `services/answer_prompt.py`: derive the verified
  duration only from final selected context, preserve its actual citation ref,
  and append it through the deterministic renderer while Gemini answers the other
  requested parts. Ordinary generated-number checks remain unchanged; arbitrary
  model-generated derived numbers are still rejected. Pure obsolete calculation
  refusals are replaced without dropping factual or other missing-information
  clauses. Month precision is disclosed; explicitly requested unavailable exact
  days still yield `partial`.
- `services/answer_semantics.py`: a missing informational attribute described as
  `is unavailable in the provided documents` is recognized as a gap. Cited
  negative service facts remain facts, including the explicit no-fax statement.
- `test_v2_answer_reliability_hotfix.py`: 13 focused regression methods cover both
  failures, compound completeness, source identity, numeric rejection, ambiguous
  periods, explicit source scope and precision/missing-information distinctions.

## Verification actually executed

All deterministic runs used
`DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch`,
`TESTSAFE_BLOCK_NETWORK=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
No database connection or real provider call was needed for these tests.

- `.venv/bin/python -B -m unittest test_v2_answer_reliability_hotfix test_v2_tenure_calculation.TenureTests test_abstention_contract test_abstention_policy test_v2_answer_completeness test_v2_request_coverage test_v2_routing_recovery test_v2_evidence_recovery test_v2_page_context -q` — **136 tests PASS**.
- `.venv/bin/python -B test_stage6_answer.py` — **66 checks PASS**.
- `.venv/bin/python -B test_context_and_citations.py` — **62/62 PASS**.
- The built Linux image ran
  `python -B -m unittest test_v2_answer_reliability_hotfix test_v2_tenure_calculation.TenureTests -q`
  in a temporary container with `--network none`, no secrets/user-data mounts,
  read-only root, 768 MiB RAM and 0.5 CPU — **24 tests PASS**. These overlap the
  local tests and are not counted as additional unique test methods.
- Live API: exact saved question strings, **3/3 PASS**, one POST per question,
  stable turn IDs and no automatic resend. History retained exactly six messages
  and statuses `answered`, `partial`, `abstained`. Every citation named the
  original owned uploaded document and expected page. Downloaded source-PDF
  SHA256 matched the original 2,794-byte two-page fixture.
- Running source hashes matched all five final local files; all five services
  healthy, no OOM; `git diff --check` PASS.

The first new browser attempt was interrupted when browser control became
unavailable. It left an empty conversation with no committed answer; that attempt
and its original policy are preserved separately. The API continuation used that
empty conversation after reconciliation. **A fresh three-question browser render
run was not completed**; the verified after-results are live API results and
persisted metadata, not newly captured UI screenshots.

## Deployment and spend

Current release: `/srv/rag/releases/20261125-01`.
Backend image: `rag-v2-backend:aws-20261125-01`.
Image manifest: `sha256:65fe5c67d1a4c38fc6d3eb4792b239e41be5edfba3d1c1ff0ad6612868a96b58`.
Previous release `/srv/rag/releases/20261123-03` and configuration were retained
for rollback. Only `RAG_BACKEND_IMAGE` changed; API/worker were recreated.

Local Docker was stopped. The existing server built a five-file source-only
layer from its cached backend image: no dependency installs, model downloads or
frontend build. No AWS resources were added, resized or purchased; no schema
migration, quarantine operation or infrastructure/security change occurred.

Spend scope: **3 completed live API chat requests plus 1 interrupted browser
submission attempt**. The earlier attempt's SDK usage is unknown and is not
represented as zero. Exact SDK calls/tokens/cost are not exposed by the public
application and were not inferred from question count. No direct Gemini
experiments, automatic chat resends, held-out runs or load tests were performed.

## Evidence and integrity

New evidence is under ignored `deploy/aws/private/answer-fix-20261125-01/`:
predeclared policies, interrupted-attempt record, exact submissions and turn IDs,
three raw API responses, before/after history, source manifests, runtime hashes,
test logs and integrity receipt. The original 16 files under
`deploy/aws/private/e2e-20261125/` retain their exact hashes.

Only the five intended existing source files changed; all other **1,442** tracked
files retained their initial bytes. Existing staged content, HEAD and protected
evaluation assets remained intact. No credentials were written into artifacts,
no direct database or `rag_db` access occurred, and no staging, commit, push,
reset, clean or stash was performed.

Verified conversation: `7832ea34-3e89-4aea-ac23-20b2ce54e300`.
