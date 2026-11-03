from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_review_schemas import AIReviewContent, AIReviewResponse
from app.ai_review_service import (
    MAX_REVIEW_SOURCE_CHARS,
    AIReviewNotConfigured,
    AIReviewOutputError,
    AIReviewProviderError,
    generate_ai_review,
    review_model_name,
)
from app.auth import get_current_user
from app.database import get_db
from app.models import AIReview, EvaluationRecord, Task, TaskVersion, User

router = APIRouter(tags=["AI reviews"])


def _owned_evaluation(db: Session, evaluation_id: int, user_id: int) -> EvaluationRecord:
    record = db.scalar(
        select(EvaluationRecord).where(
            EvaluationRecord.id == evaluation_id,
            EvaluationRecord.user_id == user_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    return record


def _review_response(review_record: AIReview) -> AIReviewResponse:
    return AIReviewResponse(
        id=review_record.id,
        evaluation_id=review_record.evaluation_id,
        model=review_record.model,
        review=AIReviewContent.model_validate(review_record.review_json),
        created_at=review_record.created_at,
    )


def _evaluation_context(db: Session, record: EvaluationRecord) -> dict:
    task_context = None
    if record.task_id:
        task = db.get(Task, record.task_id)
        version = db.get(TaskVersion, record.task_version_id) if record.task_version_id else None
        if task is not None:
            task_context = {
                "task_id": task.task_id,
                "title": task.title,
                "instructions": task.instructions,
                "function_name": version.function_name if version else None,
                "version": version.version if version else None,
            }

    result = record.result_json or {}
    test_feedback = result.get("test_feedback", [])
    return {
        "language": record.language,
        "task": task_context,
        "evaluation": {
            "status": record.status,
            "syntax_valid": result.get("syntax_valid"),
            "score": record.score,
            "passed_tests": record.passed_tests,
            "total_tests": record.total_tests,
            "execution_performed": record.execution_performed,
            "execution_timed_out": record.execution_timed_out,
            "test_outcomes": [
                {"name": case.get("name"), "passed": case.get("passed")}
                for case in test_feedback
                if isinstance(case, dict)
            ],
            "static_findings": result.get("findings", []),
        },
    }


@router.post(
    "/api/v1/evaluations/{evaluation_id}/review",
    response_model=AIReviewResponse,
    status_code=status.HTTP_200_OK,
)
def create_or_get_ai_review(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIReviewResponse:
    record = _owned_evaluation(db, evaluation_id, current_user.id)
    existing = db.scalar(select(AIReview).where(AIReview.evaluation_id == record.id))
    if existing is not None:
        return _review_response(existing)

    if len(record.source_code) > MAX_REVIEW_SOURCE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"AI review is limited to {MAX_REVIEW_SOURCE_CHARS} source characters per evaluation.",
        )

    try:
        review, model = generate_ai_review(record.source_code, _evaluation_context(db, record))
    except AIReviewNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIReviewProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except AIReviewOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    review_record = AIReview(
        evaluation_id=record.id,
        model=model,
        review_json=review.model_dump(mode="json"),
    )
    db.add(review_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent request may have completed the same review first.
        existing = db.scalar(select(AIReview).where(AIReview.evaluation_id == record.id))
        if existing is None:
            raise HTTPException(status_code=409, detail="The AI review could not be saved.") from None
        return _review_response(existing)

    db.refresh(review_record)
    return _review_response(review_record)


@router.get(
    "/api/v1/evaluations/{evaluation_id}/review",
    response_model=AIReviewResponse,
)
def get_ai_review(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIReviewResponse:
    record = _owned_evaluation(db, evaluation_id, current_user.id)
    review_record = db.scalar(select(AIReview).where(AIReview.evaluation_id == record.id))
    if review_record is None:
        raise HTTPException(status_code=404, detail="AI review not found.")
    return _review_response(review_record)
