from app.evaluator import evaluate_submission
from app.schemas import EvaluationRequest


def test_static_analysis_does_not_award_client_supplied_score():
    request = EvaluationRequest(language="python", source_code="def add(a, b): return a + b",
        test_results=[{"name": "forged", "passed": True}])
    result = evaluate_submission(request)
    assert result.score == 0
    assert result.passed_tests == 0
    assert result.total_tests == 0


def test_missing_required_function_is_reported():
    result = evaluate_submission(EvaluationRequest(language="python", source_code="def sub(a,b): return a-b", required_functions=["add"]))
    assert result.status == "invalid"
    assert any(item.code == "MISSING_FUNCTION" for item in result.findings)


def test_syntax_error_is_reported():
    result = evaluate_submission(EvaluationRequest(language="python", source_code="def broken(:"))
    assert result.status == "invalid"
    assert result.syntax_valid is False
