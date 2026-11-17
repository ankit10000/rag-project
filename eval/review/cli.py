"""Review tooling commands. Read-only, except build-dev-review and --output/--json,
which only create NEW files (never overwrite). No command edits a workbook.

    python -m eval.review.cli validate      --kind heldout|dev [--workbook X] [--baseline-git REV] [--json OUT] [--all]
    python -m eval.review.cli progress      --kind heldout|dev [--workbook X] [--baseline-git REV] [--output OUT.md]
    python -m eval.review.cli locate        --kind heldout|dev [--workbook X] --case CASE_ID
    python -m eval.review.cli check-sources --kind heldout|dev [--workbook X]
    python -m eval.review.cli build-dev-review [--output docs/remediation/dev_review/dev_review_sheet.xlsx]
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

from eval.framework.integrity import ROOT

WORKBOOKS = {
    "heldout": "docs/remediation/heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx",
    "dev": "docs/remediation/dev_review/dev_review_sheet.xlsx",
}
MANIFEST = os.path.join(ROOT, "eval", "phase35", "frozen_manifest.json")
DATASET_VERSION = "phase35-corrected-2026-11-12"


def _dataset():
    from eval.framework.integrity import load_dataset, split_of
    docs, cases = load_dataset()
    return docs, {c["id"]: c for c in cases}, split_of


def _expected_ids(kind, cases_by_id, split_of):
    if kind == "dev":
        from eval.review.dev_artifact import DEV_REVIEW_CASES
        return [cid for cid, _ in DEV_REVIEW_CASES]
    return [cid for cid in cases_by_id if split_of(cid) == "heldout"]


def _path(args):
    return os.path.join(ROOT, args.workbook or WORKBOOKS[args.kind])


def _sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _manifest_sha():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)["content_sha256"]


def _baseline(args, tmp):
    """Workbook as committed at --baseline-git REV (read via `git show`; nothing is checked out)."""
    if not args.baseline_git:
        return None
    from eval.review.workbook import read_workbook
    rel = os.path.relpath(_path(args), ROOT).replace(os.sep, "/")
    blob = subprocess.run(["git", "-C", ROOT, "show", f"{args.baseline_git}:{rel}"], capture_output=True, timeout=30)
    if blob.returncode != 0:
        raise SystemExit(f"cannot read {rel} at {args.baseline_git}: {blob.stderr.decode(errors='replace').strip()}")
    target = os.path.join(tmp, "baseline.xlsx")
    with open(target, "wb") as fh:
        fh.write(blob.stdout)
    return read_workbook(target)


def _report(args):
    from eval.review.checks import validate_book
    from eval.review.workbook import read_workbook
    _, cases_by_id, split_of = _dataset()
    path = _path(args)
    with tempfile.TemporaryDirectory() as tmp:
        baseline = _baseline(args, tmp)
        book = read_workbook(path)
        report = validate_book(book, _expected_ids(args.kind, cases_by_id, split_of), cases_by_id, split_of, baseline)
    report["workbook"] = os.path.relpath(path, ROOT)
    return report, path


def _write_new(path, text):
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)


def cmd_validate(args):
    report, _ = _report(args)
    limit = None if args.all else 20
    print(f"status: {report['status']}")
    print("counts:", json.dumps(report["counts"]))
    print(f"errors ({len(report['errors'])}):")
    for line in report["errors"][:limit]:
        print("  -", line)
    print(f"incomplete ({len(report['incomplete'])}):")
    for line in report["incomplete"][:limit]:
        print("  -", line)
    if limit and len(report["incomplete"]) > limit:
        print(f"  ... {len(report['incomplete']) - limit} more (use --all)")
    if args.json:
        _write_new(args.json, json.dumps(report, indent=1, default=str))
    return 1 if report["errors"] else 0


def cmd_progress(args):
    from eval.review.progress import render_progress
    report, path = _report(args)
    text = render_progress(report, args.kind, _sha256(path), _manifest_sha())
    if args.output:
        _write_new(args.output, text)
        print(f"progress report written: {args.output}")
    else:
        print(text)
    return 0


def _index():
    from eval.review.sources import SourceIndex
    docs, _, _ = _dataset()
    return SourceIndex(docs)


def cmd_locate(args):
    from eval.review.sources import DISCLAIMER, case_sources
    from eval.review.workbook import read_workbook
    rows = [r for r in read_workbook(_path(args)).cases if r.get("case_id") == args.case]
    if not rows:
        print(f"case {args.case} is not in {_path(args)}")
        return 1
    index = _index()
    for n, (document, page, span) in enumerate(case_sources(rows[0]), 1):
        r = index.locate(document, page, span)
        print(f"source {n}: {document} page {page}")
        print(f"  PDF: {r['pdf_path']} (found: {r['pdf_found']}, pages: {r['pdf_page_count']}, page valid: {r['page_valid']})")
        print(f"  source_pages.md line: {r['source_pages_md_line']}")
        print(f"  span text on PDF page: {r['span_on_pdf_page']}; on dataset page: {r['span_on_dataset_page']}")
        print(f"  same text also on: {r['span_also_on'] or 'no other page'}")
        print(f"  lookup problem: {r['problem'] or 'none'}")
    print(DISCLAIMER)
    return 0


def cmd_check_sources(args):
    from eval.review.sources import check_book_sources
    from eval.review.workbook import read_workbook
    result = check_book_sources(read_workbook(_path(args)), _index())
    print(f"references: {result['references']}; lookup problems: {len(result['problems'])}")
    for p in result["problems"]:
        print(f"  - {p['case_id']}: {p['document']} p.{p['page']}: {p['problem']}")
    print(result["note"])
    return 1 if result["problems"] else 0


def cmd_build_dev_review(args):
    from eval.framework.frozen_manifest import load_frozen_manifest
    from eval.review.dev_artifact import DEV_REVIEW_CASES, build_dev_review
    manifest, problems = load_frozen_manifest(MANIFEST)
    if problems:
        raise SystemExit(f"frozen manifest problem: {problems}")
    _, cases_by_id, split_of = _dataset()
    wrong = [cid for cid, _ in DEV_REVIEW_CASES if cid in cases_by_id and split_of(cid) != "dev"]
    if wrong:
        raise SystemExit(f"not development cases: {wrong}")
    try:
        ids = build_dev_review(args.output, cases_by_id, DATASET_VERSION, manifest["content_sha256"],
                               manifest["content"]["dataset"]["file_sha256"])
    except FileExistsError as error:
        print(f"REFUSED: {error} (an existing review workbook is never replaced)", file=sys.stderr)
        return 1
    print(f"development review workbook written: {args.output} ({len(ids)} cases: {', '.join(ids)})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, func in (("validate", cmd_validate), ("progress", cmd_progress), ("locate", cmd_locate),
                       ("check-sources", cmd_check_sources)):
        s = sub.add_parser(name)
        s.add_argument("--kind", choices=sorted(WORKBOOKS), required=True)
        s.add_argument("--workbook", help="override the default workbook path")
        s.set_defaults(func=func)
        if name in ("validate", "progress"):
            s.add_argument("--baseline-git", help="git revision holding the pre-review workbook (e.g. HEAD)")
        if name == "validate":
            s.add_argument("--json")
            s.add_argument("--all", action="store_true")
        if name == "progress":
            s.add_argument("--output")
        if name == "locate":
            s.add_argument("--case", required=True)
    b = sub.add_parser("build-dev-review")
    b.add_argument("--output", default=os.path.join(ROOT, WORKBOOKS["dev"]))
    b.set_defaults(func=cmd_build_dev_review)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
