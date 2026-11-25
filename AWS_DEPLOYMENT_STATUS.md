# AWS RAG demonstration deployment

2026-11-23 · **AWS_RAG_DEMO_DEPLOYED** · Verified for the selected light demonstration workload.

**Public application: https://rag-demo.3-109-17-151.sslip.io**. The original
`https://3.109.17.151` link redirects to this free hostname, preserving paths and
queries. Use `/register` to create an account;
the AWS database is fresh. Existing localhost accounts and private documents were
not migrated. This is operational demonstration acceptance, separate from formal
held-out evaluation or independent-human acceptance.

## Server, services and cost

| Item | Verified configuration |
|---|---|
| Instance | `rag-v2-demo-app-20261123`, `ap-south-1a` (Mumbai) |
| Bundle | `medium_3_1`: 4 GB RAM, 2 vCPU, 80 GB SSD, USD 24/month |
| OS/runtime | Ubuntu 24.04 LTS amd64; Docker 29.9.3; Compose 5.8.0 |
| Application | Python 3.14.10, CPU Torch 2.15.0, Node 24.22.3, Next 16.4.6 |
| Services | One FastAPI process, one durable OCR/indexing worker, Next.js, PostgreSQL 18/pgvector, Caddy 2.11.9; all healthy |
| HTTPS | Free `rag-demo.3-109-17-151.sslip.io` hostname on attached static IPv4 `3.109.17.151`; trusted Let's Encrypt certificates; automatic short-lived renewal; original HTTPS IP redirects to hostname |
| Public ports | TCP 80/443; SSH limited to the recorded administrative /32; PostgreSQL/API/Next have no published ports |
| Database | `rag_v2_demo`; restricted `rag_v2_app`, NOSUPERUSER/NOBYPASSRLS; nine FORCE RLS tables |
| Persistent state | `/srv/rag/state`; shared revision-pinned read-only model/OCR cache at `/srv/rag/models` |
| Current release | `/srv/rag/releases/20261123-03`, `/srv/rag/current` symlink; existing application images unchanged |

Only one paid server was created. No RDS, NAT gateway, load balancer, Kubernetes,
CloudFront, paid registry, snapshot subscription or external storage service was
created. The static IP remains attached. The account remains on the **FREE** plan;
no account upgrade occurred.

Initial reported credits: **USD 99.999985**. Latest account API reports
**USD 119.999985**, expiring **2027-03-11 13:16:42 UTC**. The increased reported
balance does **not** expand the owner's original USD 100 authorization.

The guard keeps USD 10 contingency and a USD 90 spending ceiling for planning.
A 107-day compute window estimates **USD 84.43** (USD 84.45 including the small
ancillary allowance). The original 110-day estimate exceeds the verified expiry.
These are pre-credit estimates; applicable taxes and Gemini billing are separate.
Monitoring-only cumulative pre-credit alerts at **USD 25/50/75/90** are configured
to the supplied email. Alerts are delayed notifications, not a hard spending cap.
Export before **2027-03-10** and delete the server/release its IP when finished;
a stopped Lightsail instance remains billable.

Pricing, account and alert evidence: `deploy/aws/evidence/`; official references:
`deploy/aws/pricing-evidence.json`.

## Actual functional acceptance

### Free hostname verification — 2026-11-23

The requested free shared hostname resolves to the existing static IP. Release
`20261123-03` changes proxy/allowed-origin configuration only; database state and
application images remain intact, with the previous configuration retained for
rollback. Public checks passed **13/13**: trusted HTTPS login/register/health,
IP redirects including query preservation, canonical-origin validation,
foreign-origin/host rejection, and existing synthetic-account login, secure
cookies, authenticated access and logout. No certificate bypass was used for
these public checks. Evidence: `deploy/aws/evidence/hostname-20261123.json`.

During this update the proxy was found unhealthy: 52 orphaned `ssl_client` zombie
processes approached its existing 64-task limit. Enabling Docker `init: true`
reaped them correctly. **12/12** additional internal readiness probes passed;
the task count remained **8 before and after**, with **zero zombies**, and all
five services are healthy. Server size and task limits were unchanged. This
hostname update used **zero Gemini calls**, created **zero AWS resources**, and
required no database migration, domain purchase or paid DNS service. The hostname
uses the external sslip.io shared DNS service rather than an owned domain.

### Original application acceptance

| Check | Observed result |
|---|---|
| Public TLS | Normal curl, OpenSSL IP verification and Chromium trust PASS; no certificate bypass on AWS |
| OCR/indexing | Synthetic scanned policy and native/scanned two-page resume reached READY using actual pinned Tesseract and CPU embeddings |
| OCR answer | Real Gemini returned 83 credits and 17 days with the owned original page-1 citation |
| Memory/follow-up | Concise preference recalled; USER_SUPPORTED memory with actual user-message provenance |
| Education | Both retained questions returned degree, institute and 2016–2020 dates with original page-2 citations |
| Partial answer | Project improvement 40→12 minutes retained, missing telephone acknowledged, final status `partial`, page-1 citation |
| Timeout reconciliation | Actual committed POST response replaced with browser-visible 504; real committed GET recovered it; duplicate-safe retry preserved the same two messages |
| Reopening/history | All five canonical answers retained exact API text, statuses and citation arrays; UI facts, badges, chips and authorized PDF navigation survived refresh and actual restart |
| Two-user HTTP isolation | 19 foreign-resource paths returned 404; documents/chats/memories lists empty; foreign chat rejected before generation |
| Database isolation | Restricted-role read-only probe: positive owner controls across nine tenant tables, all other-owner counts zero |
| Deletion fence | A real eight-page scan job was observed RUNNING; deletion cancelled it; after five seconds it remained cancelled and inaccessible |
| Post-deletion DB | No served documents, active jobs, chunks, conversations, messages, memories, provenance or turn receipts reappeared; other owner still saw zero rows |
| Restart | Actual API/worker process IDs and start times changed; saved answers/documents persisted |
| Proxy persistence | Trusted certificate fingerprint unchanged after Caddy restart |

**Gemini verification used exactly 12 successful SDK calls, 5,282 reported total
tokens. No further Gemini test calls were made after the owner's spending
instruction.** Remaining isolation, restart, deletion and restore work used zero
provider calls; an explicit SDK-deny mode protected those checks. The ordinary
production API is now restored without test mounts or instrumentation; generation
occurs only for application requests.

The original cloud browser experiment remains **FAIL** from a follow-up wait race.
The follow-up was recovered by its existing turn UUID without resubmission. The
first continuation remains **FAIL** from real API admission 503s after all five
answer cases passed. A later isolation attempt remains **FAIL** from comparing
literal Markdown with rendered text. Separate corrected zero-provider isolation
and persistence cases pass. None of these original outcomes or receipts was
rewritten, and no fresh experiment reset the SDK budget.

Canonical case and RLS summaries are in `deploy/aws/evidence/`. Original failures,
traces, client credentials and receipts are preserved with restrictive permissions
under ignored `deploy/aws/private/acceptance-evidence/` and the receipt archive.

## Demonstrated corrections

- Exact configurable API hosts permit private Compose hostname `api`, retaining
  strict host rejection and refusing wildcard/invalid configuration.
- Explicit `RAG_PUBLIC_ORIGIN` plus Caddy full-authority forwarding preserves HTTPS
  browser-origin validation through the private HTTP hop; forwarded headers alone
  cannot establish trust.
- Caddy TLS health selection and unmatched-host 404 handling verified.
- Worker SIGTERM drains its in-flight attempt before another claim.
- Measured worker memory headroom increased within the same 4 GB host.
- The original four-connection Uvicorn limit produced 503s during ordinary UI
  polling. Final HTTP admission is 12 with idle keep-alive disabled; **model
  generation is independently serialized to one**, using the existing total
  request deadline. Saved-result recovery remains independent of that gate.
- Host initialization uses explicit Bash, verified Docker signing keys and pinned
  packages. Canonical's stalled security HTTP mirror was changed to verified
  HTTPS; repository signature checks remain enabled. SSH candidate configuration
  is validated as a file before key-only hardening is applied.

## Resource evidence

Local two-core Linux/amd64 emulation passed actual embeddings, reranking and
repeated OCR with no OOM. Summed container caps are **3,424 MiB**: API 1,152,
worker 1,408, PostgreSQL 384, frontend 384, Caddy 96. No extra container swap.
Conservative sum of individual local cgroup peaks: **2.38 GiB**.

Native AWS sampling during the real journeys recorded:

- Peak aggregate container working memory: **1,456,246,784 bytes**.
- Minimum host available memory: **2,034,352,128 bytes**.
- Peak host busy CPU: **99.65%**, including profiler/host overhead and steal time.
- **Zero OOM events**. Final root disk: approximately **69 GB free**.

This establishes headroom for the tested light workload, not sustained CPU-heavy
or adversarial concurrent 25 MB/100-page upload certification. Local emulated CPU
percentages were rejected as unreliable; native /proc/cgroup measurements are
recorded separately in `native-host-summary-20261123.json`.

## Backup, restore and operations

Daily encrypted consistent database/upload exports are enabled by
`rag-encrypted-backup.timer` (02:30 UTC), retaining three exports. API/worker
writers stop for the snapshot and restart afterward. Host memory/disk monitoring
runs every minute, Docker logs are bounded, services restart automatically, and
`rag-compose.service` starts the stack at boot. Caddy's persisted state manages
certificate renewal.

Verified cloud export:

- Server: `/srv/rag/backups/rag-export-378104047c664a9daf0dc6f291391f15.tar.cms`
- Off-host: `deploy/aws/private/exports/rag-export-378104047c664a9daf0dc6f291391f15.tar.cms`
- Bytes: **11,735,622**; encrypted-copy SHA256:
  `ca0d4c2e524cca378ff44541912be2c3155c8b265294700e517fd4d93e834613`.
- Recovery database: `rag_aws_restore_97706a54e00d45b0b2d935a1bb037d04`.
- Restore PASS: **ten nonempty table counts identical**, two upload checksums,
  nine FORCE RLS tables. Application database left untouched. Private decryption
  key remained on the Mac throughout; ciphertext alone was copied off-host.

Off-host retrieval is an explicit operator command, not an always-on external
backup service. Use `data/pull_backup.py --sudo-remote` with the recorded SSH key
and known-host file; it retains three client exports. Restore uses
`data/backup.py restore` with the client-only `tools/docker` SSH adapter; actual
executed arguments/results are represented by the restore evidence JSON. Keep
`deploy/aws/private/backup-recipient.key` and its certificate with exported data;
never upload the private decryption key to the server.

For a manual export, invoke the installed systemd backup service as a standalone
command. Retain each release directory, its deployment env snapshot and image tag
for configuration rollback; restore a backup for data recovery. No automatic
schema rollback or destructive down-migration is performed.

**Noncritical deployment limitation:** automatic approval review rejected a live
backup-helper file replacement combined with a read-only probe. That deployed
file was left unchanged; the tested repository fix prevents a child process from
consuming subsequent streamed SSH shell commands. Scheduled/standalone deployed
backup and actual off-host restore already passed. The final read-only deletion
probe was executed separately and passed.

## Executed verification

- Linux backend/standalone frontend production builds and pinned install: PASS.
- `DATABASE_URL=postgresql:///rag_test_scratch HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m unittest deploy.aws.test_check_budget deploy.aws.test_runtime_contract deploy.aws.data.test_data deploy.aws.tests.test_provider_guard test_v2_security.V2BodyDeadlineTests test_v2_security.V2ServerErrorRedactionTests -q` — **29/29 PASS**.
- `.venv/bin/python -B -m unittest deploy.aws.image.test_profile_capacity -q` — **2/2 PASS**.
- `npm --prefix frontend test` — **25/25 PASS**; `run typecheck` and `run lint` PASS.
- New mocked Playwright desktop/mobile answer contracts — **10/10 PASS**.
- Real local Linux provider-free browser — **1/1 PASS**.
- Real AWS generation — five canonical answer cases PASS across the preserved
  experiment/continuation; **12 SDK calls**, no generation rerun.
- `RAG_AWS_E2E_PHASE=isolation` with `RAG_AWS_FAILED_FROM` set to continuation-01,
  `RAG_E2E_EXTERNAL=1 RAG_E2E_URL=https://3.109.17.151`, desktop Chromium,
  `tests/browser/aws-deployment.spec.ts` — **1/1 PASS**, 36.9 s.
- `RAG_AWS_E2E_PHASE=persistence` with isolation-02 state and actual restart
  receipt, same strict public URL/spec/project — **1/1 PASS**, 46.5 s.
- Exact successful browser commands, working directory and outcomes are preserved
  in `deploy/aws/evidence/browser-commands-20261123.json`.
- Fresh/idempotent migrations, read-only RLS before/after deletion, encrypted
  off-host copy and guarded fresh-database restore: PASS.

## Repository integrity and decision

Initial `main` HEAD: `3edf2db7e7661465c2565adf196a94183668cfbb`; clean index/tree
baseline covered 1,341 existing files. Four existing implementation files changed:
`backend/v2/app.py`, frontend API gateway/Next config, and worker CLI. Deployment
files and focused tests are new. All **44 protected evaluation assets**, historical
project results and the Git index remain intact. No `rag_db` access, private-data
migration, official held-out execution, frozen-policy/human-review modification,
staging, commit, push, reset, clean or stash.
Local capacity-test containers were stopped after acceptance; their data and
pre-existing user containers were retained.

**No critical blocker remains for this verified AWS demonstration.** Formal
evaluation acceptance and broader production/load certification remain separate.
