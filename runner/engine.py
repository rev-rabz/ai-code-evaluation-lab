import base64
import json
import time

import docker
from docker.errors import DockerException, ImageNotFound


class ExecutionError(RuntimeError):
    """Raised when the isolated execution environment cannot run a job."""


class DockerExecutionEngine:
    """Run one Python submission and trusted task tests in a disposable container."""

    image = "ai-code-evaluation-python-runner:0.1.0"
    timeout_seconds = 5
    poll_interval_seconds = 0.1
    output_limit_bytes = 16_384

    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
        except DockerException as exc:
            raise ExecutionError("Docker daemon is unavailable.") from exc

    def execute(
        self,
        source_code: str,
        *,
        function_name: str,
        test_cases: list[dict[str, object]],
    ) -> dict[str, object]:
        encoded_source = source_code.encode("utf-8")
        if not encoded_source or len(encoded_source) > 32_000:
            raise ExecutionError("Source code must be between 1 byte and 32 KB.")
        if not test_cases or len(test_cases) > 100:
            raise ExecutionError("A trusted test suite of 1 to 100 cases is required.")

        test_spec = json.dumps({"function_name": function_name, "test_cases": test_cases})
        started = time.monotonic()
        container = None
        timed_out = False
        exit_code = 1
        stdout = stderr = ""
        test_results: list[dict[str, object]] = []
        try:
            container = self.client.containers.create(
                self.image,
                command=["/usr/local/bin/python", "-I", "-S", "/opt/runner/entrypoint.py"],
                user="65534:65534", tty=True, read_only=True, network_disabled=True,
                cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                mem_limit="128m", nano_cpus=500_000_000, pids_limit=32,
                ulimits=[
                    docker.types.Ulimit(name="cpu", soft=6, hard=7),
                    docker.types.Ulimit(name="fsize", soft=1_048_576, hard=1_048_576),
                    docker.types.Ulimit(name="nproc", soft=16, hard=16),
                    docker.types.Ulimit(name="nofile", soft=64, hard=64),
                    docker.types.Ulimit(name="core", soft=0, hard=0),
                ],
                tmpfs={
                    "/workspace": "rw,noexec,nosuid,nodev,size=1m,uid=65534,gid=65534,mode=0700",
                    "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65534,gid=65534,mode=0700",
                    "/output": "rw,noexec,nosuid,nodev,size=2m,uid=65534,gid=65534,mode=0700",
                },
                working_dir="/workspace",
                environment={
                    "EVAL_SOURCE_B64": base64.b64encode(encoded_source).decode("ascii"),
                    "EVAL_TESTS_B64": base64.b64encode(test_spec.encode("utf-8")).decode("ascii"),
                },
                log_config=docker.types.LogConfig(
                    type="json-file", config={"max-size": "1m", "max-file": "1"}
                ),
                labels={"app": "ai-code-evaluation-lab", "purpose": "untrusted-code"},
            )
            container.start()
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                container.reload()
                state = container.attrs.get("State", {})
                if state.get("Status") != "running":
                    exit_code = int(state.get("ExitCode", 1))
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    container.kill()
                    container.wait(timeout=2)
                    break
                time.sleep(self.poll_interval_seconds)
            stdout, stderr, test_results = self._read_container_result(container)
        except (DockerException, ImageNotFound) as exc:
            raise ExecutionError("Runner image is missing or Docker could not start the sandbox.") from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass
        return {
            "exit_code": exit_code, "timed_out": timed_out,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "stdout": stdout, "stderr": stderr, "test_results": test_results,
        }

    def _read_container_result(
        self, container: object
    ) -> tuple[str, str, list[dict[str, object]]]:
        try:
            logs = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        except (DockerException, AttributeError):
            return "", "", []
        marker = "__EVAL_RESULT__"
        for line in reversed(logs.splitlines()):
            if not line.startswith(marker):
                continue
            try:
                result = json.loads(line[len(marker):])
                stdout = base64.b64decode(result["stdout"], validate=True)
                stderr = base64.b64decode(result["stderr"], validate=True)
                cases = result.get("test_results", [])
                if not isinstance(cases, list):
                    cases = []
                return (
                    stdout[:self.output_limit_bytes].decode("utf-8", errors="replace"),
                    stderr[:self.output_limit_bytes].decode("utf-8", errors="replace"),
                    cases,
                )
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                return "", "", []
        return "", "", []
