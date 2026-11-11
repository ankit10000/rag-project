"""P2-03: document / page metadata filtering across the retrieval pipeline.

Controlled corpus inserted straight into the scratch document_chunks table (real rows, real SQL):
  * several documents, several pages, several chunks per page
  * identical shared text in every chunk (so ONLY the filter separates documents/pages)
  * a distinctive token per chunk, near-duplicate document names (prefix / suffix / case variants /
    a name containing quotes and SQL text) to expose substring matching or injection
Retrievers exercised: semantic_search (vector), bm25_search, fts_search, reciprocal_rank_fusion,
hybrid_search_detailed (bm25 and fts backends, RRF and interleave, with and without reranking).

Vectors are DETERMINISTIC substitutes (unit basis vector + tiny per-chunk offset; the query maps to the
same basis vector). The cross-encoder used for the "after reranking" checks is the REAL local model
(HF offline); a spy proves what the reranker receives. No Gemini, no network, rag_db never touched.
"""
import testsafe  # refuses to run against anything but a scratch database
testsafe.require_scratch_db()

import contextlib
import io
import sys
import uuid
from unittest import mock

import numpy as np

import services.hybrid_search_service as hybrid
import services.search_service as search
from services import retrieval_config as cfg
from services.bm25_service import bm25_search, clear_bm25_cache
from services.database import get_connection
from services.fts_service import fts_search
from services.hybrid_search_service import hybrid_search, hybrid_search_detailed
from services.rrf_service import reciprocal_rank_fusion
from services.search_service import build_scope_filter, semantic_search

FAILURES = []
RUN = uuid.uuid4().hex[:8]
PREFIX = "p2_03_"
P = f"{PREFIX}{RUN}_"
SHARED = "quarterly retention policy review"
QUERY = SHARED


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------- corpus
ALPHA = P + "alpha.pdf"            # pages 1-3, 2 chunks each
BETA = P + "beta.pdf"              # pages 1-2, 2 chunks each, same shared text
ALPHA_OLD = P + "alpha.pdf.old"    # name that STARTS WITH alpha.pdf (substring / prefix trap)
ALPHA_UP = P + "ALPHA.pdf"         # case variant
QUOTE = P + "o'brien; DROP TABLE document_chunks; --.pdf"   # quotes + SQL text in the name
LAYOUT = {ALPHA: {1: 2, 2: 2, 3: 2}, BETA: {1: 2, 2: 2}, ALPHA_OLD: {1: 1, 2: 1}, ALPHA_UP: {1: 1}, QUOTE: {1: 1}}
LETTER = {ALPHA: "a", BETA: "b", ALPHA_OLD: "c", ALPHA_UP: "d", QUOTE: "e"}
DIM = cfg.EMBEDDING_DIM


def token(doc, page, chunk):
    return f"tok{LETTER[doc]}{RUN}p{page}c{chunk}"


def vector(index):
    v = np.zeros(DIM)
    v[0] = 1.0
    v[1 + (index % (DIM - 2))] = 0.01 * (1 + index % 7)
    return (v / np.linalg.norm(v)).tolist()


def query_vector(_texts):
    v = np.zeros(DIM)
    v[0] = 1.0
    return [v for _ in _texts]


def load_corpus():
    rows = []
    index = 0
    for doc, pages in LAYOUT.items():
        for page, chunks in pages.items():
            for chunk in range(1, chunks + 1):
                content = f"{SHARED} {token(doc, page, chunk)} filler words for length and variety {index}"
                rows.append((doc, page, chunk, content, vector(index)))
                index += 1
    with get_connection() as conn:
        for row in rows:
            conn.execute("INSERT INTO document_chunks (document_name, page_number, chunk_id, content, embedding) "
                         "VALUES (%s, %s, %s, %s, %s)", row)
    clear_bm25_cache()
    return rows


def cleanup():
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))
    clear_bm25_cache()


def expected(docs=None, pages=None):
    """Set of (document, page, chunk) from the layout, using exact-match semantics."""
    out = set()
    for doc, pg in LAYOUT.items():
        if docs and doc not in docs:
            continue
        for page, chunks in pg.items():
            if pages and page not in pages:
                continue
            for chunk in range(1, chunks + 1):
                out.add((doc, page, chunk))
    return out


def keys(rows):
    """(document, page, chunk) of returned rows that belong to this test's corpus, via the token."""
    found = set()
    for row in rows:
        chunk = row[3] if not isinstance(row, dict) else row["chunk"][3]
        meta = row if not isinstance(row, dict) else row["chunk"]
        if f"{RUN}p" in chunk:
            for doc, pg in LAYOUT.items():
                for page, chunks in pg.items():
                    for c in range(1, chunks + 1):
                        if token(doc, page, c) in chunk.split():
                            found.add((doc, page, c))
                            assert meta[1] == doc and meta[2] == page, "row metadata disagrees with its content"
    return found


def own(rows):
    """Rows that belong to this test's documents (the scratch DB may hold other tests' rows)."""
    return [r for r in rows if (r["chunk"] if isinstance(r, dict) else r)[1].startswith(P)]


def foreign(rows):
    return [r for r in rows if not (r["chunk"] if isinstance(r, dict) else r)[1].startswith(P)]


# ------------------------------------------------------------------------ retrievers
def r_vector(**f):
    return quiet(semantic_search, QUERY, 100, **f)


def r_bm25(**f):
    return quiet(bm25_search, QUERY, 100, **f)


def r_fts(**f):
    return quiet(fts_search, QUERY, 100, **f)


def hybrid_rows(**kw):
    def run(**f):
        out = quiet(hybrid_search_detailed, QUERY, 50, rrf_top_k=100, rerank_top_k=100,
                    vector_top_k=100, keyword_top_k=100, **kw, **f)
        return [r["chunk"] for r in out["results"]]
    return run


RETRIEVERS = {
    "vector": r_vector,
    "BM25": r_bm25,
    "FTS": r_fts,
    "hybrid (vector+BM25, RRF)": hybrid_rows(rerank=False),
    "hybrid (vector+FTS, RRF)": hybrid_rows(rerank=False, keyword_backend="fts"),
    "hybrid (vector only)": hybrid_rows(rerank=False, use_keyword=False),
    "hybrid (BM25 only)": hybrid_rows(rerank=False, use_vector=False),
    "hybrid (interleave fusion)": hybrid_rows(rerank=False, fusion="interleave"),
    "hybrid + REAL reranker": hybrid_rows(rerank=True),
}


def run_all():
    # ------------------------------------------------------------- build-scope-filter (static contract)
    sql, params = build_scope_filter(["x' OR '1'='1"], ["2", 3.0])
    check("[sql] build_scope_filter emits only %s placeholders; filter values travel as parameters, never in the SQL text",
          sql == "document_name = ANY(%s) AND page_number = ANY(%s)" and params == [["x' OR '1'='1"], [2, 3]])
    check("[sql] no filter values -> empty fragment, no params", build_scope_filter(None, None) == ("", [])
          and build_scope_filter([], []) == ("", []))
    check("[sql] only a document filter / only a page filter produce one clause each",
          build_scope_filter(["a"], None)[0] == "document_name = ANY(%s)"
          and build_scope_filter(None, [1])[0] == "page_number = ANY(%s)")

    with mock.patch.object(search, "generate_embeddings", side_effect=query_vector):
        for name, fn in RETRIEVERS.items():
            # 4. no filter
            rows = fn()
            got = keys(own(rows))
            check(f"[{name}] no filter: rows from all five test documents are eligible", {d for d, _, _ in got} == set(LAYOUT)
                  if name != "hybrid (vector only)" else {d for d, _, _ in got} <= set(LAYOUT) and len(got) >= 5)

            # 1. document filter
            rows = fn(document_names=[ALPHA])
            check(f"[{name}] document filter: only {ALPHA!r} (all 6 of its chunks, nothing else)",
                  keys(rows) == expected({ALPHA}) and not foreign(rows) and all(r[1] == ALPHA for r in rows))

            # 2. page filter (no doc filter): every returned row is page 2, all test page-2 chunks present
            rows = fn(pages=[2])
            check(f"[{name}] page filter [2]: every returned row is page 2; all test page-2 chunks returned",
                  all(r[2] == 2 for r in rows) and expected(pages={2}) <= keys(rows) | set())

            # 3. combined
            rows = fn(document_names=[ALPHA], pages=[2])
            check(f"[{name}] document + page filter: exactly the intersection (2 chunks)",
                  keys(rows) == expected({ALPHA}, {2}) and len(rows) == 2 and all(r[1] == ALPHA and r[2] == 2 for r in rows))

            # 5. nonexistent
            check(f"[{name}] nonexistent document -> no results", fn(document_names=[P + "nope.pdf"]) == [])
            check(f"[{name}] existing document + nonexistent page -> no results", fn(document_names=[ALPHA], pages=[99]) == [])
            check(f"[{name}] nonexistent page alone -> no results", fn(pages=[987654]) == [])
            check(f"[{name}] page 0 and negative pages do not exist (pages are 1-based) -> no results",
                  fn(document_names=[ALPHA], pages=[0]) == [] and fn(document_names=[ALPHA], pages=[-1]) == [])

            # 7. several values
            rows = fn(document_names=[ALPHA, BETA])
            check(f"[{name}] two documents: exactly those two documents' chunks",
                  keys(rows) == expected({ALPHA, BETA}) and not foreign(rows))
            rows = fn(document_names=[ALPHA], pages=[1, 3])
            check(f"[{name}] several pages [1, 3] of one document", keys(rows) == expected({ALPHA}, {1, 3}) and len(rows) == 4)
            rows = fn(document_names=[ALPHA, BETA], pages=[1, 2])
            check(f"[{name}] several documents x several pages = cross-product intersection",
                  keys(rows) == expected({ALPHA, BETA}, {1, 2}) and len(rows) == 8)

            # page-number convention: 1-based, as stored
            rows = fn(document_names=[BETA], pages=[1])
            check(f"[{name}] page 1 is the first page: BETA page 1 chunks only",
                  keys(rows) == expected({BETA}, {1}) and all(r[2] == 1 for r in rows))

            # 8. exact (not substring / prefix / case-insensitive) document matching
            rows = fn(document_names=[ALPHA])
            check(f"[{name}] exact name match: '...alpha.pdf' does not return '...alpha.pdf.old' or '...ALPHA.pdf'",
                  all(r[1] == ALPHA for r in rows) and (ALPHA_OLD, 1, 1) not in keys(rows) and (ALPHA_UP, 1, 1) not in keys(rows))
            check(f"[{name}] partial / prefix / wildcard names match nothing",
                  fn(document_names=[P + "alpha"]) == [] and fn(document_names=[P + "alph%"]) == []
                  and fn(document_names=[P + "%"]) == [] and fn(document_names=[ALPHA.upper()]) == [])
            rows = fn(document_names=[ALPHA_OLD])
            check(f"[{name}] the longer similar name returns only its own chunks",
                  keys(rows) == expected({ALPHA_OLD}) and all(r[1] == ALPHA_OLD for r in rows))

            # 9. injection-style values are data
            check(f"[{name}] SQL-looking filter value matches nothing and breaks nothing",
                  fn(document_names=["x' OR '1'='1"]) == [] and fn(document_names=["'; DROP TABLE document_chunks; --"]) == [])
            rows = fn(document_names=[QUOTE])
            check(f"[{name}] a real document whose name contains quotes/SQL text is found by exact name only",
                  keys(rows) == expected({QUOTE}) and all(r[1] == QUOTE for r in rows))

            # 6. empty filter contract: falsy => no filtering
            base = keys(own(fn()))
            check(f"[{name}] empty filters ([], (), None) mean 'no filter' (current contract)",
                  keys(own(fn(document_names=[], pages=[]))) == base and keys(own(fn(document_names=(), pages=()))) == base
                  and keys(own(fn(document_names=None, pages=None))) == base)
            check(f"[{name}] a list holding only an empty string is a real (non-matching) filter -> no results",
                  fn(document_names=[""]) == [])

    # --------------------------------------------------------------- undefined-input behaviour (PINNED)
    with mock.patch.object(search, "generate_embeddings", side_effect=query_vector):
        rows = r_bm25(document_names=[ALPHA], pages=["2"])
        check("[pinned] numeric-string page '2' is accepted (int cast)", keys(rows) == expected({ALPHA}, {2}))
        rows = r_bm25(document_names=[ALPHA], pages=[2.0])
        check("[pinned] float page 2.0 is accepted as 2 (int cast)", keys(rows) == expected({ALPHA}, {2}))
        try:
            r_vector(pages=["abc"])
            raised = None
        except Exception as error:  # noqa: BLE001
            raised = type(error).__name__
        check(f"[pinned] non-numeric page 'abc' raises ValueError (not a silent no-op) -> {raised}", raised == "ValueError")
        check("[pinned] a bare string passed as document_names is iterated per character -> matches nothing (undefined API; "
              "documented in the report)", r_bm25(document_names=ALPHA) == [] and r_vector(document_names=ALPHA) == [])

        # -------------------------------------------------------------- RRF
        v = r_vector(document_names=[ALPHA], pages=[1, 2])
        k = r_bm25(document_names=[ALPHA], pages=[1, 2])
        fused = reciprocal_rank_fusion([k, v], k=cfg.RRF_K, top_k=100)
        check("[RRF] fusing two filtered lists returns only chunks present in the filtered inputs (no new chunks)",
              {f["chunk"][0] for f in fused} <= {r[0] for r in v} | {r[0] for r in k}
              and all(f["chunk"][1] == ALPHA and f["chunk"][2] in (1, 2) for f in fused) and len(fused) == 4)
        out = quiet(hybrid_search_detailed, QUERY, 50, document_names=[ALPHA], pages=[3], rrf_top_k=100, rerank=False,
                    vector_top_k=100, keyword_top_k=100)
        check("[hybrid] counts reported for the filtered retrievers equal the filtered population (2 chunks)",
              out["counts"]["vector"] == 2 and out["counts"]["keyword"] == 2 and out["counts"]["fused"] == 2)

        # -------------------------------------------------------------- reranking: spy on the reranker input/output
        seen = {}
        real_rerank = hybrid.rerank_results

        def spy(query, results, top_k=5):
            seen["input"] = [r["chunk"] for r in results]
            seen["output"] = real_rerank(query, results, top_k=top_k)
            return seen["output"]

        with mock.patch.object(hybrid, "rerank_results", side_effect=spy):
            out = quiet(hybrid_search_detailed, QUERY, 50, document_names=[BETA], pages=[2], rrf_top_k=100,
                        rerank_top_k=100, rerank=True)
        ids_in = {c[0] for c in seen["input"]}
        check("[rerank, REAL cross-encoder] the reranker receives only chunks that satisfy the filter",
              seen["input"] and all(c[1] == BETA and c[2] == 2 for c in seen["input"]))
        check("[rerank, REAL cross-encoder] the reranker output is a subset of its input and all rows satisfy the filter",
              {r["chunk"][0] for r in out["results"]} <= ids_in and len(out["results"]) == 2
              and all(r["chunk"][1] == BETA and r["chunk"][2] == 2 and "rerank_score" in r for r in out["results"]))

        # unfiltered competitors cannot sneak in even when they would rank higher: filter to the *worst* vector match
        worst = r_vector(document_names=[ALPHA_UP])
        out = quiet(hybrid_search_detailed, QUERY, 5, document_names=[ALPHA_UP], rerank=True)
        check("[rerank] a filter to a single low-ranked document returns only that document after fusion and reranking",
              len(worst) == 1 and [r["chunk"][1] for r in out["results"]] == [ALPHA_UP])

        # hybrid_search wrapper (used by rag_service)
        rows = quiet(hybrid_search, QUERY, 10, document_names=[ALPHA], pages=[1])
        check("[hybrid_search wrapper] filter forwarded; only ALPHA page 1", {(r["chunk"][1], r["chunk"][2]) for r in rows} == {(ALPHA, 1)}
              and len(rows) == 2)

        # -------------------------------------------------------------- BM25 cache cannot leak across filters
        filtered_1 = keys(r_bm25(document_names=[BETA]))
        unfiltered = keys(own(r_bm25()))
        filtered_2 = keys(r_bm25(document_names=[BETA]))
        check("[BM25 cache] filtered -> unfiltered -> filtered gives identical filtered results (cache is scoped by filter)",
              filtered_1 == filtered_2 == expected({BETA}) and unfiltered == expected())
        with get_connection() as conn:
            conn.execute("INSERT INTO document_chunks (document_name, page_number, chunk_id, content, embedding) "
                         "VALUES (%s, 1, 99, %s, %s)", (ALPHA_UP, f"{SHARED} newtoken{RUN}", vector(500)))
        after = keys(r_bm25(document_names=[BETA]))
        new_visible = any(r[1] == ALPHA_UP for r in r_bm25(document_names=[ALPHA_UP], pages=[1])) and \
            len(r_bm25(document_names=[ALPHA_UP])) == 2
        check("[BM25 cache] an inserted row outside the filter does not change filtered results; the corpus change is "
              "picked up for its own filter", after == filtered_1 and new_visible)

        # FTS and BM25 agree on filtered populations
        for doc, pages in ((ALPHA, None), (BETA, [1]), (ALPHA_OLD, [2])):
            check(f"[FTS vs BM25] same filtered population for {doc.split('_')[-1]} pages={pages}",
                  keys(r_fts(document_names=[doc], pages=pages)) == keys(r_bm25(document_names=[doc], pages=pages)) != set())


try:
    load_corpus()
    run_all()
finally:
    cleanup()

with get_connection() as conn:
    left = conn.execute("SELECT count(*) FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",)).fetchone()[0]
    table_ok = conn.execute("SELECT to_regclass('public.document_chunks') IS NOT NULL").fetchone()[0]
check("[cleanup] test rows removed; document_chunks table still exists (injection strings did nothing)", left == 0 and table_ok)

if FAILURES:
    print("FAILED CHECKS: " + " ## ".join(FAILURES))
print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
