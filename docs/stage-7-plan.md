# Stage 7 — Task Management System

## Goal

Replace the hard-coded task catalogue with a database-backed, administrator-managed catalogue while preserving trusted grading and historical evaluation meaning.

## Scope

1. **Task catalogue**
   - Store task slug, title, description, instructions, difficulty, category, examples, publication state, and timestamps.
   - Public users can list and view published tasks.
   - Draft tasks remain private to administrators.
2. **Versioned trusted test suites**
   - Every task starts at version 1.
   - Changes to the function contract or trusted test cases create a new immutable task version.
   - Each version stores the function name and server-owned test cases (arguments and expected values).
   - Published task versions are immutable. Publishing an edit creates a new version rather than rewriting an old one.
3. **Administrator access**
   - Add an explicit administrator role to user accounts.
   - Existing accounts remain ordinary users after migration.
   - Task create, update, publish, archive, and version-management endpoints require administrator authentication.
   - Never allow task authors to submit trusted expected values through evaluation requests.
4. **Evaluation integration**
   - Resolve the requested task and active published version on the API.
   - Send only that version's server-owned cases to the trusted runner.
   - Persist the exact task-version identifier with each evaluation so later edits cannot change the meaning of an old score.
   - Preserve existing user ownership and history access controls.
5. **Verification**
   - Migration tests for existing accounts and evaluations.
   - Permission tests for anonymous, ordinary-user, and administrator access.
   - Task lifecycle and immutable-version tests.
   - Evaluation tests proving version pinning and server-side scoring.
   - CI (pytest and Ruff), followed by local PostgreSQL/Docker integration checks.

## Data model

- `tasks`: stable task identity and editable descriptive metadata.
- `task_versions`: immutable function contract and trusted test-suite snapshot, unique by `(task_id, version)`.
- `users.is_admin`: explicit administrative authorization; migration defaults existing users to false.
- `evaluations.task_version_id`: nullable foreign key for backward compatibility with historical records created before task versioning.

## Compatibility and rollout

- Keep the existing `python.add` task available by seeding it as a published task/version during migration.
- Preserve the existing `task_id` field in API responses and history.
- Old evaluation records remain readable; their `task_version_id` is null and must be identified as legacy/unversioned rather than assigned a guessed version.
- Do not remove the legacy client `test_results` field in this stage; it remains ignored for scoring.

## Security boundaries

- Task-management writes are administrator-only; registration never grants admin rights.
- Expected values and complete test suites stay on the trusted API/runner side and are never sent to candidate containers.
- Task versioning improves reproducibility, not sandbox isolation. The Docker socket, shared host kernel, and same-host runner deployment limitations documented in the README remain.
- No public self-service promotion to administrator. Initial administrator provisioning must be an explicit operator action outside public registration.

## Out of scope

- AI-generated task descriptions or tests.
- Public task submissions/reviews, leaderboards, and organization/team roles.
- A web frontend for administrators.
- Alembic downgrade guarantees for destructive data transformations.