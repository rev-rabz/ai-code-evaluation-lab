import runner.main as runner_main
from fastapi.testclient import TestClient


client = TestClient(runner_main.app)


def test_runner_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.delenv("RUNNER_TOKEN", raising=False)
    response = client.post(
        "/internal/execute",
        json={"source_code": "print('hello')"},
    )

    assert response.status_code == 401


def test_runner_rejects_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("RUNNER_TOKEN", "expected-secret")
    response = client.post(
        "/internal/execute",
        headers={"Authorization": "Bearer wrong-secret"},
        json={"source_code": "print('hello')"},
    )

    assert response.status_code == 401


def test_runner_rejects_oversized_source() -> None:
    response = client.post(
        "/internal/execute",
        headers={"Authorization": "Bearer token"},
        json={"source_code": "x" * 32_001},
    )

    assert response.status_code == 422


def test_runner_executes_through_engine_after_authentication(monkeypatch) -> None:
    monkeypatch.setenv("RUNNER_TOKEN", "expected-secret")

    class FakeEngine:
        def execute(self, source_code: str) -> dict[str, object]:
            assert source_code == "print('hello')"
            return {
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 4.2,
                "stdout": "hello\n",
                "stderr": "",
            }

    monkeypatch.setattr(runner_main, "DockerExecutionEngine", FakeEngine)
    response = client.post(
        "/internal/execute",
        headers={"Authorization": "Bearer expected-secret"},
        json={"source_code": "print('hello')"},
    )

    assert response.status_code == 200
    assert response.json()["stdout"] == "hello\n"
