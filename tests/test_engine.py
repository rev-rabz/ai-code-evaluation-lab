import base64
import json

import docker
import pytest
import requests

from runner.engine import DockerExecutionEngine, ExecutionError


def result_log(stdout: bytes = b"hello\n", stderr: bytes = b"") -> bytes:
    payload = {
        "stdout": base64.b64encode(stdout).decode("ascii"),
        "stderr": base64.b64encode(stderr).decode("ascii"),
    }
    return ("__EVAL_RESULT__" + json.dumps(payload)).encode("utf-8")


class FakeContainer:
    def __init__(
        self,
        logs: bytes | None = None,
        wait_error: Exception | None = None,
        start_error: Exception | None = None,
        exit_code: int = 0,
    ) -> None:
        self.started = False
        self.removed = False
        self.killed = False
        self.wait_calls = 0
        self.logs_payload = logs if logs is not None else result_log()
        self.wait_error = wait_error
        self.start_error = start_error
        self.exit_code = exit_code

    def start(self) -> None:
        if self.start_error:
            raise self.start_error
        self.started = True

    def wait(self, timeout: int) -> dict[str, int]:
        self.wait_calls += 1
        if self.wait_error and self.wait_calls == 1:
            raise self.wait_error
        if self.wait_calls == 1:
            assert timeout == 7
        else:
            assert timeout == 2
        return {"StatusCode": self.exit_code}

    def kill(self) -> None:
        self.killed = True

    def logs(self, stdout: bool, stderr: bool) -> bytes:
        assert stdout is True
        assert stderr is False
        return self.logs_payload

    def remove(self, force: bool) -> None:
        assert force is True
        self.removed = True


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self.container = container
        self.options = None

    def create(self, image: str, **kwargs):
        self.options = {"image": image, **kwargs}
        return self.container


class FakeDockerClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainers(container)


def make_engine(monkeypatch, container: FakeContainer):
    client = FakeDockerClient(container)
    monkeypatch.setattr(docker, "from_env", lambda: client)
    return DockerExecutionEngine(), client


def test_engine_uses_restricted_container_configuration(monkeypatch) -> None:
    container = FakeContainer()
    engine, client = make_engine(monkeypatch, container)

    result = engine.execute("print('hello')")

    options = client.containers.options
    assert options["network_disabled"] is True
    assert options["read_only"] is True
    assert options["user"] == "65534:65534"
    assert options["tty"] is True
    assert options["cap_drop"] == ["ALL"]
    assert options["pids_limit"] == 32
    assert options["mem_limit"] == "128m"
    assert options["tmpfs"]["/workspace"].startswith("rw,noexec,nosuid,nodev")
    assert options["tmpfs"]["/output"].startswith("rw,noexec,nosuid,nodev")
    assert options["environment"]["EVAL_SOURCE_B64"] == base64.b64encode(
        b"print('hello')"
    ).decode("ascii")
    assert options["log_config"].config == {"max-size": "1m", "max-file": "1"}
    assert container.started is True
    assert container.removed is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"


def test_engine_returns_runtime_exception_output_and_exit_code(monkeypatch) -> None:
    container = FakeContainer(
        logs=result_log(stderr=b"Traceback: boom\n"),
        exit_code=1,
    )
    engine, _ = make_engine(monkeypatch, container)

    result = engine.execute("raise RuntimeError('boom')")

    assert result["exit_code"] == 1
    assert result["timed_out"] is False
    assert "Traceback" in result["stderr"]
    assert container.removed is True


def test_engine_kills_timed_out_container_and_cleans_it_up(monkeypatch) -> None:
    container = FakeContainer(wait_error=requests.exceptions.ReadTimeout("wait expired"))
    engine, _ = make_engine(monkeypatch, container)

    result = engine.execute("while True: pass")

    assert result["timed_out"] is True
    assert container.killed is True
    assert container.wait_calls == 2
    assert container.removed is True


def test_engine_truncates_stdout_and_stderr(monkeypatch) -> None:
    container = FakeContainer(
        logs=result_log(
            stdout=b"x" * 20_000,
            stderr=b"y" * 20_000,
        )
    )
    engine, _ = make_engine(monkeypatch, container)

    result = engine.execute("print('large output')")

    assert len(result["stdout"].encode("utf-8")) == engine.output_limit_bytes
    assert len(result["stderr"].encode("utf-8")) == engine.output_limit_bytes


def test_engine_removes_container_when_start_fails(monkeypatch) -> None:
    container = FakeContainer(start_error=docker.errors.DockerException("start failed"))
    engine, _ = make_engine(monkeypatch, container)

    with pytest.raises(ExecutionError, match="Docker could not start"):
        engine.execute("print('hello')")

    assert container.removed is True


def test_engine_rejects_source_larger_than_limit() -> None:
    engine = object.__new__(DockerExecutionEngine)

    with pytest.raises(ExecutionError, match="32 KB"):
        engine.execute("x" * 32_001)
