from fastapi.testclient import TestClient

import runner.main as runner_main

client = TestClient(runner_main.app)
PAYLOAD = {
    "source_code": "def add(a, b): return a + b",
    "function_name": "add",
    "test_cases": [{"name": "basic", "args": [2, 3], "expected": 5}],
}


def test_runner_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("RUNNER_TOKEN", raising=False)
    response = client.post("/internal/execute", json=PAYLOAD)
    assert response.status_code == 401


def test_runner_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("RUNNER_TOKEN", "expected-secret")
    response = client.post("/internal/execute", headers={"Authorization": "Bearer wrong"}, json=PAYLOAD)
    assert response.status_code == 401


def test_runner_rejects_oversized_source():
    response = client.post("/internal/execute", headers={"Authorization": "Bearer token"},
                           json={**PAYLOAD, "source_code": "x" * 32_001})
    assert response.status_code == 422


def test_runner_requires_at_least_one_trusted_test():
    response = client.post("/internal/execute", headers={"Authorization": "Bearer token"},
                           json={**PAYLOAD, "test_cases": []})
    assert response.status_code == 422


def test_runner_executes_through_engine_after_authentication(monkeypatch):
    monkeypatch.setenv("RUNNER_TOKEN", "expected-secret")

    class FakeEngine:
        def execute(self, source_code, *, function_name, test_cases):
            assert source_code == PAYLOAD["source_code"]
            assert function_name == "add"
            assert test_cases[0]["expected"] == 5
            return {"exit_code": 0, "timed_out": False, "duration_ms": 4.2,
                    "stdout": "", "stderr": "",
                    "test_results": [{"name": "basic", "passed": True, "expected": 5, "actual": 5}]}

    monkeypatch.setattr(runner_main, "DockerExecutionEngine", FakeEngine)
    response = client.post("/internal/execute", headers={"Authorization": "Bearer expected-secret"},
                           json=PAYLOAD)
    assert response.status_code == 200
    assert response.json()["test_results"][0]["passed"] is True
