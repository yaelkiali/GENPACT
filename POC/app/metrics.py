# app/metrics.py
# Prometheus metrics — exposed for Grafana integration
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Total requests sent — partitioned by model
REQUESTS_TOTAL = Counter(
    "ai_requests_total",
    "Total AI chat requests",
    ["model", "status"],
)

# Response time — Histogram computes mean, percentiles, etc.
REQUEST_DURATION = Histogram(
    "ai_request_duration_seconds",
    "Request duration in seconds",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# Token counters
TOKENS_TOTAL = Counter(
    "ai_tokens_total",
    "Total tokens processed",
    ["model", "direction"],  # direction = "input" / "output"
)


def get_metrics_response():
    """Returns all metrics in Prometheus exposition format."""
    return generate_latest(), CONTENT_TYPE_LATEST
