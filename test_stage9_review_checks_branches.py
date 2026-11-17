"""Stage 9 Phase E2: branch coverage for eval/review/checks.py (TEST-14).

Unit test on in-memory ReviewBook objects built from a FAKE three-case dataset, plus one
temporary workbook for the file-structure branches. No real workbook, database, LLM or network.
"""
import testsafe
testsafe.require_scratch_db()

import copy
import datetime
import os
import sys
import tempfile

from openpyxl import Workbook

from eval.review.checks import PROPOSED_PREFIX, _covers, _flag, definition_drift, valid_date, validate_book
from eval.review.dev_artifact import HEADERS, case_row
from eval.review.workbook import DECISIONS, LEDGER_COLUMNS, ReviewBook, column_key, read_workbook

FAILURES = []
KEYS = [column_key(h) for h in HEADERS]
SIGNED = {"reviewer name": "R", "reviewer independence confirmation": "yes", "date completed": "2026-11-20"}


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def fake_case(cid, page):
    return {"id": cid, "_module": "data_X", "category": "direct_factual", "tier": "both", "question": f"Q-{cid}",
            "history": [], "gold_facts": [["USD 40"]], "forbidden": [], "expect_abstain": False,
            "expect_partial": False, "expect_conflict": False, "tier1_chunks": None,
            "gold_sources": [{"document": "Alpha.pdf", "page": page, "span": "The fee is USD 40."}]}


CASES = {c["id"]: c for c in (fake_case("X-1", 1), fake_case("X-2", 1), fake_case("X-3", 2))}
EXPECTED = sorted(CASES)


def dev_split(_cid):
    return "dev"


def row(cid, **edits):
    out = dict(zip(KEYS, case_row(CASES[cid], "focus")))
    out["reviewer_attention"] = None
    out.update(edits)
    return out


def decided(cid, decision="VALID", **extra):
    fields = {"reviewer_decision": decision, "reviewer_name": "T", "review_date": "2026-11-20", **extra}
    return row(cid, **fields)


def ledger(n, cid, text, split="dev"):
    return dict(zip(LEDGER_COLUMNS, (str(n), cid, split, "data_X.py", "gold_facts", "[]", "[]", text)))


def book(rows=None, entries=(), signoff=SIGNED, dv=("Y2:Y4", DECISIONS)):
    rows = rows if rows is not None else [row(c) for c in EXPECTED]
    for n, r in enumerate(rows, 2):
        r["_row"] = n
    return ReviewBook(path="mem", case_sheet="Development Cases", columns=list(KEYS), cases=rows,
                      ledger_columns=list(LEDGER_COLUMNS), ledger=[dict(e) for e in entries],
                      signoff=dict(signoff), decision_validation=dv)


def run(b, baseline=None, split_of=dev_split):
    return validate_book(b, EXPECTED, CASES, split_of, baseline)


def has(items, text):
    return any(text in i for i in items)


ALL_VALID = [decided(c) for c in EXPECTED]

# ------------------------------------------------------------- pure helpers --
check("_flag: TRUE/false parsed, 'yes' and blank are not booleans",
      _flag(" true ") is True and _flag("FALSE") is False and _flag("yes") is None and _flag(None) is None)
check("valid_date: impossible 2026-02-30 rejected, 2026-02-28 and a date cell accepted",
      not valid_date("2026-02-30") and valid_date(" 2026-02-28 ") and valid_date(datetime.date(2026, 2, 28)))
check("valid_date: non-string non-date rejected", not valid_date(20261120))
check("_covers: one range covering all rows", _covers("Y2:Y4", 2, 4))
check("_covers: multi-range where the second part covers", _covers("Y1:Y1 Y2:Y100", 2, 50))
check("_covers: split ranges with a gap do not count as covering", not _covers("Y2:Y3 Y5:Y10", 2, 10))
check("_covers: single cell is not a range", not _covers("Y2", 2, 2))

# --------------------------------------------------------- definition drift --
drift_cases = {
    "history_json": '[{"role": "user", "content": "x"}]', "forbidden_strings_json": '["USD 50"]',
    "expected_sources_json": '[{"document": "Alpha.pdf", "page": 2, "span": "The fee is USD 40."}]',
    "tier": "answer_only", "category": "compound", "data_file": "data_Y.py",
    "expected_facts_json": "[[\"USD 40\"", "expect_abstain": "yes",
}
for field, value in drift_cases.items():
    check(f"definition drift detected in {field}", definition_drift(row("X-1", **{field: value}), CASES["X-1"]) == [field])
check("blank history cell equals an empty history (no drift)",
      definition_drift(row("X-1", history_json=None), CASES["X-1"]) == [])
r = run(book([row("X-1", expected_facts_json="{not json"), row("X-2"), row("X-3")]))
check("invalid JSON cell -> definition error, NEEDS_RESOLUTION",
      has(r["errors"], "X-1: case definition differs") and has(r["errors"], "expected_facts_json")
      and r["status"] == "NEEDS_RESOLUTION")

# ---------------------------------------------------------------- structure --
r = run(book(dv=None))
check("no decision dropdown -> error", has(r["errors"], "decision dropdown missing"))
r = run(book(dv=("Y2:Y4", ("VALID", "EXCLUDE"))))
check("dropdown with the wrong choices -> error", has(r["errors"], "decision dropdown missing or not"))
r = run(book(dv=("Y2:Y3", DECISIONS)))
check("dropdown not covering every case row -> error", has(r["errors"], "does not cover case rows 2-4"))
r = run(book(dv=("Y2:Y2 Y3:Y4", DECISIONS)))
check("multi-range dropdown with no single covering range -> error (documents _covers)",
      has(r["errors"], "does not cover case rows 2-4"))
b = book()
b.columns = [k for k in KEYS if k != "review_date"]
check("missing case column -> error", has(run(b)["errors"], "missing case column: review_date"))
b = book()
b.ledger_columns = ["n", "case"]
check("ledger columns in a different layout -> error", has(run(b)["errors"], "correction ledger columns differ"))
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "bare.xlsx")
    wb = Workbook()
    wb.active.title = "Something else"
    wb.save(path)
    r = run(read_workbook(path))
    check("workbook without case, ledger or read-me sheets -> three missing-sheet errors",
          has(r["errors"], "missing sheet: Held-out Cases or Development Cases")
          and has(r["errors"], "missing sheet: Correction Ledger") and has(r["errors"], "missing sheet: Read Me"))
    check("no sign-off fields -> incomplete", has(r["incomplete"], "no sign-off fields found"))

# ----------------------------------------------------------- rows and status --
r = run(book([decided("X-1"), row("X-2"), row("X-3")]))
check("one of three decided -> IN_PROGRESS with 2 pending",
      r["status"] == "IN_PROGRESS" and r["counts"]["reviewed"] == 1 and r["counts"]["pending"] == 2)
r = run(book([decided("X-1", "  VALID "), decided("X-2", "EXCLUDE\t", reviewer_rationale="dup"), decided("X-3")],
             entries=[ledger(1, "X-2", PROPOSED_PREFIX + " drop")]))
check("whitespace-padded decisions are accepted and counted",
      r["errors"] == [] and r["counts"]["VALID"] == 2 and r["counts"]["EXCLUDE"] == 1 and r["status"] == "COMPLETE")
r = run(book([decided("X-1", review_date="2026-02-30"), decided("X-2"), decided("X-3")]))
check("impossible date 2026-02-30 -> incomplete", has(r["incomplete"], "X-1: review date not YYYY-MM-DD"))
r = run(book(ALL_VALID, signoff={}))
check("README without sign-off fields -> incomplete, not COMPLETE",
      has(r["incomplete"], "no sign-off fields found") and r["status"] == "IN_PROGRESS")

# ------------------------------------------------------------------- ledger --
r = run(book(entries=[ledger(1, "X-1", "applied 2026-11-12")]), split_of=lambda cid: "heldout" if cid == "X-1" else "dev")
check("ledger split contradicting the split rule -> error", has(r["errors"], "ledger #1: split 'dev' != split rule for X-1"))
history = [ledger(1, "X-1", "applied 2026-11-12"), ledger(2, "X-3", "applied 2026-11-12")]
base = book(entries=history)
r = run(book(ALL_VALID, entries=history[:1]), baseline=base)
check("deleted historical entry -> error", has(r["errors"], "historical ledger entries 1-2 were changed"))
check("FIXED: failed history check reports historical_verified 0 and a FAILED flag",
      r["ledger"]["historical_verified"] == 0 and r["ledger"]["historical_check"] == "FAILED")
r = run(book(ALL_VALID, entries=history), baseline=base)
check("intact history -> verified count 2, check passed",
      r["ledger"]["historical_verified"] == 2 and r["ledger"]["historical_check"] == "passed" and r["errors"] == [])
r = run(book(ALL_VALID, entries=history))
check("no baseline -> historical check 'not run', count 0",
      r["ledger"]["historical_verified"] == 0 and r["ledger"]["historical_check"].startswith("not run"))
check("FIXED: no baseline + unmarked entries -> reported as incomplete (were silently ignored)",
      has(r["incomplete"], "ledger entries [1, 2] are not marked") and r["errors"] == []
      and r["status"] == "IN_PROGRESS")
r = run(book(ALL_VALID, entries=history + [ledger(3, "X-1", "sneaked in")]), baseline=base)
check("with a baseline an unmarked new entry is still an error",
      has(r["errors"], "ledger #3 (X-1): new entry not marked") and not has(r["incomplete"], "not verified"))
proposal = [decided("X-1"), decided("X-2", "NEEDS REVISION", reviewer_rationale="fact missing"), decided("X-3")]
r = run(book(proposal, entries=[ledger(1, "X-2", PROPOSED_PREFIX + " add a fact")]))
check("no baseline + only PROPOSED entries -> no unverified-ledger finding, COMPLETE",
      not has(r["incomplete"], "not marked") and r["status"] == "COMPLETE")
snapshot = copy.deepcopy(base.ledger)
run(book(ALL_VALID, entries=history), baseline=base)
check("validation does not modify the baseline", base.ledger == snapshot)

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
