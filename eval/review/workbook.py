"""Read a ground-truth review workbook into plain data (read-only)."""

from dataclasses import dataclass, field

CASE_SHEETS = ("Held-out Cases", "Development Cases")
README_SHEET = "Read Me & Sign-off"
LEDGER_SHEET = "Correction Ledger"
DECISIONS = ("VALID", "NEEDS REVISION", "EXCLUDE")
REVIEWER_FIELDS = ("reviewer_decision", "reviewer_rationale", "reviewer_name", "review_date")
REQUIRED_CASE_COLUMNS = (
    "case_id", "data_file", "split", "category", "tier", "question", "history_json",
    "expected_facts_json", "forbidden_strings_json", "expected_sources_json",
    "expect_abstain", "expect_partial", "expect_conflict", *REVIEWER_FIELDS, "reviewer_attention",
)
LEDGER_COLUMNS = ("change_no", "case_id", "split", "data_file", "changed_field",
                  "previous_value_json_or_text", "current_value_json_or_text", "source_or_rationale")
SIGNOFF_PREFIX = "Sign-off - "
SIGNOFF_PLACEHOLDER = "To be completed by"


@dataclass
class ReviewBook:
    path: str
    case_sheet: str | None = None
    columns: list = field(default_factory=list)
    cases: list = field(default_factory=list)          # dicts with "_row"
    ledger_columns: list = field(default_factory=list)
    ledger: list = field(default_factory=list)         # dicts with "_row"
    signoff: dict = field(default_factory=dict)        # label -> value (None when blank)
    decision_validation: tuple | None = None           # (sqref, allowed values)
    missing_sheets: list = field(default_factory=list)


def column_key(header) -> str:
    """'expected_facts_json (each group ...)' -> 'expected_facts_json'."""
    return str(header or "").split(" ")[0]


def blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _rows(ws):
    header = [column_key(c.value) for c in ws[1]]
    out = []
    for cells in ws.iter_rows(min_row=2):
        values = [c.value for c in cells]
        if all(blank(v) for v in values):
            continue
        row = dict(zip(header, values))
        row["_row"] = cells[0].row
        out.append(row)
    return header, out


def _decision_validation(ws, columns):
    if "reviewer_decision" not in columns:
        return None
    from openpyxl.utils import get_column_letter
    letter = get_column_letter(columns.index("reviewer_decision") + 1)
    for dv in ws.data_validations.dataValidation:
        if dv.type == "list" and str(dv.sqref).startswith(letter):
            allowed = tuple(v.strip() for v in (dv.formula1 or "").strip('"').split(","))
            return str(dv.sqref), allowed
    return None


def _signoff(ws) -> dict:
    out = {}
    for label, value in ws.iter_rows(min_row=1, max_col=2, values_only=True):
        if isinstance(label, str) and label.startswith(SIGNOFF_PREFIX):
            text = None if blank(value) else str(value).strip()
            out[label[len(SIGNOFF_PREFIX):]] = None if text and text.startswith(SIGNOFF_PLACEHOLDER) else text
    return out


def read_workbook(path: str) -> ReviewBook:
    """Load without modifying the file (openpyxl only reads)."""
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    book = ReviewBook(path=path)
    case_sheet = next((name for name in CASE_SHEETS if name in wb.sheetnames), None)
    if case_sheet is None:
        book.missing_sheets.append(" or ".join(CASE_SHEETS))
    else:
        book.case_sheet = case_sheet
        book.columns, book.cases = _rows(wb[case_sheet])
        book.decision_validation = _decision_validation(wb[case_sheet], book.columns)
    if LEDGER_SHEET in wb.sheetnames:
        book.ledger_columns, book.ledger = _rows(wb[LEDGER_SHEET])
    else:
        book.missing_sheets.append(LEDGER_SHEET)
    if README_SHEET in wb.sheetnames:
        book.signoff = _signoff(wb[README_SHEET])
    else:
        book.missing_sheets.append(README_SHEET)
    wb.close()
    return book
