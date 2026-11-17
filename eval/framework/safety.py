"""Execution gates for evaluation runs (nothing here runs an evaluation).

A run request must name: mode (offline | development | heldout), explicit
split(s), explicit output path(s) that do not exist yet, whether live provider
calls are allowed (opt-in), and — for held-out — a written approval file.
``check_run_request`` returns a list of blocking problems; an empty list is
the only "allowed" outcome.

The official runner (eval/phase35/run_eval.py) calls ``runner_gate`` before
any side effect. ``--split dev`` needs no approval; ``heldout`` and ``all``
go through ``check_run_request`` with the frozen manifest and an approval file.

Approval file: a JSON object, every field required and checked exactly:
    {"marker": "HELDOUT EVALUATION AUTHORIZED",
     "approved_by": "<name>", "approved_on": "<YYYY-MM-DD>",
     "splits": ["heldout"],            # the runner's splits ("all" = ["dev", "heldout"])
     "tiers": [1],
     "output_paths": ["eval/phase35/results/tier1_heldout.jsonl"],   # repo-relative or absolute
     "frozen_manifest_sha256": "<content_sha256 of the frozen manifest>"}
"""

import json
import os
from dataclasses import dataclass, field

MODES = ("offline", "development", "heldout")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Frozen thresholds (docs/remediation/HELDOUT_THRESHOLD_FREEZE.md and the Stage B dev report).
# Exact minimum counts; a score is never rounded up to pass.
FROZEN_THRESHOLDS = {
    ("dev", 1): {"cases": 47, "min_correct": 41},
    ("dev", 2): {"cases": 42, "min_correct": 28},
    ("heldout", 1): {"cases": 113, "min_correct": 97, "percent": 85},
    ("heldout", 2): {"cases": 106, "min_correct": 69, "percent": 65},
}

HELDOUT_APPROVAL_MARKER = "HELDOUT EVALUATION AUTHORIZED"
APPROVAL_FIELDS = ("marker", "approved_by", "approved_on", "splits", "tiers", "output_paths",
                   "frozen_manifest_sha256")
RUNNER_SPLITS = {"dev": ["dev"], "heldout": ["heldout"], "all": ["dev", "heldout"]}


@dataclass
class RunRequest:
    mode: str
    splits: list
    tiers: list
    output_paths: list
    allow_live_provider: bool = False
    approval_file: str | None = None
    dataset_manifest: dict | None = None
    frozen_manifest: dict | None = None
    frozen_manifest_sha256: str | None = None
    notes: list = field(default_factory=list)


def threshold_result(split: str, tier: int, correct: int, evaluated: int) -> dict:
    """PASS/FAIL against the frozen exact minimum (no rounding)."""
    spec = FROZEN_THRESHOLDS.get((split, tier))
    if spec is None:
        return {"status": "NO_FROZEN_THRESHOLD", "split": split, "tier": tier}
    complete = evaluated == spec["cases"]
    return {
        "split": split, "tier": tier, "correct": correct, "evaluated": evaluated,
        "required_cases": spec["cases"], "min_correct": spec["min_correct"],
        "status": ("PASS" if correct >= spec["min_correct"] else "FAIL") if complete else "INCOMPLETE",
    }


def protect_output(path: str) -> list:
    if not path:
        return ["output path is required"]
    if os.path.exists(path):
        return [f"output already exists (never overwritten): {path}"]
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        return [f"output directory does not exist: {parent}"]
    return []


def _resolve(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.join(ROOT, path)))


def _same_strings(value, expected) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value) and sorted(value) == sorted(expected)


def _approval_binding_problems(approval: dict, req: RunRequest) -> list:
    problems = []
    if approval["marker"] != HELDOUT_APPROVAL_MARKER:
        problems.append(f"approval file lacks the marker {HELDOUT_APPROVAL_MARKER!r}")
    for key in ("approved_by", "approved_on"):
        if not isinstance(approval[key], str) or not approval[key].strip():
            problems.append(f"approval field {key!r} must be a non-empty string")
    if not _same_strings(approval["splits"], req.splits or []):
        problems.append(f"approval splits {approval['splits']!r} do not match the requested splits {req.splits!r}")
    tiers = approval["tiers"]
    if not (isinstance(tiers, list) and all(type(t) is int for t in tiers) and sorted(tiers) == sorted(req.tiers or [])):
        problems.append(f"approval tiers {tiers!r} do not match the requested tiers {req.tiers!r}")
    outputs = approval["output_paths"]
    if not (isinstance(outputs, list) and all(isinstance(p, str) and p for p in outputs)
            and sorted(map(_resolve, outputs)) == sorted(map(_resolve, req.output_paths or []))):
        problems.append("approval output_paths do not match the requested output paths")
    if not req.frozen_manifest_sha256 or approval["frozen_manifest_sha256"] != req.frozen_manifest_sha256:
        problems.append("approval frozen_manifest_sha256 does not match the frozen manifest in use")
    return problems


def approval_problems(req: RunRequest) -> list:
    """Validate the held-out approval file and bind it to this exact request."""
    if not req.approval_file or not os.path.isfile(req.approval_file):
        return ["held-out execution requires an existing written approval file"]
    try:
        with open(req.approval_file, encoding="utf-8-sig") as fh:
            approval = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"approval file is malformed (not readable JSON: {error.__class__.__name__})"]
    if not isinstance(approval, dict):
        return ["approval file is malformed (must be a JSON object)"]
    missing = [k for k in APPROVAL_FIELDS if k not in approval]
    if missing:
        return [f"approval file is incomplete; missing fields: {missing}"]
    return _approval_binding_problems(approval, req)


def check_run_request(req: RunRequest) -> list:
    problems = []
    if req.mode not in MODES:
        problems.append(f"mode must be one of {MODES} (got {req.mode!r})")
    if not req.splits:
        problems.append("explicit split selection is required (no default to all)")
    if any(s not in ("dev", "heldout") for s in req.splits or []):
        problems.append("splits must be 'dev' and/or 'heldout'")
    if not req.tiers or any(t not in (1, 2) for t in req.tiers):
        problems.append("explicit tiers (1 and/or 2) are required")
    if not req.output_paths:
        problems.append("explicit output paths are required")
    for p in req.output_paths or []:
        problems.extend(protect_output(p))

    if req.mode == "offline" and req.allow_live_provider:
        problems.append("offline mode cannot allow live provider calls")
    if req.mode in ("development", "heldout") and not req.allow_live_provider:
        problems.append("live provider calls require explicit opt-in (allow_live_provider=True)")

    if "heldout" in (req.splits or []) or req.mode == "heldout":
        if req.mode != "heldout":
            problems.append("the held-out split can only be run in 'heldout' mode")
        problems.extend(approval_problems(req))
        if not req.dataset_manifest or not req.frozen_manifest:
            problems.append("held-out execution requires the current and the frozen dataset manifests")
        else:
            from eval.framework.integrity import compare_to_manifest
            diffs = compare_to_manifest(req.dataset_manifest, req.frozen_manifest)
            if diffs:
                problems.append(f"dataset differs from the frozen manifest: {diffs}")
            if not req.dataset_manifest.get("valid"):
                problems.append("dataset manifest is not valid")
    return problems


def runner_gate(split: str, tier: int, output_path: str, approval_file: str | None,
                frozen_manifest_path: str, limit: int | None = None) -> list:
    """Gate for eval/phase35/run_eval.py. Pure checks: no database, no provider, no writes.

    'dev' is allowed without approval (unchanged behaviour, --limit included).
    'heldout' and 'all' require a verified frozen manifest and a bound approval
    file, and refuse any --limit (a partial held-out run would break run-once);
    anything missing, malformed or mismatched is refused.
    """
    if split == "dev":
        return []
    if split not in RUNNER_SPLITS:
        return [f"unknown split {split!r}"]
    if limit is not None:
        return [f"--limit is not allowed with --split {split} (held-out runs are complete and run once)"]
    from eval.framework.frozen_manifest import load_frozen_manifest, verify_frozen_manifest

    frozen, problems = load_frozen_manifest(frozen_manifest_path)
    if problems:
        return problems
    try:
        problems, current = verify_frozen_manifest(frozen)
    except OSError as error:
        return [f"frozen assets could not be verified: {error.__class__.__name__}: {error.filename}"]
    req = RunRequest(mode="heldout", splits=RUNNER_SPLITS[split], tiers=[tier], output_paths=[output_path],
                     allow_live_provider=True, approval_file=approval_file,
                     dataset_manifest=current["dataset"], frozen_manifest=frozen["content"]["dataset"],
                     frozen_manifest_sha256=frozen["content_sha256"])
    return problems + check_run_request(req)
