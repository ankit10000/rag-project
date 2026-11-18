# Candidate re-freeze checklist — no execution authorization

The new `candidate_manifest.json` is schema `phase-e2-integration-candidate/1`, not a frozen manifest. It wraps unchanged `readiness.propose_refreeze` output. The original `WP8_PROPOSED_REFREEZE_PLAN.json`, current official frozen manifest and expected hash are preserved.

## Verified snapshot

- Parent content identity: `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.
- All **27 parent assets** reproduce their declared portable hashes.
- **20 existing WP6/WP7 candidates** are recorded from actual bytes: 14 scorer Python modules, its current annotations JSON, and five runner-preparation modules.
- Two annotations remain separate: current dataset/package annotation snapshot and the retained historical c1bbcae input. Both pass existing annotation validation against their actual Git-pinned datasets. Each yields its own scorer aggregate with the same current module bytes.
- `validate_current_candidate(root, candidate)` rereads current files and the parent, validates both annotations, rebuilds proposal and aggregate identities, and compares strict canonical JSON. Even self-rehashed tampering or False-to-0 coercion is refused.
- `write_candidate` uses exclusive creation. It refuses the entire official `eval/phase35/` subtree (including results and symlink aliases), and never overwrites an existing candidate.

To reproduce current validation without writing anything:

```python
import json
from pathlib import Path
from eval.acceptance_preparation.integration.snapshot import validate_current_candidate
root = Path(".").resolve()
candidate = json.loads((root / "eval/acceptance_preparation/integration/candidate_manifest.json").read_text())
print(validate_current_candidate(root, candidate))
```

The `PASS` status means **snapshot consistency only**, not formal acceptance, human approval or re-freeze completion.

## Future reviewed dependency scope

`future_freeze_scope` lists current services/gates and new governance/provenance/integration/review paths that require explicit dependency review. Each future approved hash is null. No unstable in-progress module is silently added to the historical 20-file snapshot, and no hash is invented for a future modified gate or runner.

The list includes safety/frozen-manifest/hashing/integrity/reporting/review/harness files; answer, retrieval, chunking, extraction and configuration services; `acceptance_preparation/adoption.py`, `readiness.py`, `clarifications.py`; and the new gate-policy, provenance, clarification, integration and independent-review packages. This is a proposed scope checklist, not automatic asset adoption. The complete runtime and governance dependency closure must be finalized from the actual reviewed integration patch, including any additional modules it imports.

## Actions after independent and owner decisions

1. Record independent review and owner decisions with authentic source records; preserve original annotations/workbooks/ledgers.
2. Resolve SC-06/SC-07/SC-08 and any applicable policy questions without retroactively altering historical diagnostic results.
3. Approve exact scorer/annotation/dataset identities and threshold/gate/runtime-provenance policies; keep unknown identity fail-closed.
4. Review the concrete frozen integration patch and its complete dependency closure. Capture actual hashes after approval; do not substitute current pre-patch hashes for future hashes.
5. Run deterministic scorer/v1 compatibility, strict provenance, identity-refusal, concurrent/exclusive output, failure and rollback tests against that patch and its approved policies.
6. Generate a **new**, separately named lineage-bound manifest and reviewed package only after re-freeze authorization. Verify all included hashes and the parent relationship. Retain the old manifest, baseline and every historical result.
7. Complete separate readiness review and obtain separate authorization before any held-out evaluation. No held-out run or `--split all` is authorized here.

No re-freeze is executed by this candidate builder or validator. New output paths and exclusive writes do not constitute approval to replace an official baseline.
