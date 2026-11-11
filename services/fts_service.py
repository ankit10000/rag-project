"""PostgreSQL full-text search retriever (alternative keyword backend)."""
from services.bm25_service import tokenize
from services.database import get_connection
from services.search_service import build_scope_filter


def fts_search(
    query: str,
    top_k: int = 5,
    document_names=None,
    pages=None,
    config: str = "english",
):
    """
    OR-matches the query terms with to_tsquery and ranks with ts_rank_cd.
    Returns the same (id, document_name, page_number, content, score) tuples
    as bm25_search. NOTE: ts_rank_cd has no corpus-wide IDF, so it is
    BM25-style at best; see docs/phase2_report.md for measurements.
    """
    terms = tokenize(query)

    if not terms:
        return []

    # tokenize() only yields [a-z0-9]+, so joining with | is injection-safe.
    tsquery = " | ".join(dict.fromkeys(terms))

    scope_sql, scope_params = build_scope_filter(document_names, pages)
    extra = f"AND {scope_sql}" if scope_sql else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, document_name, page_number, content,
                   ts_rank_cd(to_tsvector(%s::regconfig, content),
                              to_tsquery(%s::regconfig, %s)) AS score
            FROM document_chunks
            WHERE to_tsvector(%s::regconfig, content) @@ to_tsquery(%s::regconfig, %s)
            {extra}
            ORDER BY score DESC, id
            LIMIT %s
            """,
            (config, config, tsquery, config, config, tsquery, *scope_params, top_k),
        ).fetchall()

    return [(*row[:4], float(row[4])) for row in rows]
