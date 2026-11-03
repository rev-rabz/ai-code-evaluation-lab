from app.evaluator import evaluate_submission
from app.schemas import EvaluationRequest, TestResult


def test_valid_source_and_all_tests_pass() -> None:
    request = EvaluationRequest(
        language="python",
        source_code="def add(a, b):\n    return a + b\n",
        required_functions=["add"],
        test_results=[
            TestResult(name="positive numbers", passed=True, expected=5, actual=5),
            TestResult(name="negative numbers", passed=True, expected=-1, actual=-1),
        ],
    )

    result = evaluate_submission(request)

    assert result.status == "valid"
    assert result.syntax_valid is True
    assert result.score == 100
    assert result.passed_tests == 2
    assert result.total_tests == 2
    assert result.execution_performed is False


def test_missing_required_function_is_reported() -> None:
    request = EvaluationRequest(
        language="python",
        source_code="def subtract(a, b):\n    return a - b\n",
        required_functions=["add"],
    )

    result = evaluate_submission(request)

    assert result.status == "invalid"
    assert any(finding.code == "MISSING_FUNCTION" for finding in result.findings)


def test_syntax_error_is_reported() -> None:
    request = EvaluationRequest(
        language="python",
        source_code="def broken(:\n    pass",
    )

    result = evaluate_submission(request)

    assert result.status == "invalid"
    assert result.syntax_valid is False
    assert result.findings[0].code == "PYTHON_SYNTAX_ERROR"


def test_failed_tests_reduce_score() -> None:
    request = EvaluationRequest(
        language="python",
        source_code="def add(a, b):\n    return a + b\n",
        required_functions=["add"],
        test_results=[
            TestResult(name="case one", passed=True),
            TestResult(name="case two", passed=False),
        ],
    )

    result = evaluate_submission(request)

    assert result.score == 50
    assert result.pass_rate == 0.5
