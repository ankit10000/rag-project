"""
Evaluation harness for Phase 2. Everything here targets a SCRATCH database
(default rag_phase2_eval); it refuses to run against the production rag_db.

IMPORTANT: call use_scratch_database() BEFORE importing anything from
services.* so services.database picks up the scratch DATABASE_URL.
"""
import hashlib
import math
import os
import re
import statistics

import psycopg

SCRATCH_DB = "rag_phase2_eval"
PROTECTED_DBS = {"rag_db", "postgres"}


def _admin_url(url: str) -> str:
    return url.rsplit("/", 1)[0] + "/postgres"


def use_scratch_database(name: str = SCRATCH_DB) -> str:
    """Create (if needed) the scratch DB and point DATABASE_URL at it."""
    if name in PROTECTED_DBS:
        raise RuntimeError(f"refusing to use protected database {name!r}")

    from dotenv import load_dotenv
    load_dotenv()
    base = os.environ["DATABASE_URL"]
    url = base.rsplit("/", 1)[0] + "/" + name

    with psycopg.connect(_admin_url(base), autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{name}"')

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                id bigserial PRIMARY KEY,
                document_name text NOT NULL,
                page_number integer NOT NULL,
                chunk_id integer NOT NULL,
                content text NOT NULL,
                embedding vector(384) NOT NULL,
                UNIQUE (document_name, page_number, chunk_id)
            )
            """
        )

    os.environ["DATABASE_URL"] = url
    return url


def drop_scratch_database(name: str = SCRATCH_DB):
    if name in PROTECTED_DBS:
        raise RuntimeError(f"refusing to drop protected database {name!r}")

    from dotenv import load_dotenv
    load_dotenv()
    base = os.environ.get("DATABASE_URL_BASE") or os.environ["DATABASE_URL"]

    with psycopg.connect(_admin_url(base), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def assert_scratch():
    from services import database
    name = database.DATABASE_URL.rsplit("/", 1)[1]
    if name in PROTECTED_DBS:
        raise RuntimeError(f"harness is pointed at {name!r}; aborting")


def load_corpus(docs: dict, chunk_fn, embed_fn, dedupe=True) -> int:
    """
    Replace the scratch table with `docs` chunked by chunk_fn(page_text).
    Returns the number of chunks stored. Identical chunk text inside one
    document is stored once when dedupe is true.
    """
    from pgvector.psycopg import register_vector
    from services.database import get_connection

    assert_scratch()
    rows = []

    for document, pages in docs.items():
        seen = set()
        for page_number, text in enumerate(pages, start=1):
            for chunk_id, content in enumerate(chunk_fn(text), start=1):
                if dedupe:
                    key = hashlib.sha1(
                        re.sub(r"\s+", " ", content).lower().encode()
                    ).hexdigest()
                    if key in seen:
                        continue
                    seen.add(key)
                rows.append((document, page_number, chunk_id, content))

    embeddings = embed_fn([r[3] for r in rows])

    with get_connection() as conn:
        conn.execute("TRUNCATE document_chunks RESTART IDENTITY")
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO document_chunks
                    (document_name, page_number, chunk_id, content, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [(*r, e.tolist()) for r, e in zip(rows, embeddings)],
            )

    return len(rows)


# ---------------------------------------------------------------- metrics ---
def covers(chunk, gold_item) -> bool:
    document, span = gold_item
    return chunk[1] == document and span.lower() in " ".join(chunk[3].split()).lower()


def score_query(chunks, gold, k):
    """Chunk-level binary-relevance metrics for one query."""
    top = chunks[:k]
    covered = {i for i, g in enumerate(gold) if any(covers(c, g) for c in top)}
    relevant_flags = [any(covers(c, g) for g in gold) for c in top]

    recall = len(covered) / len(gold)
    precision = sum(relevant_flags) / k

    rr = 0.0
    for rank, flag in enumerate(relevant_flags, start=1):
        if flag:
            rr = 1.0 / rank
            break

    dcg = sum(1.0 / math.log2(r + 1) for r, f in enumerate(relevant_flags, start=1) if f)
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(gold), k) + 1))
    ndcg = dcg / ideal if ideal else 0.0

    return {
        "recall": recall,
        "precision": precision,
        "mrr": rr,
        "ndcg": ndcg,
        "hit1": 1.0 if relevant_flags[:1] == [True] else 0.0,
    }


def mean(values):
    return sum(values) / len(values) if values else 0.0


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def median(values):
    return statistics.median(values) if values else 0.0
