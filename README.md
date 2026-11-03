# AI Code Evaluation Lab

A Python/FastAPI platform for inspecting code submissions and optionally running Python code in a disposable, restricted Docker container.

> **Execution status:** The API never evaluates submitted code inside its own process. When execution is requested, it forwards source to a separate internal runner service. The runner launches a fresh container with no network, a read-only root filesystem, a non-root user, dropped Linux capabilities, resource limits, and automatic cleanup.

## Features

- FastAPI endpoint for Python submissions
- Python syntax validation and basic static analysis
- Test-result aggregation and structured feedback
- Optional isolated Python execution through a separate runner service
- Per-run timeout, memory, CPU, process, file-size, and output limits
- Pytest and Ruff checks in GitHub Actions

## Stack

- Python 3.11+
- FastAPI, Pydantic, and HTTPX
- Docker Engine and Docker SDK for Python
- Pytest and Ruff

## Run the API without code execution

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,runner]"
uvicorn app.main:app --reload
```

The API is available at http://127.0.0.1:8000 and its docs at http://127.0.0.1:8000/docs. Execution requests return HTTP 503 until the runner is configured.

## Run the isolated execution stack

Requirements: Docker Engine with Compose v2. The runner requires access to the host Docker socket to create per-submission containers.

1. Copy `.env.example` to `.env`.
2. Generate a long random token, for example:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Put the generated value in `RUNNER_TOKEN` in `.env`.
4. Start the stack:

   ```bash
   docker compose --env-file .env up --build
   ```

The API is exposed on port 8000. The runner is not published to the host; it is reachable only on the Compose network and requires the shared bearer token.

## Execute a submission

Send a POST request to `/api/v1/evaluations`:

```json
{
  "language": "python",
  "source_code": "print('Hello from the sandbox')",
  "execute": true
}
```

The response includes `execution_performed`, `execution_exit_code`, `execution_timed_out`, `execution_duration_ms`, `stdout`, and `stderr`.

Set `execute` to false (the default) to perform static inspection only.

## Sandbox controls

Each execution gets a new container with:

- Network disabled
- Read-only container root filesystem
- Non-root UID/GID 65534
- All Linux capabilities dropped
- `no-new-privileges`
- 128 MiB memory limit and 0.5 CPU quota
- 32-process limit
- 5-second wall-clock timeout and CPU ulimits
- 16 MiB `/tmp` and 2 MiB output tmpfs, both no-exec
- 1 MiB per-file size limit, bounded response output, and forced container cleanup

The submitted source is mounted read-only. Standard output and standard error are written to a size-limited tmpfs and read back after execution.

## Important security limitations

This is a development-stage isolation layer, **not a claim of perfect or production-grade sandbox security**. Containers share the host kernel; Docker alone is not a complete security boundary. The runner service has access to the Docker daemon socket, which is effectively host-level authority. Keep it private, protect the bearer token, use a dedicated disposable host/VM, keep Docker and the host kernel patched, and do not expose the runner endpoint publicly.

For higher-risk multi-tenant workloads, use a stronger isolation boundary such as dedicated ephemeral VMs or a purpose-built sandbox runtime, add host-level monitoring and quotas, and perform an independent security review before accepting arbitrary public submissions.

The current test-result fields are client-supplied input for API demonstration only. They are **not trusted evidence** and must not be used to award real evaluation scores until test cases are executed and attested by a trusted isolated test harness.

## API

- `GET /health` — API health
- `POST /api/v1/evaluations` — inspect source; optionally request execution
- Runner's `POST /internal/execute` — private, token-protected internal endpoint

## Development checks

```bash
python -m pip install -e ".[dev,runner]"
pytest
ruff check .
``

## Roadmap

- [x] API skeleton, schemas, syntax checks, and initial CI
- [x] Separate runner service and disposable restricted execution containers
- [ ] Execute trusted test cases inside the isolated runner and derive scores server-side
- [ ] Persistent evaluation history (PostgreSQL)
- [ ] Optional AI-generated review with evidence-linked findings
- [ ] Authentication, rate limiting, monitoring, and reviewer dashboard

## License

MIT
