# Stage 9 — API Hardening and Observability

## Goals

Reduce abuse of expensive endpoints, make service health observable, and give operators enough request context to investigate failures without logging credentials or submitted code.

## Scope

1. Add Redis-backed fixed-window rate limits for account registration, login, evaluation creation, and AI review generation.
2. Hash rate-limit identities before storing Redis keys. Do not trust `X-Forwarded-For` without an explicit trusted-proxy configuration.
3. Fail closed with HTTP 503 when Redis cannot enforce a rate limit; do not silently fall back to per-process memory counters.
4. Add liveness and readiness endpoints. Readiness verifies database and Redis connectivity.
5. Add request IDs, structured request logs, basic HTTP security headers, and Prometheus request counters/latency histograms.
6. Protect the metrics endpoint with an optional bearer token; leave it disabled when no token is configured.
7. Add tests for rate-limit behavior, Redis failure, health checks, metrics access, request IDs, and sensitive-log exclusion.

## Rate-limit policy

Initial fixed-window defaults:

| Operation | Identity | Limit |
|---|---|---:|
| Account registration | Client IP | 5 per hour |
| Login | Client IP | 10 per minute |
| Evaluation creation | User ID | 30 per hour |
| AI review request | User ID | 5 per hour |

Limits are enforced by a Redis atomic increment/expiry script and apply across API processes sharing the same Redis instance. Rate-limit keys contain an HMAC digest of the identity, not the raw IP address or user ID. The current client IP is the direct ASGI peer address; forwarded headers are ignored because trusted proxies are not configured.

These are starting defaults, not a substitute for edge/WAF protection against distributed abuse. Repeated AI-review POSTs count against the rate limit even when a cached review is returned.

## Redis configuration

Docker Compose starts a private Redis service for ephemeral rate-limit counters. Configure `REDIS_URL` for other deployments. Redis is not used as the system of record; losing its counters resets active windows but does not affect PostgreSQL evaluation or review history.

The rate-limited endpoints return HTTP 503 when Redis is unavailable rather than bypassing protection. `/health/live` remains available to indicate that the process is running; `/health/ready` returns 503 if PostgreSQL or Redis is unavailable.

## Observability

- Every HTTP response includes an opaque `X-Request-ID`.
- One-line JSON request logs include request ID, method, matched route template, status code, and duration in milliseconds.
- Logs deliberately exclude headers, query strings, request bodies, source code, IP addresses, and exception details.
- Security response headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`.
- Prometheus metrics count requests by method, route template and status code, and record request duration. Unmatched paths use a fixed label to avoid high-cardinality labels. The `/metrics` scrape is excluded from its own counters.
- `GET /metrics` returns 404 unless `METRICS_TOKEN` is configured; when enabled, it requires `Authorization: Bearer <METRICS_TOKEN>`.

## Limitations and future work

- Fixed-window limits can allow bursts around window boundaries. An edge proxy/WAF, distributed abuse detection, and per-account/email-based login throttling remain useful future controls.
- Metrics are process-local Prometheus counters and histograms; each API replica exposes its own metrics for Prometheus scraping.
- No external error-reporting service, distributed tracing, dashboards, alerting, or AI concurrency semaphore is included in this stage.
- Forwarded client IP support must only be enabled after configuring explicit trusted proxy ranges.
