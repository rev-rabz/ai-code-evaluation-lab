from typing import Any, Literal

from pydantic import BaseModel, Field


class TestResult(BaseModel):
    __test__ = False

    name: str = Field(min_length=1, max_length=200)
    passed: bool
    expected: Any | None = None
    actual: Any | None = None
    duration_ms: float | None = Field(default=None, ge=0)


class EvaluationRequest(BaseModel):
    language: Literal["python"]
    source_code: str = Field(min_length=1, max_length=100_000)
    required_functions: list[str] = Field(default_factory=list, max_length=100)
    test_results: list[TestResult] = Field(default_factory=list, max_length=500)
    execute: bool = False


class Finding(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    line: int | None = None


class TestCaseFeedback(BaseModel):
    name: str
    passed: bool
    expected: Any | None = None
    actual: Any | None = None
    duration_ms: float | None = None


class EvaluationResponse(BaseModel):
    status: Literal["valid", "invalid"]
    syntax_valid: bool
    score: float
    passed_tests: int
    total_tests: int
    pass_rate: float
    findings: list[Finding]
    test_feedback: list[TestCaseFeedback]
    execution_requested: bool = False
    execution_performed: bool = False
    execution_exit_code: int | None = None
    execution_timed_out: bool = False
    execution_duration_ms: float | None = None
    stdout: str = ""
    stderr: str = ""
    note: str
