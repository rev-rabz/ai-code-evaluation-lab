# Stage 5 — Authentication and private evaluation history

## Goal

Introduce user accounts and ensure evaluation submissions and stored source/results belong to the authenticated account that created them.

## Delivered scope

- Account registration with email normalization and duplicate-email handling.
- Argon2 password hashing; raw passwords are never stored or returned.
- Login returns a signed HS256 JWT access token with a 30-minute expiry.
- `GET /api/v1/auth/me` returns the current account.
- Evaluation submission requires a valid bearer token.
- Evaluation records carry a nullable `user_id` foreign key.
- History list, filters, and detail retrieval are scoped to the current user. Cross-account detail lookup returns 404.
- Alembic migration adds account and ownership schema while preserving Stage 4 rows.
- Docker Compose requires an independent `JWT_SECRET`.

## Endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/evaluations` (authenticated)
- `GET /api/v1/evaluations` (authenticated and owner-filtered)
- `GET /api/v1/evaluations/{id}` (authenticated and owner-filtered)

The task catalogue and health endpoint remain public.

## Data migration

Legacy evaluation rows are retained with `user_id = NULL`. They are not automatically assigned to a new account and are not returned by authenticated history queries. This avoids guessing ownership.

## Security notes and limitations

- Password hashing uses Argon2.
- Access tokens expire after 30 minutes; refresh, revocation, and logout are not implemented.
- Registration and login need rate limiting before public exposure.
- Email verification, password reset, account deletion, and administrative account management are not included.
- The runner still has Docker socket authority; containers share the host kernel; the test harness shares a Python process with submitted code. Stage 5 does not make arbitrary public code execution production-safe.
- No ownership transfer or legacy-row reassignment endpoint is provided.

## Validation plan

- Registration succeeds; duplicate email returns 409.
- Weak passwords fail validation.
- Correct login returns a token; incorrect credentials return 401.
- Protected endpoints reject missing/invalid tokens.
- Authenticated evaluation persists the caller's user ID.
- A second user cannot list or retrieve the first user's records.
- Existing Stage 1–4 evaluation and runner tests remain green.
- Alembic upgrades a Stage 4 database without dropping its history.
