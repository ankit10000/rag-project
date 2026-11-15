"""Execution gates for FUTURE evaluation runs (nothing here runs an evaluation).

A run request must name: mode (offline | development | heldout), explicit
split(s), explicit output path(s) that do not exist yet, whether live provider
calls are allowed (opt-in), and — for held-out — a written approval file.
``check_run_request`` returns a list of blocking problems; an empty list is
the only "allowed" outcome. The existing runner (eval/phase35/run_eval.py) is
not modified; integrating this gate into it is a documented future step.
"""

import os
from dataclasses import dataclass, field

MODES = ("offline", "development", "heldout")

# Frozen thresholds (docs/remediation/HELDOUT_THRESHOLD_FREEZE.md and the Stage B dev report).
# Exact minimum counts; a score is never rounded up to pass.
FROZEN_THRESHOLDS = {
    ("dev", 1): {"cases": 47, "min_correct": 41},
    ("dev", 2): {"cases": 42, "min_correct": 28},
    ("heldout", 1): {"cases": 113, "min_correct": 97, "percent": 85},
    ("heldout", 2): {"cases": 106, "min_correct": 69, "percent": 65},
}

HELDOUT_APPROVAL_MARKER = "HELDOUT EVALUATION AUTHORIZED"


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
        if not req.approval_file or not os.path.isfile(req.approval_file):
            problems.append("held-out execution requires an existing written approval file")
        else:
            text = open(req.approval_file, encoding="utf-8").read()
            if HELDOUT_APPROVAL_MARKER not in text:
                problems.append(f"approval file lacks the marker {HELDOUT_APPROVAL_MARKER!r}")
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
