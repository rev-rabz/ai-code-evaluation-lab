"""Add reviewer role, assignment, and human-review records.

Revision ID: 0004_stage10_reviewers
Revises: 0003_stage8_ai_reviews
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004_stage10_reviewers"
down_revision = "0003_stage8_ai_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "is_reviewer" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column(
            "users",
            sa.Column("is_reviewer", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if not inspect(bind).has_table("evaluation_assignments"):
        op.create_table(
            "evaluation_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "evaluation_id",
                sa.Integer(),
                sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "reviewer_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "assigned_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("evaluation_id", name="uq_evaluation_assignments_evaluation_id"),
        )
        op.create_index("ix_evaluation_assignments_reviewer_id", "evaluation_assignments", ["reviewer_id"])

    if not inspect(bind).has_table("evaluation_reviews"):
        op.create_table(
            "evaluation_reviews",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "evaluation_id",
                sa.Integer(),
                sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "reviewer_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("decision", sa.String(20), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("evaluation_id", name="uq_evaluation_reviews_evaluation_id"),
            sa.CheckConstraint("decision IN ('approved', 'needs_changes', 'flagged')", name="ck_evaluation_reviews_decision"),
        )
        op.create_index("ix_evaluation_reviews_reviewer_id", "evaluation_reviews", ["reviewer_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("evaluation_reviews"):
        op.drop_index("ix_evaluation_reviews_reviewer_id", table_name="evaluation_reviews")
        op.drop_table("evaluation_reviews")
    if inspector.has_table("evaluation_assignments"):
        op.drop_index("ix_evaluation_assignments_reviewer_id", table_name="evaluation_assignments")
        op.drop_table("evaluation_assignments")
    if "is_reviewer" in {column["name"] for column in inspector.get_columns("users")}:
        op.drop_column("users", "is_reviewer")
