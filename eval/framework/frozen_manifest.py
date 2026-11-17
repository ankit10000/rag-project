"""Frozen Phase 3.5 evaluation manifest: build and verify (read-only; writes nothing).

The manifest has two parts:
  content     deterministic: identical on every platform for identical file
              content (portable hashes, dataset description, thresholds).
              ``content_sha256`` is the SHA-256 of its canonical JSON.
  provenance  informational and NOT reproducible: generation time, git HEAD,
              platform, Python version and the raw (un-normalized) file hashes.

Verification rebuilds ``content`` from the working tree and requires it to be
identical to the frozen one. It never repairs or rewrites anything.
Only eval/framework/cli.py writes a manifest, to a new file (mode "x").
"""

import datetime
import hashlib
import json
import os
import platform
import subprocess

from eval.framework import hashing
from eval.framework.integrity import ROOT, build_manifest

MANIFEST_FORMAT = "phase35-frozen-manifest/1"
SOURCE_PDF_DIR = "docs/remediation/heldout_review/source_pdfs"
REVIEW_DIR = "docs/remediation/heldout_review"

# (group, repository-relative path, kind). Source PDFs are added by listing SOURCE_PDF_DIR.
FROZEN_ASSETS = (
    ("dataset", "eval/phase35/data_A.py", "text"),
    ("dataset", "eval/phase35/data_B.py", "text"),
    ("dataset", "eval/phase35/data_C.py", "text"),
    ("dataset", "eval/phase35/data_D.py", "text"),
    ("validator", "eval/phase35/validate.py", "text"),
    ("scorer", "eval/phase35/run_eval.py", "text"),
    ("scorer", "eval/answer_scoring.py", "text"),
    ("thresholds", "docs/remediation/HELDOUT_THRESHOLD_FREEZE.md", "text"),
    ("dataset_corrections", "docs/remediation/HELDOUT_DATASET_CORRECTIONS.md", "text"),
    ("source_pages", f"{REVIEW_DIR}/source_pages.md", "text"),
    ("human_review", f"{REVIEW_DIR}/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx", "binary"),
    ("human_review", f"{REVIEW_DIR}/heldout_review_sheet.csv", "text"),
    ("human_review", f"{REVIEW_DIR}/heldout_review_sheet_REVIEWED_by_Claude.csv", "text"),
    ("human_review", f"{REVIEW_DIR}/README.md", "text"),
    ("human_review", f"{REVIEW_DIR}/REVIEW_SIGNOFF_REPORT.md", "text"),
)


def asset_list(root: str = ROOT) -> list:
    pdfs = sorted(n for n in os.listdir(os.path.join(root, SOURCE_PDF_DIR)) if n.lower().endswith(".pdf"))
    return list(FROZEN_ASSETS) + [("source_pdf", f"{SOURCE_PDF_DIR}/{n}", "binary") for n in pdfs]


def _read(root: str, rel_path: str) -> bytes:
    with open(os.path.join(root, *rel_path.split("/")), "rb") as fh:
        return fh.read()


def asset_records(root: str = ROOT) -> list:
    """Portable hash and git blob id of every frozen asset (deterministic)."""
    records = []
    for group, rel_path, kind in asset_list(root):
        data = _read(root, rel_path)
        records.append({
            "group": group, "path": rel_path, "kind": kind,
            "portable_sha256": hashing.portable_sha256(data, kind),
            "git_blob_sha1": hashing.git_blob_sha1(data, kind),
        })
    return records


def _thresholds() -> dict:
    from eval.framework.safety import FROZEN_THRESHOLDS
    return {f"{split}/tier{tier}": dict(spec) for (split, tier), spec in sorted(FROZEN_THRESHOLDS.items())}


def build_content(dataset_version: str) -> dict:
    dataset = build_manifest(dataset_version)
    assets = asset_records()
    pdf_names = sorted(r["path"].rsplit("/", 1)[1] for r in assets if r["group"] == "source_pdf")
    return {
        "manifest_format": MANIFEST_FORMAT,
        "hashing": {
            "algorithm": hashing.HASH_ALGORITHM,
            "text_normalization": hashing.TEXT_NORMALIZATION,
            "binary_normalization": hashing.BINARY_NORMALIZATION,
            "git_blob_sha1": "sha1 of b'blob <len>\\0' + normalized content",
        },
        "dataset": dataset,
        "thresholds": _thresholds(),
        "source_pdfs_match_dataset_documents": pdf_names == sorted(dataset_documents()),
        "assets": assets,
    }


def dataset_documents() -> list:
    from eval.framework.integrity import load_dataset
    docs, _ = load_dataset()
    return list(docs)


def content_sha256(content: dict) -> str:
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git_head() -> str | None:
    try:
        out = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        return f"unavailable: {error.__class__.__name__}"
    return out.stdout.strip() if out.returncode == 0 else "unavailable"


def build_frozen_manifest(dataset_version: str) -> dict:
    content = build_content(dataset_version)
    raw = {r["path"]: hashing.raw_sha256(_read(ROOT, r["path"])) for r in content["assets"]}
    return {
        "content_sha256": content_sha256(content),
        "content": content,
        "provenance": {
            "note": "informational only; not part of content_sha256 and not expected to reproduce",
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "git_head": _git_head(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "raw_sha256": raw,
        },
    }


def load_frozen_manifest(path: str) -> tuple:
    """Return (manifest, problems). Fails closed on anything missing or malformed."""
    if not path or not os.path.isfile(path):
        return None, [f"frozen manifest not found: {path}"]
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [f"frozen manifest is unreadable or not JSON: {error.__class__.__name__}"]
    content = manifest.get("content") if isinstance(manifest, dict) else None
    if not isinstance(content, dict) or not isinstance(content.get("dataset"), dict):
        return None, ["frozen manifest is malformed (missing content/dataset)"]
    if content.get("manifest_format") != MANIFEST_FORMAT:
        return None, [f"frozen manifest format is not {MANIFEST_FORMAT!r}"]
    if manifest.get("content_sha256") != content_sha256(content):
        return None, ["frozen manifest content_sha256 does not match its content (edited or corrupted)"]
    return manifest, []


def verify_frozen_manifest(manifest: dict) -> tuple:
    """Rebuild the content from the working tree. Return (problems, rebuilt_content)."""
    frozen = manifest["content"]
    current = build_content(frozen["dataset"].get("dataset_version", ""))
    problems = []
    frozen_assets = {a["path"]: a for a in frozen.get("assets", [])}
    current_assets = {a["path"]: a for a in current["assets"]}
    for path in sorted(set(frozen_assets) | set(current_assets)):
        if path not in current_assets:
            problems.append(f"frozen asset missing from the working tree: {path}")
        elif path not in frozen_assets:
            problems.append(f"asset not in the frozen manifest: {path}")
        elif frozen_assets[path] != current_assets[path]:
            problems.append(f"frozen asset changed: {path}")
    for key in ("manifest_format", "hashing", "dataset", "thresholds", "source_pdfs_match_dataset_documents"):
        if frozen.get(key) != current.get(key):
            problems.append(f"frozen manifest section differs from the working tree: {key}")
    if not current["dataset"].get("valid"):
        problems.append("current dataset is not valid")
    return problems, current
