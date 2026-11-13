"""Prometheus metrics with an isolated registry (safe under repeated app factories)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "analystforge_http_requests_total",
    "HTTP requests processed",
    labelnames=("method", "route", "status"),
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "analystforge_http_request_duration_seconds",
    "HTTP request latency",
    labelnames=("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.75, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)
PROVIDER_REQUESTS = Counter(
    "analystforge_provider_requests_total",
    "Calls made to external data providers",
    labelnames=("provider", "operation", "outcome"),
    registry=REGISTRY,
)
PROVIDER_LATENCY = Histogram(
    "analystforge_provider_latency_seconds",
    "Latency of external data provider calls",
    labelnames=("provider", "operation"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)
JOBS_TOTAL = Counter(
    "analystforge_jobs_total",
    "Background jobs by kind and outcome",
    labelnames=("kind", "outcome"),
    registry=REGISTRY,
)
ALERTS_FIRED = Counter(
    "analystforge_alerts_fired_total",
    "Alerts fired by channel",
    labelnames=("channel",),
    registry=REGISTRY,
)
READY = Gauge(
    "analystforge_ready",
    "1 when the latest readiness probe succeeded",
    registry=REGISTRY,
)
