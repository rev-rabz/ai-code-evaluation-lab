import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from runner.engine import DockerExecutionEngine, ExecutionError

app = FastAPI(title="AI Code Evaluation Runner", docs_url=None, redoc_url=None)
engine = DockerExecutionEngine()


class ExecuteRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=32_000)


class ExecuteResponse(BaseModel):
    exit_code: int
    timed_out: bool
    duration_ms: float
    stdout: str
    stderr: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/execute", response_model=ExecuteResponse)
def execute(
    request: ExecuteRequest,
    authorization: str | None = Header(default=None),
) -> ExecuteResponse:
    expected = os.getenv("RUNNER_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = engine.execute(request.source_code)
    except ExecutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ExecuteResponse(**result)
