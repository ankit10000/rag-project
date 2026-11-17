"""Stage 9 Phase E2: the frozen v1 scorer is unchanged (TEST-12).

Pure static checks plus a side-effect-free import of eval/phase35/run_eval.py. `git show` is run
read-only to compare the scorer functions with the committed HEAD version. No database, no LLM,
no network, no evaluation.
"""
import testsafe
testsafe.require_scratch_db()

import ast
import hashlib
import os
import subprocess
import sys

from eval.framework.hashing import portable_sha256
from eval.framework.integrity import ROOT

FAILURES = []
RUN_EVAL = os.path.join(ROOT, "eval", "phase35", "run_eval.py")
ANSWER_SCORING = os.path.join(ROOT, "eval", "answer_scoring.py")
ANSWER_SCORING_SHA256 = "c3b5422820b96266be8529e853653ebc40184e3b48e2cd7991f68663cf8167af"
SNAPSHOT_NAMES = ("score_generic", "norm_numbers", "split_of", "tier1_context", "NUM_RE", "REF_RE")
# sha256(ast.dump(node)) recorded in Phase E2 with Python 3.14 (ast.dump output is version-specific).
RECORDED_PYTHON = (3, 14)
RECORDED_AST = {
    "score_generic": "2e74b5de7bbb84f7fe028ae2947afabc6876eb1e78d4e86ec0ab85d983f48862",
    "norm_numbers": "9a75415a6fcac2aa6d39b0469fc112451edc8da9e16f6827f2dd3f7873f5d18e",
    "split_of": "d81562b3efcf3a9718d04736af672991b586200d99459fd4b0ff4f838f3e3495",
    "tier1_context": "5b53e97aee1b6a31d9c1dc2bd16db360dde4e07cb6c1aef8763e0669af01c6bf",
    "NUM_RE": "e2dc71ce594da2cad0cfc9043d8c0c91ffe9c7a28d5926b8e59001cc7c2fa0ce",
    "REF_RE": "cfafff8e6924f646909619b6520e8bcd20d2fb1a271248c99bffeb5b40556a6a",
}


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def snapshots(source: str) -> dict:
    """sha256 of ast.dump for the frozen functions and the NUM_RE / REF_RE assignments."""
    out = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in SNAPSHOT_NAMES:
            out[node.name] = hashlib.sha256(ast.dump(node).encode()).hexdigest()
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                getattr(node.targets[0], "id", None) in SNAPSHOT_NAMES:
            out[node.targets[0].id] = hashlib.sha256(ast.dump(node).encode()).hexdigest()
    return out


def head_source():
    """run_eval.py as committed at HEAD (read-only `git show`), or None when git cannot provide it."""
    try:
        out = subprocess.run(["git", "-C", ROOT, "show", "HEAD:eval/phase35/run_eval.py"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"      git unavailable: {error.__class__.__name__}")
        return None
    return out.stdout if out.returncode == 0 else None


with open(ANSWER_SCORING, "rb") as fh:
    check("eval/answer_scoring.py SHA-256 unchanged (portable, CRLF-neutral)",
          portable_sha256(fh.read(), "text") == ANSWER_SCORING_SHA256)

with open(RUN_EVAL, encoding="utf-8") as fh:
    current_source = fh.read()
current = snapshots(current_source)
check("all six frozen definitions found in run_eval.py", sorted(current) == sorted(SNAPSHOT_NAMES))

head = head_source()
if head is None:
    print("SKIP | git HEAD comparison not run (git or the HEAD blob is unavailable); recorded hashes still apply")
else:
    head_snap = snapshots(head)
    for name in SNAPSHOT_NAMES:
        check(f"run_eval.{name}: AST identical to git HEAD", current.get(name) == head_snap.get(name))

if sys.version_info[:2] == RECORDED_PYTHON:
    for name in SNAPSHOT_NAMES:
        check(f"run_eval.{name}: AST identical to the Phase E2 recording", current.get(name) == RECORDED_AST[name])
else:
    print(f"SKIP | recorded AST hashes were taken on Python {RECORDED_PYTHON}; running {sys.version_info[:2]}")

imported = set()
for node in ast.walk(ast.parse(current_source)):
    if isinstance(node, ast.ImportFrom):
        imported.add(node.module or "")
        imported.update(f"{node.module}.{a.name}" for a in node.names)
    elif isinstance(node, ast.Import):
        imported.update(a.name for a in node.names)
check("run_eval.py has no import of a scoring_v2 module (static)", not any("scoring_v2" in m for m in imported))

from eval import answer_scoring  # noqa: E402
from eval.phase35 import run_eval  # noqa: E402

check("INSUFFICIENCY_PHRASES has 22 entries", len(answer_scoring.INSUFFICIENCY_PHRASES) == 22)
check("DISAGREEMENT_PHRASES has 7 entries", len(answer_scoring.DISAGREEMENT_PHRASES) == 7)
check("run_eval uses the very same phrase lists", run_eval.INSUFFICIENCY_PHRASES is answer_scoring.INSUFFICIENCY_PHRASES
      and run_eval.DISAGREEMENT_PHRASES is answer_scoring.DISAGREEMENT_PHRASES)

import eval.probes.scorer_regression  # noqa: E402,F401  (the probe harness must not alter v1)

check("phrase lists still 22 / 7 after importing the probe harness",
      len(answer_scoring.INSUFFICIENCY_PHRASES) == 22 and len(answer_scoring.DISAGREEMENT_PHRASES) == 7)
check("no eval.scoring_v2 module loaded at runtime", not any(m.startswith("eval.scoring_v2") for m in sys.modules))
check("importing run_eval loads no services.* module",
      not any(m == "services" or m.startswith("services.") for m in sys.modules))

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
