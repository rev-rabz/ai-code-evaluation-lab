from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, aliased

from app.ai_review_schemas import AIReviewContent
from app.auth import get_current_user
from app.database import get_db
from app.models import (
    AIReview,
    EvaluationAssignment,
    EvaluationRecord,
    EvaluationReview,
    Task,
    TaskVersion,
    User,
)
from app.reviewer_schemas import AssignmentUpdate, HumanReviewUpsert

router = APIRouter(tags=["reviewer"])


def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin and not current_user.is_reviewer:
        raise HTTPException(status_code=403, detail="Reviewer access is required.")
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return current_user


def _accessible_evaluation(db: Session, evaluation_id: int, current_user: User) -> tuple[EvaluationRecord, EvaluationAssignment | None]:
    record = db.get(EvaluationRecord, evaluation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    assignment = db.scalar(
        select(EvaluationAssignment).where(EvaluationAssignment.evaluation_id == evaluation_id)
    )
    if not current_user.is_admin and (assignment is None or assignment.reviewer_id != current_user.id):
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    return record, assignment


@router.get("/api/v1/admin/reviewers")
def list_eligible_reviewers(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[dict]:
    users = db.scalars(
        select(User)
        .where((User.is_reviewer.is_(True)) | (User.is_admin.is_(True)))
        .order_by(User.email)
    ).all()
    return [
        {"id": user.id, "email": user.email, "is_reviewer": user.is_reviewer, "is_admin": user.is_admin}
        for user in users
    ]


@router.put("/api/v1/admin/evaluations/{evaluation_id}/assignment")
def set_evaluation_assignment(
    evaluation_id: int,
    request: AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict:
    record = db.get(EvaluationRecord, evaluation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    assignment = db.scalar(
        select(EvaluationAssignment).where(EvaluationAssignment.evaluation_id == evaluation_id)
    )
    if request.reviewer_id is None:
        if assignment is not None:
            db.delete(assignment)
            db.commit()
        return {"evaluation_id": evaluation_id, "assignment": None}

    reviewer = db.get(User, request.reviewer_id)
    if reviewer is None or (not reviewer.is_reviewer and not reviewer.is_admin):
        raise HTTPException(status_code=422, detail="Assignment target must be an active reviewer or administrator.")

    if assignment is None:
        assignment = EvaluationAssignment(
            evaluation_id=evaluation_id,
            reviewer_id=reviewer.id,
            assigned_by_user_id=current_user.id,
            assigned_at=datetime.now(UTC),
        )
        db.add(assignment)
    else:
        assignment.reviewer_id = reviewer.id
        assignment.assigned_by_user_id = current_user.id
        assignment.assigned_at = datetime.now(UTC)
    db.commit()
    db.refresh(assignment)
    return {
        "evaluation_id": evaluation_id,
        "assignment": {
            "reviewer_id": reviewer.id,
            "reviewer_email": reviewer.email,
            "assigned_by_user_id": current_user.id,
            "assigned_at": assignment.assigned_at,
        },
    }


@router.get("/api/v1/reviewer/evaluations")
def list_review_queue(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    task_id: str | None = Query(default=None, max_length=100),
    evaluation_status: str | None = Query(default=None, alias="status", max_length=20),
    decision: str | None = Query(default=None, max_length=20),
    reviewer_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
) -> dict:
    if reviewer_id is not None and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only administrators may filter by reviewer.")

    submitter = aliased(User)
    assigned_reviewer = aliased(User)
    review_author = aliased(User)
    filters = []
    if not current_user.is_admin:
        filters.append(EvaluationAssignment.reviewer_id == current_user.id)
    elif reviewer_id is not None:
        filters.append(EvaluationAssignment.reviewer_id == reviewer_id)
    if task_id:
        filters.append(EvaluationRecord.task_id == task_id)
    if evaluation_status:
        filters.append(EvaluationRecord.status == evaluation_status)
    if decision:
        if decision not in {"approved", "needs_changes", "flagged", "pending"}:
            raise HTTPException(status_code=422, detail="Unsupported human review decision.")
        if decision == "pending":
            filters.append(EvaluationReview.id.is_(None))
        else:
            filters.append(EvaluationReview.decision == decision)

    statement = (
        select(
            EvaluationRecord,
            submitter.email,
            EvaluationAssignment,
            assigned_reviewer.email,
            EvaluationReview,
            review_author.email,
            AIReview.id,
        )
        .outerjoin(submitter, EvaluationRecord.user_id == submitter.id)
        .outerjoin(EvaluationAssignment, EvaluationAssignment.evaluation_id == EvaluationRecord.id)
        .outerjoin(assigned_reviewer, EvaluationAssignment.reviewer_id == assigned_reviewer.id)
        .outerjoin(EvaluationReview, EvaluationReview.evaluation_id == EvaluationRecord.id)
        .outerjoin(review_author, EvaluationReview.reviewer_id == review_author.id)
        .outerjoin(AIReview, AIReview.evaluation_id == EvaluationRecord.id)
        .where(*filters)
    )
    count_statement = (
        select(func.count(EvaluationRecord.id))
        .outerjoin(EvaluationAssignment, EvaluationAssignment.evaluation_id == EvaluationRecord.id)
        .outerjoin(EvaluationReview, EvaluationReview.evaluation_id == EvaluationRecord.id)
        .where(*filters)
    )
    total = db.scalar(count_statement) or 0
    rows = db.execute(
        statement.order_by(desc(EvaluationRecord.created_at), desc(EvaluationRecord.id))
        .offset(offset)
        .limit(limit)
    ).all()

    items = []
    for record, submitter_email, assignment, assigned_reviewer_email, human_review, review_author_email, ai_review_id in rows:
        items.append({
            "id": record.id,
            "submitter": {"user_id": record.user_id, "email": submitter_email} if record.user_id is not None else None,
            "task_id": record.task_id,
            "task_version_id": record.task_version_id,
            "language": record.language,
            "status": record.status,
            "score": record.score,
            "passed_tests": record.passed_tests,
            "total_tests": record.total_tests,
            "execution_performed": record.execution_performed,
            "execution_timed_out": record.execution_timed_out,
            "execution_duration_ms": (record.result_json or {}).get("execution_duration_ms"),
            "created_at": record.created_at,
            "assignment": {
                "reviewer_id": assignment.reviewer_id,
                "reviewer_email": assigned_reviewer_email,
                "assigned_at": assignment.assigned_at,
            } if assignment is not None else None,
            "human_review": {
                "decision": human_review.decision,
                "notes": human_review.notes,
                "reviewer_id": human_review.reviewer_id,
                "reviewer_email": review_author_email,
                "updated_at": human_review.updated_at,
            } if human_review is not None else None,
            "has_ai_review": ai_review_id is not None,
        })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/api/v1/reviewer/evaluations/{evaluation_id}")
def get_review_detail(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
) -> dict:
    record, assignment = _accessible_evaluation(db, evaluation_id, current_user)
    submitter = db.get(User, record.user_id) if record.user_id is not None else None
    task = db.get(Task, record.task_id) if record.task_id else None
    version = db.get(TaskVersion, record.task_version_id) if record.task_version_id else None
    human_review = db.scalar(
        select(EvaluationReview).where(EvaluationReview.evaluation_id == record.id)
    )
    review_author = db.get(User, human_review.reviewer_id) if human_review is not None else None
    ai_review = db.scalar(select(AIReview).where(AIReview.evaluation_id == record.id))
    ai_review_payload = None
    if ai_review is not None:
        ai_review_payload = {
            "id": ai_review.id,
            "model": ai_review.model,
            "review": AIReviewContent.model_validate(ai_review.review_json).model_dump(mode="json"),
            "created_at": ai_review.created_at,
        }

    return {
        "id": record.id,
        "submitter": {"user_id": record.user_id, "email": submitter.email} if submitter is not None else None,
        "task": {
            "task_id": task.task_id,
            "title": task.title,
            "version": version.version if version is not None else None,
            "function_name": version.function_name if version is not None else None,
        } if task is not None else None,
        "language": record.language,
        "status": record.status,
        "score": record.score,
        "passed_tests": record.passed_tests,
        "total_tests": record.total_tests,
        "execution_performed": record.execution_performed,
        "execution_timed_out": record.execution_timed_out,
        "execution_duration_ms": (record.result_json or {}).get("execution_duration_ms"),
        "created_at": record.created_at,
        "source_code": record.source_code,
        "result": record.result_json,
        "assignment": {
            "reviewer_id": assignment.reviewer_id,
            "assigned_by_user_id": assignment.assigned_by_user_id,
            "assigned_at": assignment.assigned_at,
        } if assignment is not None else None,
        "human_review": {
            "id": human_review.id,
            "decision": human_review.decision,
            "notes": human_review.notes,
            "reviewer_id": human_review.reviewer_id,
            "reviewer_email": review_author.email if review_author is not None else None,
            "created_at": human_review.created_at,
            "updated_at": human_review.updated_at,
        } if human_review is not None else None,
        "ai_review": ai_review_payload,
    }


@router.put("/api/v1/reviewer/evaluations/{evaluation_id}/review")
def save_human_review(
    evaluation_id: int,
    request: HumanReviewUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
) -> dict:
    record, _ = _accessible_evaluation(db, evaluation_id, current_user)
    review = db.scalar(
        select(EvaluationReview).where(EvaluationReview.evaluation_id == record.id)
    )
    now = datetime.now(UTC)
    if review is None:
        review = EvaluationReview(
            evaluation_id=record.id,
            reviewer_id=current_user.id,
            decision=request.decision,
            notes=request.notes,
            created_at=now,
            updated_at=now,
        )
        db.add(review)
    else:
        review.reviewer_id = current_user.id
        review.decision = request.decision
        review.notes = request.notes
        review.updated_at = now
    db.commit()
    db.refresh(review)
    return {
        "id": review.id,
        "evaluation_id": review.evaluation_id,
        "decision": review.decision,
        "notes": review.notes,
        "reviewer_id": review.reviewer_id,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }
