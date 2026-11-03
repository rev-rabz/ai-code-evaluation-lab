import ast

from app.schemas import EvaluationRequest, EvaluationResponse, Finding


def evaluate_submission(request: EvaluationRequest) -> EvaluationResponse:
    """Perform static inspection only; client-supplied results never affect scores."""
    findings: list[Finding] = []
    syntax_valid = True
    try:
        tree = ast.parse(request.source_code)
    except SyntaxError as exc:
        syntax_valid = False
        tree = None
        findings.append(Finding(
            code="PYTHON_SYNTAX_ERROR", severity="error", message=exc.msg, line=exc.lineno
        ))

    if tree is not None:
        defined_functions = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in request.required_functions:
            if name not in defined_functions:
                findings.append(Finding(
                    code="MISSING_FUNCTION", severity="error",
                    message=f"Required function '{name}' was not found."
                ))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module in {"subprocess", "socket", "ctypes"}:
                    findings.append(Finding(
                        code="REVIEW_IMPORT", severity="warning",
                        message=f"Import '{module}' requires security review.", line=node.lineno
                    ))

    has_errors = any(finding.severity == "error" for finding in findings)
    return EvaluationResponse(
        status="valid" if syntax_valid and not has_errors else "invalid",
        syntax_valid=syntax_valid, score=0.0, passed_tests=0, total_tests=0, pass_rate=0.0,
        findings=findings, test_feedback=[], task_id=request.task_id,
        note=("Static inspection only. Client-supplied test_results are ignored; a score is "
              "awarded only after a registered server-owned test suite runs in the isolated runner."),
    )
