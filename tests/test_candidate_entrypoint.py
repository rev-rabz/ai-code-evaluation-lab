import base64
import json
import os
import subprocess
import sys
from pathlib import Path


def test_candidate_entrypoint_receives_only_source_and_one_case_input():
    entrypoint = Path(__file__).parents[1] / "runner" / "candidate_entrypoint.py"
    source = (
        "import os\n"
        "def add(a, b):\n"
        "    assert 'EVAL_TESTS_B64' not in os.environ\n"
        "    assert 'EVAL_EXPECTED' not in os.environ\n"
        "    return a + b\n"
    )
    env = {
        **os.environ,
        "EVAL_SOURCE_B64": base64.b64encode(json.dumps(source).encode()).decode(),
        "EVAL_ARGS_B64": base64.b64encode(json.dumps([2, 3]).encode()).decode(),
        "EVAL_FUNCTION_NAME": "add",
    }
    env.pop("EVAL_TESTS_B64", None)
    env.pop("EVAL_EXPECTED", None)

    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(entrypoint)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0
    marker = "__EVAL_CANDIDATE_RESULT__"
    payload_line = next(line for line in completed.stdout.splitlines() if line.startswith(marker))
    payload = json.loads(payload_line[len(marker):])
    assert payload["result"] == {"ok": True, "actual": 5}


def test_candidate_entrypoint_reports_submission_exceptions():
    entrypoint = Path(__file__).parents[1] / "runner" / "candidate_entrypoint.py"
    source = "def add(a, b):\n    raise RuntimeError('candidate failed')\n"
    env = {
        **os.environ,
        "EVAL_SOURCE_B64": base64.b64encode(source.encode()).decode(),
        "EVAL_ARGS_B64": base64.b64encode(b"[1, 2]").decode(),
        "EVAL_FUNCTION_NAME": "add",
    }

    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(entrypoint)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    marker = "__EVAL_CANDIDATE_RESULT__"
    payload_line = next(line for line in completed.stdout.splitlines() if line.startswith(marker))
    payload = json.loads(payload_line[len(marker):])
    assert completed.returncode == 0
    assert payload["result"]["ok"] is False
    assert "RuntimeError: candidate failed" in payload["result"]["error"]
