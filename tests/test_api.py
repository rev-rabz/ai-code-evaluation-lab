from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_evaluation_endpoint_returns_structured_result() -> None:
    response = client.post(
        "/api/v1/evaluations",
        json={
            "language": "python",
            "source_code": "def add(a, b):\n    return a + b\n",
            "required_functions": ["add"],
            "test_results": [
                {"name": "adds two numbers", "passed": True, "expected": 5, "actual": 5}
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "valid"
    assert body["score"] == 100
    assert body["execution_performed"] is False
    assert body["execution_requested"] is False
    assert "untrusted" in body["note"]
    assert "not executed" not in body["note"]


def test_evaluation_endpoint_rejects_unsupported_language() -> None:
    response = client.post(
        "/api/v1/evaluations",
        json={"language": "javascript", "source_code": "function add(a, b) { return a + b; }"},
    )

    assert response.status_code == 422


def test_evaluation_endpoint_rejects_empty_source() -> None:
    response = client.post(
        "/api/v1/evaluations",
        json={"language": "python", "source_code": ""},
    )

    assert response.status_code == 422


def test_execution_requires_runner_configuration(monkeypatch) -> None:
    monkeypatch.delenv("RUNNER_URL", raising=False)
    monkeypatch.delenv("RUNNER_TOKEN", raising=False)

    response = client.post(
        "/api/v1/evaluations",
        json={"language": "python", "source_code": "print('hello')", "execute": True},
    )

    assert response.status_code == 503


def test_execution_response_is_returned_from_internal_runner(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 12.5,
                "stdout": "hello\n",
                "stderr": "",
            }

    def fake_post(url, json, headers, timeout):
        assert url == "http://runner:8001/internal/execute"
        assert json["source_code"] == "print('hello')"
        assert headers["Authorization"] == "Bearer test-secret"
        assert timeout == 8.0
        return FakeResponse()

    monkeypatch.setenv("RUNNER_URL", "http://runner:8001")
    monkeypatch.setenv("RUNNER_TOKEN", "test-secret")
    monkeypatch.setattr("app.main.httpx.post", fake_post)

    response = client.post(
        "/api/v1/evaluations",
        json={"language": "python", "source_code": "print('hello')", "execute": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_requested"] is True
    assert body["execution_performed"] is True
    assert body["execution_exit_code"] == 0
    assert body["stdout"] == "hello\n"
    assert "untrusted" in body["note"]
    assert "not executed" not in body["note"]
