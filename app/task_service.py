from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskVersion


def version_payload(version: TaskVersion) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "function_name": version.function_name,
        "test_case_count": len(version.test_cases),
        "is_published": version.is_published,
        "created_at": version.created_at.isoformat(),
    }


def task_payload(task: Task, version: TaskVersion | None = None) -> dict:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "instructions": task.instructions,
        "difficulty": task.difficulty,
        "category": task.category,
        "examples": task.examples,
        "is_published": task.active_version_id is not None and not task.is_archived,
        "is_archived": task.is_archived,
        "active_version": version.version if version else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def get_active_version(db: Session, task: Task) -> TaskVersion | None:
    if task.active_version_id is None:
        return None
    return db.get(TaskVersion, task.active_version_id)


def get_published_task(db: Session, task_id: str) -> tuple[Task, TaskVersion]:
    task = db.scalar(select(Task).where(Task.task_id == task_id, Task.is_archived.is_(False)))
    if task is None:
        raise LookupError("Task not found.")
    version = get_active_version(db, task)
    if version is None or not version.is_published:
        raise LookupError("Task not found.")
    return task, version


def create_version(db: Session, task: Task, function_name: str, test_cases: list[dict]) -> TaskVersion:
    latest = db.scalar(
        select(TaskVersion).where(TaskVersion.task_id == task.task_id).order_by(TaskVersion.version.desc()).limit(1)
    )
    version = TaskVersion(
        task_id=task.task_id,
        version=(latest.version + 1) if latest else 1,
        function_name=function_name,
        test_cases=test_cases,
        is_published=False,
    )
    db.add(version)
    db.flush()
    return version


def now_utc() -> datetime:
    return datetime.now(UTC)
