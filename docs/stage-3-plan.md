# Stage 3: Trusted Test Evaluation

## Goal

Move evaluation evidence and scoring from client-supplied test results to test cases controlled by the evaluator. The client submits source code and a task identifier; the server selects the task's test suite, the isolated runner executes the submission against that suite, and the API derives the score from the runner's structured results.

## Trust boundaries

- `source_code` and every field supplied by the client are untrusted.
- The client must not submit pass/fail values, expected values, actual values, test definitions, or a score that the API treats as authoritative.
- Task identifiers select from a server-maintained allowlist. Unknown task identifiers are rejected.
- Test definitions and scoring policy are maintained with the application, not accepted from the request.
- The API validates the runner response and calculates the final score itself. A runner response is trusted only across the private, authenticated API-to-runner channel.
- Execution output is diagnostic only. It is never used as proof that tests passed.

## First vertical slice

1. Add a server-owned task catalogue with one small Python function task (addition).
2. Add a request field for the task identifier. Keep the legacy `test_results` field temporarily for compatibility, but never use it for authoritative scoring.
3. Extend the private runner contract to accept a task identifier and return structured test-case outcomes in addition to process output and exit status.
4. Run the trusted test suite in the disposable execution container alongside the submitted module.
5. Validate runner results and compute `passed_tests`, `total_tests`, `pass_rate`, and `score` in the API. A failed execution or timeout must not earn a passing score.
6. Add unit tests for task lookup, malformed runner results, scoring, runtime errors, timeouts, and attempts to supply client-authored test results.
7. Update the API docs and README with the new request/response contract and its security limitations.

## Initial scoring rule

- Each registered test case has equal weight.
- `score = round(passed_tests / total_tests * 100, 2)`.
- A syntax error, execution timeout, or submission runtime failure produces zero passed tests.
- A task with no registered tests is invalid configuration and must not silently receive a perfect score.
- Static-analysis findings remain separate from the test score.

## Security and limitations

The test catalogue and scoring rules are server-controlled, but this stage is not a claim of cheat-proof hidden tests or production-grade isolation. Python code running in the same process as a test harness may attempt introspection or tampering. The Docker runner also retains Docker-socket access and shares the host kernel. Keep the runner private and on a dedicated disposable host/VM. A stronger isolation boundary and independent security review are required before public multi-tenant use.

## Out of scope for this first slice

- User-authored or dynamically uploaded tests
- Persistent evaluation history
- AI-generated grading
- Multiple programming languages
- Production authentication, quotas, and multi-tenant scheduling
