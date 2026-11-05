import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "ai_code_eval_http_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "route", "status_code"],
)
REQUEST_DURATION = Histogram(
    "ai_code_eval_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

request_logger = logging.getLogger("app.request")


def install_observability(app: FastAPI) -> None:
    # Uvicorn configures its own loggers but may leave the root logger at WARNING
    # with no handler. Configure a root stream so app.request INFO events reach
    # the container logs, while preserving any handler installed by the host.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(stream_handler)

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        finally:
            duration = time.perf_counter() - started_at
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            method = request.method

            # Avoid self-observation and unbounded labels for arbitrary unmatched paths.
            if route_template != "/metrics":
                REQUEST_COUNT.labels(method, route_template, str(status_code)).inc()
                REQUEST_DURATION.labels(method, route_template).observe(duration)

            request_logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": method,
                        "route": route_template,
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 2),
                    },
                    separators=(",", ":"),
                )
            )
