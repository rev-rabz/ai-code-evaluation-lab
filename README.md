# AI Code Evaluation Lab

A Python/FastAPI platform for inspecting code submissions, running trusted tests in disposable Docker containers, and retaining private evaluation history for registered users.

> **Execution status:** The API never evaluates submitted code inside its own process. When execution is requested, it forwards source to a separate internal runner service. The runner launches a fresh container with no network, a read-only root filesystem, a non-root user, dropped Linux capabilities, resource limits, and automatic cleanup.

## Features

- FastAPI endpoint for Python submissions
- Python syntax validation and basic static analysis
- Server-owned Python task catalogue and trusted test feedback
- Server-calculated scores from tests executed in the isolated runner
- Persistent PostgreSQL evaluation history (SQLite for local development)
- Account registration and login with Argon2 password hashing
- Short-lived signed bearer tokens (JWT)
- Authenticated submissions and user-scoped history/detail endpoints
- Alembic schema migrations
- Per-run timeout, memory, CPU, process, file-size, and output limits
- Pytest and Ruff checks in GitHub Actions
- Optional AI-generated code reviews with source-line evidence and user-scoped persistence

## Stack

- Python 3.11+
- FastAPI, Pydantic, HTTPX
- SQLAlchemy and Alembic
- PostgreSQL / SQLite
- Argon2 password hashing and PyJWT
- Docker Engine and Docker SDK for Python
- Pytest and Ruff

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,runner]"
```

Set the required environment variables before starting the API:

- `JWT_SECRET`: a long random signing secret
- `RUNNER_URL` and `RUNNER_TOKEN`: required only for code execution
- `DATABASE_URL`: optional; defaults to SQLite at `./data/evaluations.db`

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Apply database migrations and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at http://127.0.0.1:8000 and its docs at http://127.0.0.1:8000/docs.

## Run the Docker execution stack

Requirements: Docker Engine with Compose v2. The runner requires access to the host Docker socket to create per-submission containers.

1. Copy `.env.example` to `.env`.
2. Generate three independent random values for `RUNNER_TOKEN`, `POSTGRES_PASSWORD`, and `JWT_SECRET`.
3. Start the stack:

   ```bash
   docker compose --env-file .env up --build
   ```

The API is exposed on port 8000. PostgreSQL stores evaluation history in a named Docker volume. The API container applies Alembic migrations before starting. The runner is not published to the host; it is reachable only on the Compose network and requires the shared bearer token.

Do not use `docker compose down -v` unless you intend to delete the PostgreSQL volume and all saved evaluation history.

## Authentication

Register an account:

```http
POST /api/v1/auth/register
Content-Type: application/json

{"email":"developer@example.com","password":"a-long-unique-password"}
```

Passwords must be at least 12 characters. The API stores an Argon2 password hash, never the submitted password.

Log in:

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email":"developer@example.com","password":"a-long-unique-password"}
```

The response contains a bearer access token valid for 30 minutes. Send it on protected requests:

```http
Authorization: Bearer <access_token>
```

Use `GET /api/v1/auth/me` to retrieve the authenticated account. Evaluation submission and history endpoints require authentication. A user can only list or retrieve their own evaluation records; another user's record returns 404.

## Execute a submission

Send a POST request to `/api/v1/evaluations` with a valid bearer token:

```json
{
  "language": "python",
  "source_code": "def add(a, b): return a + b",
  "task_id": "python.add",
  "execute": true
}
```

The response includes `execution_performed`, `execution_exit_code`, `execution_timed_out`, `execution_duration_ms`, `stdout`, `stderr`, trusted test feedback, and a score calculated by the API. List available tasks with public `GET /api/v1/tasks`.

Set `execute` to false (the default) to perform static inspection only. All new evaluations are associated with the authenticated account.

## Task management (Stage 7)

The public task catalogue contains published, non-archived tasks only:

- `GET /api/v1/tasks` — list published tasks
- `GET /api/v1/tasks/{task_id}` — task description, instructions, examples, active version, and test names/arguments (expected values are never exposed)

Task administration requires an account with the administrator flag:

- `GET /api/v1/admin/tasks` — list all tasks, including drafts and archived tasks
- `POST /api/v1/admin/tasks` — create a draft task and version 1 with trusted tests
- `PATCH /api/v1/admin/tasks/{task_id}` — update descriptive metadata
- `GET /api/v1/admin/tasks/{task_id}/versions` — inspect version history and trusted test cases
- `POST /api/v1/admin/tasks/{task_id}/versions` — create the next immutable test-suite version
- `POST /api/v1/admin/tasks/{task_id}/versions/{version_id}/publish` — publish and activate a version
- `POST /api/v1/admin/tasks/{task_id}/archive` — archive a task

New accounts are never administrators by default. After registering an operator account, an operator with database access can explicitly grant administrator access inside the API container:

```bash
docker compose exec api python -m app.promote_admin developer@example.com
```

Task version test cases are immutable through the API: create a new version to change the function contract or trusted tests. Evaluation history stores `task_version_id`; pre-Stage-7 records remain unversioned and are not retroactively assigned a version.

See [docs/stage-7-plan.md](docs/stage-7-plan.md) for the milestone plan.

## AI code reviews (Stage 8)

AI review is optional and separate from evaluation. It never changes trusted test scores or executes model-generated code.

**The default provider is local Ollama.** This runs the model on your own computer and does not send submitted source code to an external AI API. The first model download requires an internet connection and several GB of disk space; inference then runs locally. The default model is `qwen3.5:4b`.

### Windows + Docker Desktop setup (no API credits)

1. Install Ollama for Windows from [ollama.com/download](https://ollama.com/download).
2. Open PowerShell on Windows (not inside the API container) and download the model:

   ```powershell
   ollama pull qwen3.5:4b
   ollama list
   ```

3. Ensure the Ollama service is reachable from Docker Desktop. If the API container cannot connect, set the Windows user environment variable `OLLAMA_HOST` to `0.0.0.0:11434`, quit Ollama from the system tray, and reopen it. Ollama's API has no built-in authentication: do not expose port 11434 to the public internet or untrusted networks, and keep Windows Firewall rules restrictive.
4. Set these values in your project `.env`:

   ```dotenv
   AI_REVIEW_PROVIDER=ollama
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   OLLAMA_REVIEW_MODEL=qwen3.5:4b
   ```

5. Recreate the API container so it receives the provider settings:

   ```powershell
   docker compose --env-file .env up -d --force-recreate api
   ```

6. Confirm Docker can reach Ollama and see the downloaded model:

   ```powershell
   docker compose exec api python -c "import httpx; r=httpx.get('http://host.docker.internal:11434/api/tags', timeout=10); r.raise_for_status(); print([m['name'] for m in r.json().get('models', [])])"
   ```

If the connection test fails, check that Ollama is running on Windows, that `OLLAMA_HOST` is configured as above, and that Windows Firewall permits the local Docker-to-host connection only.

### Request and retrieve a review

After creating an evaluation, explicitly request a review:

```http
POST /api/v1/evaluations/{id}/review
Authorization: Bearer <access_token>
```

Retrieve the saved review:

```http
GET /api/v1/evaluations/{id}/review
Authorization: Bearer <access_token>
```

The review includes a summary, strengths, actionable findings, and next steps. Every finding has a 1-based source line range and exact quoted code excerpt; the API rejects findings whose excerpt does not match the stored submission. Repeating the POST returns the existing review rather than making another model request.

### Optional OpenAI provider

OpenAI remains available as an optional alternative. Set `AI_REVIEW_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally `OPENAI_REVIEW_MODEL`. OpenAI API usage is billed separately from a ChatGPT subscription. Keep the key in `.env` or a deployment secret store; never commit it. The application sends source code to OpenAI only when a user explicitly requests a review with this provider selected.

### Privacy and trust boundaries

- With Ollama, submitted source and limited evaluation context are sent from the API container to the Ollama service running on your own machine. They are not sent to an external model API. Downloading model files requires internet access.
- With OpenAI, submitted source code is sent to the Responses API only after an authenticated user explicitly requests a review. The request uses `store: false`.
- Expected test values, actual execution output, stdout, and stderr are not sent to either provider.
- Submitted source is treated as untrusted prompt data. No tools are exposed to the model and no generated code is executed.
- Every finding must cite source lines and an exact excerpt; the API validates the citation against the saved source.
- Review output is advisory and never changes trusted scores or test outcomes.

See [docs/stage-8-plan.md](docs/stage-8-plan.md) for scope and trust boundaries.

## Evaluation history

- `GET /api/v1/evaluations?limit=20&offset=0` — list the authenticated user's records
- `GET /api/v1/evaluations?task_id=python.add` — filter the authenticated user's records by task
- `GET /api/v1/evaluations/{id}` — retrieve the authenticated user's full result and source code

The migration preserves pre-Stage-5 history rows, but those legacy rows have no account owner and are not exposed through authenticated history endpoints. No automatic ownership assignment is performed.

## Sandbox controls

Each test case gets a new candidate container with:

- Network disabled
- Read-only container root filesystem
- Non-root UID/GID 65534
- All Linux capabilities dropped
- `no-new-privileges`
- 128 MiB memory limit and 0.5 CPU quota
- 32-process limit
- 5-second per-case wall-clock timeout, 30-second overall execution budget, and CPU ulimits
- 16 MiB no-exec `/tmp` tmpfs, with bounded in-memory stdout/stderr capture
- 1 MiB per-file size limit, bounded response output, and forced container cleanup

The submitted source and one test case's arguments are passed to a disposable candidate container through bounded environment values. Candidate code runs from memory; it does not receive the expected value or the full test suite. Standard output and standard error are captured in memory with a 16 KiB limit and returned through a bounded result marker.

## Important security limitations

This is a development-stage isolation layer, **not a claim of perfect or production-grade sandbox security**. Containers share the host kernel; Docker alone is not a complete security boundary. The runner service has access to the Docker daemon socket, which is effectively host-level authority. Keep it private, protect the bearer token, use a dedicated disposable host/VM, keep Docker and the host kernel patched, and do not expose the runner endpoint publicly.

For higher-risk multi-tenant workloads, use a stronger isolation boundary such as dedicated ephemeral VMs or a purpose-built sandbox runtime, add host-level monitoring and quotas, and perform an independent security review before accepting arbitrary public submissions.

The legacy `test_results` request field is retained temporarily for compatibility, but is ignored for scoring. Only server-registered test cases are sent to the private runner. The API validates the runner's test report and calculates the score itself. The first registered task is `python.add`, with five fixed test cases. The runner keeps expected values and the complete test suite outside candidate containers, starts a fresh candidate container for each test case, and compares returned values in the trusted runner process. A candidate receives only its source, function name, and the current case's arguments. This closes the earlier same-process test-harness tampering weakness, but it is not cheat-proof or production-grade sandboxing.

Authentication includes registration, login, per-user record ownership, and Stage 9 Redis-backed endpoint rate limits. It does not yet include email verification, password reset, refresh tokens, token revocation/logout, or account deletion. JWT access tokens remain valid until expiry if stolen.

## API

- `GET /health` — health check
- `GET /api/v1/tasks` — public task catalogue
- `POST /api/v1/auth/register` — create account
- `POST /api/v1/auth/login` — obtain bearer token
- `GET /api/v1/auth/me` — current account (authenticated)
- `POST /api/v1/evaluations` — submit evaluation (authenticated)
- `GET /api/v1/evaluations` — own evaluation history (authenticated)
- `GET /api/v1/evaluations/{id}` — own evaluation detail (authenticated)
- Runner's `POST /internal/execute` — private, token-protected internal endpoint

## Development checks

```bash
python -m pip install -e ".[dev,runner]"
alembic upgrade head
pytest
ruff check .
```

## API hardening and observability (Stage 9)

Stage 9 adds Redis-backed request limits, health probes, request IDs, structured request logs, security response headers, and Prometheus metrics.

Docker Compose starts Redis for ephemeral rate-limit counters. Initial limits are 5 registrations per hour per client IP, 10 login attempts per minute per client IP, 30 evaluation submissions per hour per user, and 5 AI-review requests per hour per user. Rate-limited endpoints fail closed with HTTP 503 if Redis is unavailable. Redis is not a system of record; PostgreSQL remains authoritative for evaluation and review data.

- `GET /health/live` — process liveness without dependency checks.
- `GET /health/ready` — readiness check for PostgreSQL and Redis.
- `GET /metrics` — Prometheus metrics; disabled with 404 unless `METRICS_TOKEN` is configured, then requires a bearer token.
- Every HTTP response includes an `X-Request-ID`; structured logs include route template, status and duration, but never request bodies, source code, headers, query strings or client IP addresses.

See [docs/stage-9-plan.md](docs/stage-9-plan.md) for details and limits.

## Roadmap

- [x] API skeleton, schemas, syntax checks, and initial CI
- [x] Separate runner service and disposable restricted execution containers
- [x] Execute registered trusted test cases in the isolated runner and derive scores server-side
- [x] Persistent evaluation history (PostgreSQL in Compose; SQLite for local development)
- [x] Authentication, bearer tokens, and per-user evaluation ownership
- [x] Separate candidate execution from trusted grading data (Stage 6)
- [x] Database-backed task management, administrator controls, and immutable trusted test-suite versions (Stage 7; see `docs/stage-7-plan.md`)
- [x] Optional AI-generated review with evidence-linked findings (Stage 8 — local Ollama default and optional OpenAI provider)
- [x] API rate limiting, health probes, request IDs, structured logs, and Prometheus metrics (Stage 9; see `docs/stage-9-plan.md`)
- [ ] Reviewer dashboard
- [ ] Stronger execution isolation and independent security review

## License

MIT
