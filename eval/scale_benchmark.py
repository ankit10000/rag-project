"""
PostgreSQL / index benchmark on a synthetic large corpus (scratch DB
rag_phase2_scale ONLY). Measures exact scan vs HNSW vs IVFFlat, FTS with and
without a GIN index, in-memory BM25 build/query cost, filtered queries, and
connection cost.

    .venv\\Scripts\\python.exe eval\\scale_benchmark.py <n_filler_docs> [--m32]

Latency phases take eval/results/.bench.lock (atomic create, stale after 30
min) so that other benchmark agents do not run timing loops at the same time.
Corpus loading, index builds and recall-vs-exact computations run unlocked.
Appends its report to eval/results_scale.txt.
"""
import contextlib
import gc
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval import harness  # noqa: E402

harness.use_scratch_database("rag_phase2_scale")

import psutil  # noqa: E402
import psycopg  # noqa: E402
from pgvector import Vector  # noqa: E402

from eval.corpus import DOCS as CORE, QUERIES, make_distractors  # noqa: E402
from services import bm25_service  # noqa: E402
from services.bm25_service import bm25_search, clear_bm25_cache  # noqa: E402
from services.chunker import chunk_page  # noqa: E402
from services.database import DATABASE_URL, get_connection  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402
from services.fts_service import fts_search  # noqa: E402

harness.assert_scratch()
assert DATABASE_URL.rsplit("/", 1)[1] == "rag_phase2_scale"

N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 500
DO_M32 = "--m32" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, "results", ".bench.lock")
SHOW = []
REPS = 3


def say(line=""):
    print(line, flush=True)
    SHOW.append(line)


@contextlib.contextmanager
def bench_lock(max_hold=600):
    """Atomic lock file; poll every 10 s; stale after 30 min."""
    while True:
        try:
            with open(LOCK, "x") as f:
                f.write(f"scale_benchmark pid={os.getpid()} t={time.time()}")
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(LOCK) > 1800:
                    os.remove(LOCK)
                    continue
            except OSError:
                pass
            time.sleep(10)
    t0 = time.time()
    try:
        yield
    finally:
        if time.time() - t0 > max_hold:
            say(f"(warning: lock held {time.time() - t0:.0f}s)")
        try:
            os.remove(LOCK)
        except OSError:
            pass


def per_query_ms(fn, items, reps=REPS):
    """fn(item) per query; per-query median over reps; returns (median, p95, mean) across queries."""
    per = []
    for it in items:
        vals = []
        for _ in range(reps):
            t = time.perf_counter()
            fn(it)
            vals.append((time.perf_counter() - t) * 1000)
        per.append(statistics.median(vals))
    return statistics.median(per), harness.pct(per, 95), statistics.mean(per)


def explain(conn, sql, params):
    rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params).fetchall()
    return [r[0] for r in rows]


def plan_summary(lines):
    node = next((l.strip() for l in lines if "Scan" in l), lines[0].strip())
    node = node.lstrip("-> ").strip()
    ex = next((l.strip() for l in lines if l.strip().startswith("Execution Time")), "")
    return f"{node.split('  (')[0]}; {ex}"


def reset_indexes(conn):
    for ix in ("chunks_hnsw", "chunks_hnsw32", "chunks_ivf", "chunks_fts", "chunks_docname"):
        conn.execute(f"DROP INDEX IF EXISTS {ix}")
    conn.commit()


# ------------------------------------------------------------------ corpus ---
say(f"## Run: {N_DOCS} filler docs, {time.strftime('%Y-%m-%d %H:%M')}")
docs = {**CORE, **make_distractors(N_DOCS, pages_per_doc=3, seed=21)}
with get_connection() as conn:
    reset_indexes(conn)
t = time.time()
n = harness.load_corpus(docs, lambda tx: chunk_page(tx, 100, 20, "words"), generate_embeddings)
say(f"Loaded {n} chunks from {len(docs)} documents in {time.time() - t:.0f}s (embedding included)")

with get_connection() as conn:
    conn.execute("ANALYZE document_chunks")
    conn.commit()
    sizes = conn.execute(
        "SELECT pg_size_pretty(pg_table_size('document_chunks')), pg_size_pretty(pg_indexes_size('document_chunks'))"
    ).fetchone()
say(f"Table size {sizes[0]}; existing indexes (PK + UNIQUE) {sizes[1]}")

evalq = [q for q in QUERIES if q[2]]          # 38 queries with gold
queries = [q[0] for q in evalq]
say(f"Evaluation queries: {len(queries)}; each timed {REPS}x, per-query median, then median/p95 across queries")
vectors = [Vector(generate_embeddings([q])[0].tolist()) for q in queries]
VSQL = "SELECT id FROM document_chunks ORDER BY embedding <=> %s LIMIT 10"


def vec_ids(conn, v):
    return {r[0] for r in conn.execute(VSQL, (v,)).fetchall()}


def recall_vs(found, exact):
    return harness.mean([len(a & b) / len(b) for a, b in zip(found, exact)])


def idx_size(conn, name):
    return conn.execute("SELECT pg_size_pretty(pg_relation_size(%s::regclass)), pg_relation_size(%s::regclass)", (name, name)).fetchone()


# ----------------------------------------------------------------- vectors ---
say(f"\n### Vector search top-10 (N={n})")
say("| Index | median ms | p95 ms | recall@10 vs exact | build s | size | plan |")
say("|---|---|---|---|---|---|---|")

conn = get_connection()
exact = [vec_ids(conn, v) for v in vectors]
with bench_lock():
    med, p95, _ = per_query_ms(lambda v: vec_ids(conn, v), vectors)
plan = explain(conn, VSQL, (vectors[0],))
say(f"| none (exact seq scan) | {med:.2f} | {p95:.2f} | 1.000 | - | 0 | {plan_summary(plan)} |")
FULL_PLANS = {"exact": plan}


def measure_index(label, ddl, name, settings, plan_key):
    conn.execute(f"DROP INDEX IF EXISTS {name}")
    t0 = time.time()
    conn.execute(ddl)
    conn.commit()
    build = time.time() - t0
    conn.execute("ANALYZE document_chunks")
    conn.commit()
    size = idx_size(conn, name)[0]
    for sname, setting in settings:
        conn.execute(setting)
        found = [vec_ids(conn, v) for v in vectors]
        rec = recall_vs(found, exact)
        with bench_lock():
            med, p95, _ = per_query_ms(lambda v: vec_ids(conn, v), vectors)
        pl = explain(conn, VSQL, (vectors[0],))
        FULL_PLANS[f"{label} {sname}"] = pl
        say(f"| {label} {sname} | {med:.2f} | {p95:.2f} | {rec:.3f} | {build:.1f} | {size} | {plan_summary(pl)} |")
    return build


measure_index(
    "HNSW m=16 efc=64",
    "CREATE INDEX chunks_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
    "chunks_hnsw",
    [("ef_search=40", "SET hnsw.ef_search = 40"), ("ef_search=100", "SET hnsw.ef_search = 100")],
    "hnsw16",
)

# filtered vector queries (document scope) with the HNSW index in place
conn.execute("SET hnsw.ef_search = 40")
core_names = list(CORE)
fq = [(v, q[2][0][0]) for v, q in zip(vectors, evalq)]


def filt_ids(c, v, doc):
    return {r[0] for r in c.execute(
        "SELECT id FROM document_chunks WHERE document_name = %s ORDER BY embedding <=> %s LIMIT 10", (doc, v)).fetchall()}


filt_found = [filt_ids(conn, v, d) for v, d in fq]
conn.execute("DROP INDEX chunks_hnsw")
conn.commit()
filt_exact = [filt_ids(conn, v, d) for v, d in fq]
say(f"\nFiltered vector query (document_name = gold doc), HNSW m=16 ef_search=40: "
    f"recall@10 vs exact filtered = {recall_vs(filt_found, filt_exact):.3f} "
    f"(mean exact result size {harness.mean([len(s) for s in filt_exact]):.1f}; "
    f"post-filtering after the index scan can return fewer rows)")
FULL_PLANS["filtered exact"] = explain(
    conn, "SELECT id FROM document_chunks WHERE document_name = %s ORDER BY embedding <=> %s LIMIT 10",
    (fq[0][1], fq[0][0]))
say("Filtered exact plan (no vector index): " + plan_summary(FULL_PLANS["filtered exact"]))

if DO_M32:
    measure_index(
        "HNSW m=32 efc=128",
        "CREATE INDEX chunks_hnsw32 ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 32, ef_construction = 128)",
        "chunks_hnsw32",
        [("ef_search=40", "SET hnsw.ef_search = 40"), ("ef_search=100", "SET hnsw.ef_search = 100")],
        "hnsw32",
    )
    conn.execute("DROP INDEX chunks_hnsw32")
    conn.commit()

lists = max(10, int(n ** 0.5))
measure_index(
    f"IVFFlat lists={lists}",
    f"CREATE INDEX chunks_ivf ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})",
    "chunks_ivf",
    [("probes=1", "SET ivfflat.probes = 1"), ("probes=10", "SET ivfflat.probes = 10")],
    "ivf",
)
conn.execute("DROP INDEX chunks_ivf")
conn.commit()
conn.close()

# ----------------------------------------------------------------- keyword ---
say(f"\n### Keyword search (N={n}, 38 queries, top-10)")
say("| Backend | median ms | p95 ms |")
say("|---|---|---|")

proc = psutil.Process()
gc.collect()
rss0 = proc.memory_info().rss
clear_bm25_cache()
t0 = time.perf_counter()
bm25_search("warm", 10)
first_ms = (time.perf_counter() - t0) * 1000
gc.collect()
rss1 = proc.memory_info().rss
say(f"| BM25 in-memory: first call (SELECT all rows + tokenise + build) | {first_ms:.0f} (single call) | - |")
say(f"\nBM25 resident memory delta after first build: {(rss1 - rss0) / 1e6:.1f} MB for {n} chunks "
    f"(~{(rss1 - rss0) / max(n, 1) / 1024:.1f} KB/chunk; RSS delta, includes document text copies)")

with bench_lock():
    med, p95, _ = per_query_ms(lambda q: bm25_search(q, 10), queries)
    say(f"| BM25 in-memory: cached index, per query (incl. fingerprint query) | {med:.2f} | {p95:.2f} |")
    # isolate fingerprint cost
    c = get_connection()
    fmed, fp95, _ = per_query_ms(lambda _: bm25_service._fingerprint(c, "", []), [0] * 10, 3)
    c.close()
    say(f"| BM25 fingerprint query alone (count/max/sum hashtext over {n} rows) | {fmed:.2f} | {fp95:.2f} |")
    med, p95, _ = per_query_ms(lambda q: bm25_search(q, 10, document_names=["database_operations_guide.pdf"]), queries[:10], 2)
    say(f"| BM25 single-document scope (cached) | {med:.2f} | {p95:.2f} |")

    # corpus change: insert one row -> next search rebuilds the whole index
    c = get_connection()
    emb = generate_embeddings(["bench row"])[0].tolist()
    c.execute("INSERT INTO document_chunks (document_name, page_number, chunk_id, content, embedding) "
              "VALUES ('bench_extra.pdf', 1, 1, 'bench row extra content', %s)", (emb,))
    c.commit()
    t0 = time.perf_counter()
    bm25_search("bench row", 10)
    rebuild_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    bm25_search("bench row", 10)
    again_ms = (time.perf_counter() - t0) * 1000
    c.execute("DELETE FROM document_chunks WHERE document_name = 'bench_extra.pdf'")
    c.commit()
    c.close()
    say(f"| BM25 after a 1-row insert (full rebuild on next query) | {rebuild_ms:.0f} (single call) | - |")
    say(f"| BM25 next query after rebuild | {again_ms:.1f} (single call) | - |")

    with get_connection() as c:
        med, p95, _ = per_query_ms(lambda q: fts_search(q, 10), queries)
        say(f"| PostgreSQL FTS, no index (seq scan, to_tsvector per row) | {med:.2f} | {p95:.2f} |")
        med, p95, _ = per_query_ms(lambda q: fts_search(q, 10, document_names=["database_operations_guide.pdf"]), queries[:10], 2)
        say(f"| PostgreSQL FTS, no index, 1-document scope | {med:.2f} | {p95:.2f} |")

TSQ = "hnsw | index | recall"
FTS_SQL = ("SELECT id, ts_rank_cd(to_tsvector('english', content), to_tsquery('english', %s)) s FROM document_chunks "
           "WHERE to_tsvector('english', content) @@ to_tsquery('english', %s) ORDER BY s DESC, id LIMIT 10")
with get_connection() as c:
    FULL_PLANS["fts no index"] = explain(c, FTS_SQL, (TSQ, TSQ))
    t0 = time.time()
    c.execute("CREATE INDEX chunks_fts ON document_chunks USING gin (to_tsvector('english', content))")
    c.commit()
    fts_build = time.time() - t0
    c.execute("ANALYZE document_chunks")
    c.commit()
    fts_size = idx_size(c, "chunks_fts")[0]

with bench_lock():
    med, p95, _ = per_query_ms(lambda q: fts_search(q, 10), queries)
    say(f"| PostgreSQL FTS, GIN expression index | {med:.2f} | {p95:.2f} |")
    med, p95, _ = per_query_ms(lambda q: fts_search(q, 10, document_names=["database_operations_guide.pdf"]), queries[:10], 2)
    say(f"| PostgreSQL FTS, GIN index, 1-document scope | {med:.2f} | {p95:.2f} |")
with get_connection() as c:
    FULL_PLANS["fts gin"] = explain(c, FTS_SQL, (TSQ, TSQ))
    c.execute("DROP INDEX chunks_fts")
    c.commit()
say(f"\nGIN FTS index build {fts_build:.2f}s, size {fts_size}")
say("FTS plan without index: " + plan_summary(FULL_PLANS["fts no index"]))
say("FTS plan with GIN: " + plan_summary(FULL_PLANS["fts gin"]))
say("(note: fts_search passes the config as a bound ::regconfig parameter; the GIN index is only usable if the planner "
    "treats it as a constant. Plan above uses literal 'english' like the index; the timing rows use the real service query.)")

# --------------------------------------------------------- filter btree ------
say(f"\n### Document-name filter (N={n})")
DOC = "database_operations_guide.pdf"
FSQL = "SELECT id FROM document_chunks WHERE document_name = ANY(%s) ORDER BY id"
with get_connection() as c:
    FULL_PLANS["docfilter existing"] = explain(c, FSQL, ([DOC],))
    with bench_lock():
        m0, p0, _ = per_query_ms(lambda _: c.execute(FSQL, ([DOC],)).fetchall(), [0] * 20, 5)
    c.execute("CREATE INDEX chunks_docname ON document_chunks (document_name)")
    c.commit()
    c.execute("ANALYZE document_chunks")
    c.commit()
    FULL_PLANS["docfilter extra btree"] = explain(c, FSQL, ([DOC],))
    with bench_lock():
        m1, p1, _ = per_query_ms(lambda _: c.execute(FSQL, ([DOC],)).fetchall(), [0] * 20, 5)
    extra_size = idx_size(c, "chunks_docname")[0]
    uq = c.execute("SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) FROM pg_indexes "
                   "WHERE tablename='document_chunks'").fetchall()
    c.execute("DROP INDEX chunks_docname")
    c.commit()
say(f"- filter plan with only PK + UNIQUE(document_name,page_number,chunk_id): {plan_summary(FULL_PLANS['docfilter existing'])}; median {m0:.3f} ms")
say(f"- filter plan after adding extra btree(document_name) ({extra_size}): {plan_summary(FULL_PLANS['docfilter extra btree'])}; median {m1:.3f} ms")
say(f"- existing indexes: {uq}")

# --------------------------------------------------------- connections -------
say(f"\n### Connection cost")
with bench_lock():
    med, p95, _ = per_query_ms(lambda _: get_connection().close(), [0] * 30, 1)
    say(f"- new psycopg connection + register_vector + close, per call: median {med:.2f} ms, p95 {p95:.2f} ms")
    cc = psycopg.connect(DATABASE_URL)
    med, p95, _ = per_query_ms(lambda _: cc.execute("SELECT 1").fetchone(), [0] * 50, 1)
    say(f"- reused connection, SELECT 1: median {med:.3f} ms, p95 {p95:.3f} ms")
    cc.close()
    from pgvector.psycopg import register_vector
    cc = get_connection()
    q0 = vectors[0]
    med, p95, _ = per_query_ms(lambda _: cc.execute(VSQL, (q0,)).fetchall(), [0] * 30, 1)
    say(f"- reused connection, real vector query (exact scan, N={n}): median {med:.2f} ms")
    cc.close()
    med, p95, _ = per_query_ms(lambda _: generate_embeddings(["How long does a JWT access token live?"]), [0] * 20, 1)
    say(f"- query embedding (CPU, MiniLM, warm): median {med:.1f} ms, p95 {p95:.1f} ms")
try:
    import psycopg_pool  # noqa: F401
    have_pool = True
except ImportError:
    have_pool = False
if have_pool:
    from psycopg_pool import ConnectionPool
    pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=4, configure=register_vector, open=True)
    pool.wait()
    def via_pool(_):
        with pool.connection() as pc:
            pc.execute("SELECT 1").fetchone()
    with bench_lock():
        med, p95, _ = per_query_ms(via_pool, [0] * 50, 1)
    pool.close()
    say(f"- psycopg_pool checkout, SELECT 1: median {med:.3f} ms, p95 {p95:.3f} ms")
else:
    say("- psycopg_pool is NOT installed in .venv; pool timing skipped (not installed per instructions)")

say("\n### Full plans (EXPLAIN ANALYZE, BUFFERS)")
for k, v in FULL_PLANS.items():
    say(f"\n[{k}]")
    for line in v:
        say("    " + line)
say("")

with open(os.path.join(HERE, "results_scale.txt"), "a", encoding="utf-8") as f:
    f.write("\n".join(SHOW) + "\n\n")
