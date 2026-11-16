"""Batch 2 / Stage 5: retrieval end to end on a disposable database.

Scratch database only (testsafe; run via run_tests.py --db rag_ingestion_test).
Fixtures are three generated PDFs with synthetic text, ingested through the
production ingest_pdf with the REAL embedding model; retrieval uses the REAL
cross-encoder. Both models come from the local cache (offline). Failure cases
use mocks. Cleanup removes only s5_* documents. No document text is printed.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import io
import os
import shutil
import sys
import tempfile
from unittest import mock

import numpy as np
import psycopg
import pymupdf

import services.bm25_service as bm25
import services.hybrid_search_service as hybrid
import services.reranker_service as reranker
import services.search_service as search
from services import retrieval_config as cfg
from services.context_assembly_service import assemble_context
from services.database import get_connection
from services.fts_service import fts_search
from services.ingestion_service import ingest_pdf

FAILURES = []
S5 = ["s5_hr_policy.pdf", "s5_api_reference.pdf", "s5_gardening.pdf"]
WORKDIR = tempfile.mkdtemp(prefix="s5_pdf_")
DOCS = {
    "s5_hr_policy.pdf": [
        "Employees receive twenty five days of paid annual leave per calendar year. "
        "Unused vacation days may be carried over until the end of March. Requests for time off "
        "must be approved by the line manager at least two weeks in advance. " * 2,
        "Parental leave is sixteen weeks at full pay for the primary caregiver. "
        "Sick leave requires a medical certificate after three consecutive days of absence. " * 2,
    ],
    "s5_api_reference.pdf": [
        "The payments endpoint returns error code ERR-7781 when the idempotency key was reused "
        "with a different request body. Clients must generate a new key and retry the request. " * 2,
        "Authentication uses JSON Web Tokens signed with RS256. Tokens expire after fifteen minutes "
        "and must be refreshed with the refresh endpoint before expiry. " * 2,
    ],
    "s5_gardening.pdf": [
        "Tomato seedlings should be planted after the last frost when the soil is warm. "
        "Water deeply twice a week and add mulch to keep moisture in the soil around the roots. " * 2,
    ],
}


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def make_pdf(name, pages):
    path = os.path.join(WORKDIR, name)
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=9)
    doc.save(path)
    doc.close()
    return path


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def cleanup():
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE 's5\\_%'")


def db_row(cid):
    with get_connection() as conn:
        return conn.execute("SELECT id, document_name, page_number, content FROM document_chunks WHERE id = %s",
                            (cid,)).fetchone()


cleanup()
bm25.clear_bm25_cache()
try:
    with get_connection() as conn:
        others = conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
    # Other synthetic fixtures may exist in the scratch DB (e.g. the Phase 2 corpus left by
    # test_retrieval_phase2); relevance assertions below are scoped to the s5_* documents.
    print(f"INFO | other rows already in the scratch table: {others}")
    for name, pages in DOCS.items():
        quiet(ingest_pdf, make_pdf(name, pages))
    with get_connection() as conn:
        n = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE 's5\\_%'").fetchone()[0]
    check("[fixture] fixtures ingested through ingest_pdf with the real embedding model", n >= 5)

    # ------------------------------------------------------------- vector
    rows = search.semantic_search("how many vacation days do staff get each year", top_k=3, document_names=S5)
    check("[vector] paraphrase query: the leave-policy chunk is the nearest", rows[0][1] == "s5_hr_policy.pdf")
    distances = [r[4] for r in rows]
    check("[vector] results ordered by ascending cosine distance", distances == sorted(distances))
    check("[vector] top_k respected", len(rows) == 3)
    check("[vector] returned metadata matches the stored chunk row", all(db_row(r[0]) == r[:4] for r in rows))
    check("[vector] blank query -> [] (no arbitrary nearest chunks)", search.semantic_search("  ", top_k=3) == [])
    check("[vector] unknown document filter -> [] without error",
          search.semantic_search("leave", top_k=3, document_names=["s5_missing.pdf"]) == [])
    check("[vector] document filter restricts results",
          {r[1] for r in search.semantic_search("leave", top_k=5, document_names=["s5_gardening.pdf"])} == {"s5_gardening.pdf"})
    with mock.patch.object(cfg, "SIMILARITY_THRESHOLD", 0.99):
        check("[vector] SIMILARITY_THRESHOLD (when configured) filters weak matches", search.semantic_search(
            "how many vacation days do staff get each year", top_k=5, document_names=S5) == [])
    with mock.patch.object(search, "generate_embeddings", return_value=np.zeros((1, 768))), \
            mock.patch.object(search, "get_connection") as conn_spy:
        try:
            search.semantic_search("anything", top_k=3); err = None
        except ValueError as e:
            err = e
    check("[vector] query-embedding dimension mismatch -> ValueError before any database call",
          err is not None and "EMBEDDING_DIM" in str(err) and not conn_spy.called)
    with mock.patch.object(search, "get_connection", side_effect=psycopg.OperationalError("connection refused")):
        try:
            search.semantic_search("leave", top_k=3); err = None
        except psycopg.OperationalError as e:
            err = e
    check("[vector] database failure propagates (not converted into an empty result)", err is not None)

    # ------------------------------------------------------------- keyword
    res = bm25.bm25_search("ERR-7781", 5)
    check("[bm25] exact identifier ranks the API chunk first", res and res[0][1] == "s5_api_reference.pdf")
    check("[bm25] scores descending and positive", [r[4] for r in res] == sorted((r[4] for r in res), reverse=True)
          and all(r[4] > 0 for r in res))
    check("[bm25] no duplicate chunks in a result", len({r[0] for r in res}) == len(res))
    check("[bm25] empty query -> []", bm25.bm25_search("", 5) == [])
    check("[bm25] punctuation-only (malformed) query -> []", bm25.bm25_search("?!...", 5) == [])
    check("[bm25] no matching term -> []", bm25.bm25_search("qwertyuiop zxcvbnm", 5) == [])
    check("[bm25] page filter given as int or str shares one cache entry and gives the same result",
          bm25.bm25_search("leave", 5, pages=[2]) == bm25.bm25_search("leave", 5, pages=["2"]))
    try:
        mixed = bm25.bm25_search("leave", 5, pages=[2, "1"]); err = None
    except TypeError as e:
        mixed, err = None, e
    check("[bm25] mixed int/str page filter no longer raises TypeError", err is None and mixed is not None)
    check("[bm25] new term absent before ingestion", bm25.bm25_search("zeppelinfoxtrot", 5) == [])
    quiet(ingest_pdf, make_pdf("s5_new_doc.pdf", ["The zeppelinfoxtrot procedure is documented here for testing "
                                                  "the keyword index refresh after a new document arrives."]))
    res = bm25.bm25_search("zeppelinfoxtrot", 5)
    check("[bm25] fingerprint invalidation: a newly ingested document is found without clearing the cache",
          res and res[0][1] == "s5_new_doc.pdf")
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name = 's5_new_doc.pdf'")
    check("[bm25] fingerprint invalidation: a deleted document disappears from results",
          bm25.bm25_search("zeppelinfoxtrot", 5) == [])
    fts = fts_search("ERR-7781 idempotency", 5)
    check("[fts] PostgreSQL full-text backend also finds the identifier chunk", fts and fts[0][1] == "s5_api_reference.pdf")
    check("[fts] empty query -> []", fts_search("", 5) == [])

    # ------------------------------------------------------------- hybrid + rerank (real cross-encoder)
    q = "what happens when an idempotency key is reused"
    out = quiet(hybrid.hybrid_search_detailed, q, 3, rerank=True, document_names=S5)
    check("[hybrid] reranked hybrid retrieval puts the API chunk first, status ok",
          out["rerank_status"] == "ok" and out["results"][0]["chunk"][1] == "s5_api_reference.pdf")
    scores = [r["rerank_score"] for r in out["results"]]
    check("[rerank] real cross-encoder scores descending, chunk metadata intact",
          scores == sorted(scores, reverse=True) and all(db_row(r["chunk"][0]) == r["chunk"][:4] for r in out["results"]))
    plain = quiet(hybrid.hybrid_search_detailed, q, 3, rerank=False, document_names=S5)
    reranker_saved = reranker._model
    reranker._model = None
    with mock.patch("sentence_transformers.CrossEncoder", side_effect=OSError("model files missing")):
        failed = quiet(hybrid.hybrid_search_detailed, q, 3, rerank=True, document_names=S5)
    reranker._model = reranker_saved
    check("[fallback] reranker initialisation failure keeps exactly the RRF results (same as rerank disabled)",
          failed["results"] == plain["results"] and failed["rerank_status"] == "failed:OSError")
    check("[fallback] the fallback results are the relevant ones, not an unrelated ranking",
          failed["results"][0]["chunk"][1] == "s5_api_reference.pdf")
    check("[hybrid] retrieval does not modify stored chunks", all(db_row(r["chunk"][0]) == r["chunk"][:4]
                                                                  for r in failed["results"]))
    empty = quiet(hybrid.hybrid_search_detailed, "qwertyuiop zxcvbnm", 3, rerank=False,
                  document_names=["s5_missing.pdf"])
    check("[hybrid] no candidates anywhere -> valid empty result", empty["results"] == [])

    # ------------------------------------------------------------- context
    full = quiet(hybrid.hybrid_search_detailed, "leave policy and token expiry", None, rerank=True, document_names=S5)
    bundle = assemble_context(full["results"])
    check(f"[context] end to end: at most min(FINAL_TOP_K={cfg.FINAL_TOP_K}, CONTEXT_MAX_CHUNKS="
          f"{cfg.CONTEXT_MAX_CHUNKS}) sources, in retrieval order, within CONTEXT_MAX_CHARS",
          0 < len(bundle["sources"]) <= min(cfg.FINAL_TOP_K, cfg.CONTEXT_MAX_CHUNKS)
          and [s["chunk_id"] for s in bundle["sources"]] == [r["chunk"][0] for r in full["results"]][: len(bundle["sources"])]
          and bundle["total_chars"] <= cfg.CONTEXT_MAX_CHARS)
    check("[context] sources carry the stored document and page",
          all((s["document_name"], s["page_number"]) == db_row(s["chunk_id"])[1:3] for s in bundle["sources"]))
finally:
    cleanup()
    bm25.clear_bm25_cache()
    shutil.rmtree(WORKDIR, ignore_errors=True)
    with get_connection() as conn:
        left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE 's5\\_%'").fetchone()[0]
    check("[cleanup] no s5_* rows remain", left == 0)

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
