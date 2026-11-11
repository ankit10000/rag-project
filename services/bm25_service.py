import re
import threading

from rank_bm25 import BM25Okapi

from services import retrieval_config as cfg
from services.database import get_connection
from services.search_service import build_scope_filter

_TOKEN_RE = re.compile(r"\b[a-zA-Z0-9]+\b")

# Small English stop list; only used when tokenize(..., drop_stopwords=True).
STOPWORDS = frozenset(
    "a an and are as at be by for from how i in is it of on or that the this to was "
    "what when where which who why with do does did can you your we our they their".split()
)


class LuceneBM25(BM25Okapi):
    """
    BM25Okapi with the always-positive Lucene/Elasticsearch IDF,
    log(1 + (N - n + 0.5) / (n + 0.5)). The stock rank_bm25 IDF is zero or
    negative for terms present in half the chunks or more, which silently
    drops matches when a document filter leaves only a few chunks.
    """

    def _calc_idf(self, nd):
        import math
        self.idf = {
            word: math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))
            for word, freq in nd.items()
        }
        self.average_idf = sum(self.idf.values()) / len(self.idf) if self.idf else 0.0


def tokenize(text: str, drop_stopwords: bool = False) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())

    if drop_stopwords:
        kept = [t for t in tokens if t not in STOPWORDS]
        return kept or tokens   # never return an empty query

    return tokens


# --- cached in-memory index (rebuilt only when the corpus changes) -----------
_cache = {}
_cache_lock = threading.Lock()


def _fingerprint(conn, where, params):
    return conn.execute(
        f"""
        SELECT count(*), coalesce(max(id), 0),
               coalesce(sum(hashtext(content)::bigint), 0)
        FROM document_chunks {where}
        """,
        params,
    ).fetchone()


def _get_index(document_names, pages, drop_stopwords):
    scope_sql, scope_params = build_scope_filter(document_names, pages)
    where = f"WHERE {scope_sql}" if scope_sql else ""
    key = (
        tuple(sorted(document_names)) if document_names else None,
        tuple(sorted(pages)) if pages else None,
        drop_stopwords,
    )

    with get_connection() as conn:
        fingerprint = _fingerprint(conn, where, scope_params)

        with _cache_lock:
            cached = _cache.get(key)
            if cached and cached["fingerprint"] == fingerprint:
                return cached

        documents = conn.execute(
            f"""
            SELECT id, document_name, page_number, content
            FROM document_chunks {where}
            ORDER BY id
            """,
            scope_params,
        ).fetchall()

    entry = {
        "fingerprint": fingerprint,
        "documents": documents,
        "bm25": LuceneBM25([tokenize(d[3], drop_stopwords) for d in documents])
        if documents else None,
    }

    with _cache_lock:
        _cache[key] = entry

    return entry


def clear_bm25_cache():
    with _cache_lock:
        _cache.clear()


def bm25_search(
    query: str,
    top_k: int = 5,
    document_names=None,
    pages=None,
    drop_stopwords: bool | None = None,
):
    """
    Independent keyword retriever (BM25Okapi). Returns
    (id, document_name, page_number, content, bm25_score) tuples, best first.
    Chunks that share no term with the query (score <= 0) are not returned.
    """
    if drop_stopwords is None:
        drop_stopwords = cfg.BM25_DROP_STOPWORDS

    entry = _get_index(document_names, pages, drop_stopwords)

    if not entry["documents"]:
        return []

    scores = entry["bm25"].get_scores(tokenize(query, drop_stopwords))

    ranked = sorted(
        zip(entry["documents"], scores),
        key=lambda item: item[1],
        reverse=True,
    )

    return [
        (*document, float(score))
        for document, score in ranked[:top_k]
        if score > 0
    ]
