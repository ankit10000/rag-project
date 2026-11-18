import threading
from collections import OrderedDict

from sentence_transformers import SentenceTransformer

from services import perf_metrics
from services import retrieval_config as cfg
from services.local_release_profile import require_embedding_model

# The configured embedding model (default "all-MiniLM-L6-v2", override with the
# EMBEDDING_MODEL environment variable). Vectors stored with one model are NOT
# comparable with vectors from another, even if the dimensions match.
#
# Batch 1: loaded lazily on the first embedding request (get_model), not at
# import, so importing services/the API never loads or downloads the model.
# Loaded once per process (lock-protected); a failed load is not cached, so the
# next request retries. ``embedding_service.model`` still works (module
# __getattr__ below) and triggers the same lazy load.
_model = None
_model_name = None
_model_lock = threading.Lock()


class EmbeddingModelLoadError(RuntimeError):
    """The configured embedding model could not be initialised."""


class EmbeddingModelMismatchError(ValueError):
    """A configuration change would reuse vectors from another loaded model."""


def _verify_model_configuration():
    require_embedding_model(cfg.EMBEDDING_MODEL)
    if _model is not None and _model_name is not None and _model_name != cfg.EMBEDDING_MODEL:
        raise EmbeddingModelMismatchError(
            "EMBEDDING_MODEL changed after model initialization; restart with "
            "the original index model or rebuild a verified empty index"
        )


def get_model():
    global _model, _model_name
    _verify_model_configuration()
    loaded = _model
    if loaded is not None:
        return loaded

    with _model_lock:
        _verify_model_configuration()
        if _model is None:
            name = cfg.EMBEDDING_MODEL
            try:
                with perf_metrics.timed("embedding.model_init"):
                    _model = SentenceTransformer(name)
                    _model_name = name
            except Exception as error:
                raise EmbeddingModelLoadError(
                    f"could not load embedding model {name!r} "
                    f"({type(error).__name__}: {error}); check EMBEDDING_MODEL and the "
                    "local Hugging Face cache (HF_HUB_OFFLINE=1 forbids downloads)"
                ) from error
        return _model


def is_model_loaded() -> bool:
    return _model is not None


def __getattr__(name):
    if name == "model":
        return get_model()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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

    # Check before cache lookup too: a warm cache must not bypass a model pin
    # or silently encode with the old model under a newly configured cache key.
    _verify_model_configuration()

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
        embeddings = get_model().encode(
            texts,
            normalize_embeddings=True
        )

    if single:
        _cache_put(key, embeddings)

    return embeddings
