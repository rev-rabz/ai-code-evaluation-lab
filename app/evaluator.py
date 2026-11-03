import ast

from app.schemas import (
    EvaluationRequest,
    EvaluationResponse,
    Finding,
    TestCaseFeedback,
)


def evaluate_submission(request: EvaluationRequest) -> EvaluationResponse:
    """Inspect source safely; never execute submitted code in this process."""
    findings: list[Finding] = []
    syntax_valid = True
    tree: ast.Module | None = None

    try:
        tree = ast.parse(request.source_code)
    except SyntaxError as exc:
        syntax_valid = False
        findings.append(
            Finding(
                code="PYTHON_SYNTAX_ERROR",
                severity="error",
                message=exc.msg,
                line=exc.lineno,
            )
        )

    if tree is not None:
        defined_functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function_name in request.required_functions:
            if function_name not in defined_functions:
                findings.append(
                    Finding(
                        code="MISSING_FUNCTION",
                        severity="error",
                        message=f"Required function '{function_name}' was not found.",
                    )
                )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"subprocess", "socket", "ctypes"}:
                        findings.append(
                            Finding(
                                code="REVIEW_IMPORT",
                                severity="warning",
                                message=f"Import '{alias.name}' requires security review.",
                                line=node.lineno,
                            )
                        )
            elif isinstance(node, ast.ImportFrom) and node.module in {
                "subprocess",
                "socket",
                "ctypes",
            }:
                findings.append(
                    Finding(
                        code="REVIEW_IMPORT",
                        severity="warning",
                        message=f"Import from '{node.module}' requires security review.",
                        line=node.lineno,
                    )
                )

    passed_tests = sum(result.passed for result in request.test_results)
    total_tests = len(request.test_results)
    pass_rate = passed_tests / total_tests if total_tests else 0.0

    has_errors = any(finding.severity == "error" for finding in findings)
    score = round(pass_rate * 100, 2) if total_tests else 0.0
    if not syntax_valid or has_errors:
        score = 0.0

    feedback = [
        TestCaseFeedback(
            name=result.name,
            passed=result.passed,
            expected=result.expected,
            actual=result.actual,
            duration_ms=result.duration_ms,
        )
        for result in request.test_results
    ]

    return EvaluationResponse(
        status="valid" if syntax_valid and not has_errors else "invalid",
        syntax_valid=syntax_valid,
        score=score,
        passed_tests=passed_tests,
        total_tests=total_tests,
        pass_rate=round(pass_rate, 4),
        findings=findings,
        test_feedback=feedback,
        note=(
            "Source was inspected by the API. Client-supplied test results are untrusted and "
            "must not be used as authoritative scores. Request isolated execution separately; "
            "execution output alone does not constitute a trusted test result."
        ),
    )
