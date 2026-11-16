"""Batch 2 / Stage 8 P3: rewrite-first question classification (unit; mocks only, no DB, no LLM)."""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import sys
from unittest import mock

import services.llm_service as llm
from services import rag_service as rag
from services import retrieval_config as cfg

FAILURES = []
RAW = "How long must I wait before restarting after that trip?"
REWRITTEN = "How long must I wait before restarting an Aquaflow pump after an E-41 bearing overheat trip?"
HISTORY = [{"role": "user", "content": "What does E-41 mean on the Aquaflow pumps?"},
           {"role": "assistant", "content": "E-41 is a bearing overheat fault."}]
HIT = [{"chunk": (7, "aquaflow.pdf", 3, "After an E-41 trip wait 30 minutes before restarting.", 0.5),
        "rrf_score": 0.03, "rerank_score": 5.0}]


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def run(question_type="DOCUMENT", rewrite=None, classify=None, history=HISTORY, memory_summary=""):
    """ask_question with rewrite/classify/retrieval/answer mocked; returns (result, events, mocks)."""
    events = []

    def fake_rewrite(query, history, memory_summary):
        events.append(("rewrite", query))
        return REWRITTEN if rewrite is None else rewrite(query)

    def fake_classify(text):
        events.append(("classify", text))
        return question_type if classify is None else classify(text)

    def fake_search(query, top_k):
        events.append(("retrieve", query))
        return {"results": HIT, "rerank_status": "ok"}

    answer = mock.MagicMock(return_value={"answer": "a", "sources": [], "citations": [], "status": "answered",
                                          "issues": [], "attempts": 1})
    with mock.patch.object(rag, "rewrite_query", side_effect=fake_rewrite), \
            mock.patch.object(rag, "classify_question", side_effect=fake_classify), \
            mock.patch.object(rag, "hybrid_search_detailed", side_effect=fake_search) as search, \
            mock.patch.object(rag, "generate_grounded_answer", answer), \
            contextlib.redirect_stdout(io.StringIO()):
        result = rag.ask_question(RAW, history=history, memory_summary=memory_summary)
    return result, events, {"search": search, "answer": answer}


# ---------------------------------------------------------------- A. ordering
result, events, m = run("DOCUMENT")
check("A rewrite runs before classification", [e[0] for e in events][:2] == ["rewrite", "classify"])
check("A classifier receives the rewritten standalone query, not the raw follow-up", ("classify", REWRITTEN) in events
      and ("classify", RAW) not in events)
check("A retrieval receives the same rewritten query", ("retrieve", REWRITTEN) in events
      and m["search"].call_args.kwargs == {"top_k": cfg.FINAL_TOP_K})
kw = m["answer"].call_args.kwargs
check("A the original user question still reaches answer generation", kw["question"] == RAW and kw["history"] == HISTORY)
check("A rewrite receives the original query, history and memory (inputs unchanged)", events[0] == ("rewrite", RAW))

# Through the real classify_question: the classifier prompt contains the rewritten text.
prompts = []
with mock.patch.object(rag, "rewrite_query", return_value=REWRITTEN), \
        mock.patch.object(rag, "generate_answer", side_effect=lambda p: prompts.append(p) or "DOCUMENT"), \
        mock.patch.object(rag, "hybrid_search_detailed", return_value={"results": [], "rerank_status": "skipped"}), \
        contextlib.redirect_stdout(io.StringIO()):
    rag.ask_question(RAW, history=HISTORY)
classify_prompts = [p for p in prompts if "Classify the user's question" in p]
check("A real classifier prompt is built from the rewritten query",
      len(classify_prompts) == 1 and REWRITTEN in classify_prompts[0] and RAW not in classify_prompts[0])

# No history and no memory: rewrite_query returns the query unchanged without an LLM call.
calls = []
with mock.patch.object(llm, "generate_answer", side_effect=lambda p: calls.append(p) or "x"), \
        mock.patch.object(rag, "generate_answer", side_effect=lambda p: calls.append(p) or "DOCUMENT"), \
        mock.patch.object(rag, "hybrid_search_detailed", return_value={"results": [], "rerank_status": "skipped"}), \
        contextlib.redirect_stdout(io.StringIO()):
    rag.ask_question("What is the refund window?")
check("A standalone question: no rewrite LLM call, classifier gets the raw query, one LLM call in total",
      len(calls) == 1 and "What is the refund window?" in calls[0] and "search query rewriting" not in calls[0])

# Follow-up with history: exactly one rewrite and one classification request (no extra LLM call).
calls = []
with mock.patch.object(llm, "generate_answer", side_effect=lambda p: calls.append(("rewrite", p)) or REWRITTEN), \
        mock.patch.object(rag, "generate_answer", side_effect=lambda p: calls.append(("classify", p)) or "MEMORY"), \
        contextlib.redirect_stdout(io.StringIO()):
    rag.ask_question(RAW, history=HISTORY)
kinds = [k for k, p in calls if "search query rewriting" in p or "Classify the user's question" in p]
check("A follow-up: exactly one rewrite and one classification request, rewrite first",
      kinds == ["rewrite", "classify"])

# ---------------------------------------------------------------- B. MEMORY
result, events, m = run("MEMORY", rewrite=lambda q: "What editor did the user say they prefer?")
check("B memory question stays MEMORY: retrieval skipped", not m["search"].called and "retrieve" not in [e[0] for e in events])
check("B retrieval_status is 'not_run'", result["retrieval_status"] == "not_run")
check("B MEMORY type reaches answer generation", m["answer"].call_args.kwargs["question_type"] == "MEMORY")

# ---------------------------------------------------------------- C. DOCUMENT
result, events, m = run("DOCUMENT")
check("C document follow-up retrieves with the rewritten query", m["search"].called and result["retrieval_status"] == "ok")
bundle = m["answer"].call_args.kwargs["bundle"]
check("C retrieved evidence reaches context assembly and answer generation",
      [s["chunk_id"] for s in bundle["sources"]] == [7] and bundle["sources"][0]["page_number"] == 3)
with mock.patch.object(rag, "rewrite_query", return_value=REWRITTEN), \
        mock.patch.object(rag, "generate_answer", side_effect=lambda p: "DOCUMENT" if "Classify" in p
                          else "[DOCUMENT] Wait 30 minutes before restarting [S1]."), \
        mock.patch.object(rag, "hybrid_search_detailed", return_value={"results": HIT, "rerank_status": "ok"}), \
        contextlib.redirect_stdout(io.StringIO()):
    full = rag.ask_question(RAW, history=HISTORY)
check("C end to end (real answer layer): grounded answer cites the retrieved page",
      full["status"] == "answered" and full["citations"][0]["page"] == 3 and full["retrieval_status"] == "ok")

# ---------------------------------------------------------------- D. MIXED
result, events, m = run("MIXED", memory_summary="User owns two Aquaflow AF-200 pumps.")
kw = m["answer"].call_args.kwargs
check("D MIXED still runs document retrieval", m["search"].called and result["retrieval_status"] == "ok")
check("D MIXED keeps the memory context for the answer", kw["memory_summary"] == "User owns two Aquaflow AF-200 pumps."
      and kw["question_type"] == "MIXED")

# ---------------------------------------------------------------- E. failures
def boom(_):
    raise RuntimeError("provider down")


result, events, m = run("DOCUMENT", rewrite=boom)
check("E rewrite failure: classifier and retrieval use the original question (existing contract)",
      ("classify", RAW) in events and ("retrieve", RAW) in events)
for label, bad in (("empty", ""), ("whitespace", "   ")):
    result, events, m = run("DOCUMENT", rewrite=lambda q, b=bad: b)
    check(f"E {label} rewrite falls back to the original question for classification and retrieval",
          ("classify", RAW) in events and ("retrieve", RAW) in events)
result, events, m = run(classify=boom)
check("E classification failure keeps the DOCUMENT fallback: retrieval runs, no bypass",
      m["search"].called and result["retrieval_status"] == "ok" and m["answer"].call_args.kwargs["question_type"] == "DOCUMENT")

print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
