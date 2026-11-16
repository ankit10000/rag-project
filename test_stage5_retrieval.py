"""Batch 2 / Stage 5: retrieval pipeline logic (pure unit test).

No database, no model, no network: retrievers, the cross-encoder and the LLM
are replaced by in-memory fakes. Covers RRF, reranker lifecycle and failure
isolation, hybrid failure behaviour, the no-rerank relevance policy and
context-assembly limits (FINAL_TOP_K / CONTEXT_MAX_CHUNKS).
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import copy
import io
import math
import sys
from unittest import mock

import services.hybrid_search_service as hybrid
import services.rag_service as rag
import services.reranker_service as reranker
from services import retrieval_config as cfg
from services.context_assembly_service import assemble_context
from services.rrf_service import reciprocal_rank_fusion

FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def chunk(cid, doc="d.pdf", page=1, text=None, raw=0.5):
    return (cid, doc, page, text if text is not None else f"text of chunk {cid}", raw)


# =============================================================== RRF
A = [chunk(1, raw=9.0), chunk(2, raw=8.0), chunk(3, raw=7.0)]          # keyword list
B = [chunk(3, raw=0.1), chunk(1, raw=0.2), chunk(4, raw=0.3)]          # vector list
fused = reciprocal_rank_fusion([A, B], k=60, top_k=10)
expected = {1: 1 / 61 + 1 / 62, 3: 1 / 63 + 1 / 61, 2: 1 / 62, 4: 1 / 63}
check("[rrf] manual example: order 1, 3, 2, 4", [f["chunk"][0] for f in fused] == [1, 3, 2, 4])
check("[rrf] manual example: scores equal sum of 1/(k+rank)",
      all(math.isclose(f["rrf_score"], expected[f["chunk"][0]], rel_tol=1e-12) for f in fused))
check("[rrf] duplicate ids merged (4 unique chunks from 6 entries)", len(fused) == 4)
check("[rrf] metadata of the first list's copy is kept (raw score 9.0 for chunk 1)",
      fused[0]["chunk"] == A[0])
k10 = reciprocal_rank_fusion([A, B], k=10, top_k=10)
check("[rrf] the constant k is applied: k=10 -> chunk 1 score 1/11 + 1/12",
      math.isclose(k10[0]["rrf_score"], 1 / 11 + 1 / 12))
ties = [reciprocal_rank_fusion([[chunk(7)], [chunk(8)]], top_k=5) for _ in range(3)]
check("[rrf] ties are broken by first-seen order, deterministically",
      all([f["chunk"][0] for f in t] == [7, 8] for t in ties))
same_text = reciprocal_rank_fusion([[chunk(1, text="Same  TEXT"), chunk(2, text="same text")]], top_k=5)
check("[rrf] different ids with identical normalised text collapse to the best ranked one",
      [f["chunk"][0] for f in same_text] == [1])
check("[rrf] content dedupe can be disabled", len(reciprocal_rank_fusion(
    [[chunk(1, text="x"), chunk(2, text="x")]], top_k=5, dedupe_content=False)) == 2)
check("[rrf] missing ranking (one empty list) is handled",
      [f["chunk"][0] for f in reciprocal_rank_fusion([[], B], top_k=5)] == [3, 1, 4])
check("[rrf] no lists -> []", reciprocal_rank_fusion([], top_k=5) == [])
try:
    reciprocal_rank_fusion([A, B], weights=[1.0])
    err = None
except ValueError as e:
    err = e
check("[rrf] weights/list count mismatch raises instead of silently dropping a list", err is not None)
check("[rrf] top_k limits the output", len(reciprocal_rank_fusion([A, B], top_k=2)) == 2)


# =============================================================== reranker lifecycle
class FakeCE:
    loads = []

    def __init__(self, name):
        FakeCE.loads.append(name)

    def predict(self, pairs):
        return [float(len(text)) for _, text in pairs]       # longer text = more relevant


def fresh_reranker():
    reranker._model = None
    FakeCE.loads = []


import sentence_transformers  # noqa: E402

fresh_reranker()
with mock.patch.object(sentence_transformers, "CrossEncoder", FakeCE):
    check("[rerank] lazy: empty candidate list returns [] without loading the model",
          reranker.rerank_results("q", []) == [] and FakeCE.loads == [])
    cands = [{"chunk": chunk(1, text="aa"), "rrf_score": 0.3},
             {"chunk": chunk(2, text="aaaa"), "rrf_score": 0.2},
             {"chunk": chunk(3, text="a"), "rrf_score": 0.1}]
    before = copy.deepcopy(cands)
    ranked = reranker.rerank_results("q", cands, top_k=2)
    reranker.rerank_results("q", cands, top_k=2)
    check("[rerank] initialisation: the configured model is loaded once, on first use",
          FakeCE.loads == [cfg.RERANK_MODEL])
    check("[rerank] success: ordered by score, top_k applied", [r["chunk"][0] for r in ranked] == [2, 1])
    check("[rerank] chunk tuples and rrf scores preserved",
          ranked[0]["chunk"] == cands[1]["chunk"] and ranked[0]["rrf_score"] == 0.2 and ranked[0]["rerank_score"] == 4.0)
    check("[rerank] input candidates are not mutated", cands == before)

fresh_reranker()
with mock.patch.object(sentence_transformers, "CrossEncoder", side_effect=OSError("no model in cache")):
    try:
        reranker.rerank_results("q", cands)
        err = None
    except OSError as e:
        err = e
check("[rerank] initialisation failure raises (not cached: next call retries)", err is not None and reranker._model is None)


class BadCE:
    def __init__(self, mode): self.mode = mode
    def predict(self, pairs):
        if self.mode == "raise":
            raise RuntimeError("predict failed")
        if self.mode == "short":
            return [1.0] * (len(pairs) - 1)
        return [1.0, float("nan")] + [0.5] * (len(pairs) - 2)


for mode, exc in (("raise", RuntimeError), ("short", ValueError), ("nan", ValueError)):
    with mock.patch.object(reranker, "get_reranker", return_value=BadCE(mode)):
        try:
            reranker.rerank_results("q", cands)
            err = None
        except Exception as e:  # noqa: BLE001
            err = e
    check(f"[rerank] predict {mode} -> {exc.__name__} (never a silently truncated or NaN-ordered list)",
          isinstance(err, exc))


# =============================================================== hybrid behaviour
VEC = [chunk(10, raw=0.1), chunk(11, raw=0.2), chunk(12, raw=0.3)]
KEY = [chunk(12, raw=5.0), chunk(13, raw=4.0)]


def run_hybrid(vec=VEC, key=KEY, rerank=False, rerank_fn=None, top_k=5, query="find it"):
    vec_mock = mock.Mock(side_effect=vec) if isinstance(vec, Exception) else mock.Mock(return_value=list(vec))
    key_mock = mock.Mock(side_effect=key) if isinstance(key, Exception) else mock.Mock(return_value=list(key))
    out = io.StringIO()
    with mock.patch.object(hybrid, "semantic_search", vec_mock), \
            mock.patch.object(hybrid, "keyword_search", key_mock), \
            mock.patch.object(hybrid, "rerank_results", side_effect=rerank_fn or (lambda q, r, top_k: r[:top_k])) as rr, \
            contextlib.redirect_stdout(out):
        try:
            res = hybrid.hybrid_search_detailed(query, top_k, rerank=rerank)
        except Exception as e:  # noqa: BLE001
            res = e
    return res, vec_mock, key_mock, rr, out.getvalue()


res, v, k, _, _ = run_hybrid()
check("[hybrid] both succeed: 12 (in both lists) first, then 10 (1/61), then the 1/62 tie 13 vs 11 broken by first-seen",
      [r["chunk"][0] for r in res["results"]] == [12, 10, 13, 11] and res["rerank_status"] == "disabled")
check("[hybrid] both retrievers receive the same query", v.call_args.args[0] == k.call_args.args[0] == "find it")
res, *_ = run_hybrid(vec=[])
check("[hybrid] vector empty: keyword results only", [r["chunk"][0] for r in res["results"]] == [12, 13])
res, *_ = run_hybrid(key=[])
check("[hybrid] keyword empty: vector results only", [r["chunk"][0] for r in res["results"]] == [10, 11, 12])
res, *_ = run_hybrid(vec=[], key=[])
check("[hybrid] both empty: valid empty result", res["results"] == [] and res["counts"]["fused"] == 0)
for label, kwargs in (("vector fails", {"vec": RuntimeError("db down")}),
                      ("keyword fails", {"key": RuntimeError("db down")}),
                      ("both fail", {"vec": RuntimeError("x"), "key": RuntimeError("y")})):
    res, *_ = run_hybrid(**kwargs)
    check(f"[hybrid] {label}: the exception propagates (never reported as an empty or partial success)",
          isinstance(res, RuntimeError))
res, v, k, rr, _ = run_hybrid(query="   ")
check("[hybrid] blank query: no retriever or reranker call, valid empty result",
      res["results"] == [] and not v.called and not k.called and not rr.called)
res, *_ = run_hybrid(query=None)
check("[hybrid] non-string query -> TypeError", isinstance(res, TypeError))

# reranker failure isolation
plain, *_ = run_hybrid(rerank=False)


def boom(q, r, top_k):
    raise OSError("C:/secret/path/model.bin cannot be opened")


res, _, _, _, printed = run_hybrid(rerank=True, rerank_fn=boom)
check("[fallback] reranker failure keeps the exact RRF order and scores",
      res["results"] == plain["results"] and res["rerank_status"] == "failed:OSError")
check("[fallback] diagnostic is type-only (no exception message or path printed)",
      "OSError" in printed and "secret" not in printed and "cannot be opened" not in printed)
res, *_ = run_hybrid(rerank=True, rerank_fn=lambda q, r, top_k: list(reversed(r))[:top_k])
check("[rerank] success path reports rerank_status ok and uses the reranker order",
      res["rerank_status"] == "ok" and [r["chunk"][0] for r in res["results"]] == [11, 13, 10, 12])
res, _, _, rr, _ = run_hybrid(rerank=True, top_k=0)
check("[rerank] top_k=0: reranker not called (model not loaded), empty result", res["results"] == [] and not rr.called)
with mock.patch.object(reranker, "get_reranker", return_value=BadCE("nan")):
    with mock.patch.object(hybrid, "semantic_search", return_value=list(VEC)), \
            mock.patch.object(hybrid, "keyword_search", return_value=list(KEY)), \
            contextlib.redirect_stdout(io.StringIO()):
        real = hybrid.hybrid_search_detailed("find it", 5, rerank=True)
check("[fallback] invalid reranker output (NaN) also falls back to the RRF order",
      real["results"] == plain["results"] and real["rerank_status"] == "failed:ValueError")


# =============================================================== no-rerank relevance policy (rag_service)
def run_rag(results):
    captured = {}

    def fake_answer(**kwargs):
        captured["bundle"] = kwargs["bundle"]
        return {"answer": "a", "sources": [], "citations": [], "status": "ok", "issues": [], "attempts": 1}

    with mock.patch.object(rag, "classify_question", return_value="DOCUMENT"), \
            mock.patch.object(rag, "rewrite_query", return_value="q"), \
            mock.patch.object(rag, "hybrid_search", return_value=results), \
            mock.patch.object(rag, "generate_grounded_answer", side_effect=fake_answer), \
            contextlib.redirect_stdout(io.StringIO()):
        rag.ask_question("q")
    return [s["chunk_id"] for s in captured["bundle"]["sources"]]


reranked = [{"chunk": chunk(i), "rrf_score": 0.1, "rerank_score": s} for i, s in ((1, 5.0), (2, 4.0), (3, 2.5), (4, -3.0))]
with mock.patch.object(cfg, "RERANK_SCORE_MARGIN", 2.0), mock.patch.object(cfg, "RERANK_MIN_SCORE", None):
    check("[gate] reranked results: margin gate keeps scores >= best - RERANK_SCORE_MARGIN (5.0 - 2.0)",
          run_rag(reranked) == [1, 2])
with mock.patch.object(cfg, "RERANK_MIN_SCORE", 6.0):
    check("[gate] reranked results: RERANK_MIN_SCORE floor drops all context when the best score is below it",
          run_rag(reranked) == [])
unreranked = [{"chunk": chunk(i), "rrf_score": 1 / (60 + i)} for i in range(1, 5)]
check("[gate] no-rerank / fallback results: no score gate is applied (documented gap: no approved threshold "
      "for RRF scores); candidates pass in rank order", run_rag(unreranked) == [1, 2, 3, 4])


# =============================================================== context limits
print(f"INFO | FINAL_TOP_K={cfg.FINAL_TOP_K} CONTEXT_MAX_CHUNKS={cfg.CONTEXT_MAX_CHUNKS} "
      f"CONTEXT_MAX_CHARS={cfg.CONTEXT_MAX_CHARS} RRF_TOP_K={cfg.RRF_TOP_K} RERANK_TOP_K={cfg.RERANK_TOP_K}")
many = [{"chunk": chunk(i, text=f"distinct content number {i}"), "rrf_score": 1 / (60 + i)} for i in range(1, 13)]
snapshot = copy.deepcopy(many)
bundle = assemble_context(many[: cfg.FINAL_TOP_K])
check("[context] default path: FINAL_TOP_K results -> FINAL_TOP_K sources in rank order (CONTEXT_MAX_CHUNKS not binding)",
      [s["chunk_id"] for s in bundle["sources"]] == list(range(1, cfg.FINAL_TOP_K + 1)))
bundle = assemble_context(many, max_chunks=8)
check("[context] more candidates than CONTEXT_MAX_CHUNKS: first 8 by rank kept, the rest dropped as max_chunks",
      [s["chunk_id"] for s in bundle["sources"]] == list(range(1, 9))
      and [d["chunk_id"] for d in bundle["dropped"] if d["reason"] == "max_chunks"] == list(range(9, 13)))
with mock.patch.object(hybrid, "semantic_search", return_value=[m["chunk"] for m in many]), \
        mock.patch.object(hybrid, "keyword_search", return_value=[]), \
        mock.patch.object(cfg, "RRF_TOP_K", 12):
    deep = hybrid.hybrid_search_detailed("q", 10, rerank=False)["results"]
bundle = assemble_context(deep, max_chunks=8)
check("[context] FINAL_TOP_K=10 > CONTEXT_MAX_CHUNKS=8: effective limit is the smaller one, lowest-ranked dropped",
      len(deep) == 10 and [s["chunk_id"] for s in bundle["sources"]] == list(range(1, 9)))
dups = [many[0], many[0], {"chunk": chunk(99, text="Distinct   CONTENT number 1"), "rrf_score": 0},
        {"chunk": chunk(98, text="   "), "rrf_score": 0}, many[1]]
bundle = assemble_context(dups)
check("[context] duplicate ids, duplicate content and empty chunks are excluded with reasons",
      [s["chunk_id"] for s in bundle["sources"]] == [1, 2]
      and sorted(d["reason"] for d in bundle["dropped"]) == ["duplicate_content", "duplicate_id", "empty"])
check("[context] metadata preserved (document, page, chunk id, score)",
      bundle["sources"][0]["document_name"] == "d.pdf" and bundle["sources"][0]["page_number"] == 1
      and bundle["sources"][0]["rrf_score"] == many[0]["rrf_score"])
empty = assemble_context([])
check("[context] empty retrieval -> valid empty context", empty["sources"] == [] and empty["context_text"] == "")
big = [{"chunk": chunk(i, text="w " * 3000), "rrf_score": 0} for i in range(1, 5)]
check("[context] CONTEXT_MAX_CHARS budget enforced", assemble_context(big)["total_chars"] <= cfg.CONTEXT_MAX_CHARS)
check("[context] assembly never mutates the retrieval results", many == snapshot)

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
