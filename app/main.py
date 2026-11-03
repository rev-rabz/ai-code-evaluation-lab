import os

import httpx
from fastapi import FastAPI, HTTPException

from app.evaluator import evaluate_submission
from app.schemas import EvaluationRequest, EvaluationResponse

app = FastAPI(
    title="AI Code Evaluation Lab",
    description=(
        "Inspect Python submissions and optionally execute them through an isolated runner."
    ),
    version="0.2.0",
)

EXECUTION_OUTPUT_LIMIT_BYTES = 16_384
RUNNER_REQUEST_TIMEOUT_SECONDS = 15.0


def _truncate_utf8(value: str, limit_bytes: int = EXECUTION_OUTPUT_LIMIT_BYTES) -> str:
    """Keep execution output within a byte limit without returning broken UTF-8."""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return value
    return encoded[:limit_bytes].decode("utf-8", errors="ignore")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/evaluations",
    response_model=EvaluationResponse,
    tags=["evaluations"],
)
def create_evaluation(request: EvaluationRequest) -> EvaluationResponse:
    result = evaluate_submission(request)
    result.execution_requested = request.execute

    if not request.execute:
        return result

    runner_url = os.getenv("RUNNER_URL")
    runner_token = os.getenv("RUNNER_TOKEN")
    if not runner_url or not runner_token:
        raise HTTPException(
            status_code=503,
            detail="Code execution is not configured. Set RUNNER_URL and RUNNER_TOKEN.",
        )

    try:
        response = httpx.post(
            f"{runner_url.rstrip('/')}/internal/execute",
            json={"source_code": request.source_code},
            headers={"Authorization": f"Bearer {runner_token}"},
            timeout=RUNNER_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Execution service timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail="Execution service rejected or failed the request.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Execution service is unavailable.") from exc

    execution = response.json()
    result.execution_performed = True
    result.execution_exit_code = execution["exit_code"]
    result.execution_timed_out = execution["timed_out"]
    result.execution_duration_ms = execution["duration_ms"]
    result.stdout = _truncate_utf8(execution["stdout"])
    result.stderr = _truncate_utf8(execution["stderr"])
    result.note = (
        "Source was inspected by the API and execution was performed by the isolated runner. "
        "Client-supplied test results remain untrusted and must not be used as authoritative "
        "scores; execution output alone does not constitute a trusted test result."
    )
    return result
