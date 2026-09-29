"""Prometheus metrics, served at GET /metrics.

Prometheus (Phase 7) scrapes this endpoint. Two kinds of metric:
- about the API itself: request counts and latency
- about the monitored sites: site_up and site_response_ms, refreshed from the
  database on every scrape, so they include checks made by the CronJob too.
"""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time spent handling HTTP requests",
    ["method", "path"],
)
SITE_UP = Gauge("site_up", "1 if the last check of the site succeeded, else 0", ["site"])
SITE_RESPONSE_MS = Gauge(
    "site_response_ms", "Response time of the last successful check, in ms", ["site"]
)
