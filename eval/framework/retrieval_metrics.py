"""Retrieval metrics (pure, deterministic).

Inputs
  retrieved : ranked list of hashable unit ids (best first). A "unit" is
              whatever is being judged: (document, page) pairs, document names
              or chunk ids. Duplicates are collapsed to their FIRST occurrence
              before scoring (a repeated unit cannot be counted twice).
              ``None`` entries are ignored.
  relevant  : set of relevant unit ids (binary relevance), or for nDCG an
              optional dict unit -> graded gain (>0).
  k         : positive integer cut-off.

Edge cases (explicit, never silently 0/1):
  * empty relevant set  -> recall, MRR and nDCG are None ("undefined"), and are
                           excluded from aggregates; precision@k is still defined.
  * empty retrieved     -> recall 0.0 (if relevant non-empty), precision@k 0.0,
                           MRR 0.0, nDCG 0.0.
  * k <= 0              -> ValueError.

Formulas
  Recall@K    = |rel ∩ top_k| / |rel|
  Precision@K = |rel ∩ top_k| / K            (K fixed; fewer than K results count as misses)
  RR          = 1 / rank of first relevant unit (0 if none in the list); MRR = mean RR
  DCG@K       = Σ_{i=1..K} gain_i / log2(i + 1);  nDCG@K = DCG@K / IDCG@K
  Page recall / document recall = Recall over ALL retrieved units (no cut-off)
"""

import math


def dedupe_ranked(retrieved):
    seen, out = set(), []
    for unit in retrieved or []:
        if unit is None or unit in seen:
            continue
        seen.add(unit)
        out.append(unit)
    return out


def _check_k(k):
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer")


def recall_at_k(retrieved, relevant, k):
    _check_k(k)
    relevant = set(relevant or ())
    if not relevant:
        return None
    top = dedupe_ranked(retrieved)[:k]
    return len(relevant.intersection(top)) / len(relevant)


def precision_at_k(retrieved, relevant, k):
    _check_k(k)
    top = dedupe_ranked(retrieved)[:k]
    return len(set(relevant or ()).intersection(top)) / k


def reciprocal_rank(retrieved, relevant):
    relevant = set(relevant or ())
    if not relevant:
        return None
    for rank, unit in enumerate(dedupe_ranked(retrieved), start=1):
        if unit in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved, relevant, k):
    """Binary relevance for a set; graded gains for a dict {unit: gain>0}."""
    _check_k(k)
    gains = dict(relevant) if isinstance(relevant, dict) else {u: 1.0 for u in (relevant or ())}
    gains = {u: float(g) for u, g in gains.items() if g and g > 0}
    if not gains:
        return None
    top = dedupe_ranked(retrieved)[:k]
    dcg = sum(gains.get(u, 0.0) / math.log2(i + 1) for i, u in enumerate(top, start=1))
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    return dcg / idcg if idcg else None


def coverage(retrieved, relevant):
    """Recall over the whole retrieved list (page recall, document recall)."""
    relevant = set(relevant or ())
    if not relevant:
        return None
    return len(relevant.intersection(dedupe_ranked(retrieved))) / len(relevant)


def case_metrics(retrieved_pages, relevant_pages, ks=(1, 3, 5)) -> dict:
    """Per-case metrics over (document, page) units plus document recall.

    retrieved_pages: ranked [(document, page), ...]; relevant_pages: {(document, page)}.
    Chunk-level recall is NOT computed: the current datasets have no gold chunk ids.
    """
    relevant_pages = set(relevant_pages or ())
    out = {
        "relevant_pages": len(relevant_pages),
        "retrieved_units": len(dedupe_ranked(retrieved_pages)),
        "page_recall": coverage(retrieved_pages, relevant_pages),
        "document_recall": coverage([d for d, _ in dedupe_ranked(retrieved_pages)],
                                    {d for d, _ in relevant_pages}),
        "mrr": reciprocal_rank(retrieved_pages, relevant_pages),
    }
    for k in ks:
        out[f"recall@{k}"] = recall_at_k(retrieved_pages, relevant_pages, k)
        out[f"precision@{k}"] = precision_at_k(retrieved_pages, relevant_pages, k)
        out[f"ndcg@{k}"] = ndcg_at_k(retrieved_pages, relevant_pages, k)
    return out


def aggregate(per_case: list, group_key=None) -> dict:
    """Mean of each metric over cases where it is defined (None excluded).

    Returns {"overall": {...}, "by_group": {group: {...}}} with n per metric.
    """
    def mean_block(rows):
        keys = sorted({k for r in rows for k, v in r["metrics"].items() if isinstance(v, (int, float))})
        block = {}
        for key in keys:
            values = [r["metrics"][key] for r in rows if isinstance(r["metrics"].get(key), (int, float))]
            block[key] = {"mean": (sum(values) / len(values)) if values else None, "n": len(values)}
        block["cases"] = len(rows)
        return block

    result = {"overall": mean_block(per_case)}
    if group_key:
        groups = {}
        for r in per_case:
            groups.setdefault(r.get(group_key), []).append(r)
        result["by_group"] = {g: mean_block(rows) for g, rows in sorted(groups.items(), key=lambda x: str(x[0]))}
    return result


def tier2_row_metrics(row: dict, case: dict, ks=(1, 3, 5)) -> dict:
    """Adapter for an existing Tier 2 result row (eval/phase35 format).

    Uses row["retrieved"] (rank order, fields document_name/page_number) and the
    case's gold_sources; no re-retrieval, no model call.
    """
    retrieved = [(r.get("document_name"), r.get("page_number")) for r in row.get("retrieved") or []]
    relevant = {(s["document"], s["page"]) for s in case.get("gold_sources") or []}
    return {"id": row["id"], "category": row.get("category"), "metrics": case_metrics(retrieved, relevant, ks)}
