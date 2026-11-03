import json

from fastapi.testclient import TestClient

from app.ai_review_service import REVIEW_JSON_SCHEMA
from app.main import app

client = TestClient(app)


def _create_evaluation(source_code: str = "def add(a, b):\n    return a - b") -> int:
    response = client.post(
        "/api/v1/evaluations",
        json={"language": "python", "source_code": source_code},
    )
    assert response.status_code == 200
    history = client.get("/api/v1/evaluations")
    assert history.status_code == 200
    return history.json()[0]["id"]


def _provider_payload(review: dict) -> dict:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(review)}],
            }
        ],
    }


def _valid_review() -> dict:
    return {
        "summary": "The function is syntactically valid but subtracts instead of adding.",
        "strengths": ["The implementation is concise."],
        "findings": [
            {
                "category": "correctness",
                "severity": "error",
                "title": "Wrong arithmetic operator",
                "explanation": "The function subtracts b from a, which does not implement addition.",
                "evidence": {
                    "line_start": 2,
                    "line_end": 2,
                    "code_excerpt": "    return a - b",
                },
                "suggestion": "Use the addition operator so the function returns a + b.",
            }
        ],
        "next_steps": ["Add tests for positive, negative, and zero inputs."],
    }


def test_ai_review_is_opt_in_and_persisted(monkeypatch):
    evaluation_id = _create_evaluation()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return _provider_payload(_valid_review())

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        assert url == "https://api.openai.com/v1/responses"
        assert json["store"] is False
        assert json["text"]["format"]["schema"] == REVIEW_JSON_SCHEMA
        assert headers["Authorization"] == "Bearer test-key"
        return FakeResponse()

    monkeypatch.setattr("app.ai_review_service.httpx.post", fake_post)

    created = client.post(f"/api/v1/evaluations/{evaluation_id}/review")
    assert created.status_code == 200
    body = created.json()
    assert body["evaluation_id"] == evaluation_id
    assert body["review"]["findings"][0]["evidence"]["line_start"] == 2
    assert len(calls) == 1

    fetched = client.get(f"/api/v1/evaluations/{evaluation_id}/review")
    assert fetched.status_code == 200
    assert fetched.json() == body

    repeated = client.post(f"/api/v1/evaluations/{evaluation_id}/review")
    assert repeated.status_code == 200
    assert repeated.json() == body
    assert len(calls) == 1


def test_ai_review_requires_provider_configuration(monkeypatch):
    evaluation_id = _create_evaluation()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(f"/api/v1/evaluations/{evaluation_id}/review")
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_ai_review_rejects_unowned_evaluations():
    evaluation_id = _create_evaluation()
    from app.auth import get_current_user
    from app.models import User

    app.dependency_overrides[get_current_user] = lambda: User(
        id=99,
        email="other@example.com",
        hashed_password="not-used",
        is_admin=False,
    )
    response = client.post(f"/api/v1/evaluations/{evaluation_id}/review")
    assert response.status_code == 404


def test_ai_review_rejects_unverifiable_evidence(monkeypatch):
    evaluation_id = _create_evaluation()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    invalid_review = _valid_review()
    invalid_review["findings"][0]["evidence"]["code_excerpt"] = "return a + b"

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return _provider_payload(invalid_review)

    monkeypatch.setattr("app.ai_review_service.httpx.post", lambda *args, **kwargs: FakeResponse())
    response = client.post(f"/api/v1/evaluations/{evaluation_id}/review")
    assert response.status_code == 502
    assert "does not exactly match" in response.json()["detail"]
    assert client.get(f"/api/v1/evaluations/{evaluation_id}/review").status_code == 404


def test_ai_review_rejects_source_above_limit(monkeypatch):
    evaluation_id = _create_evaluation("x" * 25_001)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = client.post(f"/api/v1/evaluations/{evaluation_id}/review")
    assert response.status_code == 413
