# AI Code Evaluation Lab

A Python/FastAPI starter platform for evaluating code submissions with syntax validation, static checks, test-case result analysis, and structured feedback.

> **Security status:** This MVP does not execute submitted code. It parses Python source with the standard-library AST module and evaluates test results supplied by a trusted runner. Arbitrary submissions must not be executed on the API server. A separately isolated execution adapter is a planned next stage.

## MVP features

- FastAPI endpoint for submitting Python source and test-case results
- Python syntax validation without executing the submission
- Basic static analysis (for example, missing functions and suspicious constructs)
- Test result aggregation with pass rate and per-case feedback
- Structured evaluation response suitable for a dashboard or future AI reviewer
- Pytest test suite and GitHub Actions CI

## Stack

- Python 3.11+
- FastAPI and Pydantic
- Pytest
- Ruff

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open the interactive API docs at http://127.0.0.1:8000/docs.

## Evaluate a submission

Send a POST request to `/api/v1/evaluations`:

```json
{
  "language": "python",
  "source_code": "def add(a, b):\n    return a + b\n",
  "required_functions": ["add"],
  "test_results": [
    {"name": "adds positive numbers", "passed": true, "expected": 5, "actual": 5},
    {"name": "adds negative numbers", "passed": false, "expected": -1, "actual": 0}
  ]
}
```

The endpoint validates syntax and source structure, then summarizes the supplied test results. In this MVP, `test_results` must come from a trusted test runner; the API does not run the submitted code.

## API

- `GET /health` — service health
- `POST /api/v1/evaluations` — evaluate source and trusted test results

## Roadmap

- [x] API skeleton and typed request/response models
- [x] Syntax validation and basic static analysis
- [x] Test-result scoring and feedback
- [x] Automated tests and CI
- [ ] Persistent evaluation history (PostgreSQL)
- [ ] Isolated execution service with strict CPU, memory, process, filesystem, and network controls
- [ ] Optional AI-generated review with evidence-linked findings
- [ ] Authentication, rate limiting, and a reviewer dashboard

## Security principles

Never run untrusted source code inside the FastAPI process or a normal application container. The future execution service should use a dedicated isolation boundary, non-root execution, read-only filesystems, no network by default, resource limits, syscall restrictions, and per-job cleanup. Docker alone should not be treated as a complete security boundary.

## Development

```bash
pytest
ruff check .
```

## License

MIT
