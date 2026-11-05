from typing import Literal

from pydantic import BaseModel, Field


class AssignmentUpdate(BaseModel):
    reviewer_id: int | None


class HumanReviewUpsert(BaseModel):
    decision: Literal["approved", "needs_changes", "flagged"]
    notes: str = Field(default="", max_length=4000)
