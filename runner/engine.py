import base64
import io
import json
import tarfile
import time

import docker
from docker.errors import DockerException, ImageNotFound


class ExecutionError(RuntimeError):
    """Raised when the isolated execution environment cannot run a job."""


class DockerExecutionEngine:
    """Run one Python submission in a disposable, restricted container."""

    image = "ai-code-evaluation-python-runner:0.1.0"
    timeout_seconds = 5
    output_limit_bytes = 16_384

    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
        except DockerException as exc:
            raise ExecutionError("Docker daemon is unavailable.") from exc

    def execute(self, source_code: str) -> dict[str, object]:
        encoded_source = source_code.encode("utf-8")
        if not encoded_source or len(encoded_source) > 32_000:
            raise ExecutionError("Source code must be between 1 byte and 32 KB.")

        started = time.monotonic()
        container = None
        timed_out = False
        exit_code = 1
        stdout = ""
        stderr = ""
        try:
            container = self.client.containers.create(
                self.image,
                command=[
                    "/usr/local/bin/python",
                    "-I",
                    "-S",
                    "/opt/runner/entrypoint.py",
                ],
                user="65534:65534",\n                tty=True,
                read_only=True,
                network_disabled=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="128m",
                nano_cpus=500_000_000,
                pids_limit=32,
                ulimits=[
                    docker.types.Ulimit(name="cpu", soft=4, hard=5),
                    docker.types.Ulimit(name="fsize", soft=1_048_576, hard=1_048_576),
                    docker.types.Ulimit(name="nproc", soft=16, hard=16),
                    docker.types.Ulimit(name="nofile", soft=64, hard=64),
                    docker.types.Ulimit(name="core", soft=0, hard=0),
                ],
                tmpfs={
                    "/workspace": "rw,noexec,nosuid,nodev,size=1m",
                    "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65534,gid=65534,mode=0700",
                    "/output": "rw,noexec,nosuid,nodev,size=2m,uid=65534,gid=65534,mode=0700",
                },
                working_dir="/workspace",
                labels={"app": "ai-code-evaluation-lab", "purpose": "untrusted-code"},
            )
            container.put_archive("/workspace", self._source_archive(encoded_source))
            container.start()
            try:
                result = container.wait(timeout=self.timeout_seconds + 2)
                exit_code = int(result.get("StatusCode", 1))
            except Exception as exc:
                if exc.__class__.__name__ not in {"ReadTimeout", "Timeout"}:
                    raise
                timed_out = True
                try:
                    container.kill()
                except DockerException:
                    pass
                container.wait(timeout=2)

            stdout, stderr = self._read_container_result(container)
        except (DockerException, ImageNotFound) as exc:
            raise ExecutionError(
                "Runner image is missing or Docker could not start the sandbox."
            ) from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass

        return {
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "stdout": stdout,
            "stderr": stderr,
        }

    def _source_archive(self, source: bytes) -> bytes:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as bundle:
            info = tarfile.TarInfo("submission.py")
            info.size = len(source)
            info.mode = 0o444
            bundle.addfile(info, io.BytesIO(source))
        archive.seek(0)
        return archive.read()

    def _read_container_result(self, container: object) -> tuple[str, str]:
        try:
            logs = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        except (DockerException, AttributeError):
            return "", ""

        marker = "__EVAL_RESULT__"
        for line in reversed(logs.splitlines()):
            if not line.startswith(marker):
                continue
            try:
                result = json.loads(line[len(marker) :])
                stdout = base64.b64decode(result["stdout"], validate=True)
                stderr = base64.b64decode(result["stderr"], validate=True)
                return (
                    stdout[: self.output_limit_bytes].decode("utf-8", errors="replace"),
                    stderr[: self.output_limit_bytes].decode("utf-8", errors="replace"),
                )
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                return "", ""
        return "", ""
