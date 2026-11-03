from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvaluationRecord(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(30), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    score: Mapped[float] = mapped_column(nullable=False)
    passed_tests: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tests: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_performed: Mapped[bool] = mapped_column(nullable=False)
    execution_timed_out: Mapped[bool] = mapped_column(nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
