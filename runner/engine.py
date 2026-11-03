import base64
import json
import time
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound


class ExecutionError(RuntimeError):
    """Raised when the isolated execution environment cannot run a job."""


class DockerExecutionEngine:
    """Orchestrate trusted grading while each candidate invocation runs separately."""

    image = "ai-code-evaluation-python-runner:0.1.0"
    case_timeout_seconds = 5.0
    overall_timeout_seconds = 30.0
    poll_interval_seconds = 0.05
    output_limit_bytes = 16_384
    candidate_marker = "__EVAL_CANDIDATE_RESULT__"

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
        test_cases: list[dict[str, Any]],
    ) -> dict[str, object]:
        source_bytes = source_code.encode("utf-8")
        if not source_bytes or len(source_bytes) > 32_000:
            raise ExecutionError("Source code must be between 1 byte and 32 KB.")
        encoded_source = json.dumps(source_code, ensure_ascii=False).encode("utf-8")
        if not test_cases or len(test_cases) > 100:
            raise ExecutionError("A trusted test suite of 1 to 100 cases is required.")

        started = time.monotonic()
        deadline = started + self.overall_timeout_seconds
        test_results: list[dict[str, object]] = []
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        timed_out = False

        for case in test_cases:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                test_results.append(self._failed_case(case, "Execution time budget exhausted."))
                continue

            case_result = self._run_candidate(
                encoded_source,
                function_name=function_name,
                args=case.get("args", []),
                timeout=min(self.case_timeout_seconds, remaining),
            )
            stdout_parts.append(case_result["stdout"])
            stderr_parts.append(case_result["stderr"])
            if case_result["timed_out"]:
                timed_out = True
                test_results.append(self._failed_case(case, "Execution timed out."))
                # Do not spend more resources after a submission has exhausted its time.
                for remaining_case in test_cases[len(test_results):]:
                    test_results.append(self._failed_case(remaining_case, "Skipped after execution timeout."))
                break

            candidate = case_result["result"]
            if candidate is None or not candidate.get("ok"):
                actual = candidate.get("error", "Candidate process returned no valid result.") if candidate else "Candidate process returned no valid result."
                passed = False
            else:
                actual = candidate.get("actual")
                passed = actual == case.get("expected")
            test_results.append({
                "name": str(case["name"]),
                "passed": bool(passed),
                "expected": case.get("expected"),
                "actual": actual,
            })

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "exit_code": 124 if timed_out else 0,
            "timed_out": timed_out,
            "duration_ms": duration_ms,
            "stdout": self._truncate("\n".join(stdout_parts)),
            "stderr": self._truncate("\n".join(stderr_parts)),
            "test_results": test_results,
        }

    def _run_candidate(
        self,
        encoded_source: bytes,
        *,
        function_name: str,
        args: object,
        timeout: float,
    ) -> dict[str, object]:
        encoded_args = json.dumps(args, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded_args) > self.output_limit_bytes:
            return {"result": {"ok": False, "error": "Test arguments exceed the execution limit."},
                    "stdout": "", "stderr": "", "timed_out": False}

        container = None
        timed_out = False
        exit_code = 1
        try:
            container = self.client.containers.create(
                self.image,
                command=["/usr/local/bin/python", "-I", "-S", "/opt/runner/candidate_entrypoint.py"],
                user="65534:65534",
                tty=False,
                read_only=True,
                network_disabled=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="128m",
                nano_cpus=500_000_000,
                pids_limit=32,
                ulimits=[
                    docker.types.Ulimit(name="cpu", soft=6, hard=7),
                    docker.types.Ulimit(name="fsize", soft=1_048_576, hard=1_048_576),
                    docker.types.Ulimit(name="nproc", soft=16, hard=16),
                    docker.types.Ulimit(name="nofile", soft=64, hard=64),
                    docker.types.Ulimit(name="core", soft=0, hard=0),
                ],
                tmpfs={
                    "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65534,gid=65534,mode=0700",
                },
                working_dir="/",
                environment={
                    "EVAL_SOURCE_B64": base64.b64encode(encoded_source).decode("ascii"),
                    "EVAL_ARGS_B64": base64.b64encode(encoded_args).decode("ascii"),
                    "EVAL_FUNCTION_NAME": function_name,
                },
                log_config=docker.types.LogConfig(
                    type="json-file", config={"max-size": "1m", "max-file": "1"}
                ),
                labels={"app": "ai-code-evaluation-lab", "purpose": "untrusted-candidate"},
            )
            container.start()
            case_deadline = time.monotonic() + timeout
            while True:
                container.reload()
                state = container.attrs.get("State", {})
                if state.get("Status") != "running":
                    exit_code = int(state.get("ExitCode", 1))
                    break
                if time.monotonic() >= case_deadline:
                    timed_out = True
                    try:
                        container.kill()
                        container.wait(timeout=2)
                    except DockerException:
                        pass
                    break
                time.sleep(self.poll_interval_seconds)

            result, stdout, stderr = self._read_candidate_result(container)
            if exit_code != 0 or result is None:
                result = {"ok": False, "error": "Candidate process failed before returning a result."}
            return {"result": result, "stdout": stdout, "stderr": stderr, "timed_out": timed_out}
        except (DockerException, ImageNotFound) as exc:
            raise ExecutionError("Runner image is missing or Docker could not start the candidate sandbox.") from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass

    def _read_candidate_result(
        self, container: object
    ) -> tuple[dict[str, object] | None, str, str]:
        try:
            logs = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        except (DockerException, AttributeError):
            return None, "", ""

        for line in reversed(logs.splitlines()):
            if not line.startswith(self.candidate_marker):
                continue
            try:
                payload = json.loads(line[len(self.candidate_marker):])
                result = payload.get("result")
                if not isinstance(result, dict):
                    return None, "", ""
                stdout = base64.b64decode(payload.get("stdout", ""), validate=True)
                stderr = base64.b64decode(payload.get("stderr", ""), validate=True)
                return (
                    result,
                    self._truncate(stdout.decode("utf-8", errors="replace")),
                    self._truncate(stderr.decode("utf-8", errors="replace")),
                )
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                return None, "", ""
        return None, "", ""

    def _failed_case(self, case: dict[str, Any], reason: str) -> dict[str, object]:
        return {
            "name": str(case["name"]),
            "passed": False,
            "expected": case.get("expected"),
            "actual": reason,
        }

    def _truncate(self, value: str) -> str:
        encoded = value.encode("utf-8")
        return value if len(encoded) <= self.output_limit_bytes else encoded[:self.output_limit_bytes].decode("utf-8", errors="ignore")
