"""Add user accounts and evaluation ownership.

Revision ID: 0001_stage5_auth
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0001_stage5_auth"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("hashed_password", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    inspector = inspect(bind)
    if not inspector.has_table("evaluations"):
        op.create_table(
            "evaluations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("task_id", sa.String(length=100), nullable=True),
            sa.Column("language", sa.String(length=30), nullable=False),
            sa.Column("source_code", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("passed_tests", sa.Integer(), nullable=False),
            sa.Column("total_tests", sa.Integer(), nullable=False),
            sa.Column("execution_performed", sa.Boolean(), nullable=False),
            sa.Column("execution_timed_out", sa.Boolean(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
    else:
        columns = {column["name"] for column in inspect(bind).get_columns("evaluations")}
        if "user_id" not in columns:
            with op.batch_alter_table("evaluations") as batch_op:
                batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_evaluations_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL"
                )

    for table, column, index, unique in [
        ("users", "email", "ix_users_email", True),
        ("evaluations", "user_id", "ix_evaluations_user_id", False),
    ]:
        existing = {item["name"] for item in inspect(bind).get_indexes(table)}
        if index not in existing:
            op.create_index(index, table, [column], unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("evaluations"):
        indexes = {item["name"] for item in inspect(bind).get_indexes("evaluations")}
        if "ix_evaluations_user_id" in indexes:
            op.drop_index("ix_evaluations_user_id", table_name="evaluations")
        columns = {column["name"] for column in inspect(bind).get_columns("evaluations")}
        if "user_id" in columns:
            with op.batch_alter_table("evaluations") as batch_op:
                batch_op.drop_column("user_id")
    if inspect(bind).has_table("users"):
        indexes = {item["name"] for item in inspect(bind).get_indexes("users")}
        if "ix_users_email" in indexes:
            op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
