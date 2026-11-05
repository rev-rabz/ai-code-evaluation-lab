# Stage 10 — Reviewer Dashboard

## Goals

Give administrators and designated reviewers a secure workflow for inspecting saved code evaluations, reading their execution and static-analysis results, and recording a human decision. Preserve the existing rule that ordinary users can only see their own submissions.

## Role and access model

- **User:** can create submissions and access only their own evaluation history and AI reviews.
- **Reviewer:** can access only evaluations currently assigned to that reviewer, and can create or update the human review for an assigned evaluation.
- **Administrator:** retains task-management privileges, can list all evaluations, assign or reassign evaluations to reviewers, and inspect all review records.
- A reviewer is not automatically an administrator. Reviewer access must be granted explicitly by an operator command; public registration never grants either elevated role.
- Unassigned evaluations are visible to administrators only. A reviewer must not be able to enumerate another reviewer's assignments or infer whether an inaccessible evaluation exists; inaccessible detail endpoints return 404.

## Scope

### 10.1 Reviewer identity and assignment

1. Add `users.is_reviewer`, defaulting to false for every existing and newly registered account.
2. Add an explicit operator command to promote or demote a reviewer account, analogous to the administrator promotion command.
3. Add one current assignment per evaluation, including reviewer, assigning administrator, and assignment timestamp. Reassignment replaces the current assignment while retaining clear attribution for the latest assignment.
4. Only administrators may list eligible reviewers and create, change, or remove assignments. Assignment targets must be active accounts explicitly marked as reviewers or administrators.

### 10.2 Reviewer API

1. Add a paginated evaluation queue. Reviewers see their assigned evaluations only; administrators may filter across all evaluations.
2. Return queue metadata needed for triage: submitter email, task/version, language, status, score, passed/total tests, execution flags, submission time, assignment, and whether a human review exists.
3. Add a detail endpoint that returns the saved source, trusted evaluation result, task metadata, and any saved AI review, subject to the same assignment check.
4. Add a human review record with decision `approved`, `needs_changes`, or `flagged`, optional notes (maximum 4,000 characters), reviewer identity, and timestamps. A reviewer may write only for an evaluation assigned to them; administrators may review any evaluation.
5. Human review is distinct from AI review and does not alter trusted scores, test outcomes, or the model-generated review.

### 10.3 Dashboard

Serve a first-party dashboard at `/reviewer` with no external CDN dependencies:

- Login using the existing account endpoint.
- Queue with status/task filters and pagination.
- Detail view for source code, score, test feedback, execution metadata, static-analysis findings, and AI review (when present).
- Assignment controls for administrators.
- Human decision and notes form for authorized reviewers.
- Explicit empty, loading, error, and unauthorized states; logout clears the in-memory access token.
- Render untrusted source and review content as text, never as injected HTML. The browser must not persist bearer tokens in localStorage or sessionStorage.

The dashboard page itself may be served publicly, but every data and mutation endpoint remains authenticated and role/assignment protected.

## Data model and migration

Create an Alembic revision after `0003_stage8_ai_reviews` that adds:

- `users.is_reviewer BOOLEAN NOT NULL DEFAULT FALSE`
- `evaluation_assignments`: one current assignment per evaluation, reviewer foreign key, assigning-admin foreign key, and assignment timestamp.
- `evaluation_reviews`: one current human review per evaluation, reviewer foreign key, constrained decision value, notes, and created/updated timestamps.

Existing users are not promoted during migration. Existing evaluations remain unassigned and are therefore visible only to administrators until assigned.

## Security requirements

- Reuse the existing JWT authentication and database-backed user lookup.
- Enforce authorization in the API on every request; hiding controls in the UI is not authorization.
- Return 404 for a reviewer attempting to access an unassigned evaluation or an evaluation assigned to someone else.
- Do not expose password hashes, JWTs, trusted expected values beyond what the submitting user's existing detail response already exposes, or another reviewer's private queue.
- Validate assignment targets and review decisions server-side.
- Never execute code from the dashboard. Evaluation execution remains confined to the private runner.
- Human review must never modify the score, test feedback, or AI review.

## Test and acceptance criteria

- Migration upgrades and downgrades cleanly on SQLite and PostgreSQL.
- Existing user-history privacy and evaluation APIs continue to pass unchanged.
- Regular users receive 403 from reviewer/admin APIs.
- Reviewers can list and inspect only their own assignments; cross-reviewer and unassigned detail requests return 404.
- Reviewers cannot assign work or manage tasks.
- Administrators can list all evaluations, assign/reassign/unassign work, and inspect any evaluation.
- Only designated reviewers/admins can be assignment targets.
- Human review validation, ownership, and attribution are covered by tests.
- Dashboard assets are served, use the API's protected routes, and safely render untrusted text.
- Full Pytest and Ruff checks pass in CI; local Docker smoke testing confirms migration, login, assignment, review submission, and authorization boundaries.

## Out of scope

- Public multi-tenant code execution or production-grade sandbox claims.
- Email invitations, notifications, reviewer workload balancing, and automated assignment.
- Review history/versioning and multi-reviewer consensus on one evaluation.
- Changing trusted task suites, test scoring, or AI review generation.
- Replacing the existing authentication/token model with a new identity provider.

## Delivery order

1. Reviewer role, assignment/review models, Alembic migration, and operator promotion command.
2. Protected admin/reviewer APIs with authorization and regression tests.
3. First-party reviewer dashboard and UI smoke tests.
4. README/roadmap updates, full CI, Docker verification, and pull request review.
