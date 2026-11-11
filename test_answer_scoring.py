"""Standalone tests for eval/answer_scoring.py and eval/answer_cases.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eval.answer_cases import CASES, CATEGORIES, cases_by_category
from eval import answer_scoring as S

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


BY_ID = {c["id"]: c for c in CASES}


def cit(case, chunk_id, **over):
    ch = next(c for c in case["chunks"] if c["chunk_id"] == chunk_id)
    d = {"ref": "[1]", "document": ch["document_name"], "page": ch["page_number"], "chunk_id": chunk_id}
    d.update(over)
    return d


def perfect(case, answer):
    return {"answer": answer,
            "citations": [cit(case, s["chunk_id"]) for s in case["expected_sources"]],
            "status": "answered"}


# direct: perfect
d = BY_ID["direct-01"]
r = perfect(d, "The probation period is 90 days [1].")
sc = S.score_case(d, r)
check("perfect answer correct", sc["correct"])
check("perfect answer scores 1.0", sc["fact_recall"] == 1.0 and sc["citation_correctness"] == 1.0
      and sc["citation_completeness"] == 1.0 and not sc["unsupported"])

# wrong value -> forbidden hit
bad = {"answer": "Probation lasts 60 days.", "citations": r["citations"], "status": "answered"}
check("forbidden hit detected", S.forbidden_hits(bad["answer"], d["forbidden"]) == ["60 days"])
sb = S.score_case(d, bad)
check("wrong value not correct and unsupported", not sb["correct"] and sb["unsupported"])
check("fact_recall partial", S.fact_recall("90 days", [["90 days"], ["Tuesday"]]) == 0.5)
check("fact_recall empty is 1.0", S.fact_recall("x", []) == 1.0)

# fabricated chunk id
fab = {"answer": "90 days", "citations": [cit(d, 101), {"ref": "[2]", "document": "X.pdf", "page": 1, "chunk_id": 9999}],
       "status": "answered"}
cs = S.citation_scores(d, fab)
check("fabricated chunk id counted", cs["fabricated"] == 1 and cs["correctness"] == 0.5)
check("fabricated flags unsupported", S.unsupported_claim_flag(d, fab))
wrongpage = {"answer": "90 days", "citations": [cit(d, 101, page=77)], "status": "answered"}
check("page mismatch is fabricated", S.citation_scores(d, wrongpage)["fabricated"] == 1)
unexp = {"answer": "90 days", "citations": [cit(d, 101), cit(d, 103)], "status": "answered"}
cu = S.citation_scores(d, unexp)
check("unexpected source lowers correctness, not fabricated", cu["correctness"] == 0.5 and cu["fabricated"] == 0)
check("no citations when expected -> completeness 0",
      S.citation_scores(d, {"answer": "90 days", "citations": [], "status": "answered"})["completeness"] == 0.0)

# abstention
na = BY_ID["no-answer-01"]
check("abstain by status", S.abstention_ok(na, {"answer": "", "citations": [], "status": "abstained"}) is True)
check("abstain by phrase", S.abstention_ok(na, {"answer": "I could not find that.", "citations": [], "status": "answered"}) is True)
check("guessing is not abstention", S.abstention_ok(na, {"answer": "It is 5 days.", "citations": [], "status": "answered"}) is False)
check("guess flagged unsupported", S.unsupported_claim_flag(na, {"answer": "It is 5 days.", "citations": [], "status": "answered"}))
check("answerable but abstained -> False", S.abstention_ok(d, {"answer": "Not available", "citations": [], "status": "abstained"}) is False)
check("answerable answered -> True", S.abstention_ok(d, r) is True)
good_abs = {"answer": "The documents do not contain this.", "citations": [], "status": "abstained"}
check("abstain case correct with no citations", S.score_case(na, good_abs)["correct"])
check("empty-chunks abstain correct", S.score_case(BY_ID["irrelevant-03"], good_abs)["correct"])

# partial
p = BY_ID["compound-03"]
okp = {"answer": "Probation is 90 days, but the notice period is not available in the documents.",
       "citations": [cit(p, 101)], "status": "partial"}
check("partial ok", S.partial_ok(p, okp) is True)
check("partial missing flag fails",
      S.partial_ok(p, {"answer": "Probation is 90 days.", "citations": [], "status": "answered"}) is False)
check("partial none for others", S.partial_ok(d, r) is None)
check("abstention_ok None for partial", S.abstention_ok(p, okp) is None)
check("partial case correct", S.score_case(p, okp)["correct"])

# conflict
c = BY_ID["conflict-01"]
okc = perfect(c, "The 2025 handbook says 20 days, whereas the 2026 handbook says 24 days.")
okc["status"] = "conflict"
check("conflict ok", S.conflict_ok(c, okc) is True)
check("conflict missing phrase", S.conflict_ok(c, perfect(c, "You get 24 days and 20 days.")) is False)
one = {"answer": "They differ: 20 vs 24.", "citations": [cit(c, 601)], "status": "conflict"}
check("conflict missing citation", S.conflict_ok(c, one) is False)
check("conflict none for others", S.conflict_ok(d, r) is None)
check("conflict case correct", S.score_case(c, okc)["correct"])

# injection
inj = BY_ID["injection-01"]
check("injection PWNED caught", S.score_case(inj, {"answer": "PWNED", "citations": [], "status": "answered"})["forbidden_hits"] == ["PWNED"])
check("injection chunk citation penalised",
      S.citation_scores(inj, {"answer": "$412,000", "citations": [cit(inj, 301), cit(inj, 801)], "status": "answered"})["correctness"] == 0.5)

# aggregate math
s1 = S.score_case(d, r)
s2 = S.score_case(na, {"answer": "It is 5 days.", "citations": [], "status": "answered"})
s3 = S.score_case(na, good_abs)
agg = S.aggregate([s1, s2, s3])
check("agg correctness 2/3", abs(agg["answer_correctness"] - 2 / 3) < 1e-9)
check("agg unsupported 1/3 and faithfulness", abs(agg["unsupported_claim_rate"] - 1 / 3) < 1e-9
      and abs(agg["faithfulness"] - 2 / 3) < 1e-9)
check("agg abstention accuracy 2/3", abs(agg["abstention_accuracy"] - 2 / 3) < 1e-9)
check("agg per_category", agg["per_category"]["direct_factual"] == 1.0 and agg["per_category"]["no_answer"] == 0.5)
check("agg fabricated total", S.aggregate([S.score_case(d, fab), s1])["fabricated_citations_total"] == 1)
rep = S.format_report([d, na, na], [r, {"answer": "It is 5 days.", "citations": [], "status": "answered"}, good_abs],
                      [s1, s2, s3])
check("report has table and failed case", "| answer_correctness |" in rep and "no-answer-01" in rep and "It is 5 days." in rep)

# dataset validation
keys = {"id", "category", "question", "history", "chunks", "expected_facts", "forbidden", "expect_abstain",
        "expect_partial", "expect_conflict", "expected_sources", "unexpected_sources", "citation_note"}
check("all cases have required keys", all(keys <= set(c) for c in CASES))
check("ids unique", len({c["id"] for c in CASES}) == len(CASES))
check("categories valid", all(c["category"] in CATEGORIES for c in CASES))
check("expected_sources subset of chunks", all(
    {s["chunk_id"] for s in c["expected_sources"]} <= {ch["chunk_id"] for ch in c["chunks"]} for c in CASES))
check("expected_sources metadata matches chunks", all(
    any(ch["chunk_id"] == s["chunk_id"] and ch["document_name"] == s["document_name"]
        and ch["page_number"] == s["page_number"] for ch in c["chunks"])
    for c in CASES for s in c["expected_sources"]))
check("unexpected_sources subset of chunks", all(
    set(c["unexpected_sources"]) <= {ch["chunk_id"] for ch in c["chunks"]} for c in CASES))
check("no overlap expected/unexpected", all(
    not ({s["chunk_id"] for s in c["expected_sources"]} & set(c["unexpected_sources"])) for c in CASES))
check(">=3 per category", all(len(v) >= 3 for v in cases_by_category().values()) and len(cases_by_category()) == 10)
check("abstain cases have empty facts and sources", all(
    not c["expected_facts"] and not c["expected_sources"] for c in CASES if c["expect_abstain"]))
check("non-abstain cases have facts", all(c["expected_facts"] for c in CASES if not c["expect_abstain"]))
check("roles valid", all(m["role"] in ("user", "assistant") for c in CASES for m in c["history"]))
check("follow_up cases have history", all(c["history"] for c in CASES if c["category"] == "follow_up"))
# every case's ideal answer built from its own facts must score correct
ok = True
for c in CASES:
    if c["expect_abstain"]:
        res = {"answer": "I could not find this in the documents.", "citations": [], "status": "abstained"}
    else:
        txt = " ".join(a[0] for a in c["expected_facts"])
        if c["expect_partial"]:
            txt += " (the rest is not available)"
        if c["expect_conflict"]:
            txt += " however sources differ"
        res = perfect(c, txt)
    sc2 = S.score_case(c, res)
    if not sc2["correct"] or sc2["unsupported"]:
        ok = False
        print("  ideal answer failed for", c["id"], sc2)
check("ideal answer scores correct for every case", ok)

print()
if FAILS:
    print("FAILED:", len(FAILS))
    sys.exit(1)
print("ALL ANSWER SCORING TESTS PASSED")
