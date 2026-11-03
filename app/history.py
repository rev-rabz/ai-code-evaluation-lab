from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvaluationHistoryItem(BaseModel):
    id: int
    task_id: str | None
    language: str
    status: str
    score: float
    passed_tests: int
    total_tests: int
    execution_performed: bool
    execution_timed_out: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationHistoryDetail(EvaluationHistoryItem):
    source_code: str
    result: dict
