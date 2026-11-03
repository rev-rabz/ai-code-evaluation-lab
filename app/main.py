import os

import httpx
from fastapi import FastAPI, HTTPException

from app.evaluator import evaluate_submission
from app.schemas import EvaluationRequest, EvaluationResponse

app = FastAPI(
    title="AI Code Evaluation Lab",
    description="Inspect Python submissions and optionally execute them through an isolated runner.",
    version="0.2.0",
)


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
            timeout=8.0,
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
    result.stdout = execution["stdout"]
    result.stderr = execution["stderr"]
    return result
