"""Prepare public, revision-pinned HF/OCR assets outside application images.

Default: copy existing local cache only. --download explicitly fetches public model
artifacts, never project PDFs, provider keys or evaluation data. Runtime is offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

MODELS = {
    "sentence-transformers/all-MiniLM-L6-v2": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "cross-encoder/ms-marco-MiniLM-L-6-v2": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
}
OCR_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
OCR_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def verify_assets(root: Path, *, full: bool = False) -> dict:
    manifest = json.loads((root / "assets-manifest.json").read_text())
    if manifest.get("models") != MODELS or manifest.get("ocr_sha256") != OCR_SHA256:
        raise ValueError("asset identity differs from the tested deployment pins")
    if digest(root / "tessdata/eng.traineddata") != OCR_SHA256:
        raise ValueError("OCR asset hash mismatch")
    if not manifest.get("files"):
        raise ValueError("model manifest is empty")
    for name, expected in manifest["files"].items():
        file = root / name
        if not file.resolve().is_relative_to(root.resolve()) or not file.is_file():
            raise ValueError("model artifact unavailable")
        if file.stat().st_size != expected["bytes"] or (full and digest(file) != expected["sha256"]):
            raise ValueError("model artifact changed")
    return {"status": "PASS", "files": len(manifest["files"]),
            "bytes": sum(item["bytes"] for item in manifest["files"].values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-hf-home", type=Path, default=Path.home() / ".cache/huggingface")
    parser.add_argument("--source-tessdata", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = args.destination.resolve()
    if args.verify:
        print(json.dumps(verify_assets(root, full=True)))
        return
    if root.exists() and any(root.iterdir()):
        raise ValueError("destination must be empty; verified assets are never overwritten")
    root.mkdir(parents=True, exist_ok=True)
    for model, revision in MODELS.items():
        key = "models--" + model.replace("/", "--")
        source = args.source_hf_home / "hub" / key / "snapshots" / revision
        if args.download:
            from huggingface_hub import snapshot_download
            source = Path(snapshot_download(model, revision=revision,
                                           ignore_patterns=["onnx/*", "openvino/*", "*.bin", "*.h5", "*.ot"]))
        if not source.is_dir():
            raise ValueError("pinned model cache unavailable; prepare explicitly before deployment")
        target = root / "huggingface/hub" / key
        shutil.copytree(source, target / "snapshots" / revision, symlinks=False)
        (target / "refs").mkdir()
        (target / "refs/main").write_text(revision)
    ocr = root / "tessdata/eng.traineddata"
    ocr.parent.mkdir()
    if args.source_tessdata:
        shutil.copyfile(args.source_tessdata / "eng.traineddata", ocr)
    elif args.download:
        with urllib.request.urlopen(OCR_URL, timeout=30) as response, ocr.open("xb") as output:
            output.write(response.read(8 * 1024 * 1024 + 1))
    else:
        raise ValueError("pinned tessdata source required for offline preparation")
    if digest(ocr) != OCR_SHA256:
        raise ValueError("OCR checksum mismatch")
    files = {str(file.relative_to(root)): {"sha256": digest(file), "bytes": file.stat().st_size}
             for file in sorted(root.rglob("*")) if file.is_file()}
    manifest = {"models": MODELS, "ocr_sha256": OCR_SHA256, "files": files}
    (root / "assets-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(verify_assets(root, full=True)))


if __name__ == "__main__":
    main()
