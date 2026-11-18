# WP6 technical handoff to WP7 and WP8

This note records engineering dependencies, not owner approval or an acceptance sign-off. The recovered baseline is local `main` at `690fcfb`. WP1–WP5 reports, revised proposals and the WP5 v2.1 specification remain historical inputs. The current user instruction authorizes experimental WP6 implementation while explicitly prohibiting owner policy decisions and changes to frozen assets.

| Work | Can proceed independently | Decision or release dependency |
|---|---|---|
| WP6 pure scorer and offline dev-only comparison | Implement specification rules, synthetic probes, deterministic validation, three-way diff and reproducibility evidence | Treat implementation as experimental; do not select the acceptance scorer |
| Real-case annotations | Preserve a complete 160-case literal-only baseline pinned to unchanged data; synthetic annotation tests may exercise richer kinds | Assertion/distractor/history/disclosure/negatable real-case annotations need review; TA-03 and V-5 must be resolved together |
| Flip inventory | Generate dev-only observed flips with rule codes | WP5 §16.5 requires a **human-approved** golden flip list; observed flips are not that list |
| WP7 output claims and isolation | Prepare synthetic tests for exclusive outputs, symlinks, concurrent claims, consumed approvals, connect guards and provider failures | Applying changes to the frozen live runner/gate and activating held-out behavior belongs to the approved WP7/WP8 release |
| WP7 run provenance | Define future run headers: dataset manifest identity, version, git revision, portable data-file hashes, resolved config/models, chunk count/table hash and exact row context hashes | Existing historical runs lack headers; operator-pinned reconstruction remains non-acceptance evidence |
| WP7 manifest/report | Prepare scorer-keyed reporting/threshold interfaces and manifest lineage design | New `scorer_v2` asset group, manifest format 2, `acceptance_scorer`, and `report --scorer` require V-5 and re-freeze; v2 thresholds require separate owner review |
| WP7 error policy | Report error rows and refuse experimental acceptance while unapproved | V-9 chooses counted failures versus invalid-run policy; no agent decision |
| WP8 corrections and re-freeze | Validate proposed changes on in-memory copies; preserve pending state | Independent human review, owner-approved correction set, V-1–V-11 decisions as applicable, regenerated reviewed package and lineage-aware manifest |
| WP9 held-out readiness | Identify remaining checklist dependencies | A readiness review is not permission to run held-out evaluation; separate explicit authorization remains required |

WP5 §15 explicitly assigns manifest, threshold, report and run-header production integration to WP7/WP8. The old remaining-decisions report said not to start WP6 before approvals; the current user request supersedes that scheduling restriction for independent engineering, without supplying those approvals.

## Integrity evidence

`test_stage9_v2_integrity.py` checks the 44 protected raw-byte hashes captured before WP6; the frozen manifest content identity `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`; all 72 Phase D v1 probe outcomes and phrase contents after v2 import; fresh import tripwires; all 160 literal-only annotations; and reproducible scorer identities across module ordering and LF/CRLF conversion. Its subprocess tests import no services or providers and invoke no evaluation runner.

These checks establish experimental implementation integrity. They do not approve scoring policy, real-case annotations, flip outcomes, thresholds, held-out results or re-freezing. Package-level historical dev re-scoring and sidecar output validation are covered separately by the WP6 runner tests.

## Remaining specification limits

- WP5 §16.5's human-approved flip golden list cannot be completed by an agent. Literal-only baseline annotations intentionally do not claim the richer real-case annotation policy was approved.
- V-6 through V-11 contain recommended defaults in the implementation specification. Exercising those defaults experimentally is not approval to deploy them as acceptance policy.
- Historical Tier 2 reconstruction records assumed chunk configuration and PyMuPDF versions; matching references and v1 scores are indirect evidence, not direct historical text hashes. Future WP7 row hashes close that gap.
- A portable source hash records source identity, not interpreter/Unicode/PyMuPDF behavior. Environment versions must remain recorded in sidecars.
