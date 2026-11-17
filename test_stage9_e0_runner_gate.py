"""Stage 9 Phase E0: split gate in the official runner eval/phase35/run_eval.py.

Unit test: every side-effect boundary (scratch database, ingestion, case
execution, provider services) is replaced by a recording tripwire. Results go
to a temporary directory. Approval files are temporary test fixtures bound to
temporary output paths, so they can never authorize a real run. No database,
no LLM call, no evaluation case is executed.

The gate runs against a FIXTURE frozen manifest built from the current working
tree in a temporary directory (Phase E2, TEST-11), so this test does not depend
on the committed manifest still reproducing. Whether the committed manifest
reproduces is live state, reported by check_stage9_readiness.py.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import json
import os
import sys
import tempfile
from unittest import mock

import psycopg

from eval.framework import safety
from eval.framework.frozen_manifest import build_content, content_sha256, load_frozen_manifest
from eval.framework.integrity import ROOT, load_dataset, split_of
from eval.phase35 import run_eval as R

FAILURES = []
DATASET_VERSION = "phase35-corrected-2026-11-12"
FIXTURE_DIR = tempfile.TemporaryDirectory()
FIXTURE_CONTENT = build_content(DATASET_VERSION)
FIXTURE_MANIFEST = os.path.join(FIXTURE_DIR.name, "frozen_manifest.json")
with open(FIXTURE_MANIFEST, "w", encoding="utf-8") as _fh:
    json.dump({"content_sha256": content_sha256(FIXTURE_CONTENT), "content": FIXTURE_CONTENT}, _fh)
MANIFEST, _FIXTURE_PROBLEMS = load_frozen_manifest(FIXTURE_MANIFEST)
REAL_FROZEN_MANIFEST = R.FROZEN_MANIFEST
_, CASES = load_dataset()
DEV_IDS = [c["id"] for c in CASES if split_of(c["id"]) == "dev"]
REAL_RESULTS_DIR = R.RESULTS_DIR
DROP = object()


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


class Tripwire(Exception):
    pass


def snapshot(folder):
    out = {}
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), "rb") as fh:
            out[name] = fh.read()
    return out


@contextlib.contextmanager
def sandbox():
    """Temp results dir (with an existing dev file) and tripwires on every side-effect boundary."""
    calls = []

    def tripwire(name):
        def fn(*args, **kwargs):
            calls.append(name)
            raise Tripwire(name)
        return fn

    with tempfile.TemporaryDirectory() as tmp:
        results = os.path.join(tmp, "results")
        os.mkdir(results)
        with open(os.path.join(results, "tier1_dev.jsonl"), "w", encoding="utf-8") as fh:
            fh.write('{"id": "pre-existing"}\n')
        with mock.patch.object(R, "RESULTS_DIR", results), \
                mock.patch.object(R, "FROZEN_MANIFEST", FIXTURE_MANIFEST), \
                mock.patch.object(R.harness, "use_scratch_database", tripwire("db:create/connect scratch")), \
                mock.patch.object(psycopg, "connect", tripwire("db:psycopg.connect")), \
                mock.patch.object(R, "build_scratch_corpus", tripwire("db:truncate+ingest")), \
                mock.patch.object(R, "run_tier1", tripwire("case:tier1")), \
                mock.patch.object(R, "run_tier2", tripwire("case:tier2")):
            yield tmp, results, calls


def run_main(argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            R.main(argv)
            return "returned", err.getvalue()
        except SystemExit as exit_:
            return f"exit:{exit_.code}", err.getvalue()
        except Tripwire as hit:
            return f"tripwire:{hit}", err.getvalue()


def write_approval(tmp, results, split="heldout", tier=1, raw=None, **overrides):
    """A TEST-ONLY approval, bound to a temporary output path."""
    approval = {
        "marker": safety.HELDOUT_APPROVAL_MARKER,
        "approved_by": "TEST FIXTURE - NOT AN AUTHORIZATION", "approved_on": "2000-01-01",
        "splits": safety.RUNNER_SPLITS[split], "tiers": [tier],
        "output_paths": [os.path.join(results, f"tier{tier}_{split}.jsonl")],
        "frozen_manifest_sha256": MANIFEST["content_sha256"],
    }
    for key, value in overrides.items():
        if value is DROP:
            approval.pop(key)
        else:
            approval[key] = value
    path = os.path.join(tmp, "approval.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(raw if raw is not None else json.dumps(approval))
    return path


def expect_refused(label, argv, needle, prepare=None):
    """Run the runner and require exit 3, the reason, no side effect and unchanged results."""
    with sandbox() as (tmp, results, calls):
        extra = prepare(tmp, results) if prepare else []
        before = snapshot(results)
        outcome, err = run_main(argv + extra)
        check(f"{label}: refused (exit 3)", outcome == "exit:3")
        check(f"{label}: reason reported ({needle!r})", needle in err)
        check(f"{label}: no DB / ingestion / case execution", calls == [])
        check(f"{label}: result files unchanged", snapshot(results) == before)


def approval_arg(**kw):
    split = kw.pop("split", "heldout")
    tier = kw.pop("tier", 1)
    return lambda tmp, results: ["--approval-file", write_approval(tmp, results, split, tier, **kw)]


check("fixture frozen manifest (built from the working tree in a temp dir) loads",
      MANIFEST is not None and _FIXTURE_PROBLEMS == [])
check("runner default --frozen-manifest is the committed eval/phase35/frozen_manifest.json",
      os.path.normpath(REAL_FROZEN_MANIFEST) == os.path.join(ROOT, "eval", "phase35", "frozen_manifest.json"))

# ---------------------------------------------------------------- refusals --
HELD = ["--tier", "1", "--split", "heldout"]
ALL = ["--tier", "1", "--split", "all"]
expect_refused("heldout without approval", HELD, "requires an existing written approval file")
expect_refused("all without approval", ALL, "requires an existing written approval file")
expect_refused("tier 2 heldout without approval", ["--tier", "2", "--split", "heldout", "--fresh"],
               "requires an existing written approval file")
expect_refused("malformed approval (not JSON)", HELD, "malformed", approval_arg(raw="marker: yes {"))
expect_refused("malformed approval (JSON list)", HELD, "malformed", approval_arg(raw="[]"))
expect_refused("incomplete approval", HELD, "incomplete", approval_arg(frozen_manifest_sha256=DROP))
expect_refused("approval without marker", HELD, "marker", approval_arg(marker="AUTHORIZED"))
expect_refused("approval with empty approver", HELD, "approved_by", approval_arg(approved_by=" "))
expect_refused("heldout approval used for --split all", ALL, "splits", approval_arg(split="heldout"))
expect_refused("all approval used for --split heldout", HELD, "splits",
               lambda tmp, results: ["--approval-file", write_approval(
                   tmp, results, "all", output_paths=[os.path.join(results, "tier1_heldout.jsonl")])])
expect_refused("approval for another tier", HELD, "tiers", approval_arg(tiers=[2]))
expect_refused("approval tier given as boolean", HELD, "tiers", approval_arg(tiers=[True]))
expect_refused("approval for another output path", HELD, "output_paths", approval_arg(output_paths=["x.jsonl"]))
expect_refused("approval for another frozen manifest", HELD, "frozen_manifest_sha256",
               approval_arg(frozen_manifest_sha256="0" * 64))


def missing_manifest(tmp, results):
    return ["--approval-file", write_approval(tmp, results), "--frozen-manifest", os.path.join(tmp, "none.json")]


def tampered_manifest(tmp, results):
    bad = json.loads(json.dumps(MANIFEST))
    bad["content"]["thresholds"]["heldout/tier1"]["min_correct"] = 90
    path = os.path.join(tmp, "tampered.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bad, fh)
    return ["--approval-file", write_approval(tmp, results), "--frozen-manifest", path]


def stale_manifest(tmp, results):
    """Self-consistent manifest whose recorded scorer hash no longer matches the file."""
    bad = json.loads(json.dumps(MANIFEST))
    for asset in bad["content"]["assets"]:
        if asset["path"] == "eval/answer_scoring.py":
            asset["portable_sha256"] = "0" * 64
    bad["content_sha256"] = content_sha256(bad["content"])
    path = os.path.join(tmp, "stale.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bad, fh)
    approval = write_approval(tmp, results, frozen_manifest_sha256=bad["content_sha256"])
    return ["--approval-file", approval, "--frozen-manifest", path]


def existing_heldout_output(tmp, results):
    with open(os.path.join(results, "tier1_heldout.jsonl"), "w", encoding="utf-8") as fh:
        fh.write('{"id": "earlier"}\n')
    return ["--approval-file", write_approval(tmp, results)]


# --limit with held-out/all: refused even with an otherwise valid test approval.
expect_refused("heldout with --limit (valid approval)", HELD + ["--limit", "5"], "--limit is not allowed",
               approval_arg())
expect_refused("all with --limit (valid approval)", ALL + ["--limit", "5"], "--limit is not allowed",
               approval_arg(split="all"))
expect_refused("tier 2 heldout with --limit 0", ["--tier", "2", "--split", "heldout", "--limit", "0"],
               "--limit is not allowed", approval_arg(tier=2))
expect_refused("all with --limit, no approval", ALL + ["--limit", "1"], "--limit is not allowed")
check("gate function: dev keeps --limit", safety.runner_gate("dev", 1, "x", None, "missing", limit=3) == [])

expect_refused("frozen manifest missing", HELD, "frozen manifest not found", missing_manifest)
expect_refused("frozen manifest edited", HELD, "does not match its content", tampered_manifest)
expect_refused("frozen asset changed since freeze", HELD, "frozen asset changed: eval/answer_scoring.py",
               stale_manifest)
expect_refused("held-out output already exists", HELD + ["--fresh"], "never overwritten", existing_heldout_output)


def fixture_against_real_results_dir(tmp, results):
    path = write_approval(tmp, results)
    R.RESULTS_DIR = REAL_RESULTS_DIR      # restored by the sandbox's mock.patch
    return ["--approval-file", path]


real_before = snapshot(REAL_RESULTS_DIR)
expect_refused("test fixture cannot authorize the real results path", HELD, "output_paths",
               fixture_against_real_results_dir)
check("real results directory unchanged", snapshot(REAL_RESULTS_DIR) == real_before)

# ------------------------------------------- valid test-only approval passes --
for split, tier in (("heldout", 1), ("all", 2)):
    with sandbox() as (tmp, results, calls):
        before = snapshot(results)
        approval = write_approval(tmp, results, split, tier)
        outcome, err = run_main(["--tier", str(tier), "--split", split, "--approval-file", approval])
        label = f"valid test approval ({split}, tier {tier})"
        accepted = outcome == "tripwire:db:create/connect scratch" and "REFUSED" not in err
        if not accepted:
            print(f"      gate output: {outcome}\n{err}")
        check(f"{label}: gate accepted (fixture manifest), stopped at the first side effect", accepted)
        check(f"{label}: no case executed, no ingestion", calls == ["db:create/connect scratch"])
        check(f"{label}: no result file written", snapshot(results) == before)

check("gate function: dev needs no approval or manifest", safety.runner_gate("dev", 1, "x", None, "missing") == [])
check("gate function: unknown split refused", safety.runner_gate("train", 1, "x", None, FIXTURE_MANIFEST) != [])
check("provider services never imported", not any(m == "services" or m.startswith("services.") for m in sys.modules))


# ---------------------------------------------------- dev behaviour unchanged --
def fake_case(case, docs):
    return {"id": case["id"], "split": case["split"], "status": "answered", "latency_s": 0.0,
            "score": {"correct": True, "citation_correctness": 1.0, "citation_completeness": 1.0}}


def run_dev(argv):
    calls = []
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(R, "RESULTS_DIR", tmp), \
            mock.patch.object(R, "bootstrap_execution", lambda: calls.append("bootstrap")), \
            mock.patch.object(R.harness, "assert_scratch", lambda: None), \
            mock.patch.object(psycopg, "connect", mock.Mock(side_effect=Tripwire("db"))), \
            mock.patch.object(R, "build_scratch_corpus", lambda docs: calls.append("ingest")), \
            mock.patch.object(R, "run_tier1", fake_case), mock.patch.object(R, "run_tier2", fake_case):
        outcome, _ = run_main(argv + ["--pause", "0", "--frozen-manifest", os.path.join(tmp, "absent.json")])
        files = os.listdir(tmp)
        rows = []
        for name in files:
            with open(os.path.join(tmp, name), encoding="utf-8") as fh:
                rows += [json.loads(line) for line in fh]
    return outcome, calls, files, rows


outcome, calls, files, rows = run_dev(["--tier", "1"])
check("default split: runs without approval", outcome == "returned" and calls == ["bootstrap"])
check("default split: writes tier1_dev.jsonl", files == ["tier1_dev.jsonl"])
check("default split: exactly the 47 dev cases, in dataset order", [r["id"] for r in rows] == DEV_IDS
      and len(rows) == 47 and all(r["split"] == "dev" for r in rows))
outcome, calls, files, rows = run_dev(["--tier", "1", "--split", "dev", "--limit", "3"])
check("explicit dev: runs without approval, --limit honoured", outcome == "returned" and len(rows) == 3
      and [r["id"] for r in rows] == DEV_IDS[:3])
outcome, calls, files, rows = run_dev(["--tier", "2", "--split", "dev"])
check("dev tier 2: 42 dev cases, ingestion step still runs first", outcome == "returned" and len(rows) == 42
      and calls == ["bootstrap", "ingest"] and all(split_of(r["id"]) == "dev" for r in rows))

FIXTURE_DIR.cleanup()
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
