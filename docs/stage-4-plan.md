# Stage 4: Persistent Evaluation History

## Goal

Persist every accepted evaluation result so submissions can be inspected after the request has completed or the API has restarted.

## Implemented

- SQLAlchemy 2 models for evaluation history.
- PostgreSQL 16 service and named data volume in Docker Compose.
- SQLite fallback for local development.
- API persists static-inspection results and executed evaluation results.
- List endpoint supports pagination and optional task filtering.
- Detail endpoint returns the original submitted source and full evaluation result.
- Tests use isolated in-memory SQLite databases.

## API

- `GET /api/v1/evaluations?limit=20&offset=0&task_id=python.add`
- `GET /api/v1/evaluations/{id}`

The list endpoint returns summary fields only. The detail endpoint includes submitted source code and the full saved response.

## Data and privacy

The database stores submitted source code, task identifier, language, status, score, test counts, execution flags, timestamps, and a JSON copy of the response. Treat this as potentially sensitive user data. Restrict database and backup access. Retention, deletion, ownership, and authentication are not implemented in this milestone.

## Schema lifecycle

The API currently creates missing tables on startup using SQLAlchemy metadata. This is suitable for the initial development milestone but does not replace versioned Alembic migrations for production schema changes.

## Security limitations

Stage 4 does not change the Stage 2/3 sandbox limitations. The runner still has Docker socket access and the submitted code shares a process with the test harness inside the disposable container. The service is not ready for arbitrary public multi-tenant submissions.

## Follow-up

- Add Alembic migrations.
- Add retention and deletion controls.
- Add authentication and per-user evaluation ownership.
- Add filters by status/date and export.
