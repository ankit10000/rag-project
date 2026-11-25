# Deployed RAG browser test — 25 November 2026

**Result: FAIL — two answer-reliability defects remain.** Testing completed on
`https://rag-demo.3-109-17-151.sslip.io` using the supplied account and the real UI.
This is a bounded live smoke test, separate from historical acceptance evidence.

| Check | Actual result |
|---|---|
| Login | PASS; supplied credentials opened the authenticated dashboard |
| PDF upload | PASS; a new 2,794-byte synthetic PDF uploaded through the visible Upload PDF button |
| Processing | PASS; both native pages reached READY; job showed Complete / 100% |
| Dates, duration and education | FAIL; February 2022–November 2025, degree and institute were correct, but the answer refused to calculate the approximately **3 years 9 months / 45 months** duration; badge was `answered` |
| Multi-page compound question | FAIL on status; all three roadmap milestones/dates, 83,000-credit budget and explicit no-fax fact were correct; telephone was correctly declared unavailable, but badge was `answered` instead of `partial` |
| Unavailable salary | PASS; `abstained`, no invented salary |
| Citations | PASS on document/page identity and source navigation; page 1 and page 2 opened in the real PDF viewer and their contents were visually compared with the answers |
| Refresh | PASS; same three answers, four citation chips and badges survived reload, without duplicate turns |
| Existing data | Original two-page document remained READY; original conversation was retained |
| Logout | PASS; returned to the login page |

Strict question acceptance: **1/3 PASS, 2/3 FAIL**. Supported retrieved facts were
correct in the two failed cases; the failures were calculation completeness and
status classification. Source citations do not themselves establish a missing
salary/telephone fact; those are reporting caveats, not source-supported values.

Offline inspection reproduced both relevant parser gaps without database or
provider calls:

- `services/tenure_calculation.py`: duration intent and employer were recognized,
  but the source format `Employer: Cedarbridge Labs. Employment: February 2022
  to November 2025` produced zero matching periods. The adjacent-header parser
  rejects the intervening `Employment` field. The live generic answer then
  repeated the dates without calculating the requested duration.
- `services/answer_semantics.py`: `telephone number is unavailable in the
  provided documents` was not recognized as an evidence gap, whereas
  `The document does not provide a telephone number` was. This reproduces a
  classification gap consistent with the live incorrect `answered` badge.

These offline observations describe the current repository. No deployed
instrumentation or software change was made, so they are not a captured
internal execution trace of the cloud request.

**Budget:** exactly **3 submitted chat requests**, zero resubmissions, zero direct
Gemini experiments, zero new AWS resources or configuration changes. The normal
application can make multiple SDK calls per turn; exact SDK calls/tokens/cost
were not exposed by the browser and were not inferred from the question count.
No load test, full evaluation, billing query, restart or model rebuild was run.

The new PDF and test conversation remain for review. No existing document or
conversation was deleted, no credentials were written into the report, and no
direct database access, `rag_db` access, staging, commit or push occurred.

Evidence, predeclared questions, immutable response snapshots, screenshots and
offline reproduction output are under ignored
`deploy/aws/private/e2e-20261125/`; the result manifest is `result.json`.
Conversation: `500e3aef-bc88-47c7-9a38-95cbd01c47e0`.
