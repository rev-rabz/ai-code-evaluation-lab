from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewEvidence(BaseModel):
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    code_excerpt: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_line_range(self) -> "ReviewEvidence":
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ReviewFinding(BaseModel):
    category: Literal[
        "correctness",
        "readability",
        "performance",
        "security",
        "maintainability",
        "testing",
    ]
    severity: Literal["info", "warning", "error"]
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=2000)
    evidence: ReviewEvidence
    suggestion: str = Field(min_length=1, max_length=2000)


class AIReviewContent(BaseModel):
    summary: str = Field(min_length=1, max_length=3000)
    strengths: list[str] = Field(max_length=6)
    findings: list[ReviewFinding] = Field(max_length=12)
    next_steps: list[str] = Field(max_length=6)

    model_config = ConfigDict(extra="forbid")


class AIReviewResponse(BaseModel):
    id: int
    evaluation_id: int
    model: str
    review: AIReviewContent
    created_at: datetime
