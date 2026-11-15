"""Standardized evaluation report (pure: builds a dict and Markdown text).

Writing a report to disk is done only by cli.py, which refuses to overwrite.
Every report carries an explicit evidence class so developer-authored cases are
never presented as independent validation and AI-assisted review is never
presented as human review.
"""

import datetime

from eval.framework import FRAMEWORK_VERSION

EVIDENCE_CLASSES = {
    "AUTOMATED_DEVELOPER_CASES": "Automated scoring of developer/author-written cases (not independent validation).",
    "AI_ASSISTED_REVIEWED": "Cases reviewed with AI assistance (NOT human review, NOT independent).",
    "HUMAN_REVIEWED": "Cases reviewed by a named human reviewer.",
    "INDEPENDENT_VALIDATION": "Human-reviewed, frozen held-out cases run once with frozen thresholds.",
}

HUMAN_REVIEW_STATUSES = ("NOT_REVIEWED", "AI_ASSISTED_ONLY", "HUMAN_REVIEW_PENDING", "HUMAN_REVIEWED")


def build_report(*, evidence_class, human_review_status, manifest, run_info, answer=None, retrieval=None,
                 memory=None, attribution=None, regression=None, thresholds=None, limitations=None):
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError(f"evidence_class must be one of {sorted(EVIDENCE_CLASSES)}")
    if human_review_status not in HUMAN_REVIEW_STATUSES:
        raise ValueError(f"human_review_status must be one of {HUMAN_REVIEW_STATUSES}")
    if evidence_class in ("HUMAN_REVIEWED", "INDEPENDENT_VALIDATION") and human_review_status != "HUMAN_REVIEWED":
        raise ValueError("a human-reviewed evidence class requires human_review_status=HUMAN_REVIEWED")

    return {
        "evaluator_version": FRAMEWORK_VERSION,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "evidence_class": evidence_class,
        "evidence_class_meaning": EVIDENCE_CLASSES[evidence_class],
        "human_review_status": human_review_status,
        "dataset": {k: manifest.get(k) for k in ("dataset_version", "dataset_sha256", "split_sha256", "case_count",
                                                 "split_counts", "tier_distribution", "file_sha256")} if manifest else None,
        "run": run_info or {},
        "metrics": {"answer": answer, "retrieval": retrieval, "memory": memory},
        "thresholds": thresholds,
        "attribution": attribution.as_dict() if hasattr(attribution, "as_dict") else attribution,
        "regression": regression,
        "limitations": list(limitations or []),
    }


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return "—" if v is None else str(v)


def render_markdown(report: dict) -> str:
    lines = [f"# Evaluation report ({report['evaluator_version']})", "",
             f"- Evidence class: **{report['evidence_class']}** — {report['evidence_class_meaning']}",
             f"- Human review status: **{report['human_review_status']}**",
             f"- Generated: {report['generated_at']}", ""]
    ds = report.get("dataset") or {}
    if ds:
        lines += ["## Dataset", f"- Version: {_fmt(ds.get('dataset_version'))}",
                  f"- Dataset SHA-256: `{ds.get('dataset_sha256')}`", f"- Split SHA-256: `{ds.get('split_sha256')}`",
                  f"- Cases: {ds.get('case_count')} (split {ds.get('split_counts')})", ""]
    run = report.get("run") or {}
    lines += ["## Execution"] + [f"- {k}: {_fmt(v)}" for k, v in sorted(run.items())] + [""]
    ans = (report.get("metrics") or {}).get("answer")
    if ans:
        o = ans["overall"]
        lines += ["## Answer metrics", "| metric | value | n |", "|---|---|---|",
                  f"| correct | {o['correct']}/{o['cases']} | {o['cases']} |"]
        for key in ("correctness", "completeness", "citation_correctness", "citation_completeness",
                    "unsupported_claims", "abstention_correctness", "conflict_handling", "injection_resistance"):
            item = o[key]
            lines.append(f"| {key} | {_fmt(item.get('rate', item.get('mean')))} | {item['n']} |")
        lines += ["", "Unavailable: " + "; ".join(f"{k} ({v})" for k, v in ans["unavailable_metrics"].items()), ""]
    if report.get("thresholds"):
        lines += ["## Frozen thresholds"] + [f"- {t}" for t in report["thresholds"]] + [""]
    reg = report.get("regression")
    if reg:
        lines += ["## Regression vs baseline", f"- Baseline correct: {reg['baseline_correct']}, current correct: {reg['current_correct']}",
                  f"- Counts: {reg['counts']}", f"- Regressions: {reg['regressions'] or 'none'}",
                  f"- Improvements: {reg['improvements'] or 'none'}",
                  f"- Unchanged failures: {reg['unchanged_failures'] or 'none'}", ""]
    att = report.get("attribution")
    if att:
        lines += ["## Provider / usage"] + [f"- {k}: {_fmt(v)}" for k, v in att.items()] + [""]
    lines += ["## Limitations"] + [f"- {x}" for x in report.get("limitations") or ["none recorded"]]
    return "\n".join(lines) + "\n"
