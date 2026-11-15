"""Phase 5 — low-overhead, in-process performance instrumentation.

Disabled by default (RAG_PERF_METRICS=1 enables it). When disabled every call
is a cheap no-op. When enabled it keeps BOUNDED aggregates per operation name:
call count, total/min/max duration, last input/output sizes, and named counters
(cache hits/misses, candidate counts, batch sizes). It never records content:
callers pass names and integers only (no document text, memory text, prompts,
queries, keys or credentials).

    from services.perf_metrics import timed, count
    with timed("embedding.encode", batch=len(texts)):
        ...
    count("embedding.query_cache.hit")

``snapshot()`` returns a copy of the aggregates; ``reset()`` clears them.
Nothing is written to disk or the network.
"""

import threading
import time
from contextlib import contextmanager

from services import retrieval_config as cfg

MAX_OPERATIONS = 200          # distinct operation/counter names kept (bounded)

_lock = threading.Lock()
_timings = {}
_counters = {}


def enabled() -> bool:
    return bool(cfg.PERF_METRICS_ENABLED)


@contextmanager
def timed(name: str, **sizes):
    """Time a block; ``sizes`` are integers (batch size, candidate count, ...)."""
    if not enabled():
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        # Never 'return' here: that would swallow an exception raised inside
        # the timed block. Recording is a side effect only.
        _record(name, time.perf_counter() - start, sizes)


def _record(name, elapsed, sizes):
    with _lock:
        entry = _timings.get(name)
        if entry is None:
            if len(_timings) >= MAX_OPERATIONS:
                return
            entry = _timings[name] = {"calls": 0, "total_s": 0.0, "min_s": None, "max_s": 0.0, "last_sizes": {}}
        entry["calls"] += 1
        entry["total_s"] += elapsed
        entry["min_s"] = elapsed if entry["min_s"] is None else min(entry["min_s"], elapsed)
        entry["max_s"] = max(entry["max_s"], elapsed)
        entry["last_sizes"] = {k: int(v) for k, v in sizes.items() if isinstance(v, (int, float))}


def count(name: str, amount: int = 1):
    if not enabled():
        return
    with _lock:
        if name not in _counters and len(_counters) >= MAX_OPERATIONS:
            return
        _counters[name] = _counters.get(name, 0) + int(amount)


def snapshot() -> dict:
    with _lock:
        return {
            "timings": {k: dict(v, last_sizes=dict(v["last_sizes"])) for k, v in _timings.items()},
            "counters": dict(_counters),
        }


def reset():
    with _lock:
        _timings.clear()
        _counters.clear()
