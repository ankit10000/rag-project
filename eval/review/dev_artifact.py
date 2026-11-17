"""Build the separate DEVELOPMENT review workbook (new file only; never overwrites).

Same layout and review principles as the held-out workbook, for the development
cases named by the project owner. It is not part of the held-out review, does
not affect held-out thresholds, and contains no decision: all reviewer fields
are blank. Case definitions are copied from the dataset as they stand.
"""

import json
import os

from eval.review.workbook import DECISIONS, LEDGER_COLUMNS, LEDGER_SHEET, README_SHEET

DEV_SHEET = "Development Cases"
CONFLICT_FOCUS = ("Does the expected conflict represent a genuine disagreement between sources "
                  "(rather than an ordinary update or correction)?")
# Case ids and review questions as given by the project owner (Stage 9 Phase B continuation).
DEV_REVIEW_CASES = (
    ("B-comp-04", "Should calder_sound_tile_study_TR-2026-07.pdf page 4 be included as an expected "
                  "source for the missing production-cost information?"),
    ("B-conf-02", CONFLICT_FOCUS),
    ("B-conf-03", CONFLICT_FOCUS),
    ("B-conf-04", CONFLICT_FOCUS),
    ("D-conflicting-01", CONFLICT_FOCUS),
    ("D-conflicting-03", CONFLICT_FOCUS),
    ("D-conflicting-04", CONFLICT_FOCUS),
)
HEADERS = (
    "case_id", "data_file", "split", "category", "tier", "tier1_eligible", "tier2_eligible", "question",
    "history_json", "expected_facts_json (each group required; alternatives within group)",
    "forbidden_strings_json", "expected_sources_json (document,page,gold_span)", "expect_abstain",
    "expect_partial", "expect_conflict", "citation_note", "author_review_note (context, not review)",
    "tier1_chunks_json", "correction_status", "previous_category", "previous_expected_facts_json",
    "previous_forbidden_strings_json", "previous_expect_conflict", "correction_summary",
    "reviewer_decision (VALID / NEEDS REVISION / EXCLUDE)", "reviewer_rationale", "reviewer_name",
    "review_date", "reviewer_attention", "review_focus (question from the project owner; not a decision)",
)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def case_row(case: dict, focus: str) -> list:
    flag = {True: "TRUE", False: "FALSE"}
    sources = [{"document": s["document"], "page": s["page"], "span": s["span"]} for s in case["gold_sources"]]
    return [
        case["id"], f"{case['_module']}.py", "dev", case["category"], case["tier"], "Yes",
        "Yes" if case["tier"] == "both" else "No - answer_only", case["question"], _dump(case["history"]),
        _dump(case["gold_facts"]), _dump(case["forbidden"]), _dump(sources), flag[case["expect_abstain"]],
        flag[case["expect_partial"]], flag[case["expect_conflict"]], case.get("citation_note"),
        case.get("review_note"), _dump(case["tier1_chunks"]) if case.get("tier1_chunks") else None,
        None, None, None, None, None, None,          # no correction history for these cases
        None, None, None, None,                      # reviewer fields: blank, for the human reviewer
        "Yes - see review_focus", focus,
    ]


def readme_rows(dataset_version: str, manifest_sha: str, file_hashes: dict) -> list:
    ids = ", ".join(cid for cid, _ in DEV_REVIEW_CASES)
    rows = [
        ("DEVELOPMENT REVIEW PACKAGE", "Development split only. SEPARATE from the 113-case held-out review."),
        ("Purpose", "Human ground-truth review of development cases flagged for attention. Outcomes do not "
                    "change held-out cases, held-out thresholds or the held-out review."),
        ("Cases", f"{len(DEV_REVIEW_CASES)} development cases: {ids}"),
        ("Dataset", f"version {dataset_version}; frozen manifest content_sha256 {manifest_sha}"),
        ("Review focus", "Column AD gives the owner's question for each case. It is a question, not an answer."),
        ("How to use", "Follow docs/remediation/dev_review/README.md. The criteria and decision meanings are the "
                       "same as in docs/remediation/heldout_review/HUMAN_REVIEW_GUIDE.md sections 3-4."),
        ("Decision choices", "VALID; NEEDS REVISION; EXCLUDE. Give a rationale for NEEDS REVISION or EXCLUDE "
                             "(and for every row here, since every row has a review focus). Fill reviewer "
                             "name and date (YYYY-MM-DD) on every row."),
        ("Source package", "docs/remediation/heldout_review/source_pdfs/ (12 PDFs) and source_pages.md "
                           "(all 56 dataset pages, including development pages)."),
        ("Correction ledger", "Empty. Record each proposed correction as a new row (change_no from 1); start "
                              "source_or_rationale with 'PROPOSED (not applied):'. Nothing is applied "
                              "without the project owner's approval."),
        ("Prior context", "These cases were listed for human attention in Stage 9 Phase A (an AI-produced "
                          "audit). That listing is not a decision; form your own."),
        ("Current dataset SHA-256", None),
    ]
    rows += [(path.rsplit("/", 1)[1], digest) for path, digest in sorted(file_hashes.items())]
    rows += [
        ("No evaluation", "Preparing or completing this review runs no evaluation and authorizes none."),
        ("Sign-off - reviewer name", None),
        ("Sign-off - reviewer independence confirmation", "To be completed by the development reviewer:"),
        (f"Sign-off - cases reviewed (of {len(DEV_REVIEW_CASES)})", None),
        ("Sign-off - VALID / NEEDS REVISION / EXCLUDE counts", None),
        ("Sign-off - date completed", None),
        ("Sign-off - signature", None),
    ]
    return rows


def _style(ws, widths):
    from openpyxl.styles import Alignment, Font
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width


def build_dev_review(output: str, cases_by_id: dict, dataset_version: str, manifest_sha: str,
                     file_hashes: dict) -> list:
    """Write a NEW workbook at ``output``; refuse to overwrite. Returns the case ids written."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    missing = [cid for cid, _ in DEV_REVIEW_CASES if cid not in cases_by_id]
    if missing:
        raise ValueError(f"development review case ids not in the dataset: {missing}")
    if os.path.exists(output):
        raise FileExistsError(f"refusing to overwrite {output}")
    wb = Workbook()
    readme = wb.active
    readme.title = README_SHEET
    for row in readme_rows(dataset_version, manifest_sha, file_hashes):
        readme.append(list(row))
    _style(readme, {"A": 42, "B": 110})
    cases = wb.create_sheet(DEV_SHEET)
    cases.append(list(HEADERS))
    for cid, focus in DEV_REVIEW_CASES:
        cases.append(case_row(cases_by_id[cid], focus))
    decision_col = get_column_letter(HEADERS.index("reviewer_decision (VALID / NEEDS REVISION / EXCLUDE)") + 1)
    dv = DataValidation(type="list", formula1='"' + ",".join(DECISIONS) + '"', allow_blank=True)
    dv.add(f"{decision_col}2:{decision_col}{len(DEV_REVIEW_CASES) + 1}")
    cases.add_data_validation(dv)
    cases.freeze_panes = "E2"
    _style(cases, {get_column_letter(i): 24 for i in range(1, len(HEADERS) + 1)})
    ledger = wb.create_sheet(LEDGER_SHEET)
    ledger.append(list(LEDGER_COLUMNS))
    _style(ledger, {get_column_letter(i): 30 for i in range(1, len(LEDGER_COLUMNS) + 1)})
    wb.save(output)
    return [cid for cid, _ in DEV_REVIEW_CASES]
