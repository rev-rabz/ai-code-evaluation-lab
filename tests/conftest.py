import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Task, TaskVersion, User


@pytest.fixture(autouse=True)
def isolate_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    test_user = User(id=1, email="owner@example.com", hashed_password=hash_password("Correct-Owner-Password-2026!"))
    db.add(test_user)
    task = Task(task_id="python.add", title="Add Two Numbers", description="Return the sum of two numbers.", instructions="Define add(a, b).", difficulty="beginner", category="fundamentals", examples=[{"input":"add(2, 3)","output":5}], is_archived=False)
    db.add(task)
    db.flush()
    version = TaskVersion(task_id="python.add", version=1, function_name="add", test_cases=[{"name":"positive numbers","args":[2,3],"expected":5},{"name":"negative numbers","args":[-4,-6],"expected":-10},{"name":"zero","args":[0,9],"expected":9},{"name":"mixed signs","args":[-3,8],"expected":5},{"name":"decimal numbers","args":[1.25,2.5],"expected":3.75}], is_published=True)
    db.add(version)
    db.flush()
    task.active_version_id = version.id
    db.commit()
    db.refresh(test_user)
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
