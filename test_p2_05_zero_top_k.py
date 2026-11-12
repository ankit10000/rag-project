"""P2-05-F1: an explicit top_k of 0 must return no results; None keeps the configured default.

Pure unit test: the retrievers and the reranker are replaced by in-memory fakes (no DB, no model, no network).
"""
import testsafe  # standard guard even though no DB is used
testsafe.require_scratch_db()

import sys
from unittest import mock

import services.hybrid_search_service as hybrid
from services import retrieval_config as cfg
from services.rrf_service import reciprocal_rank_fusion

FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def rows(n, tag):
    return [(i, f"{tag}.pdf", 1, f"{tag} distinct text number {i}", 1.0 / i) for i in range(1, n + 1)]


VEC, KW = rows(8, "v"), rows(8, "k")


def run(**kw):
    with mock.patch.object(hybrid, "semantic_search", return_value=VEC), \
            mock.patch.object(hybrid, "keyword_search", return_value=KW), \
            mock.patch.object(hybrid, "rerank_results", side_effect=lambda q, r, top_k: r[:top_k]):
        return hybrid.hybrid_search_detailed("q", **kw)["results"]


# --- RRF directly
lists = [VEC, KW]
check("RRF top_k=0 -> []", reciprocal_rank_fusion(lists, top_k=0) == [])
check("RRF top_k=-1 -> []", reciprocal_rank_fusion(lists, top_k=-1) == [])
check("RRF top_k=1 -> exactly 1", len(reciprocal_rank_fusion(lists, top_k=1)) == 1)
check("RRF top_k=3 -> 3", len(reciprocal_rank_fusion(lists, top_k=3)) == 3)
check("RRF default top_k=5 -> 5", len(reciprocal_rank_fusion(lists)) == 5)
check("RRF top_k=0 with empty input -> []", reciprocal_rank_fusion([], top_k=0) == [])

# --- hybrid pipeline, every fusion / rerank combination
for fusion in ("rrf", "interleave"):
    for rerank in (False, True):
        tag = f"fusion={fusion} rerank={rerank}"
        check(f"{tag}: top_k=0 -> []", run(top_k=0, fusion=fusion, rerank=rerank) == [])
        check(f"{tag}: top_k=-3 -> []", run(top_k=-3, fusion=fusion, rerank=rerank) == [])
        check(f"{tag}: top_k=1 -> 1 result", len(run(top_k=1, fusion=fusion, rerank=rerank)) == 1)
        check(f"{tag}: top_k=3 -> 3 results", len(run(top_k=3, fusion=fusion, rerank=rerank)) == 3)
        check(f"{tag}: top_k=None -> default FINAL_TOP_K ({cfg.FINAL_TOP_K})",
              len(run(top_k=None, fusion=fusion, rerank=rerank)) == cfg.FINAL_TOP_K)

# top_k=0 must not alter the other stages' reporting
with mock.patch.object(hybrid, "semantic_search", return_value=VEC), \
        mock.patch.object(hybrid, "keyword_search", return_value=KW):
    out = hybrid.hybrid_search_detailed("q", top_k=0, rerank=False)
check("top_k=0: counts still report the retrieved candidates", out["counts"]["vector"] == 8 and out["counts"]["keyword"] == 8)

# backward-compatible wrapper
with mock.patch.object(hybrid, "semantic_search", return_value=VEC), \
        mock.patch.object(hybrid, "keyword_search", return_value=KW), \
        mock.patch.object(hybrid, "rerank_results", side_effect=lambda q, r, top_k: r[:top_k]):
    check("hybrid_search wrapper top_k=0 -> []", hybrid.hybrid_search("q", top_k=0) == [])
    check("hybrid_search wrapper top_k=2 -> 2", len(hybrid.hybrid_search("q", top_k=2)) == 2)

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
