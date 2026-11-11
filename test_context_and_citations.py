"""Standalone tests for context assembly and citations (no DB, no LLM)."""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import copy
import sys

from services.context_assembly_service import assemble_context, source_index
from services.citation_service import (
    extract_citation_refs, strip_citations, remove_invalid_refs, build_citations,
    validate_answer_citations, answer_with_citations, count_uncited_sentences)

FAILS = []
COUNT = [0]


def check(name, cond):
    COUNT[0] += 1
    print(("PASS: " if cond else "FAIL: ") + name)
    if not cond:
        FAILS.append(name)


def R(cid, doc, page, content, raw=0.5, rrf=0.03, rer=None):
    d = {"chunk": (cid, doc, page, content, raw), "rrf_score": rrf}
    if rer is not None:
        d["rerank_score"] = rer
    return d


# ---- context assembly ----
res = [R(1, "a.pdf", 3, "Alpha text here", 0.9, 0.05, 0.8),
       {"chunk": (2, "b.pdf", 7, "Beta text here"), "rrf_score": 0.02}]
orig = copy.deepcopy(res)
out = assemble_context(res)
check("input not mutated", res == orig)
s = out["sources"]
check("two sources", len(s) == 2)
check("metadata preserved", (s[0]["chunk_id"], s[0]["document_name"], s[0]["page_number"]) == (1, "a.pdf", 3))
check("score fields", s[0]["rerank_score"] == 0.8 and s[0]["rrf_score"] == 0.05 and s[0]["retrieval_score"] == 0.8)
check("4-tuple works, rrf score used", s[1]["retrieval_score"] == 0.02 and s[1]["rerank_score"] is None)
check("5-tuple raw fallback", assemble_context([{"chunk": (1, "a", 1, "x y")}])["sources"][0]["retrieval_score"] is None)
check("refs S1,S2", [x["ref"] for x in s] == ["S1", "S2"])
check("header format", out["context_text"].startswith("[S1] Document: a.pdf | Page: 3 | Chunk: 1\nAlpha text here"))
check("blocks separated by blank line", "\n\n[S2] Document: b.pdf | Page: 7 | Chunk: 2\nBeta" in out["context_text"])
check("not truncated", out["truncated"] is False and out["total_chars"] == len("Alpha text here") + len("Beta text here"))

d = assemble_context([R(1, "a", 1, "one two"), R(1, "a", 1, "other"), R(2, "a", 1, "  ONE   two\n"),
                      R(3, "a", 1, "   "), R(4, "a", 1, "three four")])
check("dup id removed", {"chunk_id": 1, "reason": "duplicate_id"} in d["dropped"])
check("dup content removed (case/ws)", {"chunk_id": 2, "reason": "duplicate_content"} in d["dropped"])
check("empty dropped", {"chunk_id": 3, "reason": "empty"} in d["dropped"])
check("refs contiguous after drops", [x["ref"] for x in d["sources"]] == ["S1", "S2"] and d["sources"][1]["chunk_id"] == 4)

m = assemble_context([R(i, "a", 1, f"content number {i}") for i in range(5)], max_chunks=2)
check("max_chunks", len(m["sources"]) == 2 and sum(x["reason"] == "max_chunks" for x in m["dropped"]) == 3)
check("max_chunks sets truncated", m["truncated"] is True)

words = " ".join(f"word{i}" for i in range(100))
b = assemble_context([R(1, "a", 1, "x" * 100), R(2, "a", 1, words)], max_chars=400)
t = b["sources"][1]
check("budget truncation flagged", t["truncated"] and b["truncated"])
check("truncated within budget", b["total_chars"] <= 400 and len(t["content"]) <= 300)
check("cut at word boundary", t["content"].split()[-1] in words.split() and words.startswith(t["content"]))
b2 = assemble_context([R(1, "a", 1, "x" * 100), R(2, "a", 1, words)], max_chars=150)
check("small remaining -> budget drop", b2["dropped"] == [{"chunk_id": 2, "reason": "budget"}] and b2["truncated"])
f = assemble_context([R(1, "a", 1, words)], max_chars=50)
check("first chunk kept when over budget", len(f["sources"]) == 1 and len(f["sources"][0]["content"]) <= 50 and f["sources"][0]["truncated"])

mp = assemble_context([R(1, "a.pdf", None, "text"), R(2, "a.pdf", 0, "text2"), R(3, None, 5, "text3")])
check("missing page -> None", mp["sources"][0]["page_number"] is None and mp["sources"][1]["page_number"] is None)
check("Page: unknown in header", "[S1] Document: a.pdf | Page: unknown | Chunk: 1" in mp["context_text"])
check("missing doc -> None / unknown", mp["sources"][2]["document_name"] is None and "[S3] Document: unknown | Page: 5 | Chunk: 3" in mp["context_text"])
for e in (None, []):
    o = assemble_context(e)
    check(f"empty input {e!r}", o["sources"] == [] and o["context_text"] == "" and o["total_chars"] == 0)
check("content unchanged except trim", assemble_context([R(1, "a", 1, "  hi <b>[S9]</b>\n")])["sources"][0]["content"] == "hi <b>[S9]</b>")
check("source_index", source_index(s)["S2"]["chunk_id"] == 2 and source_index(None) == {})

# ---- citations ----
check("extract basic", extract_citation_refs("A [S1]. B [S2][S3].") == ["S1", "S2", "S3"])
check("extract list forms", extract_citation_refs("x [S1, S3] y [S1,S2] z [S4; S5]") == ["S1", "S3", "S2", "S4", "S5"])
check("extract lowercase + unique", extract_citation_refs("[s2] [S2] [S1]") == ["S2", "S1"])
check("extract ignores others", extract_citation_refs("[DOCUMENT] [1] [note] [S]") == [])
check("extract None", extract_citation_refs(None) == [])
check("strip", strip_citations("Revenue grew [S1] . Costs fell [S2, S3].") == "Revenue grew. Costs fell.")
check("strip None", strip_citations(None) == "")
check("remove_invalid partial", remove_invalid_refs("Fact [S1, S9].", ["S1"]) == "Fact [S1].")
check("remove_invalid whole", remove_invalid_refs("Fact [S9] here.", ["S1"]) == "Fact here.")
check("remove_invalid keeps valid", remove_invalid_refs("Fact [S1][S2].", ["S1", "S2"]) == "Fact [S1][S2].")

srcs = [{"ref": "S1", "chunk_id": 10, "document_name": "report.pdf", "page_number": 12},
        {"ref": "S2", "chunk_id": 11, "document_name": "notes.txt", "page_number": None}]
bc = build_citations(["S1", "S2", "S9"], srcs)
check("build_citations", bc[0] == {"ref": "S1", "document": "report.pdf", "page": 12, "chunk_id": 10})
check("build missing page", bc[1]["page"] is None and len(bc) == 2)
check("build unknown skipped", all(c["ref"] != "S9" for c in bc))

v = validate_answer_citations("Profit rose sharply this year [S1].", srcs)
check("valid answer", v["valid"] and v["cited_refs"] == ["S1"] and v["issues"] == [])
v = validate_answer_citations("Profit rose sharply this year [S1][S7].", srcs)
check("invalid ref", not v["valid"] and v["invalid_refs"] == ["S7"] and "invalid_ref" in v["issues"])
v = validate_answer_citations("Profit rose sharply this year.", srcs)
check("no citation", "no_citation" in v["issues"] and not v["valid"] and v["uncited_sentences"] == 1)
check("no citation allowed", validate_answer_citations("Profit rose.", srcs, require_citations=False)["valid"])
for a in ("", "   ", None, 42):
    v = validate_answer_citations(a, srcs)
    check(f"empty answer {a!r}", not v["valid"] and v["issues"] == ["empty_answer"])
v = validate_answer_citations("See page 99 for details [S1].", srcs)
check("fabricated page", "unknown_page_mention" in v["issues"])
check("correct page accepted", validate_answer_citations("See page 12 for details [S1].", srcs)["valid"])
check("p. / pg variants", "unknown_page_mention" in validate_answer_citations("see p. 5 [S1]", srcs)["issues"]
      and "unknown_page_mention" not in validate_answer_citations("see pg 12 [S1]", srcs)["issues"])
check("no source pages -> any page unknown",
      "unknown_page_mention" in validate_answer_citations("page 1 [S2]", [srcs[1]])["issues"])
check("fabricated filename", "unknown_document_mention" in validate_answer_citations("From other.pdf [S1].", srcs)["issues"])
check("known filename accepted", validate_answer_citations("From Report.PDF [S1].", srcs)["valid"])
check("refusal require_citations=False",
      validate_answer_citations("I couldn't find that in the documents.", srcs, require_citations=False)["valid"])
check("refusal not counted uncited", count_uncited_sentences("I couldn't find enough about this topic in the documents.") == 0)
check("short sentence not counted", count_uncited_sentences("Yes it is.") == 0)

aw = answer_with_citations("Profit rose sharply [S1, S9]. Costs fell too [S5].", srcs)
check("answer_with_citations text", aw["text"] == "Profit rose sharply [S1]. Costs fell too.")
check("answer_with_citations citations", [c["ref"] for c in aw["citations"]] == ["S1"])
check("answer_with_citations validation", aw["validation"]["invalid_refs"] == ["S9", "S5"])
check("answer_with_citations None", answer_with_citations(None, srcs)["text"] == "")

print(f"\n{COUNT[0] - len(FAILS)}/{COUNT[0]} passed")
if FAILS:
    print("FAILED:", FAILS)
    sys.exit(1)
print("ALL CONTEXT/CITATION TESTS PASSED")
