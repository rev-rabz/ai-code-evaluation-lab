import base64
import importlib
import json
import os
import resource
import runpy
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BoundedTextWriter = importlib.import_module("runner.output").BoundedTextWriter

OUTPUT_LIMIT_BYTES = 16_384
resource.setrlimit(resource.RLIMIT_CPU, (6, 7))
resource.setrlimit(resource.RLIMIT_FSIZE, (1_048_576, 1_048_576))
resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

submission_path = Path("/workspace/submission.py")
source_b64 = os.environ.pop("EVAL_SOURCE_B64", "")
tests_b64 = os.environ.pop("EVAL_TESTS_B64", "")
if not source_b64 or not tests_b64:
    raise RuntimeError("Submission source or trusted tests were not provided.")
submission_path.write_bytes(base64.b64decode(source_b64, validate=True))
test_spec = json.loads(base64.b64decode(tests_b64, validate=True))

output = Path("/output")
stdout_path = output / "stdout.txt"
stderr_path = output / "stderr.txt"
exit_code = 0
test_results = []

with stdout_path.open("w", encoding="utf-8") as stdout_file:
    with stderr_path.open("w", encoding="utf-8") as stderr_file:
        sys.stdout = BoundedTextWriter(stdout_file, OUTPUT_LIMIT_BYTES)
        sys.stderr = BoundedTextWriter(stderr_file, OUTPUT_LIMIT_BYTES)
        try:
            namespace = runpy.run_path(str(submission_path), run_name="__main__")
            function = namespace.get(test_spec["function_name"])
            if not callable(function):
                raise TypeError(f"Required callable '{test_spec['function_name']}' was not found.")
            for case in test_spec["test_cases"]:
                try:
                    actual = function(*case["args"])
                    passed = actual == case["expected"]
                    actual_json = json.loads(json.dumps(actual, default=repr))
                    test_results.append({
                        "name": case["name"],
                        "passed": bool(passed),
                        "expected": case["expected"],
                        "actual": actual_json,
                    })
                except BaseException as exc:
                    test_results.append({
                        "name": case["name"],
                        "passed": False,
                        "expected": case["expected"],
                        "actual": f"{type(exc).__name__}: {exc}",
                    })
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        except BaseException:
            traceback.print_exc()
            exit_code = 1
        finally:
            sys.stdout.flush()
            sys.stderr.flush()

sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__
result = {
    "stdout": base64.b64encode(stdout_path.read_bytes()).decode("ascii"),
    "stderr": base64.b64encode(stderr_path.read_bytes()).decode("ascii"),
    "test_results": test_results,
}
print("__EVAL_RESULT__" + json.dumps(result), flush=True)
sys.exit(exit_code)
