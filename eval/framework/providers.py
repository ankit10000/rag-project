"""Provider/model attribution and usage summaries (provider-independent, pure).

No SDK import, no API key access, no network. Inputs are whatever a run
already recorded: per-call usage records (e.g. services/llm_service.usage_log
entries {"model", "prompt", "output", "total"}), per-case rows (latency_s,
llm_calls, prompt_tokens, output_tokens) and optional run-log text.
Fields a source cannot supply are reported as "unavailable", never guessed.
"""

import re
from dataclasses import asdict, dataclass, field

UNAVAILABLE = "unavailable"

# Log lines already printed by services/llm_service.py and gemini_retry_service.py.
_FALLBACK = re.compile(r"model '([^']+)' failed \((\d+)\); trying next model")
_TIMEOUT = re.compile(r"model '([^']+)' timed out after")
_RETRY = re.compile(r"temporary error (\d+)\. Retrying in")
_QUOTA_WAIT = re.compile(r"All .* models are out of quota; waiting")


@dataclass
class RunAttribution:
    provider: str = UNAVAILABLE
    configured_models: list = field(default_factory=list)   # e.g. primary + fallbacks (names only)
    models_observed: list = field(default_factory=list)     # only from per-call records that carry a model
    model_version: str = UNAVAILABLE
    prompt_tokens: object = UNAVAILABLE
    completion_tokens: object = UNAVAILABLE
    total_tokens: object = UNAVAILABLE
    llm_calls: object = UNAVAILABLE
    latency_seconds: dict = field(default_factory=dict)
    retries: object = UNAVAILABLE
    timeouts: object = UNAVAILABLE
    fallbacks: object = UNAVAILABLE
    quota_waits: object = UNAVAILABLE
    errors: object = UNAVAILABLE
    attribution_note: str = ""

    def as_dict(self):
        return asdict(self)


def _percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, min(len(values) - 1, int(round(p / 100 * (len(values) - 1)))))]


def summarize_rows(rows, provider=UNAVAILABLE, configured_models=None, usage_records=None, log_text=None):
    att = RunAttribution(provider=provider, configured_models=list(configured_models or []))
    lat = []
    for r in rows:
        try:
            value = float(r.get("latency_s"))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            lat.append(value)
    if lat:
        att.latency_seconds = {"median": _percentile(lat, 50), "p90": _percentile(lat, 90),
                               "max": max(lat), "total": sum(lat), "n": len(lat)}

    def total(key):
        vals = [r.get(key) for r in rows]
        if not vals or any(v is None for v in vals):
            return UNAVAILABLE
        try:
            return sum(int(v) for v in vals)
        except (TypeError, ValueError):
            return UNAVAILABLE

    att.prompt_tokens = total("prompt_tokens")
    att.completion_tokens = total("output_tokens")
    att.llm_calls = total("llm_calls")
    if isinstance(att.prompt_tokens, int) and isinstance(att.completion_tokens, int):
        att.total_tokens = att.prompt_tokens + att.completion_tokens
    att.errors = sum(1 for r in rows if str(r.get("answer", "")).startswith("RUNNER ERROR") or r.get("status") == "error")

    if usage_records:
        att.models_observed = sorted({u.get("model") for u in usage_records if u.get("model")})

    if log_text is not None:
        att.fallbacks = len(_FALLBACK.findall(log_text))
        att.timeouts = len(_TIMEOUT.findall(log_text))
        att.retries = len(_RETRY.findall(log_text))
        att.quota_waits = len(_QUOTA_WAIT.findall(log_text))
        att.attribution_note = (
            "Per-answer model attribution is not stored by the current runner; model switches are "
            "inferred from fallback log lines. A quota cooldown can route calls to a fallback model "
            "without any log line, so exact per-call attribution is unavailable."
        )
    return att


def compare_providers(runs: dict) -> dict:
    """runs: {label: {"attribution": RunAttribution|dict, "correct": int, "cases": int}} -> side-by-side table."""
    table = {}
    for label, run in sorted(runs.items()):
        att = run["attribution"].as_dict() if hasattr(run["attribution"], "as_dict") else run["attribution"]
        table[label] = {"provider": att.get("provider"), "models": att.get("models_observed") or att.get("configured_models"),
                        "correct": run.get("correct"), "cases": run.get("cases"),
                        "accuracy": (run["correct"] / run["cases"]) if run.get("cases") else None,
                        "prompt_tokens": att.get("prompt_tokens"), "completion_tokens": att.get("completion_tokens"),
                        "latency": att.get("latency_seconds"), "fallbacks": att.get("fallbacks"),
                        "timeouts": att.get("timeouts"), "errors": att.get("errors")}
    return table
