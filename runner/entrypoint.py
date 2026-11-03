import resource
import runpy
import sys
import traceback
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (1_048_576, 1_048_576))
resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

output = Path("/output")
stdout_path = output / "stdout.txt"
stderr_path = output / "stderr.txt"

with stdout_path.open("w", encoding="utf-8") as stdout_file:
    with stderr_path.open("w", encoding="utf-8") as stderr_file:
        sys.stdout = stdout_file
        sys.stderr = stderr_file
        try:
            runpy.run_path("/workspace/submission.py", run_name="__main__")
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            sys.exit(code)
        except BaseException:
            traceback.print_exc(file=stderr_file)
            sys.exit(1)
