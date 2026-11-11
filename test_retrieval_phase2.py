"""
Phase 2 retrieval regression suite. Uses the scratch database named by
DATABASE_URL (run it through run_tests.py); it never reads or writes rag_db.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import os
import subprocess
import sys
import tempfile
import time
from unittest import mock

from eval import harness

harness.use_current_scratch_database()

import pymupdf  # noqa: E402

from eval.corpus import DOCS, QUERIES, make_distractors  # noqa: E402
from services import retrieval_config as cfg  # noqa: E402
from services.bm25_service import bm25_search, clear_bm25_cache, tokenize  # noqa: E402
from services.chunker import chunk_page, chunk_text_sentences  # noqa: E402
from services.database import get_connection  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402
from services.fts_service import fts_search  # noqa: E402
from services.hybrid_search_service import hybrid_search, hybrid_search_detailed  # noqa: E402
from services.reranker_service import rerank_results  # noqa: E402
from services.rrf_service import reciprocal_rank_fusion  # noqa: E402
from services.search_service import semantic_search  # noqa: E402

harness.assert_scratch()
failures = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "|", name, ("" if cond else f"  <-- {detail}"))
    if not cond:
        failures.append(name)


def chunk_fn(text):
    return chunk_page(text, 100, 20, "words")


def load(docs):
    clear_bm25_cache()
    return harness.load_corpus(docs, chunk_fn, generate_embeddings)


def gold_hit(results, doc, span):
    return any(harness.covers(r["chunk"], (doc, span)) for r in results)


def chunk_hit(chunks, doc, span):
    return any(harness.covers(c, (doc, span)) for c in chunks)


# ---------------------------------------------------------------- fixtures --
load(DOCS)
Q = {q[0]: q for q in QUERIES}


def gold_of(query):
    return Q[query][2][0]


# 1. semantic search -------------------------------------------------------
q = "How many vacation days do staff get each year?"
rows = semantic_search(q, top_k=3)
check("1 semantic: paraphrase finds the leave policy in vector top 3",
      chunk_hit(rows, *gold_of(q)), [r[3][:40] for r in rows])

# 2. exact keyword ---------------------------------------------------------
rows = bm25_search("ERR-4096", top_k=3)
check("2 keyword: BM25 ranks the ERR-4096 chunk first",
      rows and "ERR-4096" in rows[0][3], rows[:1])
rows = fts_search("PHD26052", top_k=3)
check("2 keyword: PostgreSQL FTS also finds an exact identifier",
      rows and "PHD26052" in rows[0][3], rows[:1])

# 3. technical terms / abbreviations ----------------------------------------
for term, doc in (("HNSW", "database_operations_guide.pdf"),
                  ("JWT", "api_reference_v2.pdf"),
                  ("mTLS", "network_security_handbook.pdf"),
                  ("MTTR", "incident_postmortems.pdf")):
    rows = bm25_search(term, top_k=3)
    check(f"3 abbreviation {term}: BM25 top result is from {doc}",
          rows and rows[0][1] == doc, rows[:1])

# 4. hybrid retrieval beats a single method on its blind spot ----------------
q = "POL-HR-031"   # vector search misses exact identifiers in a larger corpus
out = hybrid_search_detailed(q, 5, rerank=False)
check("4 hybrid: exact identifier found", gold_hit(out["results"], *gold_of(q)))
q = "What happens to old row versions after an update in the database?"
# Known RRF limitation (documented in the report): a strong single-retriever hit can fall out of the
# final top 5 when keyword noise outranks it. It must stay inside the reranker candidate pool (top 10).
pool = hybrid_search_detailed(q, cfg.RRF_TOP_K, rerank=False)["results"]
check("4 hybrid: paraphrase hit stays inside the RRF candidate pool (top 10)", gold_hit(pool, *gold_of(q)))
out = hybrid_search_detailed("probation notice period", 5)
check("4 hybrid: timings and counts reported",
      {"vector", "keyword", "fusion", "rerank", "total"} <= set(out["timings_ms"])
      and out["counts"]["vector"] > 0 and out["counts"]["keyword"] > 0, out["timings_ms"])

# 5. RRF ranking -------------------------------------------------------------
A = [(1, "d", 1, "alpha"), (2, "d", 1, "beta"), (3, "d", 1, "gamma")]
B = [(2, "d", 1, "beta"), (4, "d", 1, "delta"), (1, "d", 1, "alpha")]
fused = reciprocal_rank_fusion([A, B], k=60, top_k=10)
ids = [f["chunk"][0] for f in fused]
expect = {1: 1 / 61 + 1 / 63, 2: 1 / 62 + 1 / 61, 3: 1 / 63, 4: 1 / 62}
check("5 RRF: scores follow 1/(k+rank) summed over lists",
      all(abs(f["rrf_score"] - expect[f["chunk"][0]]) < 1e-12 for f in fused))
check("5 RRF: items in both lists outrank single-list items", ids[:2] == [2, 1] and ids[2:] == [4, 3], ids)
check("5 RRF: k parameter changes scores",
      reciprocal_rank_fusion([A], k=10, top_k=1)[0]["rrf_score"] == 1 / 11)
check("5 RRF: weights respected",
      reciprocal_rank_fusion([A, B], weights=[0.0, 1.0], top_k=1)[0]["chunk"][0] == 2)
check("5 RRF: deterministic on ties",
      [f["chunk"][0] for f in reciprocal_rank_fusion([[(7, "d", 1, "x")], [(8, "d", 1, "y")]])] == [7, 8])
check("5 RRF: top_k respected", len(reciprocal_rank_fusion([A, B], top_k=2)) == 2)

# 6. reranker ordering -------------------------------------------------------
cands = [{"chunk": (i, "d", 1, f"text {i}"), "rrf_score": 0.1} for i in range(4)]
with mock.patch("services.reranker_service.get_reranker") as fake:
    fake.return_value.predict.return_value = [0.1, 2.5, -1.0, 1.0]
    ranked = rerank_results("q", cands, top_k=3)
check("6 reranker: sorted by score, highest first",
      [r["chunk"][0] for r in ranked] == [1, 3, 0] and ranked[0]["rerank_score"] == 2.5)
check("6 reranker: rrf score and chunk preserved", ranked[0]["rrf_score"] == 0.1 and ranked[0]["chunk"][3] == "text 1")
check("6 reranker: empty input -> []", rerank_results("q", []) == [])
real = hybrid_search_detailed("How long does a JWT access token live?", 5, rerank=True)["results"]
check("6 reranker (real model): scores descending",
      [r["rerank_score"] for r in real] == sorted((r["rerank_score"] for r in real), reverse=True))
check("6 reranker (real model): relevant chunk first",
      harness.covers(real[0]["chunk"], ("api_reference_v2.pdf", "expire after 3600 seconds")), real[0]["chunk"][3][:60])

# 7. duplicate chunk removal --------------------------------------------------
dup_a = (1, "d", 1, "Same   text here")
dup_b = (2, "e", 5, "same text   HERE")
fused = reciprocal_rank_fusion([[dup_a], [dup_b], [dup_a]], top_k=5)
check("7 duplicates: same id and same text collapse to one result", len(fused) == 1 and fused[0]["chunk"][0] == 1)
check("7 duplicates: identical text can be kept when dedupe disabled",
      len(reciprocal_rank_fusion([[dup_a], [dup_b]], top_k=5, dedupe_content=False)) == 2)
pdf_dir = tempfile.mkdtemp(prefix="phase2_pdf_")
pdf_path = os.path.join(pdf_dir, "dup_test.pdf")
paragraph = ("This repeated disclaimer paragraph appears on every page and must be stored only once "
             "by ingestion because it carries no new information for retrieval at all today. ") * 2
doc = pymupdf.open()
for n in (1, 2, 3, 1):   # page 4 is an exact copy of page 1
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 560, 780),
                        paragraph + f"\n\nUnique page {n} content mentions the topic marker zebra{n} with "
                                    "enough extra words to pass the minimum length filter easily.",
                        fontsize=9)
doc.save(pdf_path)
doc.close()
from services.ingestion_service import ingest_pdf  # noqa: E402
with get_connection() as conn:
    conn.execute("TRUNCATE document_chunks RESTART IDENTITY")
clear_bm25_cache()
ingest_pdf(pdf_path)
with get_connection() as conn:
    stored = conn.execute("SELECT page_number, content FROM document_chunks ORDER BY id").fetchall()
texts = [" ".join(c.split()).lower() for _, c in stored]
check("7 duplicates: ingestion stores no identical chunk text", len(texts) == len(set(texts)), len(texts))
check("7 duplicates: a page that repeats an earlier page exactly is stored once",
      sorted(p for p, _ in stored) == [1, 2, 3], [p for p, _ in stored])

# 10. page metadata preserved (PDF ingest -> every retrieval stage) ------------
pages_found = {}
for n in range(1, 4):
    res = hybrid_search_detailed(f"zebra{n}", 3, document_names=["dup_test.pdf"])["results"]
    pages_found[n] = res[0]["chunk"][2] if res else None
check("10 page metadata: ingested page numbers survive hybrid retrieval",
      all(pages_found[n] == n for n in pages_found), pages_found)
check("10 page metadata: document name preserved",
      all(r["chunk"][1] == "dup_test.pdf" for r in hybrid_search_detailed("zebra2", 3)["results"]))

# 8/9. metadata filtering and document isolation -----------------------------
load(DOCS)
target = ["hr_policy_manual.pdf"]
for label, fn in (
    ("vector", lambda: semantic_search("policy", 10, document_names=target)),
    ("BM25", lambda: bm25_search("policy leave notice", 10, document_names=target)),
    ("FTS", lambda: fts_search("policy leave notice", 10, document_names=target)),
    ("hybrid", lambda: [r["chunk"] for r in hybrid_search_detailed("policy leave", 10, document_names=target)["results"]]),
):
    rows = fn()
    check(f"8 metadata filter ({label}): only the requested document", rows and all(r[1] == target[0] for r in rows), {r[1] for r in rows})
for label, fn in (
    ("vector", lambda: semantic_search("limit", 10, pages=[2])),
    ("BM25", lambda: bm25_search("limit the", 10, pages=[2])),
    ("FTS", lambda: fts_search("limit the", 10, pages=[2])),
):
    rows = fn()
    check(f"8 page filter ({label}): only page 2", rows and all(r[2] == 2 for r in rows), {r[2] for r in rows})
rows = bm25_search("policy", 10, document_names=["hr_policy_manual.pdf", "api_reference_v2.pdf"])
check("8 filter accepts several documents", {r[1] for r in rows} <= {"hr_policy_manual.pdf", "api_reference_v2.pdf"} and len(rows) > 0)

# 9. isolation: scope caches must not leak between documents, and a query for
# another document's fact must not surface it.
a = bm25_search("TLS certificate", 5, document_names=["network_security_handbook.pdf"])
b = bm25_search("TLS certificate", 5, document_names=["incident_postmortems.pdf"])
unscoped = bm25_search("TLS certificate", 5)
check("9 isolation: cached BM25 indexes are scoped per document set",
      {r[1] for r in a} == {"network_security_handbook.pdf"} and {r[1] for r in b} == {"incident_postmortems.pdf"}
      and len({r[1] for r in unscoped}) > 1)
res = hybrid_search_detailed("What is the phone number of the admissions office?", 5,
                             document_names=["hr_policy_manual.pdf"])["results"]
check("9 isolation: fact from another document is not returned under a filter",
      not gold_hit(res, "candidate_list_2026.pdf", "0135-2224433"))
with get_connection() as conn:
    before = conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
hybrid_search_detailed("anything", 5)
with get_connection() as conn:
    after = conn.execute("SELECT count(*) FROM document_chunks").fetchone()[0]
check("9 isolation: retrieval never modifies stored chunks", before == after)

# new chunks become visible to the cached BM25 index
with get_connection() as conn:
    conn.execute("INSERT INTO document_chunks (document_name, page_number, chunk_id, content, embedding) "
                 "VALUES ('late.pdf', 1, 1, 'quokkaword is a brand new term', %s)",
                 (generate_embeddings(["quokkaword is a brand new term"])[0].tolist(),))
check("9 cache: BM25 index refreshes after the corpus changes",
      bm25_search("quokkaword", 3) and bm25_search("quokkaword", 3)[0][1] == "late.pdf")
with get_connection() as conn:
    conn.execute("DELETE FROM document_chunks WHERE document_name = 'late.pdf'")

# 11. empty results ----------------------------------------------------------
check("11 empty: unknown document filter -> []",
      semantic_search("x", 5, document_names=["nope.pdf"]) == []
      and bm25_search("policy", 5, document_names=["nope.pdf"]) == []
      and fts_search("policy", 5, document_names=["nope.pdf"]) == []
      and hybrid_search("policy", 5, document_names=["nope.pdf"]) == [])
check("11 empty: query with no matching term -> BM25 []", bm25_search("qwertyuiop zxcvbnm", 5) == [])
check("11 empty: similarity threshold can return nothing",
      semantic_search("Give me a recipe for lasagna.", 5, similarity_threshold=0.95) == [])
with get_connection() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS _hold AS SELECT * FROM document_chunks WITH NO DATA")
    conn.execute("INSERT INTO _hold SELECT * FROM document_chunks")
    conn.execute("TRUNCATE document_chunks")
clear_bm25_cache()
check("11 empty: completely empty corpus -> [] from every stage",
      semantic_search("x", 5) == [] and bm25_search("x", 5) == [] and hybrid_search("x", 5) == [])
with get_connection() as conn:
    conn.execute("INSERT INTO document_chunks SELECT * FROM _hold")
    conn.execute("DROP TABLE _hold")
clear_bm25_cache()

# 12. very short queries -----------------------------------------------------
for short in ("a", "?", "", "  ", "ID", "JWT", "é"):
    try:
        res = hybrid_search(short, 3)
        ok = isinstance(res, list)
        detail = ""
    except Exception as error:   # pragma: no cover
        ok, detail = False, repr(error)
    check(f"12 short query {short!r}: no crash", ok, detail)
res = hybrid_search("JWT", 3)
check("12 short query 'JWT': relevant chunk in top 3", gold_hit(res, "api_reference_v2.pdf", "JSON Web Tokens"))
check("12 tokenizer keeps short queries non-empty with stopword removal", tokenize("what is the", True) == ["what", "is", "the"])

# 13. compound questions ----------------------------------------------------
multi = [q for q in QUERIES if q[1] == "multi"]
covered, total = 0, 0
for query, _, gold, _ in multi:
    res = hybrid_search_detailed(query, 5)["results"]
    for g in gold:
        total += 1
        covered += gold_hit(res, *g)
check(f"13 compound: all facts of multi-part questions retrieved ({covered}/{total})", covered == total)

# 14. large documents ---------------------------------------------------------
big = make_distractors(1, pages_per_doc=300, seed=11)["filler_000.pdf"]
big[216] = big[216] + " The calibration constant for the Zephyr9 spectrometer is 4.2713 volts."
docs_large = {**DOCS, **make_distractors(60, seed=3), "big_document.pdf": big}
t0 = time.time()
n_chunks = load(docs_large)
res = hybrid_search_detailed("Zephyr9 spectrometer calibration constant", 5)
lat = res["timings_ms"]["total"]
check(f"14 large: needle on page 217 of a 300-page document found ({n_chunks} chunks)",
      any(r["chunk"][1] == "big_document.pdf" and r["chunk"][2] == 217 for r in res["results"]),
      [(r["chunk"][1], r["chunk"][2]) for r in res["results"]])
check(f"14 large: retrieval latency {lat:.0f} ms < 5000 ms", lat < 5000)
res2 = hybrid_search_detailed("Zephyr9 spectrometer calibration constant", 5,
                              document_names=["big_document.pdf"], pages=[217])
check("14 large: document+page filter isolates the page",
      res2["results"] and all(r["chunk"][2] == 217 for r in res2["results"]))
load(DOCS)

# 15. existing RAG answer generation stays compatible ------------------------
import services.rag_service as rag  # noqa: E402

captured = {}


def fake_generate(prompt):
    captured["prompt"] = prompt
    if "Classify the user's question" in prompt:
        return "DOCUMENT"
    return "[DOCUMENT] The notice period after confirmation is two months. [S1]"


with mock.patch.object(rag, "generate_answer", side_effect=fake_generate), \
        mock.patch.object(rag, "rewrite_query", side_effect=lambda query, history, memory_summary: query):
    out = rag.ask_question("What is the notice period after confirmation?")
check("15 RAG: answer returned and classification tag stripped",
      out["answer"].startswith("The notice period") and not out["answer"].startswith("["), out)
check("15 RAG: sources carry document and page",
      any(x["document"] == "hr_policy_manual.pdf" and x["page"] == 3 for x in out["sources"]), out["sources"])
check("15 RAG: retrieved context placed in the prompt",
      "Document: hr_policy_manual.pdf" in captured["prompt"] and "Page: 3" in captured["prompt"])
check("15 RAG: answer text keeps its [S1] marker for traceability", "[S1]" in out["answer"], out["answer"])

with mock.patch.object(rag, "generate_answer", side_effect=lambda p: "MEMORY" if "Classify" in p else "[MEMORY] ok"), \
        mock.patch.object(rag, "rewrite_query", side_effect=lambda query, history, memory_summary: query), \
        mock.patch.object(rag, "hybrid_search") as spy:
    rag.ask_question("What did I tell you about my project?", memory_summary="x")
check("15 RAG: memory questions still skip document retrieval", not spy.called)

legacy = hybrid_search("notice period", top_k=5)
check("15 RAG: legacy hybrid_search(query, top_k) shape unchanged",
      legacy and {"chunk", "rrf_score", "rerank_score"} <= set(legacy[0]) and len(legacy[0]["chunk"]) == 5)

# configuration -----------------------------------------------------------------
env = dict(os.environ, VECTOR_TOP_K="17", RRF_K="42", FINAL_TOP_K="3", SIMILARITY_THRESHOLD="0.5",
           RERANK_ENABLED="false", BM25_BACKEND="fts")
code = ("from services import retrieval_config as c; "
        "print(c.VECTOR_TOP_K, c.RRF_K, c.FINAL_TOP_K, c.SIMILARITY_THRESHOLD, c.RERANK_ENABLED, c.BM25_BACKEND)")
out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout.strip()
check("config: environment variables override defaults", out == "17 42 3 0.5 False fts", out)
check("config: embedding dimension default matches the column", cfg.EMBEDDING_DIM == 384)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL PHASE 2 RETRIEVAL TESTS PASSED")
