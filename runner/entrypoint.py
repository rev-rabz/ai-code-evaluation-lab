import base64
import json
import importlib
import os
import resource
import runpy
import sys
import traceback
from pathlib import Path

# -I excludes the script directory; add only the trusted runner directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BoundedTextWriter = importlib.import_module("output").BoundedTextWriter

OUTPUT_LIMIT_BYTES = 16_384

resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (1_048_576, 1_048_576))
resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

submission_path = Path("/workspace/submission.py")
source_b64 = os.environ.pop("EVAL_SOURCE_B64", "")
if not source_b64:
    raise RuntimeError("Submission source was not provided.")
submission_path.write_bytes(base64.b64decode(source_b64, validate=True))

output = Path("/output")
stdout_path = output / "stdout.txt"
stderr_path = output / "stderr.txt"
exit_code = 0

with stdout_path.open("w", encoding="utf-8") as stdout_file:
    with stderr_path.open("w", encoding="utf-8") as stderr_file:
        sys.stdout = BoundedTextWriter(stdout_file, OUTPUT_LIMIT_BYTES)
        sys.stderr = BoundedTextWriter(stderr_file, OUTPUT_LIMIT_BYTES)
        try:
            runpy.run_path(str(submission_path), run_name="__main__")
        except SystemExit as exc:
            if exc.code is None:
                exit_code = 0
            elif isinstance(exc.code, int):
                exit_code = exc.code
            else:
                exit_code = 1
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
}
print("__EVAL_RESULT__" + json.dumps(result), flush=True)
sys.exit(exit_code)
