from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Task, TaskVersion, User
from app.task_schemas import TaskCreate, TaskMetadataUpdate, TaskVersionCreate
from app.task_service import create_version, get_active_version, get_published_task, task_payload, version_payload

router = APIRouter(tags=["tasks"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return current_user


@router.get("/api/v1/tasks")
def list_published_tasks(db: Session = Depends(get_db)) -> list[dict]:
    tasks = db.scalars(
        select(Task).where(Task.is_archived.is_(False), Task.active_version_id.is_not(None)).order_by(Task.title)
    ).all()
    return [
        task_payload(task, get_active_version(db, task))
        for task in tasks
        if (version := get_active_version(db, task)) is not None and version.is_published
    ]


@router.get("/api/v1/tasks/{task_id}")
def read_published_task(task_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        task, version = get_published_task(db, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Task not found.") from exc
    return {**task_payload(task, version), "version": version_payload(version), "test_cases": [
        {"name": case["name"], "args": case["args"]} for case in version.test_cases
    ]}


@router.get("/api/v1/admin/tasks")
def list_admin_tasks(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> list[dict]:
    tasks = db.scalars(select(Task).order_by(Task.updated_at.desc())).all()
    return [task_payload(task, get_active_version(db, task)) for task in tasks]


@router.post("/api/v1/admin/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    request: TaskCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    if db.get(Task, request.task_id):
        raise HTTPException(status_code=409, detail="A task with this task_id already exists.")
    task = Task(
        task_id=request.task_id,
        title=request.title,
        description=request.description,
        instructions=request.instructions,
        difficulty=request.difficulty,
        category=request.category,
        examples=request.examples,
        is_archived=False,
    )
    db.add(task)
    cases = [case.model_dump(mode="json") for case in request.test_cases]
    version = create_version(db, task, request.function_name, cases)
    db.commit()
    db.refresh(task)
    db.refresh(version)
    return {**task_payload(task), "version": version_payload(version)}


@router.patch("/api/v1/admin/tasks/{task_id}")
def update_task_metadata(
    task_id: str,
    request: TaskMetadataUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    for key, value in request.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task_payload(task, get_active_version(db, task))


@router.post("/api/v1/admin/tasks/{task_id}/versions", status_code=status.HTTP_201_CREATED)
def create_task_version(
    task_id: str,
    request: TaskVersionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    cases = [case.model_dump(mode="json") for case in request.test_cases]
    version = create_version(db, task, request.function_name, cases)
    db.commit()
    db.refresh(version)
    return version_payload(version)


@router.post("/api/v1/admin/tasks/{task_id}/versions/{version_id}/publish")
def publish_task_version(
    task_id: str,
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    task = db.get(Task, task_id)
    version = db.scalar(select(TaskVersion).where(
        TaskVersion.id == version_id, TaskVersion.task_id == task_id
    ))
    if task is None or version is None:
        raise HTTPException(status_code=404, detail="Task version not found.")
    if not version.test_cases:
        raise HTTPException(status_code=422, detail="A task version must contain trusted test cases.")
    version.is_published = True
    task.active_version_id = version.id
    task.is_archived = False
    db.commit()
    db.refresh(task)
    return {**task_payload(task, version), "version": version_payload(version)}


@router.post("/api/v1/admin/tasks/{task_id}/archive")
def archive_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    task.is_archived = True
    db.commit()
    return {"task_id": task_id, "is_archived": True}
