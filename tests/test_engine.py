import base64
import json

import docker
import pytest

from runner.engine import DockerExecutionEngine, ExecutionError


def result_log(actual=3):
    payload = {
        "result": {"ok": True, "actual": actual},
        "stdout": base64.b64encode(b"ok").decode(),
        "stderr": "",
    }
    return (DockerExecutionEngine.candidate_marker + json.dumps(payload)).encode()


class FakeContainer:
    def __init__(self, logs=None, polls_until_exit=1, exit_code=0, start_error=None):
        self.logs_payload = logs or result_log()
        self.polls_until_exit = polls_until_exit
        self.exit_code = exit_code
        self.start_error = start_error
        self.attrs = {"State": {"Status": "created", "ExitCode": 0}}
        self.reload_calls = 0
        self.removed = False
        self.killed = False

    def start(self):
        if self.start_error:
            raise self.start_error
        self.attrs["State"]["Status"] = "running"

    def reload(self):
        self.reload_calls += 1
        if self.polls_until_exit is not None and self.reload_calls >= self.polls_until_exit:
            self.attrs["State"].update(Status="exited", ExitCode=self.exit_code)

    def wait(self, timeout):
        return {"StatusCode": self.exit_code}

    def kill(self):
        self.killed = True
        self.attrs["State"]["Status"] = "exited"

    def logs(self, stdout, stderr):
        return self.logs_payload

    def remove(self, force):
        self.removed = True


class FakeContainers:
    def __init__(self, container):
        self.container = container
        self.options = None

    def create(self, image, **kwargs):
        self.options = {"image": image, **kwargs}
        return self.container


class FakeClient:
    def __init__(self, container):
        self.containers = FakeContainers(container)


def make_engine(monkeypatch, container):
    client = FakeClient(container)
    monkeypatch.setattr(docker, "from_env", lambda: client)
    return DockerExecutionEngine(), client


def test_engine_runs_with_restricted_container_and_excludes_trusted_suite(monkeypatch):
    container = FakeContainer()
    engine, client = make_engine(monkeypatch, container)
    result = engine.execute(
        "def add(a,b): return a+b",
        function_name="add",
        test_cases=[{"name": "one", "args": [1, 2], "expected": 3}],
    )
    options = client.containers.options
    environment = options["environment"]
    assert options["network_disabled"] and options["read_only"]
    assert options["user"] == "65534:65534"
    assert set(environment) == {"EVAL_SOURCE_B64", "EVAL_ARGS_B64", "EVAL_FUNCTION_NAME"}
    assert json.loads(base64.b64decode(environment["EVAL_ARGS_B64"])) == [1, 2]
    assert "EVAL_TESTS_B64" not in environment
    assert "expected" not in environment
    assert result["test_results"][0]["passed"] is True
    assert result["stdout"] == "ok"
    assert container.removed


def test_timeout_kills_and_removes_container(monkeypatch):
    container = FakeContainer(polls_until_exit=None)
    engine, _ = make_engine(monkeypatch, container)
    engine.case_timeout_seconds = 0.01
    engine.poll_interval_seconds = 0.01
    result = engine.execute(
        "while True: pass",
        function_name="add",
        test_cases=[{"name": "one", "args": [1, 2], "expected": 3}],
    )
    assert result["timed_out"] and container.killed and container.removed
    assert result["test_results"][0]["passed"] is False


def test_start_failure_still_removes_container(monkeypatch):
    container = FakeContainer(start_error=docker.errors.DockerException("failed"))
    engine, _ = make_engine(monkeypatch, container)
    with pytest.raises(ExecutionError):
        engine.execute(
            "pass",
            function_name="add",
            test_cases=[{"name": "one", "args": [], "expected": None}],
        )
    assert container.removed
