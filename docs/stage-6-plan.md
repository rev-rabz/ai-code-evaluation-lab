# Stage 6: Execution Security Hardening

## Objective

Move trusted grading logic outside the process that executes submitted code. A submission must never receive the trusted test suite, expected values, or access to the runner's Docker control socket.

## Scope

1. Replace the current single-container test harness with a trusted runner-side orchestrator.
2. Execute each test case in a fresh disposable candidate container.
3. Pass only the submission source, required function name, and that case's arguments into the candidate container. Never pass expected values or the test catalogue.
4. Compare the candidate's returned value with the expected value in the trusted runner process.
5. Keep resource limits, no network, read-only root filesystem, non-root execution, dropped capabilities, bounded output, timeout enforcement, and forced cleanup.
6. Add regression tests proving the candidate process receives no expected values or complete test suite, and that timeouts/runtime failures cannot earn passing marks.
7. Update security documentation to explain the improved boundary and remaining risks.

## Explicit non-goals

- This stage does not remove the runner service's Docker socket mount.
- Containers still share the host kernel; this is not a production-grade multi-tenant sandbox.
- This stage does not add rate limiting, queueing, multiple languages, or a frontend.
- This stage does not claim protection against kernel/container-runtime vulnerabilities or a compromised Docker host.

## Acceptance criteria

- The candidate container receives only one test case's input arguments and source code.
- Trusted expected values and the full test suite remain in the runner service process.
- The runner computes pass/fail itself.
- Every candidate container is removed, including on timeout and errors.
- A correct solution passes all registered tests; incorrect, crashing, and infinite-loop submissions cannot obtain a passing score.
- Existing API authentication, history, and scoring tests continue to pass.
- Pytest and Ruff pass in CI.
