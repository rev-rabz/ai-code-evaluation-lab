"""Execute one untrusted test invocation without access to trusted grading data."""
import base64
import io
import json
import os
import sys

OUTPUT_LIMIT_BYTES = 16_384
MARKER = "__EVAL_CANDIDATE_RESULT__"


class BoundedTextWriter:
    def __init__(self, stream: io.StringIO, limit_bytes: int) -> None:
        self.stream = stream
        self.limit_bytes = limit_bytes
        self.bytes_written = 0

    def write(self, value: str) -> int:
        if not isinstance(value, str):
            raise TypeError("write() argument must be str")
        remaining = self.limit_bytes - self.bytes_written
        if remaining > 0:
            accepted = value[:remaining].encode("utf-8")[:remaining].decode("utf-8", errors="ignore")
            self.stream.write(accepted)
            self.bytes_written += len(accepted.encode("utf-8"))
        return len(value)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


def _decode_env(name: str) -> object:
    encoded = os.environ.pop(name, "")
    if not encoded:
        raise ValueError(f"Missing {name}.")
    return json.loads(base64.b64decode(encoded, validate=True))


def _safe_actual(value: object, depth: int = 0) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else repr(value)
    if isinstance(value, str):
        return value[:4_096]
    if depth >= 5:
        return f"<{type(value).__name__}>"
    if isinstance(value, (list, tuple)):
        return [_safe_actual(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key)[:256]: _safe_actual(item, depth + 1)
            for key, item in list(value.items())[:100]
        }
    return f"<{type(value).__name__}>"


def main() -> int:
    protocol_stdout = sys.__stdout__
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = BoundedTextWriter(stdout_buffer, OUTPUT_LIMIT_BYTES)
    sys.stderr = BoundedTextWriter(stderr_buffer, OUTPUT_LIMIT_BYTES)

    result: dict[str, object]
    try:
        source = _decode_env("EVAL_SOURCE_B64")
        args = _decode_env("EVAL_ARGS_B64")
        function_name = os.environ.pop("EVAL_FUNCTION_NAME", "")
        if not isinstance(source, str) or not isinstance(args, list) or not function_name:
            raise ValueError("Invalid candidate invocation.")
        namespace: dict[str, object] = {"__name__": "__submission__"}
        exec(compile(source, "<submission>", "exec"), namespace, namespace)
        function = namespace.get(function_name)
        if not callable(function):
            raise TypeError(f"Required callable '{function_name}' was not found.")
        actual = function(*args)
        result = {"ok": True, "actual": _safe_actual(actual)}
    except BaseException as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:OUTPUT_LIMIT_BYTES]}
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            result["error"] = f"{type(exc).__name__}: submission terminated execution"
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    payload = {
        "result": result,
        "stdout": base64.b64encode(stdout_buffer.getvalue().encode("utf-8")).decode("ascii"),
        "stderr": base64.b64encode(stderr_buffer.getvalue().encode("utf-8")).decode("ascii"),
    }
    protocol_stdout.write(MARKER + json.dumps(payload, separators=(",", ":")) + "\n")
    protocol_stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
