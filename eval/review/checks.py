"""Validate a review workbook and count progress (read-only; decides nothing).

``validate_book`` returns a report with:
  counts      decisions / pending / missing fields, computed from the file
  errors      integrity problems needing human resolution (wrong ids, edited
              case definitions, bad ledger references, invalid decision values)
  incomplete  review work not finished yet (pending rows, missing rationale,
              name, date, sign-off fields, missing ledger proposals)
  status      NOT_STARTED | IN_PROGRESS | NEEDS_RESOLUTION | COMPLETE
"""

import datetime
import json
import re
from collections import Counter

from eval.review.workbook import DECISIONS, LEDGER_COLUMNS, REQUIRED_CASE_COLUMNS, blank

PROPOSED_PREFIX = "PROPOSED (not applied):"
FLAG_FIELDS = ("expect_abstain", "expect_partial", "expect_conflict")


def _flag(value) -> bool | None:
    text = str(value).strip().upper() if value is not None else ""
    return {"TRUE": True, "FALSE": False}.get(text)


def _json(value):
    try:
        return json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return "<invalid JSON>"


def definition_drift(row: dict, case: dict) -> list:
    """Fields where the workbook row differs from the dataset definition."""
    sources = _json(row.get("expected_sources_json"))
    expected = {
        "data_file": (row.get("data_file"), f"{case['_module']}.py"),
        "category": (row.get("category"), case["category"]),
        "tier": (row.get("tier"), case["tier"]),
        "question": (row.get("question"), case["question"]),
        "history_json": (_json(row.get("history_json") or "[]"), case["history"]),
        "expected_facts_json": (_json(row.get("expected_facts_json")), case["gold_facts"]),
        "forbidden_strings_json": (_json(row.get("forbidden_strings_json")), case["forbidden"]),
        "expected_sources_json": (sources, [{"document": s["document"], "page": s["page"], "span": s["span"]}
                                            for s in case["gold_sources"]]),
    }
    drift = [name for name, (got, want) in expected.items() if got != want]
    drift += [f for f in FLAG_FIELDS if _flag(row.get(f)) != case[f]]
    return drift


def valid_date(value) -> bool:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return True
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return False
    try:
        datetime.date.fromisoformat(value.strip())
        return True
    except ValueError:
        return False


def _structure_errors(book) -> list:
    errors = [f"missing sheet: {name}" for name in book.missing_sheets]
    if book.case_sheet:
        errors += [f"missing case column: {c}" for c in REQUIRED_CASE_COLUMNS if c not in book.columns]
        if book.ledger_columns and tuple(book.ledger_columns[:len(LEDGER_COLUMNS)]) != LEDGER_COLUMNS:
            errors.append("correction ledger columns differ from the expected layout")
        dv = book.decision_validation
        rows = [c["_row"] for c in book.cases]
        if dv is None or tuple(dv[1]) != DECISIONS:
            errors.append(f"decision dropdown missing or not {DECISIONS}")
        elif rows and not _covers(dv[0], min(rows), max(rows)):
            errors.append(f"decision dropdown {dv[0]} does not cover case rows {min(rows)}-{max(rows)}")
    return errors


def _covers(sqref: str, first: int, last: int) -> bool:
    for part in sqref.split():
        nums = [int(n) for n in re.findall(r"\d+", part)]
        if len(nums) == 2 and nums[0] <= first and nums[1] >= last:
            return True
    return False


def _id_errors(book, expected_ids, cases_by_id, split_of) -> list:
    ids = [c.get("case_id") for c in book.cases]
    errors = [f"duplicate case row: {i} (x{n})" for i, n in Counter(ids).items() if n > 1]
    errors += [f"case missing from workbook: {i}" for i in sorted(set(expected_ids) - set(ids))]
    errors += [f"unexpected case in workbook: {i}" for i in sorted(set(ids) - set(expected_ids), key=str)]
    for row in book.cases:
        cid = row.get("case_id")
        if cid in cases_by_id:
            if row.get("split") != split_of(cid):
                errors.append(f"{cid}: split column {row.get('split')!r} != split rule {split_of(cid)!r}")
            drift = definition_drift(row, cases_by_id[cid])
            if drift:
                errors.append(f"{cid}: case definition differs from the dataset: {drift}")
    return errors


def _row_findings(book) -> tuple:
    errors, incomplete = [], []
    for row in book.cases:
        cid, decision = row.get("case_id"), row.get("reviewer_decision")
        decision = decision.strip() if isinstance(decision, str) else decision
        name, date, rationale = row.get("reviewer_name"), row.get("review_date"), row.get("reviewer_rationale")
        if blank(decision):
            incomplete.append(f"{cid}: no decision")
            if not blank(name) or not blank(date):
                incomplete.append(f"{cid}: reviewer name/date entered without a decision")
            continue
        if decision not in DECISIONS:
            errors.append(f"{cid}: invalid decision {decision!r}")
        if decision in ("NEEDS REVISION", "EXCLUDE") and blank(rationale):
            incomplete.append(f"{cid}: {decision} without a rationale")
        if blank(name):
            incomplete.append(f"{cid}: reviewer name missing")
        if blank(date):
            incomplete.append(f"{cid}: review date missing")
        elif not valid_date(date):
            incomplete.append(f"{cid}: review date not YYYY-MM-DD: {date!r}")
        if not blank(row.get("reviewer_attention")) and blank(rationale):
            incomplete.append(f"{cid}: attention flag not addressed in a rationale")
    return errors, incomplete


def _decision_of(book) -> dict:
    return {c.get("case_id"): (c.get("reviewer_decision") or "").strip() if isinstance(c.get("reviewer_decision"), str)
            else c.get("reviewer_decision") for c in book.cases}


def _ledger_findings(book, cases_by_id, split_of, baseline) -> tuple:
    errors, incomplete = [], []
    entries = [{k: v for k, v in e.items() if k != "_row"} for e in book.ledger]
    if [str(e.get("change_no")).strip() for e in entries] != [str(i) for i in range(1, len(entries) + 1)]:
        errors.append("ledger change_no is not the sequence 1..N")
    history, history_check = 0, "not run (no baseline)"
    if baseline is not None:
        base = [{k: v for k, v in e.items() if k != "_row"} for e in baseline.ledger]
        history, history_check = len(base), "passed"
        if entries[:history] != base:
            errors.append(f"historical ledger entries 1-{history} were changed")
            history_check = "FAILED"
    decisions, in_book = _decision_of(book), {c.get("case_id") for c in book.cases}
    proposed_ids, unverified = set(), []
    for n, e in enumerate(entries, 1):
        cid, text = e.get("case_id"), str(e.get("source_or_rationale") or "")
        if cid not in cases_by_id:
            errors.append(f"ledger #{n}: unknown case id {cid!r}")
            continue
        if e.get("split") != split_of(cid):
            errors.append(f"ledger #{n}: split {e.get('split')!r} != split rule for {cid}")
        if n <= history:
            continue
        if not text.startswith(PROPOSED_PREFIX):
            if baseline is not None:
                errors.append(f"ledger #{n} ({cid}): new entry not marked {PROPOSED_PREFIX!r}")
            else:
                unverified.append(n)
            continue
        proposed_ids.add(cid)
        if cid not in in_book:
            errors.append(f"ledger #{n}: proposed correction for {cid}, which is not in this workbook")
        elif decisions.get(cid) not in ("NEEDS REVISION", "EXCLUDE"):
            errors.append(f"ledger #{n}: proposed correction for {cid} without a NEEDS REVISION/EXCLUDE decision")
    if unverified:
        # Without a baseline an unmarked entry may be history or an unmarked new correction; it cannot
        # be told apart, so the review cannot be COMPLETE until a baseline verifies it (--baseline-git).
        incomplete.append(f"ledger entries {unverified} are not marked {PROPOSED_PREFIX!r} and were not "
                          "verified as historical: no baseline given (use --baseline-git)")
    for cid, decision in decisions.items():
        if decision in ("NEEDS REVISION", "EXCLUDE") and cid not in proposed_ids:
            incomplete.append(f"{cid}: {decision} without a PROPOSED ledger entry")
    verified = history if history_check == "passed" else 0
    return errors, incomplete, {"entries": len(entries), "historical_verified": verified,
                                "historical_check": history_check,
                                "proposed": sum(1 for e in entries[history:]
                                                if str(e.get("source_or_rationale") or "").startswith(PROPOSED_PREFIX))}


def _counts(book, expected_ids) -> dict:
    decisions = Counter(_decision_of(book).values())
    reviewed = sum(n for d, n in decisions.items() if not blank(d))
    return {
        "expected_cases": len(expected_ids), "rows": len(book.cases), "reviewed": reviewed,
        **{d: decisions.get(d, 0) for d in DECISIONS},
        "pending": sum(n for d, n in decisions.items() if blank(d)),
    }


def validate_book(book, expected_ids, cases_by_id, split_of, baseline=None) -> dict:
    errors = _structure_errors(book) + _id_errors(book, expected_ids, cases_by_id, split_of)
    row_errors, incomplete = _row_findings(book)
    ledger_errors, ledger_incomplete, ledger = _ledger_findings(book, cases_by_id, split_of, baseline)
    errors += row_errors + ledger_errors
    incomplete += ledger_incomplete
    signoff = {label: not blank(value) for label, value in book.signoff.items()}
    if not signoff:
        incomplete.append("no sign-off fields found")
    incomplete += [f"sign-off field blank: {label}" for label, ok in signoff.items() if not ok]
    counts = _counts(book, expected_ids)
    if errors:
        status = "NEEDS_RESOLUTION"
    elif counts["reviewed"] == 0:
        status = "NOT_STARTED"
    else:
        status = "COMPLETE" if not incomplete and counts["reviewed"] == counts["expected_cases"] else "IN_PROGRESS"
    attention = [{"case_id": c.get("case_id"), "decision": c.get("reviewer_decision"),
                  "rationale_entered": not blank(c.get("reviewer_rationale"))}
                 for c in book.cases if not blank(c.get("reviewer_attention"))]
    names = sorted({str(c.get("reviewer_name")).strip() for c in book.cases if not blank(c.get("reviewer_name"))})
    return {"workbook": book.path, "case_sheet": book.case_sheet, "status": status, "counts": counts,
            "reviewer_names": names, "attention": attention, "ledger": ledger, "signoff_filled": signoff,
            "errors": errors, "incomplete": incomplete}
