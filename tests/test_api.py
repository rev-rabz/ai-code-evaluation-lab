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
