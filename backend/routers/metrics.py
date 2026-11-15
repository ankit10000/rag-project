"""Read-only view of Phase 5 in-process metrics (names and numbers only)."""

from fastapi import APIRouter

from backend.schemas import MetricsResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/performance", response_model=MetricsResponse)
def performance():
    from services import perf_metrics

    snap = perf_metrics.snapshot()
    return MetricsResponse(
        enabled=perf_metrics.enabled(),
        timings=snap["timings"],
        counters=snap["counters"],
        note=("In-process aggregates since start (RAG_PERF_METRICS=1 to enable). Contains operation "
              "names and numbers only; not a benchmark."),
    )
