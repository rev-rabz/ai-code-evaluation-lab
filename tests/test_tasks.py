from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.models import User

client = TestClient(app)


def _admin_override():
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, email="admin@example.com", hashed_password="not-used", is_admin=True
    )


def test_regular_user_cannot_manage_tasks():
    response = client.post("/api/v1/admin/tasks", json={})
    assert response.status_code == 403


def test_admin_task_lifecycle_and_immutable_versions():
    _admin_override()
    payload = {
        "task_id": "python.multiply",
        "title": "Multiply Two Numbers",
        "description": "Return the product of two numbers.",
        "instructions": "Define multiply(a, b) and return a * b.",
        "difficulty": "beginner",
        "category": "fundamentals",
        "function_name": "multiply",
        "examples": [{"input": "multiply(2, 4)", "output": 8}],
        "test_cases": [{"name": "positive", "args": [2, 4], "expected": 8}],
    }
    created = client.post("/api/v1/admin/tasks", json=payload)
    assert created.status_code == 201
    first = created.json()["version"]
    assert first["version"] == 1
    assert first["is_published"] is False

    assert client.get("/api/v1/tasks/python.multiply").status_code == 404
    published = client.post(
        f"/api/v1/admin/tasks/python.multiply/versions/{first['id']}/publish"
    )
    assert published.status_code == 200
    assert published.json()["active_version"] == 1

    public_detail = client.get("/api/v1/tasks/python.multiply")
    assert public_detail.status_code == 200
    assert public_detail.json()["test_cases"] == [{"name": "positive", "args": [2, 4]}]
    assert "expected" not in public_detail.text

    next_version = client.post("/api/v1/admin/tasks/python.multiply/versions", json={
        "function_name": "multiply",
        "test_cases": [
            {"name": "positive", "args": [3, 4], "expected": 12},
            {"name": "zero", "args": [0, 5], "expected": 0},
        ],
    })
    assert next_version.status_code == 201
    second = next_version.json()
    assert second["version"] == 2
    assert second["is_published"] is False

    # Creating a draft does not replace the active published version.
    assert client.get("/api/v1/tasks/python.multiply").json()["active_version"] == 1
    published_second = client.post(
        f"/api/v1/admin/tasks/python.multiply/versions/{second['id']}/publish"
    )
    assert published_second.status_code == 200
    assert published_second.json()["active_version"] == 2

    admin_list = client.get("/api/v1/admin/tasks")
    assert admin_list.status_code == 200
    assert any(item["task_id"] == "python.multiply" for item in admin_list.json())

    archived = client.post("/api/v1/admin/tasks/python.multiply/archive")
    assert archived.status_code == 200
    assert client.get("/api/v1/tasks/python.multiply").status_code == 404


def test_task_metadata_update_does_not_rewrite_published_test_suite():
    _admin_override()
    response = client.patch("/api/v1/admin/tasks/python.add", json={"title": "Addition Challenge"})
    assert response.status_code == 200
    assert response.json()["title"] == "Addition Challenge"
    detail = client.get("/api/v1/tasks/python.add")
    assert detail.status_code == 200
    assert detail.json()["version"]["version"] == 1
    assert detail.json()["test_cases"][0] == {"name": "positive numbers", "args": [2, 3]}
