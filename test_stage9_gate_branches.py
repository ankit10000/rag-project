"""Stage 9 Phase E2: branch coverage for eval/framework/safety.py and frozen_manifest.py (TEST-13).

Unit test: fixture manifests and approval files live in temporary directories; drift is simulated
by monkeypatching (thresholds, dataset validity, an extra source PDF, an OSError). Nothing in the
repository is written. No database, no LLM, no network, no evaluation.
"""
import testsafe
testsafe.require_scratch_db()

import copy
import json
import os
import sys
import tempfile
from unittest import mock

from eval.framework import frozen_manifest as FM
from eval.framework import safety
from eval.framework.safety import RunRequest, approval_problems, check_run_request, runner_gate, threshold_result

FAILURES = []
VERSION = "phase35-corrected-2026-11-12"


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def has(problems, text):
    return any(text in p for p in problems)


def write(folder, name, data):
    path = os.path.join(folder, name)
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


def manifest_for(content):
    return {"content_sha256": FM.content_sha256(content), "content": content}


BASE = FM.build_content(VERSION)            # the working tree as it is now (fixture, not the committed file)
FIXTURE = manifest_for(BASE)

with tempfile.TemporaryDirectory() as tmp:
    # -------------------------------------------------- load_frozen_manifest branches --
    cases = {
        "not JSON": ("bad.json", "{content: nope", "unreadable or not JSON: JSONDecodeError"),
        "not UTF-8": ("latin.json", b'{"content": "\xff\xfe"}', "unreadable or not JSON: UnicodeDecodeError"),
        "JSON list": ("list.json", "[]", "malformed (missing content/dataset)"),
        "content missing": ("nocontent.json", json.dumps({"content_sha256": "x"}), "malformed (missing content/dataset)"),
        "dataset missing": ("nodataset.json", json.dumps({"content": {"manifest_format": FM.MANIFEST_FORMAT}}),
                            "malformed (missing content/dataset)"),
        "wrong format": ("format.json", json.dumps(manifest_for({**BASE, "manifest_format": "other/9"})),
                         "format is not"),
        "content hash mismatch": ("hash.json", json.dumps({**FIXTURE, "content_sha256": "0" * 64}),
                                  "does not match its content"),
    }
    for label, (name, data, needle) in cases.items():
        manifest, problems = FM.load_frozen_manifest(write(tmp, name, data))
        check(f"load_frozen_manifest: {label} -> refused ({needle})", manifest is None and has(problems, needle))
    for label, path in (("directory", tmp), ("None", None), ("missing file", os.path.join(tmp, "absent.json"))):
        manifest, problems = FM.load_frozen_manifest(path)
        check(f"load_frozen_manifest: path is {label} -> not found", manifest is None and has(problems, "not found"))
    good = write(tmp, "good.json", json.dumps(FIXTURE))
    manifest, problems = FM.load_frozen_manifest(good)
    check("load_frozen_manifest: fixture built from the working tree loads", problems == [] and manifest == FIXTURE)

    # ------------------------------------------------- verify_frozen_manifest branches --
    problems, _ = FM.verify_frozen_manifest(FIXTURE)
    check("verify: fixture reproduces (control)", problems == [])
    real_records = FM.asset_records

    def with_extra_pdf(root=FM.ROOT):
        extra = {"group": "source_pdf", "path": f"{FM.SOURCE_PDF_DIR}/Extra.pdf", "kind": "binary",
                 "portable_sha256": "e" * 64, "git_blob_sha1": "e" * 40}
        return real_records(root) + [extra]

    with mock.patch.object(FM, "asset_records", with_extra_pdf):
        problems, _ = FM.verify_frozen_manifest(FIXTURE)
    check("verify: extra source PDF -> asset not in the frozen manifest",
          has(problems, f"asset not in the frozen manifest: {FM.SOURCE_PDF_DIR}/Extra.pdf"))
    check("verify: extra source PDF -> PDF/document match section differs",
          has(problems, "section differs from the working tree: source_pdfs_match_dataset_documents"))
    missing = copy.deepcopy(BASE)
    missing["assets"].append({"group": "dataset", "path": "eval/phase35/data_Z.py", "kind": "text",
                              "portable_sha256": "0" * 64, "git_blob_sha1": "0" * 40})
    problems, _ = FM.verify_frozen_manifest(manifest_for(missing))
    check("verify: frozen asset missing from the tree -> reported",
          has(problems, "frozen asset missing from the working tree: eval/phase35/data_Z.py"))
    drifted = {**safety.FROZEN_THRESHOLDS, ("heldout", 1): {"cases": 113, "min_correct": 90, "percent": 80}}
    with mock.patch.dict(safety.FROZEN_THRESHOLDS, drifted):
        problems, _ = FM.verify_frozen_manifest(FIXTURE)
    check("verify: threshold drift in safety.FROZEN_THRESHOLDS -> section differs: thresholds",
          problems == ["frozen manifest section differs from the working tree: thresholds"])
    real_build = FM.build_manifest

    def invalid_dataset(version):
        out = real_build(version)
        out.update(valid=False, errors=["X-1: injected test error"])
        return out

    with mock.patch.object(FM, "build_manifest", invalid_dataset):
        problems, current = FM.verify_frozen_manifest(FIXTURE)
    check("verify: invalid current dataset -> 'current dataset is not valid' and dataset section differs",
          has(problems, "current dataset is not valid") and has(problems, "section differs from the working tree: dataset"))

    # ----------------------------------------------------- runner_gate branches --
    output = os.path.join(tmp, "out", "tier1_heldout.jsonl")
    os.mkdir(os.path.dirname(output))

    def approval(**overrides):
        body = {"marker": safety.HELDOUT_APPROVAL_MARKER, "approved_by": "TEST FIXTURE - NOT AN AUTHORIZATION",
                "approved_on": "2000-01-01", "splits": ["heldout"], "tiers": [1], "output_paths": [output],
                "frozen_manifest_sha256": FIXTURE["content_sha256"], **overrides}
        return write(tmp, "approval.json", json.dumps(body))

    check("runner_gate: valid fixture manifest + bound approval -> accepted (control)",
          runner_gate("heldout", 1, output, approval(), good) == [])

    def raise_oserror(_manifest):
        raise FileNotFoundError(2, "No such file", "docs/remediation/heldout_review/source_pdfs/gone.pdf")

    with mock.patch.object(FM, "verify_frozen_manifest", raise_oserror):
        problems = runner_gate("heldout", 1, output, approval(), good)
    check("runner_gate: OSError while verifying -> refused with the error class and file",
          problems == ["frozen assets could not be verified: FileNotFoundError: "
                       "docs/remediation/heldout_review/source_pdfs/gone.pdf"])
    check("runner_gate: malformed manifest stops before verification",
          runner_gate("heldout", 1, output, approval(), write(tmp, "m.json", "[]")) ==
          ["frozen manifest is malformed (missing content/dataset)"])

    # ---------------------------------------------------- approval file branches --
    req = RunRequest(mode="heldout", splits=["heldout"], tiers=[1], output_paths=[output], allow_live_provider=True,
                     approval_file=None, dataset_manifest=BASE["dataset"], frozen_manifest=BASE["dataset"],
                     frozen_manifest_sha256=FIXTURE["content_sha256"])

    def problems_for(path):
        return approval_problems(RunRequest(**{**req.__dict__, "approval_file": path}))

    check("approval: path is a directory -> refused", has(problems_for(tmp), "requires an existing written approval file"))
    check("approval: non-UTF-8 bytes -> malformed (UnicodeDecodeError)",
          has(problems_for(write(tmp, "latin1.json", b'{"marker": "\xe9"}')), "UnicodeDecodeError"))
    with open(approval(), "rb") as fh:
        plain = fh.read()
    check("approval: UTF-8 BOM accepted (utf-8-sig)", problems_for(write(tmp, "bom.json", b"\xef\xbb\xbf" + plain)) == [])
    check("approval: duplicate splits do not match one requested split",
          has(problems_for(approval(splits=["heldout", "heldout"])), "approval splits"))
    check("approval: duplicate tiers do not match one requested tier",
          has(problems_for(approval(tiers=[1, 1])), "approval tiers"))
    check("approval: splits given as a string are refused", has(problems_for(approval(splits="heldout")), "approval splits"))
    check("approval: empty output path refused", has(problems_for(approval(output_paths=[""])), "output_paths"))
    check("approval: approved_on must be a non-empty string", has(problems_for(approval(approved_on="")), "approved_on"))
    # KNOWN GAP (ARCH-11, for WP7): approved_on is not validated as a date. This documents current behaviour.
    check("KNOWN GAP ARCH-11 (WP7): approved_on 'yesterday' is ACCEPTED today (documents current behaviour)",
          problems_for(approval(approved_on="yesterday")) == [])

# --------------------------------------------------------- check_run_request --
def request(**kw):
    base = dict(mode="development", splits=["dev"], tiers=[1], output_paths=[os.path.join(tempfile.gettempdir(),
                "wp3-never-created", "x.jsonl")], allow_live_provider=True)
    return RunRequest(**{**base, **kw})


check("run request: invalid mode refused", has(check_run_request(request(mode="prod")), "mode must be one of"))
check("run request: offline mode with live provider refused",
      has(check_run_request(request(mode="offline")), "offline mode cannot allow live provider calls"))
check("run request: development without live opt-in refused",
      has(check_run_request(request(allow_live_provider=False)), "require explicit opt-in"))
offline_heldout = check_run_request(request(mode="offline", splits=["heldout"], allow_live_provider=False))
check("run request: offline + heldout -> heldout mode required, approval and manifests required",
      has(offline_heldout, "can only be run in 'heldout' mode") and has(offline_heldout, "approval file")
      and has(offline_heldout, "requires the current and the frozen dataset manifests"))
check("run request: unknown split and missing tiers refused",
      has(check_run_request(request(splits=["train"], tiers=[])), "splits must be")
      and has(check_run_request(request(tiers=[3])), "explicit tiers"))
other = dict(BASE["dataset"], dataset_sha256="0" * 64)
diff = check_run_request(request(mode="heldout", splits=["heldout"], dataset_manifest=other,
                                 frozen_manifest=BASE["dataset"]))
check("run request: dataset differing from the frozen dataset -> named diff", has(diff, "dataset differs from the frozen "
      "manifest: ['dataset_sha256']"))
invalid = check_run_request(request(mode="heldout", splits=["heldout"], dataset_manifest=dict(BASE["dataset"], valid=False),
                                    frozen_manifest=BASE["dataset"]))
check("run request: invalid dataset manifest -> refused", has(invalid, "dataset manifest is not valid"))

# ------------------------------------------------------------ threshold_result --
check("threshold: no frozen threshold for an unknown split/tier -> NO_FROZEN_THRESHOLD",
      threshold_result("dev", 3, 10, 10)["status"] == "NO_FROZEN_THRESHOLD"
      and threshold_result("train", 1, 10, 10)["status"] == "NO_FROZEN_THRESHOLD")
check("threshold: 97/113 PASS, 96/113 FAIL (exact minimum, no rounding)",
      threshold_result("heldout", 1, 97, 113)["status"] == "PASS"
      and threshold_result("heldout", 1, 96, 113)["status"] == "FAIL")
check("threshold: 112 of 113 evaluated -> INCOMPLETE even with enough correct",
      threshold_result("heldout", 1, 112, 112)["status"] == "INCOMPLETE")
check("no services.* module imported", not any(m == "services" or m.startswith("services.") for m in sys.modules))

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
