import json
import logging

from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.main import app
from app.rate_limit import enforce_rate_limit, get_redis

client = TestClient(app)


class MemoryRedis:
    def __init__(self):
        self.counts = {}

    def eval(self, script, number_of_keys, key, window_seconds):
        assert number_of_keys == 1
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return [count, window_seconds]

    def ping(self):
        return True


def test_rate_limit_uses_hashed_identity_and_returns_retry_after():
    redis_client = MemoryRedis()

    first = enforce_rate_limit(redis_client, "test", "192.0.2.10", 2, 60)
    second = enforce_rate_limit(redis_client, "test", "192.0.2.10", 2, 60)

    assert first["X-RateLimit-Remaining"] == "1"
    assert second["X-RateLimit-Remaining"] == "0"
    stored_key = next(iter(redis_client.counts))
    assert "192.0.2.10" not in stored_key

    try:
        enforce_rate_limit(redis_client, "test", "192.0.2.10", 2, 60)
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.headers["Retry-After"] == "60"
        assert exc.headers["X-RateLimit-Limit"] == "2"
    else:
        raise AssertionError("Expected the third request to be rate limited.")


def test_register_endpoint_enforces_ip_rate_limit():
    responses = []
    for index in range(5):
        responses.append(
            client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"limited-{index}@example.com",
                    "password": "Correct-Horse-2026!",
                },
            )
        )

    assert all(response.status_code == 201 for response in responses)
    assert responses[-1].headers["X-RateLimit-Remaining"] == "0"

    blocked = client.post(
        "/api/v1/auth/register",
        json={"email": "limited-sixth@example.com", "password": "Correct-Horse-2026!"},
    )
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "3600"


def test_evaluation_creation_is_rate_limited_per_user():
    for _ in range(30):
        response = client.post(
            "/api/v1/evaluations",
            json={"language": "python", "source_code": "def add(a, b): return a + b"},
        )
        assert response.status_code == 200

    blocked = client.post(
        "/api/v1/evaluations",
        json={"language": "python", "source_code": "def add(a, b): return a + b"},
    )
    assert blocked.status_code == 429


def test_rate_limiter_fails_closed_when_redis_is_unavailable():
    class UnavailableRedis:
        def eval(self, *args, **kwargs):
            raise RedisError("connection refused")

    app.dependency_overrides[get_redis] = lambda: UnavailableRedis()
    try:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "incorrect-password"},
        )
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert response.status_code == 503
    assert "Rate limiting" in response.json()["detail"]


def test_liveness_and_readiness_endpoints():
    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "dependencies": {"database": "ok", "redis": "ok"}}


def test_readiness_fails_when_redis_is_unavailable():
    class UnavailableRedis:
        def ping(self):
            raise RedisError("connection refused")

    app.dependency_overrides[get_redis] = lambda: UnavailableRedis()
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert response.status_code == 503


def test_metrics_endpoint_requires_configured_bearer_token(monkeypatch):
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    hidden = client.get("/metrics")
    assert hidden.status_code == 404

    monkeypatch.setenv("METRICS_TOKEN", "metrics-secret")
    denied = client.get("/metrics")
    assert denied.status_code == 401

    allowed = client.get("/metrics", headers={"Authorization": "Bearer metrics-secret"})
    assert allowed.status_code == 200
    assert "ai_code_eval_http_requests_total" in allowed.text


def test_request_id_and_security_headers_are_returned(caplog):
    caplog.set_level(logging.INFO, logger="app.request")
    response = client.get("/health/live", headers={"Authorization": "Bearer do-not-log-this"})

    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 32
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "do-not-log-this" not in caplog.text

    events = [json.loads(record.getMessage()) for record in caplog.records if record.name == "app.request"]
    assert any(event["event"] == "http_request" and event["route"] == "/health/live" for event in events)


def test_structured_request_logger_is_enabled_at_info_level():
    assert logging.getLogger("app.request").getEffectiveLevel() <= logging.INFO
