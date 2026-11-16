"""Batch 2 / Stage 6: query -> retrieval -> context -> answer -> citation validation, end to end.

Scratch database only (testsafe; run via run_tests.py). Fixtures are two
generated PDFs with synthetic text, ingested with the production ingest_pdf
and the REAL embedding model; retrieval uses the REAL cross-encoder (both from
the local cache, offline). Only the LLM is faked: it reads the [S#] headers of
the prompt it receives and cites a passage, so no Gemini call is made. Covers
ask_question, main.run_turn (CLI path) and POST /api/v1/chat. Cleanup removes
only s6_* documents and the conversations created here. No document text is printed.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import os
import re
import secrets
import shutil
import sys
import tempfile
from unittest import mock

import pymupdf

os.environ["RAG_API_TOKEN"] = secrets.token_urlsafe(32)   # test-only token, never printed

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import services.llm_service as llm  # noqa: E402
import services.memory_cleanup_service as memory_cleanup  # noqa: E402
import services.memory_decision_service as memory_decision  # noqa: E402
import services.memory_service as memory_service  # noqa: E402
import services.reranker_service as reranker  # noqa: E402
from backend.app import app  # noqa: E402
from backend.schemas import ChatResponse  # noqa: E402
from services import rag_service as rag  # noqa: E402
from services import retrieval_config as cfg  # noqa: E402
from services.conversation_service import create_conversation  # noqa: E402
from services.database import get_connection  # noqa: E402
from services.ingestion_service import ingest_pdf  # noqa: E402

FAILURES = []
PREFIX = "s6_"
WORKDIR = tempfile.mkdtemp(prefix="s6_pdf_")
AUTH = {"Authorization": "Bearer " + os.environ["RAG_API_TOKEN"]}
DOCS = {
    "s6_leave_policy.pdf": ["Employees receive 25 days of paid annual leave per calendar year. "
                            "Unused leave may be carried over until 31 March of the next year. " * 3],
    "s6_api_limits.pdf": ["The public API allows 120 requests per minute per key. "
                          "Requests above the limit receive error code 429 and must back off. " * 3],
}
CONVERSATIONS = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def make_fake_llm(document, sentence, wrong_source=False):
    """Classify as DOCUMENT; answer by citing the passage of `document` (or another one)."""
    def fake(prompt):
        if "Classify the user's question" in prompt:
            return "DOCUMENT"
        if "<retrieved_documents>" not in prompt:
            return "NONE"                          # memory/summary prompts: nothing to report
        headers = re.findall(r"\[(S\d+)\] Document: (\S+) \|", prompt)
        refs = [ref for ref, doc in headers if (doc != document) == wrong_source]
        return f"[DOCUMENT] {sentence} [{refs[0]}]." if refs else "[DOCUMENT] " + rag.REFUSAL_MESSAGE
    return fake


@contextlib.contextmanager
def fake_llm(fake):
    with mock.patch.object(rag, "generate_answer", side_effect=fake), \
            mock.patch.object(llm, "generate_answer", side_effect=fake), \
            mock.patch.object(memory_service, "generate_answer", side_effect=fake), \
            mock.patch.object(memory_decision, "generate_answer", side_effect=fake), \
            mock.patch.object(memory_cleanup, "generate_answer", side_effect=fake), \
            contextlib.redirect_stdout(io.StringIO()):
        yield


def ask(question, fake):
    with fake_llm(fake):
        return rag.ask_question(question)


def cleanup():
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
        if CONVERSATIONS:
            conn.execute("DELETE FROM conversations WHERE id = ANY(%s::uuid[])", (CONVERSATIONS,))


def ingest_fixtures():
    for name, pages in DOCS.items():
        doc = pymupdf.open()
        for text in pages:
            doc.new_page().insert_textbox(pymupdf.Rect(36, 36, 559, 806), text, fontsize=10)
        path = os.path.join(WORKDIR, name)
        doc.save(path)
        doc.close()
        with contextlib.redirect_stdout(io.StringIO()):
            ingest_pdf(path)


def chunk_row(chunk_id):
    with get_connection() as conn:
        return conn.execute("SELECT document_name, page_number FROM document_chunks WHERE id = %s",
                            (chunk_id,)).fetchone()


LEAVE = make_fake_llm("s6_leave_policy.pdf", "Employees receive 25 days of paid annual leave")


def test_ask_question():
    res = ask("How many days of paid annual leave do employees get?", LEAVE)
    cite = (res["citations"] or [{}])[0]
    check("e2e: answered with retrieval_status 'ok' (real retrieval + reranker)",
          res["status"] == "answered" and res["retrieval_status"] == "ok")
    check("e2e: the citation points to the real chunk (document/page match the database)",
          cite.get("document") == "s6_leave_policy.pdf" and chunk_row(cite.get("chunk_id")) == ("s6_leave_policy.pdf", cite.get("page")))
    check("e2e: 'sources' holds only the cited chunk; 'retrieved' holds the whole context",
          [s["chunk_id"] for s in res["sources"]] == [cite.get("chunk_id")] and len(res["retrieved"]) >= 1)

    # A wide margin keeps the unrelated passage in the context, so there is a wrong passage to cite.
    with mock.patch.object(cfg, "RERANK_SCORE_MARGIN", 100.0):
        res = ask("How many days of paid annual leave do employees get?",
                  make_fake_llm("s6_leave_policy.pdf", "Employees receive 25 days of paid annual leave", wrong_source=True))
    check("e2e: the wrong passage was in the context (precondition)",
          any(r["document_name"] == "s6_api_limits.pdf" for r in res["retrieved"]))
    check("e2e: the same number cited to the WRONG retrieved passage -> unverified, no citations",
          res["status"] == "unverified" and res["citations"] == [] and "unsupported_number" in res["issues"])

    res = ask("What is the parking fee for visitors?",
              make_fake_llm("s6_leave_policy.pdf", "Visitor parking costs 7 dollars per day"))
    check("e2e: no-answer question with a fabricated cited number -> unverified (not answered)",
          res["status"] == "unverified" and "7 dollars" not in res["answer"])


def test_rerank_states():
    with mock.patch.object(cfg, "RERANK_ENABLED", False):
        res = ask("How many days of paid annual leave do employees get?", LEAVE)
    check("e2e: reranker disabled -> retrieval_status 'disabled', answer still grounded",
          res["retrieval_status"] == "disabled" and res["status"] == "answered")
    with mock.patch.object(reranker, "get_reranker", side_effect=RuntimeError("model missing")):
        res = ask("How many days of paid annual leave do employees get?", LEAVE)
    check("e2e: reranker failure -> retrieval_status 'failed:RuntimeError', RRF fallback still answers",
          res["retrieval_status"] == "failed:RuntimeError" and res["status"] == "answered")


def test_run_turn_and_api():
    conversation_id = create_conversation("s6 test")
    CONVERSATIONS.append(conversation_id)
    with fake_llm(LEAVE):
        out = main.run_turn(conversation_id, "How many days of paid annual leave do employees get?")
    check("run_turn (CLI path): previous keys kept, retrieval_status added",
          {"kind", "answer", "status", "sources", "citations", "issues", "memory_extraction", "summary_update"} <= set(out)
          and out["kind"] == "answer" and out["status"] == "answered" and out["retrieval_status"] == "ok")
    with get_connection() as conn:
        roles = [r[0] for r in conn.execute("SELECT role FROM messages WHERE conversation_id = %s ORDER BY id",
                                            (conversation_id,)).fetchall()]
    check("run_turn: user question and grounded answer are saved", roles == ["user", "assistant"])

    with fake_llm(LEAVE), TestClient(app, base_url="http://127.0.0.1") as client:
        r = client.post("/api/v1/chat", headers=AUTH,
                        json={"message": "How many days of paid annual leave do employees get?"})
    body = r.json()
    CONVERSATIONS.append(body.get("conversation_id"))
    check("API: POST /chat -> 200 with exactly the existing ChatResponse fields (retrieval_status not exposed)",
          r.status_code == 200 and set(body) == set(ChatResponse.model_fields))
    check("API: grounded answer and citation metadata pass through unchanged",
          body["status"] == "answered" and body["citations"][0]["document"] == "s6_leave_policy.pdf"
          and body["citations"][0]["ref"].startswith("S"))


cleanup()
try:
    ingest_fixtures()
    test_ask_question()
    test_rerank_states()
    test_run_turn_and_api()
finally:
    cleanup()
    shutil.rmtree(WORKDIR, ignore_errors=True)

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
check("cleanup: no s6_* chunks left in the scratch database", left == 0)

print(f"\n{len(FAILURES)} check(s) failed")
if FAILURES:
    print("FAILED: " + " ## ".join(FAILURES))
sys.exit(1 if FAILURES else 0)
