"""File-based evaluation framework commands (no model calls, no evaluation runs).

    python -m eval.framework.cli manifest --dataset-version <v> --output <manifest.json>
    python -m eval.framework.cli frozen-manifest --dataset-version <v> --output <frozen_manifest.json>
    python -m eval.framework.cli verify-frozen-manifest --manifest <frozen_manifest.json>
    python -m eval.framework.cli compare  --baseline <a.jsonl> --current <b.jsonl> --output <cmp.json>
    python -m eval.framework.cli report   --results <rows.jsonl> --split dev|heldout --tier 1|2
                                          --evidence-class <CLASS> --human-review-status <STATUS>
                                          --manifest <manifest.json> --output <report.md>
                                          [--baseline <rows.jsonl>] [--log <run_log.txt>]
                                          [--provider <name>] [--models m1,m2]

Rules: every input/output path is explicit; outputs are created with mode "x"
(an existing file is never overwritten); no command runs the RAG pipeline, a
provider, a database query or eval/phase35/run_eval.py. There is deliberately
NO "run" command: executing an evaluation needs a separate, explicitly
authorized step that must pass eval.framework.safety.check_run_request().
"""

import argparse
import json
import sys


def _read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_new(path, text):
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(text)


def cmd_manifest(args):
    from eval.framework.integrity import build_manifest
    manifest = build_manifest(args.dataset_version)
    _write_new(args.output, json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"manifest written: {args.output} (valid={manifest['valid']}, errors={len(manifest['errors'])})")
    return 0 if manifest["valid"] else 1


def cmd_frozen_manifest(args):
    from eval.framework.frozen_manifest import build_frozen_manifest
    manifest = build_frozen_manifest(args.dataset_version)
    _write_new(args.output, json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    valid = manifest["content"]["dataset"]["valid"]
    print(f"frozen manifest written: {args.output} content_sha256={manifest['content_sha256']} valid={valid}")
    return 0 if valid else 1


def cmd_verify_frozen_manifest(args):
    from eval.framework.frozen_manifest import load_frozen_manifest, verify_frozen_manifest
    manifest, problems = load_frozen_manifest(args.manifest)
    if not problems:
        problems, _ = verify_frozen_manifest(manifest)
    for problem in problems:
        print(f"MISMATCH: {problem}")
    print("frozen manifest REPRODUCED" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def cmd_compare(args):
    from eval.framework.regression import compare
    result = compare(_read_jsonl(args.baseline), _read_jsonl(args.current),
                     metric_keys=("fact_recall", "citation_correctness", "citation_completeness",
                                  "retrieval_page_recall"))
    _write_new(args.output, json.dumps(result, indent=1, ensure_ascii=False))
    print(f"comparison written: {args.output} counts={result['counts']}")
    return 0


def cmd_report(args):
    from eval.framework import answer_metrics, providers, regression, reporting, retrieval_metrics, safety
    from eval.framework.integrity import load_dataset

    _, cases = load_dataset()
    cases_by_id = {c["id"]: c for c in cases}
    rows = _read_jsonl(args.results)
    manifest = json.load(open(args.manifest, encoding="utf-8"))

    answer = answer_metrics.aggregate(rows, cases_by_id)
    retrieval = None
    if args.tier == 2:
        per_case = [retrieval_metrics.tier2_row_metrics(r, cases_by_id.get(r["id"], {})) for r in rows]
        retrieval = retrieval_metrics.aggregate(per_case, group_key="category")
    log_text = open(args.log, encoding="utf-8").read() if args.log else None
    attribution = providers.summarize_rows(rows, provider=args.provider or providers.UNAVAILABLE,
                                           configured_models=(args.models or "").split(",") if args.models else [],
                                           log_text=log_text)
    reg = regression.compare(_read_jsonl(args.baseline), rows) if args.baseline else None
    threshold = safety.threshold_result(args.split, args.tier, answer["overall"]["correct"], len(rows))

    report = reporting.build_report(
        evidence_class=args.evidence_class, human_review_status=args.human_review_status, manifest=manifest,
        run_info={"split": args.split, "tier": args.tier, "results_file": args.results, "rows": len(rows)},
        answer=answer, retrieval=retrieval, attribution=attribution, regression=reg,
        thresholds=[threshold], limitations=args.limitation or [])
    _write_new(args.output, reporting.render_markdown(report))
    _write_new(args.output + ".json", json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(f"report written: {args.output} (+ .json)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("manifest")
    m.add_argument("--dataset-version", required=True)
    m.add_argument("--output", required=True)
    m.set_defaults(func=cmd_manifest)

    f = sub.add_parser("frozen-manifest")
    f.add_argument("--dataset-version", required=True)
    f.add_argument("--output", required=True)
    f.set_defaults(func=cmd_frozen_manifest)

    v = sub.add_parser("verify-frozen-manifest")
    v.add_argument("--manifest", required=True)
    v.set_defaults(func=cmd_verify_frozen_manifest)

    c = sub.add_parser("compare")
    c.add_argument("--baseline", required=True)
    c.add_argument("--current", required=True)
    c.add_argument("--output", required=True)
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser("report")
    r.add_argument("--results", required=True)
    r.add_argument("--split", required=True, choices=("dev", "heldout"))
    r.add_argument("--tier", required=True, type=int, choices=(1, 2))
    r.add_argument("--evidence-class", required=True)
    r.add_argument("--human-review-status", required=True)
    r.add_argument("--manifest", required=True)
    r.add_argument("--output", required=True)
    r.add_argument("--baseline")
    r.add_argument("--log")
    r.add_argument("--provider")
    r.add_argument("--models")
    r.add_argument("--limitation", action="append")
    r.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
