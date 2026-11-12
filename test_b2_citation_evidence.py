"""B2: citation correctness and claim-level evidence coverage (pure unit test: fake LLM, no DB, no network)."""
import testsafe
testsafe.require_scratch_db()

import sys

from services import retrieval_config as cfg
from services.answer_prompt import build_answer_prompt, build_history_block
from services.answer_service import UNVERIFIED_MESSAGE, generate_grounded_answer
from services.citation_service import (
    count_uncited_sentences, drop_uncited_claims, split_sentences, uncited_claim_sentences,
    validate_answer_citations,
)
from services.context_assembly_service import assemble_context

FAILURES = []
MAX_CALLS = 1 + cfg.ANSWER_MAX_RETRIES


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def R(cid, doc, page, content):
    return {"chunk": (cid, doc, page, content, 0.5), "rrf_score": 0.03, "rerank_score": 1.0}


BUNDLE = assemble_context([
    R(11, "policy.pdf", 3, "Refunds are accepted within 30 days of purchase with a receipt."),
    R(22, "handbook.pdf", 7, "Employees receive 20 vacation days per year."),
])
SRC = BUNDLE["sources"]


class Fake:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


def ask(replies, qtype="DOCUMENT", bundle=BUNDLE, history=None):
    fake = Fake(replies)
    out = generate_grounded_answer("q?", bundle, qtype, fake, history)
    return out, fake


# ---------------------------------------------------------------- valid citations
out, f = ask(["[DOCUMENT] Refunds are accepted within 30 days [S1]."])
check("valid: one cited sentence accepted on the first attempt",
      out["status"] == "answered" and f.prompts.__len__() == 1 and [c["ref"] for c in out["citations"]] == ["S1"])
check("valid: structured citation carries the metadata document/page/chunk (never model text)",
      out["citations"] == [{"ref": "S1", "document": "policy.pdf", "page": 3, "chunk_id": 11}])
out, f = ask(["[DOCUMENT] Refunds take 30 days. [S1] Staff get 20 vacation days per year. [S2]"])
check("valid: marker written after the full stop belongs to that sentence (not counted as uncited)",
      out["status"] == "answered" and len(f.prompts) == 1 and [c["ref"] for c in out["citations"]] == ["S1", "S2"])
check("split_sentences moves a leading marker back to the previous sentence",
      split_sentences("Fact one is here. [S1] Fact two is here [S2].") == ["Fact one is here. [S1]", "Fact two is here [S2]."])

# ---------------------------------------------------------------- multiple sources
out, f = ask(["[DOCUMENT] Refunds take 30 days and staff get 20 days off [S1][S2]."])
check("multiple refs on one sentence: both citations kept, documents distinct",
      out["status"] == "answered" and {c["document"] for c in out["citations"]} == {"policy.pdf", "handbook.pdf"})
out, f = ask(["[DOCUMENT] Refunds take 30 days [S1, S2]."])
check("comma-separated marker [S1, S2] parsed as two citations", [c["ref"] for c in out["citations"]] == ["S1", "S2"])

# ---------------------------------------------------------------- invalid / fabricated refs
for label, reply in (("S9 (not retrieved)", "[DOCUMENT] Refunds are paid in cash at the desk [S9]."),
                     ("S0", "[DOCUMENT] Refunds are paid in cash at the desk [S0]."),
                     ("S3 (one past the last)", "[DOCUMENT] Refunds are paid in cash at the desk [S3].")):
    out, f = ask([reply])
    check(f"fabricated ref {label}: never emitted, answer unverified after bounded retries",
          out["status"] == "unverified" and out["citations"] == [] and len(f.prompts) == MAX_CALLS
          and "invalid_ref" in f.prompts[-1])
check("validate: invalid ref reported", validate_answer_citations("X is true here [S7].", SRC)["invalid_refs"] == ["S7"])

# ---------------------------------------------------------------- wrong page / document mentions
v = validate_answer_citations("The handbook on page 3 grants 20 days [S2].", SRC)
check("wrong page: page 3 exists only for S1 (policy.pdf), sentence cites S2 (handbook p.7) -> unknown_page_mention",
      "unknown_page_mention" in v["issues"])
check("right page for the cited source accepted",
      validate_answer_citations("The handbook on page 7 grants 20 days [S2].", SRC)["valid"])
check("uncited sentence may mention any retrieved page (no pairing possible)",
      "unknown_page_mention" not in validate_answer_citations("See page 3 for refunds. Refunds take 30 days [S1].", SRC)["issues"])
v = validate_answer_citations("As stated in cy.pdf, refunds take 30 days [S1].", SRC)
check("wrong document: 'cy.pdf' is not accepted just because 'policy.pdf' ends with it", "unknown_document_mention" in v["issues"])
check("exact document name accepted (case-insensitive)",
      validate_answer_citations("As stated in Policy.PDF, refunds take 30 days [S1].", SRC)["valid"])

# ---------------------------------------------------------------- missing citations / claim coverage
v = validate_answer_citations("Refunds take 30 days [S1]. Store credit is offered for every online order.", SRC)
check("uncited claim next to a cited one -> uncited_claim (not valid)", "uncited_claim" in v["issues"] and not v["valid"])
check("require_citations=False does not report uncited_claim",
      "uncited_claim" not in validate_answer_citations("Store credit is offered for every online order.", SRC, False)["issues"])
check("abstention sentence ('is not mentioned') is not an uncited claim",
      count_uncited_sentences("Refunds take 30 days [S1]. A restocking fee is not mentioned in the documents.") == 0)
check("list intro ending with ':' is not an uncited claim",
      uncited_claim_sentences("The documents state the following points:\n- Refunds take 30 days [S1]") == [])
check("meta statement that the sources disagree is not an uncited claim",
      uncited_claim_sentences("The two passages disagree about the refund window. One says 30 days [S1].") == [])
check("short sentences (< 5 words) are ignored", count_uncited_sentences("Yes. Refunds take 30 days [S1].") == 0)

out, f = ask(["[DOCUMENT] Refunds take 30 days [S1]. Store credit is offered for every online order.",
              "[DOCUMENT] Refunds take 30 days [S1]."])
check("uncited claim triggers one regeneration with feedback naming uncited_claim; corrected answer accepted",
      out["status"] == "answered" and len(f.prompts) == 2 and "uncited_claim" in f.prompts[1]
      and "Store credit" not in out["answer"])

# ---------------------------------------------------------------- unsupported claims with valid citation syntax
# Deterministic code cannot prove semantic support: this is ACCEPTED and documented as a limitation.
out, f = ask(["[DOCUMENT] Refunds are accepted within 90 days without a receipt [S1]."])
check("LIMITATION pinned: a wrong claim with a syntactically valid citation is accepted (no semantic check)",
      out["status"] == "answered" and [c["ref"] for c in out["citations"]] == ["S1"])

# ---------------------------------------------------------------- citation repair and fallback
out, f = ask(["[DOCUMENT] Refunds take 30 days [S1]. Refunds are paid in cash at any branch [S9]."])
check("repair: fabricated-ref sentence is dropped, valid citation preserved",
      out["status"] == "answered" and "cash" not in out["answer"] and "[S1]" in out["answer"]
      and [c["ref"] for c in out["citations"]] == ["S1"]
      and "dropped_uncited_sentences:1" in out["issues"] and any(i.startswith("repaired:") for i in out["issues"]))
out, f = ask(["[DOCUMENT] Refunds take 30 days [S1]. Store credit is offered for every online order."])
check("repair: persistent uncited claim is dropped after the bounded retries; cited part kept",
      out["status"] == "answered" and len(f.prompts) == MAX_CALLS and "Store credit" not in out["answer"]
      and out["answer"].startswith("Refunds take 30 days [S1]"))
out, f = ask(["[DOCUMENT] A. [S1][S9]"])
check("repair: marker group with one valid and one invalid ref keeps the valid ref (existing behaviour)",
      [c["ref"] for c in out["citations"]] == ["S1"] and "S9" not in out["answer"])
out, f = ask(["[DOCUMENT] Store credit is offered for every online order [S9]."])
check("repair: nothing valid left -> unverified fallback, no citations",
      out["status"] == "unverified" and out["answer"] == UNVERIFIED_MESSAGE and out["citations"] == [])
check("drop_uncited_claims keeps cited and abstention sentences only",
      drop_uncited_claims("Fact one is true [S1]. Invented fact sits here alone. Detail is not mentioned in the documents.")
      == "Fact one is true [S1]. Detail is not mentioned in the documents.")

# ---------------------------------------------------------------- tag must not bypass grounding (F1)
out, f = ask(["[MEMORY] Refunds are accepted within 90 days and no receipt is needed."])
check("DOCUMENT question with sources: a [MEMORY]-tagged uncited answer is NOT accepted",
      out["status"] == "unverified" and out["citations"] == [] and len(f.prompts) == MAX_CALLS
      and "no_citation" in f.prompts[-1])
out, f = ask(["[MEMORY] You told me earlier that you prefer short answers."], qtype="MEMORY")
check("MEMORY question: [MEMORY] answer without citations still accepted",
      out["status"] == "answered" and len(f.prompts) == 1)
out, f = ask(["[MEMORY] I cannot find that detail in the provided documents."])
check("DOCUMENT question: a pure abstention tagged [MEMORY] is still accepted as abstained",
      out["status"] == "abstained" and len(f.prompts) == 1)

# ---------------------------------------------------------------- previous-turn citation leakage
history = [{"role": "user", "content": "What about refunds?"},
           {"role": "assistant", "content": "Earlier answer about refunds [S3] and fees [S4]."}]
hb = build_history_block(history)
check("history: earlier assistant citations are stripped from the prompt history", "[S3]" not in hb and "[S4]" not in hb)
prompt = build_answer_prompt("q?", SRC, BUNDLE["context_text"], history)
check("prompt lists only the CURRENT refs as citable", "Use ONLY these references: S1, S2." in prompt)
out, f = ask(["[DOCUMENT] As before, refunds take 30 days [S3]."], history=history)
check("an old-turn ref ([S3]) that does not exist now is rejected (unverified, not emitted)",
      out["status"] == "unverified" and out["citations"] == [])

# ---------------------------------------------------------------- conflicting evidence
conf = assemble_context([R(1, "a.pdf", 1, "The fee is 5 dollars."), R(2, "b.pdf", 4, "The fee is 7 dollars.")])
out, f = ask(["[DOCUMENT] The two passages disagree about the fee. One says 5 dollars [S1]. The other says 7 dollars [S2]."],
             bundle=conf)
check("conflict: each version cited, meta sentence allowed, status conflict",
      out["status"] == "conflict" and [c["ref"] for c in out["citations"]] == ["S1", "S2"] and len(f.prompts) == 1)

print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
