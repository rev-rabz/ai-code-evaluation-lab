import json
import tempfile
import time
from pathlib import Path

import docker
from docker.errors import DockerException, ImageNotFound


class ExecutionError(RuntimeError):
    """Raised when the isolated execution environment cannot run a job."""


class DockerExecutionEngine:
    """Run one Python submission in a disposable, heavily restricted container."""

    image = "ai-code-evaluation-python-runner:0.1.0"
    timeout_seconds = 5
    output_limit_bytes = 16_384

    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
        except DockerException as exc:
            raise ExecutionError("Docker daemon is unavailable.") from exc

    def execute(self, source_code: str) -> dict[str, object]:
        if not source_code or len(source_code.encode("utf-8")) > 32_000:
            raise ExecutionError("Source code must be between 1 byte and 32 KB.")

        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="code-eval-") as temporary:
            root = Path(temporary)
            source_dir = root / "source"
            output_dir = root / "output"
            source_dir.mkdir(mode=0o700)
            output_dir.mkdir(mode=0o700)
            (source_dir / "submission.py").write_text(source_code, encoding="utf-8")

            container = None
            timed_out = False
            exit_code = 1
            try:
                container = self.client.containers.run(
                    self.image,
                    command=["/usr/local/bin/python", "-I", "-S", "/opt/runner/entrypoint.py"],
                    detach=True,
                    auto_remove=False,
                    user="65534:65534",
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
                    tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=16m"},
                    volumes={
                        str(source_dir): {"bind": "/workspace", "mode": "ro"},
                        str(output_dir): {"bind": "/output", "mode": "rw"},
                    },
                    working_dir="/workspace",
                    labels={"app": "ai-code-evaluation-lab", "purpose": "untrusted-code"},
                )
                try:
                    result = container.wait(timeout=self.timeout_seconds + 2)
                    exit_code = int(result.get("StatusCode", 1))
                except Exception as exc:
                    if exc.__class__.__name__ not in {"ReadTimeout", "Timeout"}:
                        raise
                    timed_out = True
                    container.kill()
                    container.wait(timeout=2)
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

            stdout = self._read_output(output_dir / "stdout.txt")
            stderr = self._read_output(output_dir / "stderr.txt")
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            return {
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "stdout": stdout,
                "stderr": stderr,
            }

    def _read_output(self, path: Path) -> str:
        if not path.exists():
            return ""
        content = path.read_bytes()[: self.output_limit_bytes]
        return content.decode("utf-8", errors="replace")
