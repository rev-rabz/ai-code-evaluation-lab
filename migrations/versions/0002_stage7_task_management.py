"""Add database-backed tasks, immutable versions, and evaluation version references.

Revision ID: 0002_stage7_tasks
Revises: 0001_stage5_auth
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_stage7_tasks"
down_revision = "0001_stage5_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "is_admin" not in {c["name"] for c in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))

    inspector = inspect(bind)
    if not inspector.has_table("tasks"):
        op.create_table(
            "tasks",
            sa.Column("task_id", sa.String(100), primary_key=True),
            sa.Column("title", sa.String(160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("instructions", sa.Text(), nullable=False),
            sa.Column("difficulty", sa.String(20), nullable=False),
            sa.Column("category", sa.String(80), nullable=False),
            sa.Column("examples", sa.JSON(), nullable=False),
            sa.Column("active_version_id", sa.Integer(), nullable=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_tasks_category", "tasks", ["category"])

    inspector = inspect(bind)
    if not inspector.has_table("task_versions"):
        op.create_table(
            "task_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_id", sa.String(100), sa.ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("function_name", sa.String(80), nullable=False),
            sa.Column("test_cases", sa.JSON(), nullable=False),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("task_id", "version", name="uq_task_versions_task_version"),
        )
        op.create_index("ix_task_versions_task_id", "task_versions", ["task_id"])

    inspector = inspect(bind)
    if "task_version_id" not in {c["name"] for c in inspector.get_columns("evaluations")}:
        with op.batch_alter_table("evaluations") as batch:
            batch.add_column(sa.Column("task_version_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_evaluations_task_version_id_task_versions",
                "task_versions", ["task_version_id"], ["id"], ondelete="SET NULL",
            )

    # Seed the existing built-in task as the first published, database-backed version.
    existing = bind.execute(sa.text("SELECT task_id FROM tasks WHERE task_id = :task_id"), {"task_id": "python.add"}).first()
    if existing is None:
        now = datetime.now(UTC)
        bind.execute(sa.text("""
            INSERT INTO tasks
            (task_id, title, description, instructions, difficulty, category, examples,
             active_version_id, is_archived, created_at, updated_at)
            VALUES
            (:task_id, :title, :description, :instructions, :difficulty, :category, :examples,
             NULL, FALSE, :created_at, :updated_at)
        """).bindparams(sa.bindparam("examples", type_=sa.JSON())), {
            "task_id": "python.add",
            "title": "Add Two Numbers",
            "description": "Implement a function that returns the sum of two numbers.",
            "instructions": "Define add(a, b) and return the arithmetic sum of a and b.",
            "difficulty": "beginner",
            "category": "fundamentals",
            "examples": [{"input": "add(2, 3)", "output": 5}],
            "created_at": now,
            "updated_at": now,
        })
        result = bind.execute(sa.text("""
            INSERT INTO task_versions (task_id, version, function_name, test_cases, is_published, created_at)
            VALUES (:task_id, 1, :function_name, :test_cases, TRUE, :created_at)
        """).bindparams(sa.bindparam("test_cases", type_=sa.JSON())), {
            "task_id": "python.add",
            "function_name": "add",
            "test_cases": [
                {"name": "positive numbers", "args": [2, 3], "expected": 5},
                {"name": "negative numbers", "args": [-4, -6], "expected": -10},
                {"name": "zero", "args": [0, 9], "expected": 9},
                {"name": "mixed signs", "args": [-3, 8], "expected": 5},
                {"name": "decimal numbers", "args": [1.25, 2.5], "expected": 3.75},
            ],
            "created_at": now,
        })
        version_id = result.lastrowid
        if version_id is None:
            version_id = bind.execute(
                sa.text("SELECT id FROM task_versions WHERE task_id = :task_id AND version = 1"),
                {"task_id": "python.add"},
            ).scalar_one()
        bind.execute(
            sa.text("UPDATE tasks SET active_version_id = :version_id WHERE task_id = :task_id"),
            {"version_id": version_id, "task_id": "python.add"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if (
        inspector.has_table("evaluations")
        and "task_version_id" in {c["name"] for c in inspector.get_columns("evaluations")}
    ):
        with op.batch_alter_table("evaluations") as batch:
            batch.drop_column("task_version_id")
    if inspector.has_table("task_versions"):
        op.drop_index("ix_task_versions_task_id", table_name="task_versions")
        op.drop_table("task_versions")
    if inspector.has_table("tasks"):
        op.drop_index("ix_tasks_category", table_name="tasks")
        op.drop_table("tasks")
    if inspector.has_table("users") and "is_admin" in {c["name"] for c in inspector.get_columns("users")}:
        op.drop_column("users", "is_admin")
