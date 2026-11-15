import threading
from collections import OrderedDict

from sentence_transformers import SentenceTransformer

from services import perf_metrics
from services import retrieval_config as cfg

# Load the configured embedding model (default "all-MiniLM-L6-v2", override
# with the EMBEDDING_MODEL environment variable). Vectors stored with one model
# are NOT comparable with vectors from another, even if the dimensions match.
with perf_metrics.timed("embedding.model_init"):
    model = SentenceTransformer(cfg.EMBEDDING_MODEL)

# Phase 5: bounded LRU cache for SINGLE-text calls (query and single-memory
# embeddings). The model is deterministic for a given text, so a cache hit
# returns exactly what encode() would. Key = (model name, exact text); no
# normalization is applied to the key. Batches (ingestion) are never cached.
# Values are copied on the way in and out so callers cannot mutate the cache.
# In-process only, cleared on restart; EMBEDDING_QUERY_CACHE_SIZE=0 disables it.
_query_cache = OrderedDict()
_query_cache_lock = threading.Lock()


def _cache_get(key):
    with _query_cache_lock:
        value = _query_cache.get(key)
        if value is not None:
            _query_cache.move_to_end(key)
            return value.copy()
    return None


def _cache_put(key, value):
    limit = cfg.EMBEDDING_QUERY_CACHE_SIZE
    if limit <= 0:
        return
    with _query_cache_lock:
        _query_cache[key] = value.copy()
        _query_cache.move_to_end(key)
        while len(_query_cache) > limit:
            _query_cache.popitem(last=False)


def clear_embedding_cache():
    with _query_cache_lock:
        _query_cache.clear()


def generate_embeddings(texts: list[str]):

    single = (
        cfg.EMBEDDING_QUERY_CACHE_SIZE > 0
        and isinstance(texts, list)
        and len(texts) == 1
        and isinstance(texts[0], str)
    )

    if single:
        key = (cfg.EMBEDDING_MODEL, texts[0])
        cached = _cache_get(key)
        if cached is not None:
            perf_metrics.count("embedding.query_cache.hit")
            return cached
        perf_metrics.count("embedding.query_cache.miss")

    with perf_metrics.timed("embedding.encode", batch=len(texts) if hasattr(texts, "__len__") else 0):
        embeddings = model.encode(
            texts,
            normalize_embeddings=True
        )

    if single:
        _cache_put(key, embeddings)

    return embeddings
