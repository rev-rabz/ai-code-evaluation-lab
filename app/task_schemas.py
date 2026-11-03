from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TestCaseInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    args: list[Any] = Field(max_length=50)
    expected: Any


class TaskCreate(BaseModel):
    task_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,99}$")
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=1, max_length=5000)
    instructions: str = Field(min_length=1, max_length=10000)
    difficulty: Literal["beginner", "intermediate", "advanced"]
    category: str = Field(min_length=2, max_length=80)
    function_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
    examples: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    test_cases: list[TestCaseInput] = Field(min_length=1, max_length=100)


class TaskMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    instructions: str | None = Field(default=None, min_length=1, max_length=10000)
    difficulty: Literal["beginner", "intermediate", "advanced"] | None = None
    category: str | None = Field(default=None, min_length=2, max_length=80)
    examples: list[dict[str, Any]] | None = Field(default=None, max_length=20)


class TaskVersionCreate(BaseModel):
    function_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
    test_cases: list[TestCaseInput] = Field(min_length=1, max_length=100)


class TaskResponse(BaseModel):
    task_id: str
    title: str
    description: str
    instructions: str
    difficulty: str
    category: str
    examples: list[dict[str, Any]]
    is_published: bool
    is_archived: bool
    active_version: int | None
    created_at: str
    updated_at: str


class TaskVersionResponse(BaseModel):
    id: int
    version: int
    function_name: str
    test_case_count: int
    is_published: bool
    created_at: str
