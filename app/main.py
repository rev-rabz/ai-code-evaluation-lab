import os

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import ACCESS_TOKEN_MINUTES, create_access_token, get_current_user, hash_password, verify_password
from app.auth_schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.database import get_db
from app.evaluator import evaluate_submission
from app.history import EvaluationHistoryDetail, EvaluationHistoryItem
from app.models import EvaluationRecord, User
from app.schemas import EvaluationRequest, EvaluationResponse, TestCaseFeedback
from app.tasks import TASKS, get_task

app = FastAPI(
    title="AI Code Evaluation Lab",
    description="Inspect Python submissions and evaluate them against server-owned tests in an isolated runner.",
    version="0.5.0",
)

EXECUTION_OUTPUT_LIMIT_BYTES = 16_384
RUNNER_REQUEST_TIMEOUT_SECONDS = 40.0


def _truncate_utf8(value: str, limit_bytes: int = EXECUTION_OUTPUT_LIMIT_BYTES) -> str:
    encoded = value.encode("utf-8")
    return value if len(encoded) <= limit_bytes else encoded[:limit_bytes].decode("utf-8", errors="ignore")


def _persist_evaluation(
    db: Session, request: EvaluationRequest, result: EvaluationResponse, user_id: int
) -> None:
    record = EvaluationRecord(
        user_id=user_id,
        task_id=result.task_id,
        language=request.language,
        source_code=request.source_code,
        status=result.status,
        score=result.score,
        passed_tests=result.passed_tests,
        total_tests=result.total_tests,
        execution_performed=result.execution_performed,
        execution_timed_out=result.execution_timed_out,
        result_json=result.model_dump(mode="json"),
    )
    db.add(record)
    db.commit()


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    email = str(request.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(email=email, hashed_password=hash_password(request.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from None
    db.refresh(user)
    return user


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(request.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user),
        expires_in=ACCESS_TOKEN_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["auth"])
def read_current_user(current_user: User = Depends(get_current_user)) -> UserResponse:
    return current_user


@app.get("/api/v1/tasks", tags=["evaluations"])
def list_tasks() -> list[dict[str, str | int]]:
    return [
        {"task_id": task.task_id, "function_name": task.function_name, "test_case_count": len(task.test_cases)}
        for task in (get_task(key) for key in sorted(TASKS))
    ]


@app.post("/api/v1/evaluations", response_model=EvaluationResponse, tags=["evaluations"])
def create_evaluation(
    request: EvaluationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationResponse:
    result = evaluate_submission(request)
    result.execution_requested = request.execute
    if not request.execute:
        _persist_evaluation(db, request, result, current_user.id)
        return result
    if not request.task_id:
        raise HTTPException(status_code=422, detail="task_id is required when execute is true.")
    try:
        task = get_task(request.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not result.syntax_valid:
        result.task_id = task.task_id
        result.total_tests = len(task.test_cases)
        result.test_feedback = [
            TestCaseFeedback(name=case.name, passed=False, expected=case.expected) for case in task.test_cases
        ]
        result.note = "Submission has a syntax error; trusted tests were not run and the score is zero."
        _persist_evaluation(db, request, result, current_user.id)
        return result

    runner_url, runner_token = os.getenv("RUNNER_URL"), os.getenv("RUNNER_TOKEN")
    if not runner_url or not runner_token:
        raise HTTPException(status_code=503, detail="Code execution is not configured.")
    payload = {
        "source_code": request.source_code,
        "function_name": task.function_name,
        "test_cases": [{"name": c.name, "args": c.args, "expected": c.expected} for c in task.test_cases],
    }
    try:
        response = httpx.post(
            f"{runner_url.rstrip('/')}/internal/execute",
            json=payload,
            headers={"Authorization": f"Bearer {runner_token}"},
            timeout=RUNNER_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        execution = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Execution service timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Execution service rejected or failed the request.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Execution service is unavailable or returned invalid data.") from exc

    timed_out = bool(execution.get("timed_out", False))
    exit_code = int(execution.get("exit_code", 1))
    raw_cases = execution.get("test_results")
    if timed_out or exit_code != 0:
        feedback = [
            TestCaseFeedback(name=case.name, passed=False, expected=case.expected) for case in task.test_cases
        ]
    else:
        if not isinstance(raw_cases, list) or len(raw_cases) != len(task.test_cases):
            raise HTTPException(status_code=502, detail="Execution service returned an invalid test report.")
        try:
            feedback = [TestCaseFeedback.model_validate(case) for case in raw_cases]
        except ValidationError as exc:
            raise HTTPException(status_code=502, detail="Execution service returned malformed test results.") from exc
    passed = sum(case.passed for case in feedback) if exit_code == 0 and not timed_out else 0
    total = len(task.test_cases)
    rate = passed / total
    result.task_id = task.task_id
    result.execution_performed = True
    result.execution_exit_code = exit_code
    result.execution_timed_out = timed_out
    result.execution_duration_ms = float(execution.get("duration_ms", 0))
    result.stdout = _truncate_utf8(str(execution.get("stdout", "")))
    result.stderr = _truncate_utf8(str(execution.get("stderr", "")))
    result.test_feedback = feedback
    result.passed_tests = passed
    result.total_tests = total
    result.pass_rate = round(rate, 4)
    result.score = round(rate * 100, 2)
    result.note = (
        "Score calculated by the API from the registered task test suite. "
        "Legacy client-supplied test_results are ignored."
    )
    _persist_evaluation(db, request, result, current_user.id)
    return result


@app.get("/api/v1/evaluations", response_model=list[EvaluationHistoryItem], tags=["history"])
def list_evaluations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    task_id: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EvaluationHistoryItem]:
    statement = select(EvaluationRecord).where(EvaluationRecord.user_id == current_user.id)
    if task_id:
        statement = statement.where(EvaluationRecord.task_id == task_id)
    records = db.scalars(
        statement.order_by(desc(EvaluationRecord.created_at), desc(EvaluationRecord.id))
        .offset(offset)
        .limit(limit)
    ).all()
    return [EvaluationHistoryItem.model_validate(record) for record in records]


@app.get("/api/v1/evaluations/{evaluation_id}", response_model=EvaluationHistoryDetail, tags=["history"])
def get_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluationHistoryDetail:
    record = db.scalar(
        select(EvaluationRecord).where(
            EvaluationRecord.id == evaluation_id,
            EvaluationRecord.user_id == current_user.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    item = EvaluationHistoryItem.model_validate(record).model_dump()
    return EvaluationHistoryDetail(**item, source_code=record.source_code, result=record.result_json)
