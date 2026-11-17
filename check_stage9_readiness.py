"""Stage 9 live-state readiness report (NOT a unit test; read-only).

Reports the state of the working tree that unit tests deliberately do not assert (Phase E2,
TEST-10 / TEST-11), because it legitimately changes as the review and approved corrections proceed:

  1. the COMMITTED frozen manifest loads and reproduces from the working tree;
  2. the dataset matches the manifest's dataset_sha256 (the scorer probes are pinned to it);
  3. the current files still equal the historical Windows freeze hashes (Phase 3.5 freeze);
  4. the real held-out and development review workbooks: integrity errors, status, counts,
     and that reading them leaves them byte-identical.

Exit 1 when a PROBLEM is found (manifest does not reproduce, dataset differs from the manifest,
workbook integrity errors or a workbook changed by reading). Differences from the historical
freeze are WARNINGS (expected after an approved re-freeze). Review progress is information only.

No database, no provider, no network, no evaluation; writes nothing.

    .venv/bin/python -B check_stage9_readiness.py
"""
import contextlib
import csv
import hashlib
import io
import os
import sys

sys.modules.setdefault("services", None)   # any provider/database service import fails loudly

from eval.framework.frozen_manifest import load_frozen_manifest, verify_frozen_manifest  # noqa: E402
from eval.framework.integrity import ROOT, dataset_hash, file_hashes, load_dataset  # noqa: E402

MANIFEST_PATH = os.path.join(ROOT, "eval", "phase35", "frozen_manifest.json")
# Recorded on Windows in docs/remediation/HELDOUT_THRESHOLD_FREEZE.md (moved here from
# test_stage9_e0_frozen_manifest.py in Phase E2).
RECORDED_FREEZE = {
    "eval/phase35/data_A.py": "c204fd037d653a27dfed00f7d9b9ad0b38dea4d20f578145aa7bc9b15201714c",
    "eval/phase35/data_B.py": "f58fc8041bed81682e0bc22be6123364f963b170db5a409204b60922aa5a3548",
    "eval/phase35/data_C.py": "6fc3ca44254f4dc536b2bde59d355134ccdee284ff359c4a6f3ebe7deb6cfea6",
    "eval/phase35/data_D.py": "6341a55f5307cf9cc47fbf1608e7dc26e3041793f6e0184528f1a3b9249d8f64",
}
RECORDED_VALIDATE_CRLF = "1727a33421202da3bd0d52aabcf0bf11dd9515c16c73a8b10e385aa356fe1a7d"
# Recorded (truncated) in docs/remediation/heldout_review/REVIEW_SIGNOFF_REPORT.md.
RECORDED_CSV = {"heldout_review_sheet.csv": ("9bd00720", "cf77"),
                "heldout_review_sheet_REVIEWED_by_Claude.csv": ("fbe1426e", "99ca")}
WORKBOOK_ROWS = {"heldout": 113, "dev": 7}


def _read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), "rb") as fh:
        return fh.read()


def manifest_section(report):
    manifest, problems = load_frozen_manifest(MANIFEST_PATH)
    if problems:
        report.problem(f"committed frozen manifest does not load: {problems}")
        return None
    problems, _ = verify_frozen_manifest(manifest)
    if problems:
        report.problem(f"committed frozen manifest does NOT reproduce from the working tree: {problems}")
    else:
        report.ok(f"committed frozen manifest REPRODUCED (content_sha256 {manifest['content_sha256']})")
    _, cases = load_dataset()
    if dataset_hash(cases) != manifest["content"]["dataset"]["dataset_sha256"]:
        report.problem("dataset differs from the manifest's dataset_sha256 (scorer probe expectations are pinned to it)")
    else:
        report.ok("dataset equals the manifest's dataset_sha256 (scorer probes pinned)")
    return manifest


def historical_section(report):
    if file_hashes() == RECORDED_FREEZE:
        report.ok("dataset modules equal the historical Windows freeze hashes")
    else:
        report.warn("dataset modules differ from the historical Windows freeze hashes (expected after an approved change)")
    crlf = _read("eval/phase35/validate.py").replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if hashlib.sha256(crlf).hexdigest() == RECORDED_VALIDATE_CRLF:
        report.ok("validate.py (CRLF form) equals the historical freeze hash")
    else:
        report.warn("validate.py differs from the historical freeze hash")
    for name, (head, tail) in RECORDED_CSV.items():
        with open(os.path.join(ROOT, "docs", "remediation", "heldout_review", name), encoding="utf-8-sig",
                  newline="") as fh:
            rows = list(csv.reader(fh))
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\r\n").writerows(rows)
        digest = hashlib.sha256(b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")).hexdigest()
        if digest.startswith(head) and digest.endswith(tail):
            report.ok(f"{name}: Windows serialization equals the recorded hash")
        else:
            report.warn(f"{name}: differs from the recorded hash (regenerated review package?)")


def workbook_section(report):
    from eval.review import cli
    for kind, rows in WORKBOOK_ROWS.items():
        path = os.path.join(ROOT, cli.WORKBOOKS[kind])
        before = hashlib.sha256(_read(cli.WORKBOOKS[kind])).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            result, _ = cli._report(type("Args", (), {"kind": kind, "workbook": None, "baseline_git": None})())
        counts = result["counts"]
        if result["errors"]:
            report.problem(f"{kind} workbook has {len(result['errors'])} integrity error(s): {result['errors'][:5]}")
        if counts["rows"] != rows or counts["pending"] + counts["reviewed"] != rows:
            report.problem(f"{kind} workbook: expected {rows} rows, counts {counts}")
        if hashlib.sha256(_read(cli.WORKBOOKS[kind])).hexdigest() != before:
            report.problem(f"{kind} workbook changed while being read: {path}")
        report.info(f"{kind} workbook: status {result['status']}; reviewed {counts['reviewed']} / pending "
                    f"{counts['pending']}; incomplete items {len(result['incomplete'])}; "
                    f"ledger {result['ledger']}")


class Report:
    def __init__(self):
        self.problems, self.warnings = [], []

    def ok(self, text):
        print(f"OK      | {text}")

    def info(self, text):
        print(f"INFO    | {text}")

    def warn(self, text):
        self.warnings.append(text)
        print(f"WARNING | {text}")

    def problem(self, text):
        self.problems.append(text)
        print(f"PROBLEM | {text}")


def main():
    report = Report()
    print("== frozen manifest (committed) ==")
    manifest_section(report)
    print("== historical Phase 3.5 freeze records ==")
    historical_section(report)
    print("== review workbooks (read-only) ==")
    workbook_section(report)
    if any(m.startswith("services.") for m in sys.modules):
        report.problem("a services.* module was imported")
    print(f"\n{len(report.problems)} problem(s), {len(report.warnings)} warning(s)")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
