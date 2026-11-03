import base64
import json

import docker
import pytest

from runner.engine import DockerExecutionEngine, ExecutionError


class FakeContainer:
    def __init__(self) -> None:
        self.started = False
        self.removed = False

    def start(self) -> None:
        self.started = True

    def wait(self, timeout: int) -> dict[str, int]:
        assert timeout == 7
        return {"StatusCode": 0}

    def logs(self, stdout: bool, stderr: bool) -> bytes:
        assert stdout is True
        assert stderr is False
        payload = {
            "stdout": base64.b64encode(b"hello\\n").decode("ascii"),
            "stderr": base64.b64encode(b"").decode("ascii"),
        }
        return ("__EVAL_RESULT__" + json.dumps(payload)).encode("utf-8")

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


def test_engine_uses_restricted_container_configuration(monkeypatch) -> None:
    container = FakeContainer()
    client = FakeDockerClient(container)
    monkeypatch.setattr(docker, "from_env", lambda: client)

    result = DockerExecutionEngine().execute("print('hello')")

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
    assert container.started is True
    assert container.removed is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\\n"


def test_engine_rejects_source_larger_than_limit() -> None:
    engine = object.__new__(DockerExecutionEngine)

    with pytest.raises(ExecutionError, match="32 KB"):
        engine.execute("x" * 32_001)
