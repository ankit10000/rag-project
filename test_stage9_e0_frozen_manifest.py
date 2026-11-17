"""Stage 9 Phase E0: portable hashing and the frozen Phase 3.5 manifest.

Unit test (pure file reads; no database, no LLM, no evaluation). Windows and
Unix checkouts are simulated in a temporary directory; no repository file is
modified.

Phase E2 (TEST-11): reproduction is tested on a FIXTURE manifest built from the
current working tree in a temporary directory, so this test does not fail
after an approved, re-frozen change. Live-state checks (the committed manifest
reproduces; current files equal the historical Windows freeze hashes) are in
check_stage9_readiness.py.
"""
import testsafe
testsafe.require_scratch_db()

import csv
import io
import json
import os
import shutil
import sys
import tempfile

from eval.framework import hashing
from eval.framework.frozen_manifest import (
    asset_list, asset_records, build_content, content_sha256, load_frozen_manifest, verify_frozen_manifest,
)
from eval.framework.integrity import ROOT

FAILURES = []
MANIFEST_PATH = os.path.join(ROOT, "eval", "phase35", "frozen_manifest.json")
DATASET_VERSION = "phase35-corrected-2026-11-12"


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), "rb") as fh:
        return fh.read()


def to_crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


# ------------------------------------------------------- normalization rules --
unix, windows = b"line one\nline two\n", b"line one\r\nline two\r\n"
check("text: CRLF and LF hash the same", hashing.portable_sha256(unix, "text") == hashing.portable_sha256(windows, "text"))
check("text: raw hashes differ (fixture really differs)", hashing.raw_sha256(unix) != hashing.raw_sha256(windows))
check("text: lone CR is not normalized", hashing.portable_sha256(b"a\rb", "text") != hashing.portable_sha256(b"a\nb", "text"))
check("text: UTF-8 BOM is preserved (a BOM change is a content change)",
      hashing.portable_sha256(b"\xef\xbb\xbfid,x\r\n", "text") != hashing.portable_sha256(b"id,x\n", "text")
      and hashing.portable_sha256(b"\xef\xbb\xbfid,x\r\n", "text") == hashing.portable_sha256(b"\xef\xbb\xbfid,x\n", "text"))
check("text: trailing whitespace is not normalized",
      hashing.portable_sha256(b"a \n", "text") != hashing.portable_sha256(b"a\n", "text"))
check("binary: no normalization", hashing.portable_sha256(windows, "binary") == hashing.raw_sha256(windows)
      and hashing.portable_sha256(windows, "binary") != hashing.portable_sha256(unix, "binary"))
check("git blob id matches git's object format (blob of 'hello\\n')",
      hashing.git_blob_sha1(b"hello\n", "text") == "ce013625030ba8dba906f756967f9e9ca394464a"
      and hashing.git_blob_sha1(b"hello\r\n", "text") == "ce013625030ba8dba906f756967f9e9ca394464a")
try:
    hashing.portable_sha256(b"x", "auto")
    check("unknown asset kind rejected", False)
except ValueError:
    check("unknown asset kind rejected", True)

# ------------------------------------------- Windows serialization of the frozen files --
# (Equality with the historical recorded freeze hashes is live state: check_stage9_readiness.py.)
validate_lf = read("eval/phase35/validate.py")
check("validate.py: portable hash identical for the CRLF and LF forms",
      hashing.portable_sha256(to_crlf(validate_lf), "text") == hashing.portable_sha256(validate_lf, "text"))

# Review CSVs were written on Windows by the csv module: BOM + CRLF row terminators, while
# newlines inside quoted fields stay LF.
for name in ("heldout_review_sheet.csv", "heldout_review_sheet_REVIEWED_by_Claude.csv"):
    rel = f"docs/remediation/heldout_review/{name}"
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    windows_bytes = b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
    check(f"{name}: portable hash identical for the Windows and macOS bytes",
          hashing.portable_sha256(windows_bytes, "text") == hashing.portable_sha256(read(rel), "text"))

# ----------------------------------------------------- Windows checkout simulation --
with tempfile.TemporaryDirectory() as tmp:
    changed = 0
    for _, rel, kind in asset_list(ROOT):
        target = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if kind == "text":
            data = to_crlf(read(rel))
            changed += data != read(rel)
            with open(target, "wb") as fh:
                fh.write(data)
        else:
            shutil.copyfile(os.path.join(ROOT, *rel.split("/")), target)
    check("simulated Windows checkout really has different bytes", changed >= 10)
    check("asset records identical for the CRLF (Windows) and LF (Unix) checkouts",
          asset_records(tmp) == asset_records(ROOT))

# ------------------------------------------- fixture manifest (built from the tree) --
with tempfile.TemporaryDirectory() as tmp:
    fixture_content = build_content(DATASET_VERSION)
    fixture_path = os.path.join(tmp, "frozen_manifest.json")
    with open(fixture_path, "w", encoding="utf-8") as fh:
        json.dump({"content_sha256": content_sha256(fixture_content), "content": fixture_content}, fh)
    fixture, problems = load_frozen_manifest(fixture_path)
    check("fixture manifest (written to a temp dir) loads and is self-consistent", fixture is not None and problems == [])
    problems, current = verify_frozen_manifest(fixture)
    check("fixture manifest reproduces from the working tree", problems == [])
    check("rebuilt content hash equals the fixture content_sha256 (deterministic rebuild)",
          content_sha256(current) == fixture["content_sha256"]
          and content_sha256(build_content(DATASET_VERSION)) == fixture["content_sha256"])
    edited = json.loads(json.dumps(fixture))
    edited["content"]["assets"][0]["portable_sha256"] = "0" * 64
    edited["content_sha256"] = content_sha256(edited["content"])
    problems, _ = verify_frozen_manifest(edited)
    check("a manifest recording a different asset hash does not reproduce",
          problems == [f"frozen asset changed: {fixture_content['assets'][0]['path']}"])

# ---------------------------------------------------------- committed manifest --
manifest, problems = load_frozen_manifest(MANIFEST_PATH)
check("committed frozen manifest loads and is self-consistent", manifest is not None and problems == [])
check("committed manifest uses the same format, hashing and asset groups as the builder",
      manifest["content"]["manifest_format"] == fixture_content["manifest_format"]
      and manifest["content"]["hashing"] == fixture_content["hashing"]
      and sorted({a["group"] for a in manifest["content"]["assets"]}) == sorted({a["group"] for a in fixture_content["assets"]}))
dataset = manifest["content"]["dataset"]
check("manifest: 160 cases, 47 dev / 113 held-out, valid",
      dataset["case_count"] == 160 and dataset["split_counts"] == {"dev": 47, "heldout": 113} and dataset["valid"])
check("manifest: held-out tier eligibility 113 / 106",
      dataset["tier_distribution"]["heldout"]["tier1_eligible"] == 113
      and dataset["tier_distribution"]["heldout"]["tier2_eligible"] == 106)
check("manifest: frozen thresholds 97/113 and 69/106",
      manifest["content"]["thresholds"]["heldout/tier1"]["min_correct"] == 97
      and manifest["content"]["thresholds"]["heldout/tier2"]["min_correct"] == 69)
check("manifest: 12 source PDFs, matching the dataset documents",
      manifest["content"]["source_pdfs_match_dataset_documents"]
      and sum(a["group"] == "source_pdf" for a in manifest["content"]["assets"]) == 12)
check("manifest: provenance is outside the hashed content", "provenance" not in manifest["content"])

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
