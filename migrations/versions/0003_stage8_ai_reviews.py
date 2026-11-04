"""Store opt-in AI code reviews for owned evaluations.

Revision ID: 0003_stage8_ai_reviews
Revises: 0002_stage7_tasks
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_stage8_ai_reviews"
down_revision = "0002_stage7_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("ai_reviews"):
        op.create_table(
            "ai_reviews",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "evaluation_id",
                sa.Integer(),
                sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("model", sa.String(120), nullable=False),
            sa.Column("review_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("evaluation_id", name="uq_ai_reviews_evaluation_id"),
        )


def downgrade() -> None:
    if inspect(op.get_bind()).has_table("ai_reviews"):
        op.drop_table("ai_reviews")
