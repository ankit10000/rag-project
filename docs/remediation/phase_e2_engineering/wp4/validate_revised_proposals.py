"""Stage 9 Phase E2 WP4: validate the revised correction proposals (read-only).

Applies REVISED_PROPOSALS.json to an in-memory copy of the dataset, runs
eval/phase35/validate.validate (must be VALID), runs v1 scorer probes
(positive, negative, hedge, formatting variants) against current, Phase D,
revised and option definitions, scans every new alternative against the whole
corpus and the dev answers, re-scores the dev result rows of TA-D1..TA-D4,
checks the TA-D4 Tier 1 context change, and checks denominators and category
counts. Exits 1 on any unexpected result.

No database, no network, no LLM. Writes nothing unless --write-log PATH is given
(a NEW file, opened with mode "x").

    cd /Volumes/Storage/rag-project && DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch \
      TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 .venv/bin/python -B \
      docs/remediation/phase_e2_engineering/wp4/validate_revised_proposals.py
"""
import argparse
import copy
import io
import json
import os
import re
import runpy
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PHASE_D = os.path.join(ROOT, "docs", "remediation", "phase_d_decision_package", "scorer_regression_probes.py")

# Phase D probe module: patches psycopg.connect to raise, loads the dataset, exposes score()/PROPOSALS.
NS = runpy.run_path(PHASE_D, run_name="phase_d_probes")
DOCS, BY_ID, PHASE_D_PROPOSALS = NS["DOCS"], NS["BY_ID"], NS["PROPOSALS"]
score_with, score_generic = NS["score"], NS["score_generic"]

from eval.framework.integrity import split_of  # noqa: E402
from eval.phase35 import validate as V  # noqa: E402
from eval.phase35.run_eval import tier1_context  # noqa: E402

with open(os.path.join(HERE, "REVISED_PROPOSALS.json"), encoding="utf-8") as fh:
    REVISED = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}

# TP-06 (A-multipage-01) G1 variants, probed for REVISED_POTENTIAL_ISSUE_DECISIONS.md.
TP06_G2 = ["24 hours", "twenty-four hours"]
TP_OPTIONS = {
    "TP06-PHASED": ("A-multipage-01", {"gold_facts": [["vessel", "counts as premises", "treated as premises",
                                                       "is premises"], TP06_G2]}),
    "TP06-X": ("A-multipage-01", {"gold_facts": [["vessel", "counts as premises", "is premises"], TP06_G2]}),
}

T, F = True, False
FLU = " Pneumococcal is free from 65 and shingles at 70."
BOAT = " Cooling-tower managers must report within 24 hours."
# (probe_id, target, answer, expected_v1, kind)
PROBES = [
    ("W-TA01-1", "CUR:A-conflict-03", "You need 48 hours' notice; the March 2026 update replaced the 24-hour rule.", F, "current false negative"),
    ("W-TA01-2", "REV:TA-01", "You need 48 hours' notice; the March 2026 update replaced the 24-hour rule.", T, "positive"),
    ("W-TA01-3", "REV:TA-01", "Give at least 48 hrs notice.", T, "format variant"),
    ("W-TA01-4", "REV:TA-01", "At least 24 hours.", F, "negative"),
    ("W-TA01-5", "REV:TA-01", "Either 24 or 48 hours.", T, "hedge passes (trade-off)"),
    ("W-TA02-1", "CUR:D-conflicting-02", "Tighten to 31 Nm; errata sheet 2 supersedes the 28 Nm printed in section 5.", F, "current false negative"),
    ("W-TA02-2", "REV:TA-02", "Tighten to 31 Nm; errata sheet 2 supersedes the 28 Nm printed in section 5.", T, "positive"),
    ("W-TA02-3", "PHD:TA-02", "Torque them to 31 N·m.", F, "Phase D false negative"),
    ("W-TA02-4", "REV:TA-02", "Torque them to 31 N·m.", T, "format variant"),
    ("W-TA02-5", "REV:TA-02", "31Nm, per errata sheet 2.", T, "format variant"),
    ("W-TA02-6", "REV:TA-02", "Use 31 N m.", T, "format variant"),
    ("W-TA02-7", "REV:TA-02", "28 Nm.", F, "negative"),
    ("W-TA02-8", "REV:TA-02", "28 Nm or 31 Nm.", T, "hedge passes (trade-off)"),
    ("W-TA02-9", "OPT:TA-02:B", "Torque them to 31 N·m.", T, "option B positive"),
    ("W-TA02-10", "OPT:TA-02:B", "Per the 31 Nov notice the torque is 28 Nm.", T, "option B false match (risk)"),
    ("W-TA02-11", "REV:TA-02", "Per the 31 Nov notice the torque is 28 Nm.", F, "explicit list rejects it"),
    ("W-TA03-1", "CUR:B-follow-01", "It is GBP 1,800 - not 2,000 as I said earlier.", F, "current false negative"),
    ("W-TA03-2", "REV:TA-03", "It is GBP 1,800 - not 2,000 as I said earlier.", T, "positive"),
    ("W-TA03-3", "REV:TA-03", "The cap is GBP 2,000.", F, "negative"),
    ("W-TA03-4", "CUR:B-follow-01", "It is either GBP 1,800 or 2,000.", F, "hedge rejected today"),
    ("W-TA03-5", "REV:TA-03", "It is either GBP 1,800 or 2,000.", T, "hedge passes (trade-off, SCORER-13)"),
    ("W-TA04-1", "REV:TA-04", "120 days' written notice; separately, stopping auto-renewal needs 90 days.", T, "positive"),
    ("W-TA04-2", "REV:TA-04", "90 days' notice.", F, "negative"),
    ("W-TA04-3", "REV:TA-04", "Either 120 days or 90 days.", T, "hedge passes (trade-off)"),
    ("W-TA04-4", "REV:TA-04", "Either 120 or 90 days.", F, "compressed hedge fails G1 literal '120 days'"),
    ("W-TA04-5", "CUR:C-direct-06", "Either 120 days or 90 days.", F, "hedge rejected today (forbidden)"),
    ("W-TA05-1", "CUR:C-multi_chunk-03", "Plan Pro includes one on-site visit a year with a two working day response; the excess is waived.", T, "current false positive"),
    ("W-TA05-2", "REV:TA-05", "Plan Pro includes one on-site visit a year with a two working day response; the excess is waived.", F, "negative"),
    ("W-TA05-3", "PHD:TA-05", "Plan Pro includes 2 on-site engineer visits a year and the excess is £0.", F, "Phase D false negative"),
    ("W-TA05-4", "REV:TA-05", "Plan Pro includes 2 on-site engineer visits a year and the excess is £0.", T, "positive"),
    ("W-TA05-5", "PHD:TA-05", "Twice-yearly on-site visits are included, and the accidental damage excess is waived.", F, "Phase D false negative"),
    ("W-TA05-6", "REV:TA-05", "Twice-yearly on-site visits are included, and the accidental damage excess is waived.", T, "positive"),
    ("W-TA05-7", "REV:TA-05", "Pro: 2 on-site visits per year and £0 excess (Basic would be £40).", F, "£40 forbidden false failure (kept; decision)"),
    ("W-TA05-8", "OPT:TA-05:B", "Pro: 2 on-site visits per year and £0 excess (Basic would be £40).", T, "option B fixes £40 false failure"),
    ("W-TA05-9", "OPT:TA-05:B", "Two on-site visits a year; the excess is £0 or £40.", T, "option B hedge passes (trade-off)"),
    ("W-TA05-10", "REV:TA-05", "Plan Pro includes 12 visits per year and the excess is waived.", T, "residual TS-4 (12 contains 2)"),
    ("W-TA06-1", "CUR:A-multichunk-01", "Yes, they can be given on the same day as flu." + FLU, T, "positive"),
    ("W-TA06-2", "CUR:A-multichunk-01", "No, they cannot be given at the same appointment." + FLU, T, "current false positive (negated echo)"),
    ("W-TA06-3", "CUR:A-multichunk-01", "Yes, you can have them at the same appointment." + FLU, T, "echo-only positive"),
    ("W-TA06-4", "OPT:TA-06:B", "No, they cannot be given at the same appointment." + FLU, T, "option B residual false positive"),
    ("W-TA06-5", "OPT:TA-06:B", "Yes, you can have them together." + FLU, F, "option B new false failure"),
    ("W-TA06-6", "OPT:TA-06:C", "Yes, you can have them together." + FLU, T, "option C positive"),
    ("W-TA06-7", "OPT:TA-06:C", "Yes, the same day as flu, in the other arm." + FLU, T, "option C positive"),
    ("W-TA06-8", "OPT:TA-06:C", "No, they cannot be given at the same appointment." + FLU, T, "option C residual false positive"),
    ("W-TA06-9", "OPT:TA-06:C", "No, you can't have them together." + FLU, T, "option C residual false positive"),
    ("W-TA06-10", "OPT:TA-06:C", "Yes, you can combine them in one go." + FLU, F, "option C echo-only answer fails"),
    ("W-TA06-11", "OPT:TA-06:D", "No, they cannot be given at the same appointment." + FLU, F, "option D rejects negated echo"),
    ("W-TA06-12", "OPT:TA-06:D", "No, they cannot be given on the same day." + FLU, T, "option D residual false positive"),
    ("W-TA06-13", "OPT:TA-06:D", "Yes, you can have them at the same appointment." + FLU, F, "option D new false failure"),
    ("W-TA06-14", "OPT:TA-06:D", "Yes, you can have them together, in the other arm." + FLU, T, "option D positive"),
    ("W-TA07-1", "CUR:D-injection-03", "Spills of more than 15 litres must be reported within 1 hour.", T, "current false positive"),
    ("W-TA07-2", "CUR:D-injection-03", "Spills over 5 litres must be reported within 11 hours.", T, "current false positive (G2 boundary)"),
    ("W-TA07-3", "REV:TA-07", "Spills of more than 15 litres must be reported within 1 hour.", F, "negative"),
    ("W-TA07-4", "REV:TA-07", "Spills over 5 litres must be reported within 11 hours.", F, "negative (G2 boundary)"),
    ("W-TA07-5", "REV:TA-07", "Spills over 5 l must be reported within 21 hours.", F, "negative (G2 boundary)"),
    ("W-TA07-6", "REV:TA-07", "Anything over 1.5 l or 25 l must be reported within 1 hour.", F, "negative"),
    ("W-TA07-7", "REV:TA-07", "Spills of more than 5 litres are reported to the HSE officer within 1 hour.", T, "positive"),
    ("W-TA07-8", "PHD:TA-07", "Report spills larger than **5 litres** to the HSE officer within **1 hour**.", F, "Phase D false negative (markdown)"),
    ("W-TA07-9", "REV:TA-07", "Report spills larger than **5 litres** to the HSE officer within **1 hour**.", T, "markdown variant"),
    ("W-TA07-10", "REV:TA-07", "Spill size: (5 litres) - report within 1 hour.", T, "parenthesis variant"),
    ("W-TA07-11", "REV:TA-07", "- Size:\n5 litres or more\n- Deadline: within 1 hour", T, "line-start variant"),
    ("W-TA07-12", "REV:TA-07", "Any 5-litre-plus spill is reported within one hour.", T, "hyphen variant"),
    ("W-TA07-13", "REV:TA-07", "Spills >5 litres: report within 1-hour.", T, "'>' variant"),
    ("W-TA07-14", "REV:TA-07", "Spills over 5 litres: report within 1 hour.", T, "NBSP before number"),
    ("W-TA07-15", "REV:TA-07", "5 litres or more must be reported within 1 hour.", F, "residual: value at answer start"),
    ("W-TA07-16", "REV:TA-07", "Report within an hour any spill over 5 litres.", F, "residual: 'an hour' not accepted"),
    ("W-TA07-17", "REV:TA-07", "Spills over 5 litres: report within 1 hour.", F, "residual: NBSP between number and unit"),
    ("W-TA07-18", "OPT:TA-07:B", "Spills of more than 15 litres must be reported within 1 hour.", T, "option B keeps false positive until v2"),
    ("W-TA08-1", "CUR:A-multipage-02", "She must be accompanied by her grandad. Ward 4 visiting is 10:00-12:00.", T, "current false positive"),
    ("W-TA08-2", "REV:TA-08", "She must be accompanied by her grandad. Ward 4 visiting is 10:00-12:00.", F, "negative"),
    ("W-TA08-3", "PHD:TA-08", "She needs an adult who isn't the patient; visiting is 10:00-12:00 and 16:00-18:00.", F, "Phase D false negative"),
    ("W-TA08-4", "REV:TA-08", "She needs an adult who isn't the patient; visiting is 10:00-12:00 and 16:00-18:00.", T, "positive"),
    ("W-TA08-5", "REV:TA-08", "Any adult other than her grandad must come; you can visit 10am-12pm or 4pm-6pm.", T, "12-hour variant"),
    ("W-TA08-6", "REV:TA-08", "Her mum or another adult (not grandad) must come; 10:00-12:00 or 16:00-18:00.", T, "paraphrase"),
    ("W-TA08-7", "REV:TA-08", "An adult who is not the patient; visiting is 10:00-12:00.", F, "negative (one block)"),
    ("W-TA09-1", "REV:TA-09", "Level 4 cut-resistant gloves; the plant manager can authorise removing the lock.", F, "negative"),
    ("W-TA09-2", "REV:TA-09", "Level 4 cut-resistant gloves; written approval from the plant manager and the HSE officer.", T, "positive"),
    ("W-TA09-3", "REV:TA-09", "Level 4 cut-resistant gloves; written approval from the plant manager and the health and safety officer.", T, "variant"),
    ("W-TA10-1", "CUR:B-direct-04", "The interviews are on 22 June 2027.", T, "current false positive"),
    ("W-TA10-2", "REV:TA-10", "The interviews are on 22 June 2027.", F, "negative"),
    ("W-TA10-3", "PHD:TA-10", "Interviews run from 21 to 22 June 2027.", F, "Phase D false negative"),
    ("W-TA10-4", "REV:TA-10", "Interviews run from 21 to 22 June 2027.", T, "range variant"),
    ("W-TA10-5", "REV:TA-10", "On 21 June and 22 June 2027.", T, "range variant"),
    ("W-TA10-6", "REV:TA-10", "June 21st and 22nd, 2027.", T, "range variant"),
    ("W-TA10-7", "REV:TA-10", "21 – 22 June 2027.", T, "range variant"),
    ("W-TA11-1", "CUR:C-multi_page-01", "Battery packs have 6 months of cover; a replacement keeps 90 days.", T, "current false positive"),
    ("W-TA11-2", "REV:TA-11", "Battery packs have 6 months of cover; a replacement keeps 90 days.", F, "negative"),
    ("W-TA11-3", "PHD:TA-11", "Batteries and filters get 6 months; a replacement gets the rest of the warranty or 90 days, whichever is longer.", F, "Phase D false negative (DATA-1)"),
    ("W-TA11-4", "REV:TA-11", "Batteries and filters get 6 months; a replacement gets the rest of the warranty or 90 days, whichever is longer.", T, "positive (mandatory)"),
    ("W-TA11-5", "REV:TA-11", "Battery packs and filters get 6 months; a replacement gets 90 days at least.", T, "positive"),
    ("W-TAD1-1", "REV:TA-D1", "On site the SOP's 750 h applies; the OEM manual says 500 h.", T, "positive"),
    ("W-TAD1-2", "REV:TA-D1", "Every 750h per the site SOP.", T, "format variant"),
    ("W-TAD1-3", "REV:TA-D1", "Every 500 h.", F, "negative"),
    ("W-TAD1-4", "REV:TA-D1", "500 h or 750 h.", T, "hedge passes (trade-off)"),
    ("W-TAD2-1", "REV:TA-D2", "21 days for international flights (memo TEP-M-09 changed it from 14).", T, "positive"),
    ("W-TAD2-2", "REV:TA-D2", "Book at least three weeks ahead.", T, "variant"),
    ("W-TAD2-3", "REV:TA-D2", "At least 14 days before departure.", F, "negative"),
    ("W-TAD2-4", "REV:TA-D2", "14 or 21 days.", T, "hedge passes (trade-off)"),
    ("W-TAD3-1", "REV:TA-D3", "USD 64 per day; the quick reference card's USD 58 is out of date.", T, "positive"),
    ("W-TAD3-2", "REV:TA-D3", "USD64 a day.", T, "format variant"),
    ("W-TAD3-3", "REV:TA-D3", "USD 58 per day, plus mileage at USD 0.58.", F, "negative"),
    ("W-TAD3-4", "REV:TA-D3", "USD 58 or USD 64.", T, "hedge passes (trade-off)"),
    ("W-TAD4-1", "REV:TA-D4", "12 stations per treatment. The report says production cost per tile was not recorded.", F, "v1 false negative (needs TS-1)"),
    ("W-TAD4-2", "REV:TA-D4", "12 stations per treatment; the production cost per tile is not stated.", T, "positive"),
    ("W-TP06-1", "CUR:A-multipage-01", "No, a moored boat is not treated as premises." + BOAT, T, "current false positive"),
    ("W-TP06-2", "TP:TP06-PHASED", "No, a moored boat is not treated as premises." + BOAT, T, "Phase D fix leaves echo (DATA-4)"),
    ("W-TP06-3", "TP:TP06-X", "No, a moored boat is not treated as premises." + BOAT, F, "option X rejects negated echo"),
    ("W-TP06-4", "TP:TP06-X", "Yes, any vessel moored at Orrin Quay counts as premises." + BOAT, T, "option X positive"),
    ("W-TP06-5", "TP:TP06-X", "Yes, a boat tied up at Orrin Quay is treated as premises." + BOAT, F, "option X new false failure"),
    ("W-TP06-6", "TP:TP06-X", "No, a vessel moored there is not premises." + BOAT, T, "option X residual false positive"),
]


def case_for(target):
    kind, _, rest = target.partition(":")
    if kind == "CUR":
        return copy.deepcopy(BY_ID[rest])
    if kind == "PHD":
        cid, changes = PHASE_D_PROPOSALS[rest]
    elif kind == "REV":
        cid, changes = REVISED[rest]["case_id"], REVISED[rest]["changes"]
    elif kind == "OPT":
        iid, oid = rest.split(":")
        cid = REVISED[iid]["case_id"]
        changes = next(o["changes"] for o in REVISED[iid]["options"] if o["option_id"] == oid)
    elif kind == "TP":
        cid, changes = TP_OPTIONS[rest]
    else:
        raise ValueError(target)
    case = copy.deepcopy(BY_ID[cid])
    case.update(copy.deepcopy(changes))
    return case


def patched_cases(overrides):
    """overrides: {case_id: changes}. Returns a full in-memory case list."""
    out = []
    for c in BY_ID.values():
        c2 = copy.deepcopy(c)
        c2.update(copy.deepcopy(overrides.get(c["id"], {})))
        out.append(c2)
    return out


def check_metadata(fail):
    print("== Proposal metadata")
    expected_ids = [f"TA-{i:02d}" for i in range(1, 12)] + [f"TA-D{i}" for i in range(1, 5)]
    if sorted(REVISED) != sorted(expected_ids):
        fail(f"issue ids {sorted(REVISED)}")
    for iid, p in REVISED.items():
        problems = []
        if p["status"] != "PENDING_OWNER_DECISION":
            problems.append("status")
        if p["supersedes"] != f"Phase D {iid}" or PHASE_D_PROPOSALS[iid][0] != p["case_id"]:
            problems.append("supersedes/case")
        if split_of(p["case_id"]) != p["split"]:
            problems.append("split")
        for o in p.get("options", []):
            if not o["changes"].keys() <= set(V.REQUIRED):
                problems.append(f"option {o['option_id']} field")
        if not p["changes"].keys() <= set(V.REQUIRED):
            problems.append("field")
        print(f"  {iid:6} {p['case_id']:18} {p['split']:8} {p['status']} {'OK' if not problems else problems}")
        if problems:
            fail(f"{iid} metadata {problems}")


def check_validate(fail):
    print("== validate.validate (in memory)")
    rec = {p["case_id"]: p["changes"] for p in REVISED.values()}
    errs = V.validate(DOCS, patched_cases(rec))
    print(f"  all 15 recommended entries applied together: {'VALID' if not errs else errs}")
    if errs:
        fail("validate recommended")
    variants = [(iid, o) for iid, p in REVISED.items() for o in p.get("options", [])]
    variants += [(name, {"option_id": "-", "changes": ch}) for name, (_, ch) in TP_OPTIONS.items()]
    for iid, o in variants:
        cid = REVISED[iid]["case_id"] if iid in REVISED else TP_OPTIONS[iid][0]
        errs = V.validate(DOCS, patched_cases({**rec, cid: o["changes"]}))
        print(f"  {iid} option {o['option_id']} (with all other recommended entries): {'VALID' if not errs else errs}")
        if errs:
            fail(f"validate {iid} {o['option_id']}")


def run_probes(fail):
    print("== v1 probes (frozen eval/phase35/run_eval.score_generic)")
    for pid, target, answer, expected, kind in PROBES:
        got = score_with(score_generic, case_for(target), answer)
        ok = got == expected
        print(f"  {'PASS' if ok else 'FAIL'} {pid:10} {target:22} v1={got!s:5} exp={expected!s:5} {kind} | {answer!r}")
        if not ok:
            fail(pid)
    print(f"  {len(PROBES)} probes")


def corpus_and_dev_scan(dev_rows):
    print("== Substring scan of every NEW alternative (vs current definition): whole corpus + dev answers")
    pages = [(d, i + 1, t.lower()) for d, ps in DOCS.items() for i, t in enumerate(ps)]
    entries = [(iid, p["case_id"], p["changes"]) for iid, p in REVISED.items()]
    entries += [(f"{iid}:{o['option_id']}", REVISED[iid]["case_id"], o["changes"])
                for iid, p in REVISED.items() for o in p.get("options", [])]
    entries += [(name, cid, ch) for name, (cid, ch) in TP_OPTIONS.items()]
    flagged = 0
    for label, cid, changes in entries:
        old = {a for g in BY_ID[cid]["gold_facts"] for a in g}
        new = sorted({a for g in changes.get("gold_facts", []) for a in g} - old)
        gold = {(s["document"], s["page"]) for s in changes.get("gold_sources", BY_ID[cid]["gold_sources"])}
        for alt in new:
            low = alt.lower()
            on_gold = sum(t.count(low) for d, p, t in pages if (d, p) in gold)
            off = [f"{d[:18]} p{p}" for d, p, t in pages if (d, p) not in gold and low in t]
            dev = sorted({r["id"] for r in dev_rows if low in (r.get("answer") or "").lower()})
            mark = "REVIEW" if off or dev else "clean"
            flagged += mark == "REVIEW"
            print(f"  {label:14} {alt!r:26} gold-pages={on_gold} other-pages={off or 0} dev-answers={dev or 0} {mark}")
    print(f"  {flagged} alternative(s) with hits outside the gold pages or in dev answers (see REVIEW lines)")


def rescore_row(case, row):
    gold = {(s["document"], s["page"]) for s in case["gold_sources"]}
    if row["tier"] == 1:
        ctx = [(c["chunk_id"], c["document"], c["page"]) for c in row["context"]]
    else:
        ctx = [(r["chunk_id"], r["document_name"], r["page_number"]) for r in row["retrieved"]]
    chunk_pair = {cid: ((d, p) if (d, p) in gold else None) for cid, d, p in ctx}
    text = " ".join(DOCS[d][p - 1] for _, d, p in ctx if d in DOCS)
    result = {"answer": row["answer"], "status": row["status"], "citations": row["citations"]}
    return score_generic(case, result, chunk_pair, set(chunk_pair), text)


def dev_rescore(dev_rows, fail):
    print("== Dev result rows re-scored in memory (current vs revised definition; result files untouched)")
    for iid in ("TA-D1", "TA-D2", "TA-D3", "TA-D4"):
        cid = REVISED[iid]["case_id"]
        for row in (r for r in dev_rows if r["id"] == cid):
            cur = rescore_row(case_for(f"CUR:{cid}"), row)
            rev = rescore_row(case_for(f"REV:{iid}"), row)
            if cur["correct"] != row["score"]["correct"]:
                fail(f"{iid} T{row['tier']} reconstruction mismatch")
            print(f"  {iid} {cid} T{row['tier']}: stored correct={row['score']['correct']} | current-def "
                  f"correct={cur['correct']} cit_compl={cur['citation_completeness']:.2f} | revised-def "
                  f"correct={rev['correct']} recall={rev['fact_recall']:.2f} cit_compl={rev['citation_completeness']:.2f}")


def check_tier1_context(fail):
    print("== TA-D4 Tier 1 context (run_eval.tier1_context)")
    out = {}
    for label, target in (("current", "CUR:B-comp-04"), ("revised", "REV:TA-D4")):
        results, chunk_pair, _ = tier1_context(case_for(target), DOCS)
        distractors = sorted((r["chunk"][1], r["chunk"][2]) for r in results if chunk_pair[r["chunk"][0]] is None)
        out[label] = [f"{d.split('_')[0]} p{p}" for d, p in distractors]
        print(f"  {label}: gold={sorted(v for v in chunk_pair.values() if v)} distractors={out[label]}")
    if out != {"current": ["calder p4", "velmoor p5"], "revised": ["calder p5", "velmoor p5"]}:
        fail("TA-D4 tier1 context")


def counts(cases):
    by_split = {}
    for c in cases:
        s = split_of(c["id"])
        d = by_split.setdefault(s, {"tier1": 0, "tier2": 0, "cat": Counter()})
        d["tier1"] += 1
        d["tier2"] += c["tier"] == "both"
        d["cat"][c["category"]] += 1
    return by_split


def check_counts(fail):
    print("== Denominators and category counts")
    before = counts(list(BY_ID.values()))
    after = counts(patched_cases({p["case_id"]: p["changes"] for p in REVISED.values()}))
    for s in ("heldout", "dev"):
        b, a = before[s], after[s]
        diff = {k: f"{b['cat'][k]}->{a['cat'][k]}" for k in sorted(set(b["cat"]) | set(a["cat"])) if b["cat"][k] != a["cat"][k]}
        print(f"  {s}: tier1 {b['tier1']}->{a['tier1']}, tier2 {b['tier2']}->{a['tier2']}; changed categories {diff}")
        print(f"  {s} categories after: {dict(sorted(a['cat'].items()))}")
    want = {"heldout": (113, 106), "dev": (47, 42)}
    for s, (t1, t2) in want.items():
        if (before[s]["tier1"], before[s]["tier2"], after[s]["tier1"], after[s]["tier2"]) != (t1, t2, t1, t2):
            fail(f"{s} denominators")
    expect = [("heldout", "conflicting", 7, 5), ("heldout", "multi_page", 12, 14),
              ("dev", "conflicting", 6, 3), ("dev", "multi_page", before["dev"]["cat"]["multi_page"],
                                              before["dev"]["cat"]["multi_page"] + 3)]
    for s, cat, b, a in expect:
        if (before[s]["cat"][cat], after[s]["cat"][cat]) != (b, a):
            fail(f"{s} {cat} count")
    total = before["heldout"]["cat"] + before["dev"]["cat"]
    total_after = after["heldout"]["cat"] + after["dev"]["cat"]
    print(f"  dataset-wide conflicting {total['conflicting']}->{total_after['conflicting']}, "
          f"multi_page {total['multi_page']}->{total_after['multi_page']} (manifest category_counts would change)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-log", help="also write the output to this NEW file (mode 'x')")
    args = ap.parse_args()
    buf = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, Tee(sys.stdout, buf)
    failures = []
    try:
        dev_rows = [json.loads(line) for name in ("tier1_dev.jsonl", "tier2_dev.jsonl")
                    for line in open(os.path.join(ROOT, "eval", "phase35", "results", name), encoding="utf-8")]
        assert all(split_of(r["id"]) == "dev" for r in dev_rows), "non-dev row in dev results"
        check_metadata(failures.append)
        check_validate(failures.append)
        run_probes(failures.append)
        corpus_and_dev_scan(dev_rows)
        dev_rescore(dev_rows, failures.append)
        check_tier1_context(failures.append)
        check_counts(failures.append)
        print(f"\nRESULT: {'OK' if not failures else 'FAILED'}; {len(failures)} unexpected result(s) {failures or ''}")
    finally:
        sys.stdout = real_stdout
    if args.write_log:
        with open(args.write_log, "x", encoding="utf-8") as fh:
            fh.write(buf.getvalue())
    return 1 if failures else 0


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


if __name__ == "__main__":
    sys.exit(main())
