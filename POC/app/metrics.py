# app/metrics.py
# מטריקות Prometheus — דודו יחבר אותן ל-Grafana
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# כמה בקשות נשלחו — לפי מודל
REQUESTS_TOTAL = Counter(
    "ai_requests_total",
    "Total AI chat requests",
    ["model", "status"],
)

# זמן תגובה — Histogram מחשב ממוצע, percentiles וכו'
REQUEST_DURATION = Histogram(
    "ai_request_duration_seconds",
    "Request duration in seconds",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

# טוקנים
TOKENS_TOTAL = Counter(
    "ai_tokens_total",
    "Total tokens processed",
    ["model", "direction"],  # direction = "input" / "output"
)


def get_metrics_response():
    """מחזיר את כל המטריקות בפורמט שפרומתאוס מבין."""
    return generate_latest(), CONTENT_TYPE_LATEST
