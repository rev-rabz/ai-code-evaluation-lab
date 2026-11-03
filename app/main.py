from fastapi import FastAPI

from app.evaluator import evaluate_submission
from app.schemas import EvaluationRequest, EvaluationResponse

app = FastAPI(
    title="AI Code Evaluation Lab",
    description="Safely inspect code submissions and summarize trusted test-runner results.",
    version="0.1.0",
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
    return evaluate_submission(request)
