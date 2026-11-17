"""Stage 9 Phase B: review workbook tooling (unit; temp fixtures; no DB, no LLM, no evaluation).

Fixtures are temporary workbooks/PDFs built from a FAKE three-case dataset. The
real held-out and development workbooks are only read, and their hashes are
checked to be unchanged.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import datetime
import hashlib
import io
import os
import sys
import tempfile

import pymupdf
from openpyxl import Workbook

from eval.framework.integrity import ROOT, load_dataset, split_of
from eval.review import cli
from eval.review.checks import PROPOSED_PREFIX, validate_book
from eval.review.dev_artifact import DEV_REVIEW_CASES, DEV_SHEET, HEADERS, build_dev_review, case_row
from eval.review.progress import render_progress
from eval.review.sources import SourceIndex, check_book_sources
from eval.review.workbook import LEDGER_COLUMNS, LEDGER_SHEET, README_SHEET, column_key, read_workbook

FAILURES = []
KEYS = [column_key(h) for h in HEADERS]
SIGNOFF = ["Sign-off - reviewer name", "Sign-off - reviewer independence confirmation",
           "Sign-off - date completed"]
DOCS = {"Alpha.pdf": ["Alpha page one. The fee is USD 40.", "Alpha page two. Opening hours 9 to 5."],
        "Beta.pdf": ["Beta page one. The fee is USD 40.", "Beta page two. Closed on Sundays."]}


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def sha256_of(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def fake_case(cid, doc, page, span, **extra):
    case = {"id": cid, "_module": "data_X", "category": "direct_factual", "tier": "both",
            "question": f"SECRET-QUESTION-{cid}", "history": [], "gold_facts": [["USD 40"]], "forbidden": [],
            "gold_sources": [{"document": doc, "page": page, "span": span}], "expect_abstain": False,
            "expect_partial": False, "expect_conflict": False, "citation_note": "", "review_note": "",
            "tier1_chunks": None}
    case.update(extra)
    return case


CASES = {c["id"]: c for c in (fake_case("X-1", "Alpha.pdf", 1, "The fee is USD 40."),
                              fake_case("X-2", "Alpha.pdf", 2, "Opening hours 9 to 5."),
                              fake_case("X-3", "Beta.pdf", 2, "Closed on Sundays."))}
EXPECTED = sorted(CASES)


def dev_split(_cid):
    return "dev"


def write_fixture(path, edits=None, ledger=(), signoff=None, cases=None, validation=True):
    """edits: {(case_id, column_key): value}; attention is cleared unless edited back in."""
    wb = Workbook()
    readme = wb.active
    readme.title = README_SHEET
    for label in SIGNOFF:
        readme.append([label, (signoff or {}).get(label)])
    ws = wb.create_sheet(DEV_SHEET)
    ws.append(list(HEADERS))
    for cid in (cases or EXPECTED):
        row = case_row(CASES[cid], "focus")
        row[KEYS.index("reviewer_attention")] = None
        for (eid, key), value in (edits or {}).items():
            if eid == cid:
                row[KEYS.index(key)] = value
        ws.append(row)
    if validation:
        from openpyxl.worksheet.datavalidation import DataValidation
        dv = DataValidation(type="list", formula1='"VALID,NEEDS REVISION,EXCLUDE"')
        dv.add(f"Y2:Y{len(cases or EXPECTED) + 1}")
        ws.add_data_validation(dv)
    led = wb.create_sheet(LEDGER_SHEET)
    led.append(list(LEDGER_COLUMNS))
    for entry in ledger:
        led.append(list(entry))
    wb.save(path)
    return path


def decided(cid, decision="VALID", rationale=None, date="2026-11-20"):
    return {(cid, "reviewer_decision"): decision, (cid, "reviewer_rationale"): rationale,
            (cid, "reviewer_name"): "Test Reviewer", (cid, "review_date"): date}


def all_valid():
    edits = {}
    for cid in EXPECTED:
        edits.update(decided(cid))
    return edits


SIGNED = {label: "filled" for label in SIGNOFF}


def run(tmp, name="wb.xlsx", baseline=None, **kw):
    path = write_fixture(os.path.join(tmp, name), **kw)
    return validate_book(read_workbook(path), EXPECTED, CASES, dev_split, baseline)


def has(items, text):
    return any(text in i for i in items)


def proposal(n, cid, text=PROPOSED_PREFIX + " evidence p.2"):
    return (str(n), cid, "dev", "data_X.py", "gold_facts", "[]", "[]", text)


with tempfile.TemporaryDirectory() as tmp:
    r = run(tmp)
    check("fresh fixture: NOT_STARTED, 0 errors, 3 pending",
          r["status"] == "NOT_STARTED" and r["errors"] == [] and r["counts"]["pending"] == 3)
    check("fresh fixture: blank sign-off reported", has(r["incomplete"], "sign-off field blank"))
    r = run(tmp, "complete.xlsx", edits=all_valid(), signoff=SIGNED)
    check("all decided + signed: COMPLETE", r["status"] == "COMPLETE" and r["counts"]["VALID"] == 3)
    r = run(tmp, "placeholder.xlsx", edits=all_valid(),
            signoff={**SIGNED, SIGNOFF[1]: "To be completed by the independent human reviewer:"})
    check("sign-off placeholder text counts as blank", r["status"] == "IN_PROGRESS"
          and has(r["incomplete"], "independence confirmation"))

    edits = {**all_valid(), **decided("X-2", "NEEDS REVISION")}
    r = run(tmp, "nr.xlsx", edits=edits, signoff=SIGNED)
    check("NEEDS REVISION without rationale -> incomplete", has(r["incomplete"], "X-2: NEEDS REVISION without a rationale"))
    check("NEEDS REVISION without ledger proposal -> incomplete", has(r["incomplete"], "without a PROPOSED ledger entry"))
    edits = {**all_valid(), **decided("X-2", "EXCLUDE", "page two is ambiguous")}
    r = run(tmp, "ex.xlsx", edits=edits, signoff=SIGNED, ledger=[proposal(1, "X-2")])
    check("EXCLUDE with rationale + proposal: COMPLETE, counted", r["status"] == "COMPLETE"
          and r["counts"]["EXCLUDE"] == 1 and r["ledger"]["proposed"] == 1)

    r = run(tmp, "bad.xlsx", edits={**all_valid(), ("X-1", "reviewer_decision"): "Valid"})
    check("invalid decision value -> error", has(r["errors"], "X-1: invalid decision 'Valid'")
          and r["status"] == "NEEDS_RESOLUTION")
    r = run(tmp, "dup.xlsx", cases=["X-1", "X-1", "X-2"])
    check("duplicate and missing ids -> errors", has(r["errors"], "duplicate case row: X-1")
          and has(r["errors"], "case missing from workbook: X-3"))
    r = validate_book(read_workbook(write_fixture(os.path.join(tmp, "extra.xlsx"))), ["X-1", "X-2"], CASES, dev_split)
    check("unexpected id -> error", has(r["errors"], "unexpected case in workbook: X-3"))
    r = run(tmp, "split.xlsx", edits={("X-1", "split"): "heldout"})
    check("split column contradicting the rule -> error", has(r["errors"], "X-1: split column 'heldout'"))
    r = run(tmp, "drift.xlsx", edits={("X-3", "question"): "edited", ("X-3", "expect_conflict"): "TRUE"})
    check("edited case definition -> error naming the fields", has(r["errors"], "X-3: case definition differs")
          and has(r["errors"], "question") and has(r["errors"], "expect_conflict"))
    r = run(tmp, "nodv.xlsx", validation=False)
    check("missing decision dropdown -> error", has(r["errors"], "decision dropdown"))

    edits = {**all_valid(), ("X-1", "reviewer_name"): None, ("X-2", "review_date"): "17/11/2026",
             ("X-3", "review_date"): datetime.datetime(2026, 11, 20)}
    r = run(tmp, "dates.xlsx", edits=edits, signoff=SIGNED)
    check("missing name / non-ISO date -> incomplete; real date cell accepted",
          has(r["incomplete"], "X-1: reviewer name missing") and has(r["incomplete"], "X-2: review date not YYYY-MM-DD")
          and not has(r["incomplete"], "X-3"))
    r = run(tmp, "nodecision.xlsx", edits={("X-1", "reviewer_name"): "Someone"})
    check("name without decision -> incomplete", has(r["incomplete"], "X-1: reviewer name/date entered without a decision"))
    r = run(tmp, "attention.xlsx", edits={**all_valid(), ("X-1", "reviewer_attention"): "Yes"}, signoff=SIGNED)
    check("attention row decided without rationale -> incomplete",
          has(r["incomplete"], "X-1: attention flag not addressed") and r["attention"][0]["case_id"] == "X-1")

    history = [("1", "X-1", "dev", "data_X.py", "forbidden", "[]", "[]", "applied 2026-11-12")]
    base = read_workbook(write_fixture(os.path.join(tmp, "base.xlsx"), ledger=history))
    edits = {**all_valid(), **decided("X-2", "NEEDS REVISION", "fact missing")}
    r = run(tmp, "led1.xlsx", edits=edits, baseline=base, ledger=history + [proposal(2, "X-2")])
    check("baseline history intact + valid proposal -> no ledger errors", r["errors"] == []
          and r["ledger"]["historical_verified"] == 1)
    changed = [history[0][:7] + ("edited",), proposal(2, "X-2")]
    r = run(tmp, "led2.xlsx", edits=edits, baseline=base, ledger=changed)
    check("edited historical ledger entry -> error", has(r["errors"], "historical ledger entries 1-1 were changed"))
    bad_ledger = history + [proposal(2, "Z-9"), proposal(3, "X-1"), ("5", "X-2", "dev", "x", "f", "", "", "not marked")]
    r = run(tmp, "led3.xlsx", edits=edits, baseline=base, ledger=bad_ledger)
    check("unknown case id in ledger -> error", has(r["errors"], "unknown case id 'Z-9'"))
    check("proposal for a VALID case -> error", has(r["errors"], "proposed correction for X-1 without a NEEDS REVISION"))
    check("change_no gap -> error", has(r["errors"], "change_no is not the sequence"))
    check("new entry not marked PROPOSED -> error", has(r["errors"], "new entry not marked"))
    r = run(tmp, "led4.xlsx", cases=["X-1", "X-2"], ledger=[proposal(1, "X-3")])
    check("proposal for a case outside the workbook -> error", has(r["errors"], "X-3, which is not in this workbook"))

    path = write_fixture(os.path.join(tmp, "ro.xlsx"), edits=all_valid())
    before = sha256_of(path)
    report = validate_book(read_workbook(path), EXPECTED, CASES, dev_split)
    check("reading/validating leaves the workbook byte-identical",
          sha256_of(path) == before)
    text = render_progress(report, "dev", before, "m" * 64)
    check("progress report has counts and no case content",
          "| VALID | 3 |" in text and "| Pending (no decision) | 0 |" in text and "SECRET-QUESTION" not in text)

    # ------------------------------------------------------------ source lookup --
    pdf_dir = os.path.join(tmp, "pdfs")
    os.mkdir(pdf_dir)
    for name, pages in DOCS.items():
        with pymupdf.open() as pdf:
            for text in pages:
                pdf.new_page().insert_text((72, 72), text, fontsize=11)
            pdf.save(os.path.join(pdf_dir, name))
    md = os.path.join(tmp, "source_pages.md")
    with open(md, "w", encoding="utf-8") as fh:
        for name, pages in DOCS.items():
            for n, text in enumerate(pages, 1):
                fh.write(f"### {name}: page {n}\n{text}\n\n")
    index = SourceIndex(DOCS, pdf_dir=pdf_dir, source_pages=md)
    ok = index.locate("Alpha.pdf", 2, "opening   HOURS 9 to 5.")
    check("span found on PDF and dataset page (case/whitespace-insensitive)", ok["problem"] is None
          and ok["span_on_pdf_page"] and ok["span_on_dataset_page"] and ok["source_pages_md_line"] == 4)
    dup = index.locate("Alpha.pdf", 1, "The fee is USD 40.")
    check("other pages with the same text are listed", dup["span_also_on"] == [("Beta.pdf", 1)])
    check("page out of range reported", index.locate("Alpha.pdf", 3, "x")["problem"] == "page out of range")
    check("missing PDF reported", index.locate("Gamma.pdf", 1, "x")["problem"] == "PDF not found")
    check("span not on stated page reported",
          index.locate("Beta.pdf", 1, "Closed on Sundays.")["problem"] == "span text not found on the stated page")
    check("empty span reported", index.locate("Beta.pdf", 1, "  ")["problem"] == "empty span")
    check("lookup result carries no decision field",
          not {"decision", "verdict", "supports", "recommendation"} & set(ok))
    bad = read_workbook(write_fixture(os.path.join(tmp, "src.xlsx"),
                                      edits={("X-3", "expected_sources_json"): '[{"document": "Beta.pdf", "page": 9, "span": "x"}]'}))
    result = check_book_sources(bad, index)
    check("check_book_sources counts and lists problems (no text)", result["references"] == 3
          and result["problems"] == [{"case_id": "X-3", "document": "Beta.pdf", "page": 9, "problem": "page out of range"}])

    # --------------------------------------------------------- development artifact --
    _, real_cases = load_dataset()
    real_by_id = {c["id"]: c for c in real_cases}
    out = os.path.join(tmp, "dev.xlsx")
    ids = build_dev_review(out, real_by_id, "v", "m" * 64, {"eval/phase35/data_A.py": "h"})
    dev_ids = [cid for cid, _ in DEV_REVIEW_CASES]
    report = validate_book(read_workbook(out), dev_ids, real_by_id, split_of)
    check("dev artifact: the 7 owner-named ids, all dev split", ids == dev_ids and all(split_of(i) == "dev" for i in ids))
    check("dev artifact: validates with 0 errors, NOT_STARTED, all reviewer fields blank",
          report["errors"] == [] and report["status"] == "NOT_STARTED" and report["counts"]["pending"] == 7)
    check("dev artifact: none of its cases is held-out", not any(split_of(i) == "heldout" for i in ids))
    try:
        build_dev_review(out, real_by_id, "v", "m", {})
        check("dev artifact: existing file is never overwritten", False)
    except FileExistsError:
        check("dev artifact: existing file is never overwritten", True)
    try:
        build_dev_review(os.path.join(tmp, "x.xlsx"), {}, "v", "m", {})
        check("dev artifact: missing case ids refused (no substitution)", False)
    except ValueError:
        check("dev artifact: missing case ids refused (no substitution)", True)

# ---------------------------------------------------------------- real workbooks (read-only) --
# Independent of review progress (TEST-10): the live status/pending counts are reported by
# check_stage9_readiness.py, not asserted here.
for kind, expected_n in (("heldout", 113), ("dev", 7)):
    path = os.path.join(ROOT, cli.WORKBOOKS[kind])
    before = sha256_of(path)
    with contextlib.redirect_stdout(io.StringIO()):
        code = cli.main(["validate", "--kind", kind])
    report, _ = cli._report(type("A", (), {"kind": kind, "workbook": None, "baseline_git": None})())
    counts = report["counts"]
    check(f"real {kind} workbook: 0 structural/integrity errors (validate exit 0)", code == 0 and report["errors"] == [])
    check(f"real {kind} workbook: {expected_n} rows, pending + reviewed == {expected_n}",
          counts["rows"] == expected_n and counts["pending"] + counts["reviewed"] == expected_n)
    check(f"real {kind} workbook: byte-identical after reading and validating", sha256_of(path) == before)

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
