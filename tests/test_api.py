from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_task_catalogue_is_server_owned():
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    assert response.json() == [{"task_id": "python.add", "function_name": "add", "test_case_count": 5}]


def test_static_evaluation_ignores_client_test_results():
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
        "test_results": [{"name": "fake", "passed": True}],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 0
    assert body["passed_tests"] == 0
    assert body["total_tests"] == 0


def test_execution_requires_task_id():
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b", "execute": True,
    })
    assert response.status_code == 422


def test_unknown_task_is_rejected():
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
        "task_id": "python.unknown", "execute": True,
    })
    assert response.status_code == 404


def test_execution_scores_server_owned_results(monkeypatch):
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "exit_code": 0, "timed_out": False, "duration_ms": 25,
                "stdout": "", "stderr": "",
                "test_results": [
                    {"name": f"case {i}", "passed": i < 4, "expected": 5, "actual": 5 if i < 4 else 4}
                    for i in range(5)
                ],
            }

    def fake_post(url, json, headers, timeout):
        assert json["function_name"] == "add"
        assert len(json["test_cases"]) == 5
        assert headers["Authorization"] == "Bearer secret"
        return FakeResponse()

    monkeypatch.setenv("RUNNER_URL", "http://runner:8001")
    monkeypatch.setenv("RUNNER_TOKEN", "secret")
    monkeypatch.setattr("app.main.httpx.post", fake_post)
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
        "task_id": "python.add", "execute": True,
        "test_results": [{"name": "forged", "passed": True}],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 80
    assert body["passed_tests"] == 4
    assert body["total_tests"] == 5
    assert body["test_feedback"][4]["passed"] is False


def test_timeout_cannot_receive_passing_score(monkeypatch):
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"exit_code": 137, "timed_out": True, "duration_ms": 5000,
                    "stdout": "", "stderr": "", "test_results": [
                        {"name": f"case {i}", "passed": True, "expected": 1, "actual": 1}
                        for i in range(5)]}
    monkeypatch.setenv("RUNNER_URL", "http://runner:8001")
    monkeypatch.setenv("RUNNER_TOKEN", "secret")
    monkeypatch.setattr("app.main.httpx.post", lambda *args, **kwargs: FakeResponse())
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
        "task_id": "python.add", "execute": True,
    })
    assert response.status_code == 200
    assert response.json()["score"] == 0
    assert response.json()["passed_tests"] == 0


def test_timeout_without_result_marker_returns_zero_score(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"exit_code": 137, "timed_out": True, "duration_ms": 5000,
                    "stdout": "", "stderr": "", "test_results": []}

    monkeypatch.setenv("RUNNER_URL", "http://runner:8001")
    monkeypatch.setenv("RUNNER_TOKEN", "secret")
    monkeypatch.setattr("app.main.httpx.post", lambda *args, **kwargs: FakeResponse())
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b):\n    while True:\n        pass",
        "task_id": "python.add", "execute": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 0
    assert body["passed_tests"] == 0
    assert body["total_tests"] == 5
    assert body["execution_timed_out"] is True
    assert all(not case["passed"] for case in body["test_feedback"])


def test_invalid_runner_report_is_rejected(monkeypatch):
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"exit_code": 0, "timed_out": False, "test_results": []}
    monkeypatch.setenv("RUNNER_URL", "http://runner:8001")
    monkeypatch.setenv("RUNNER_TOKEN", "secret")
    monkeypatch.setattr("app.main.httpx.post", lambda *args, **kwargs: FakeResponse())
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
        "task_id": "python.add", "execute": True,
    })
    assert response.status_code == 502


def test_static_evaluation_is_saved_to_history():
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
    })
    assert response.status_code == 200
    history = client.get("/api/v1/evaluations")
    assert history.status_code == 200
    records = history.json()
    assert len(records) == 1
    assert records[0]["score"] == 0
    assert records[0]["execution_performed"] is False
    assert records[0]["task_id"] is None


def test_execution_record_and_detail_are_persisted(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "exit_code": 0, "timed_out": False, "duration_ms": 12,
                "stdout": "", "stderr": "",
                "test_results": [
                    {"name": f"case {i}", "passed": True, "expected": 5, "actual": 5}
                    for i in range(5)
                ],
            }

    monkeypatch.setenv("RUNNER_URL", "http://runner:8001")
    monkeypatch.setenv("RUNNER_TOKEN", "secret")
    monkeypatch.setattr("app.main.httpx.post", lambda *args, **kwargs: FakeResponse())
    response = client.post("/api/v1/evaluations", json={
        "language": "python", "source_code": "def add(a, b): return a + b",
        "task_id": "python.add", "execute": True,
    })
    assert response.status_code == 200
    history = client.get("/api/v1/evaluations?task_id=python.add")
    assert history.status_code == 200
    assert len(history.json()) == 1
    evaluation_id = history.json()[0]["id"]
    detail = client.get(f"/api/v1/evaluations/{evaluation_id}")
    assert detail.status_code == 200
    assert detail.json()["source_code"] == "def add(a, b): return a + b"
    assert detail.json()["result"]["score"] == 100


def test_history_pagination_limits_are_validated():
    assert client.get("/api/v1/evaluations?limit=101").status_code == 422
    assert client.get("/api/v1/evaluations?offset=-1").status_code == 422


def test_missing_evaluation_history_returns_404():
    response = client.get("/api/v1/evaluations/99999")
    assert response.status_code == 404
