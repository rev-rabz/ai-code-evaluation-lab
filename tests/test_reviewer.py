from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.main import app
from app.models import EvaluationRecord, User

client = TestClient(app)


def _session():
    generator = app.dependency_overrides[get_db]()
    return next(generator), generator


def _add_reviewer(user_id: int = 2, email: str = "reviewer@example.com") -> None:
    db, generator = _session()
    try:
        db.add(User(
            id=user_id,
            email=email,
            hashed_password="not-used",
            is_reviewer=True,
        ))
        db.commit()
    finally:
        db.close()
        generator.close()


def _add_evaluation(evaluation_id: int = 1) -> None:
    db, generator = _session()
    try:
        db.add(EvaluationRecord(
            id=evaluation_id,
            user_id=1,
            task_id="python.add",
            task_version_id=None,
            language="python",
            source_code="def add(a, b):\n    return a + b",
            status="completed",
            score=100,
            passed_tests=5,
            total_tests=5,
            execution_performed=True,
            execution_timed_out=False,
            result_json={
                "score": 100,
                "test_feedback": [{"name": "positive numbers", "passed": True}],
                "findings": [],
            },
        ))
        db.commit()
    finally:
        db.close()
        generator.close()


def _admin_override() -> None:
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1,
        email="admin@example.com",
        hashed_password="not-used",
        is_admin=True,
    )


def _reviewer_override(user_id: int = 2, email: str = "reviewer@example.com") -> None:
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email=email,
        hashed_password="not-used",
        is_reviewer=True,
    )


def test_regular_user_cannot_access_reviewer_or_assignment_apis():
    assert client.get("/api/v1/reviewer/evaluations").status_code == 403
    assert client.get("/api/v1/admin/reviewers").status_code == 403
    assert client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": 2},
    ).status_code == 403


def test_admin_can_assign_and_reviewer_can_review_only_assigned_evaluations():
    _add_reviewer()
    _add_evaluation()
    _admin_override()

    eligible = client.get("/api/v1/admin/reviewers")
    assert eligible.status_code == 200
    assert eligible.json() == [{
        "id": 2,
        "email": "reviewer@example.com",
        "is_reviewer": True,
        "is_admin": False,
    }]

    assigned = client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": 2},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignment"]["reviewer_id"] == 2

    admin_queue = client.get("/api/v1/reviewer/evaluations")
    assert admin_queue.status_code == 200
    assert admin_queue.json()["total"] == 1
    assert admin_queue.json()["items"][0]["assignment"]["reviewer_email"] == "reviewer@example.com"

    _reviewer_override()
    queue = client.get("/api/v1/reviewer/evaluations")
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["id"] == 1

    detail = client.get("/api/v1/reviewer/evaluations/1")
    assert detail.status_code == 200
    assert detail.json()["source_code"] == "def add(a, b):\n    return a + b"

    saved = client.put(
        "/api/v1/reviewer/evaluations/1/review",
        json={"decision": "approved", "notes": "Correct implementation."},
    )
    assert saved.status_code == 200
    assert saved.json()["decision"] == "approved"
    assert saved.json()["reviewer_id"] == 2

    filtered = client.get("/api/v1/reviewer/evaluations?decision=approved")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["human_review"]["notes"] == "Correct implementation."

    detail_after_review = client.get("/api/v1/reviewer/evaluations/1")
    assert detail_after_review.json()["human_review"]["reviewer_email"] == "reviewer@example.com"


def test_reviewer_cannot_see_unassigned_or_another_reviewers_evaluations():
    _add_reviewer()
    _add_evaluation()
    _reviewer_override()

    queue = client.get("/api/v1/reviewer/evaluations")
    assert queue.status_code == 200
    assert queue.json()["items"] == []
    assert queue.json()["total"] == 0
    assert client.get("/api/v1/reviewer/evaluations/1").status_code == 404
    assert client.put(
        "/api/v1/reviewer/evaluations/1/review",
        json={"decision": "flagged", "notes": "Not assigned to me."},
    ).status_code == 404


def test_admin_can_unassign_evaluation():
    _add_reviewer()
    _add_evaluation()
    _admin_override()

    assert client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": 2},
    ).status_code == 200
    response = client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": None},
    )
    assert response.status_code == 200
    assert response.json()["assignment"] is None


def test_assignment_rejects_regular_accounts_as_reviewers():
    _add_evaluation()
    _admin_override()
    response = client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": 1},
    )
    assert response.status_code == 422


def test_reviewer_cannot_filter_by_another_reviewer_or_manage_assignments():
    _add_reviewer()
    _add_evaluation()
    _reviewer_override()

    assert client.get("/api/v1/reviewer/evaluations?reviewer_id=2").status_code == 403
    assert client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": 2},
    ).status_code == 403


def test_invalid_human_review_decision_is_rejected():
    _add_reviewer()
    _add_evaluation()
    _admin_override()
    assert client.put(
        "/api/v1/admin/evaluations/1/assignment",
        json={"reviewer_id": 2},
    ).status_code == 200
    _reviewer_override()
    response = client.put(
        "/api/v1/reviewer/evaluations/1/review",
        json={"decision": "maybe", "notes": ""},
    )
    assert response.status_code == 422
