"""Render a progress report (Markdown) from a validation report. Counts come only from the file."""

import datetime


def _cell(value) -> str:
    return "—" if value in (None, "") else str(value)


def render_progress(report: dict, kind: str, workbook_sha256: str, manifest_sha: str) -> str:
    c = report["counts"]
    errors, incomplete = report["errors"], report["incomplete"]
    signoff = report["signoff_filled"]
    names = ", ".join(report["reviewer_names"]) or "—"
    lines = [
        f"# {'Held-out' if kind == 'heldout' else 'Development'} review: progress report",
        "",
        f"Generated {datetime.date.today().isoformat()} by `python -m eval.review.cli progress` "
        "(computed from the saved workbook; read-only).",
        "",
        "| Item | Value |", "|---|---|",
        f"| Workbook | `{report['workbook']}` |",
        f"| Workbook SHA-256 | `{workbook_sha256}` |",
        f"| Frozen manifest content_sha256 | `{manifest_sha}` |",
        f"| Status | **{report['status']}** |",
        f"| Reviewer name(s) entered in rows | {names} |",
        "| Reviewer identity confirmed by the project owner / independence | not recorded by this tool: see the sign-off |",
        "",
        "## Counts", "", "| Measure | Count |", "|---|---:|",
        f"| Total cases expected | {c['expected_cases']} |",
        f"| Reviewed (decision entered) | {c['reviewed']} |",
        f"| VALID | {c['VALID']} |",
        f"| NEEDS REVISION | {c['NEEDS REVISION']} |",
        f"| EXCLUDE | {c['EXCLUDE']} |",
        f"| Pending (no decision) | {c['pending']} |",
        "",
        "## Attention cases", "", "| Case | Decision | Rationale entered |", "|---|---|---|",
    ]
    lines += [f"| {a['case_id']} | {_cell(a['decision'])} | {'yes' if a['rationale_entered'] else 'no'} |"
              for a in report["attention"]] or ["| — | — | — |"]
    ledger = report["ledger"]
    lines += [
        "", "## Correction ledger", "",
        f"Entries {ledger['entries']}; historical check against a baseline: "
        f"{ledger.get('historical_check', 'not run (no baseline)')} "
        f"({ledger['historical_verified']} entries verified); proposed entries: {ledger['proposed']}.",
        "", "## Sign-off", "",
    ]
    lines += [f"- {label}: {'filled' if ok else '**blank**'}" for label, ok in signoff.items()] or ["- none found"]
    lines += ["", f"## Errors needing human resolution ({len(errors)})", ""]
    lines += [f"- {e}" for e in errors] or ["- none"]
    pending = [i for i in incomplete if i.endswith(": no decision")]
    other = [i for i in incomplete if not i.endswith(": no decision")]
    lines += ["", f"## Outstanding work ({len(incomplete)})", "",
              f"- cases without a decision: {len(pending)}"]
    lines += [f"- {i}" for i in other]
    lines += ["", "*This report counts what is in the workbook. It makes no review decision and does "
                  "not authorize any evaluation.*", ""]
    return "\n".join(lines)
