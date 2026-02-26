from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("deltameta_request_count", "Total HTTP requests")
REQUEST_LATENCY = Histogram("deltameta_request_latency_seconds", "Request latency")

