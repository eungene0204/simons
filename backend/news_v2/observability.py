"""
Prometheus metrics for news_v2.

Optional dependency: if prometheus_client isn't installed, all calls are no-ops.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram

    _HAS_PROM = True
except ImportError:  # pragma: no cover
    _HAS_PROM = False


class _NoopMetric:
    def labels(self, *a: Any, **kw: Any) -> "_NoopMetric":
        return self

    def inc(self, *a: Any, **kw: Any) -> None: ...

    def dec(self, *a: Any, **kw: Any) -> None: ...

    def observe(self, *a: Any, **kw: Any) -> None: ...

    def set(self, *a: Any, **kw: Any) -> None: ...


if _HAS_PROM:
    request_total = Counter(
        "newsv2_request_total", "Total requests served", ["status", "source"]
    )
    request_latency = Histogram(
        "newsv2_request_latency_seconds", "Request latency", ["route"]
    )
    cache_hits = Counter(
        "newsv2_cache_hits_total", "Cache hits", ["layer"]
    )
    collect_runs = Counter(
        "newsv2_collect_runs_total", "Collect runs", ["provider", "status"]
    )
    collect_latency = Histogram(
        "newsv2_collect_latency_seconds", "Collect latency", ["provider"]
    )
    dedup_rate = Gauge(
        "newsv2_dedup_rate", "Dedup rate per provider", ["provider"]
    )
    ai_calls = Counter(
        "newsv2_ai_calls_total", "AI agent calls", ["model", "outcome"]
    )
    queue_depth = Gauge(
        "newsv2_queue_depth", "Celery queue depth", ["queue"]
    )
    dlq_size = Gauge("newsv2_dlq_size", "DLQ size")
else:  # pragma: no cover
    request_total = _NoopMetric()
    request_latency = _NoopMetric()
    cache_hits = _NoopMetric()
    collect_runs = _NoopMetric()
    collect_latency = _NoopMetric()
    dedup_rate = _NoopMetric()
    ai_calls = _NoopMetric()
    queue_depth = _NoopMetric()
    dlq_size = _NoopMetric()
