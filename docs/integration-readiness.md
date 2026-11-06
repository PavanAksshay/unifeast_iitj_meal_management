# UniFeast integration readiness

This repository is standalone. No existing service, database, credential, or runtime dependency is used.

## Verified local patterns

- `unifeast_core` is a Python FastAPI service. Its `requirements.txt` includes Alembic, asyncpg and FastAPI; routes use dependency-injected SQLAlchemy `AsyncSession` and JWT-backed role checks in `app/auth/dependencies.py`.
- `unifeast_web` is a Next.js 15 / React 19 npm workspace. Its `apps/admin` package is `@unifest/admin`, and the admin app runs on port 3001. The web monorepo uses shared `@unifest/ui`, `@unifest/types`, and `@unifest/utils` workspaces.
- The checked-out `unifeast_mobile_app` is a Flutter project (`lib`, `pubspec.yaml`), not a Next.js app.
- `.qa-src` is itself within the `unifeast_qa` Git checkout. For that reason the standalone repository was placed beside `unifeast_qa` at `C:\unifeast\beta\unifeast_iitj_meal_management`, not inside the outer QA checkout.

## Candidate integration path (not performed)

1. Mount versioned `/api/v1` meal routes in Core after mapping standalone student/unit identifiers to approved platform IDs. Keep an adapter boundary for platform authentication; replace the MVP HMAC test session and shared demo keys with existing JWT claims and scoped role dependencies.
2. Review each table against Core's naming, UUID, timestamp, tenancy, and migration conventions. Migrate institution, unit, student mapping, staff mapping, allocation batches/history, schedule, meal reference, serving, rebate, cycle snapshot, and audit entities with Alembic. Do not copy the standalone database wholesale.
3. Store only foreign-key references to approved existing institution/unit/student records after an explicit mapping exercise. Never infer a match from email alone.
4. Port the combined demo views into Admin navigation after choosing owners for allocations, schedules, operations, finance, and audit. The current UI is static HTML and is not a shared Admin component.
5. Map staff roles individually. Administrators manage allocations and schedules; finance reviewers approve rebates and billing; students authenticate with the platform identity. Meal completion is confirmed by the student's authenticated slide after plate collection; this revised workflow has no counter login or confirmation.
6. Export only finalized student billing snapshots to the invoicing boundary. Reconcile billable allocated days and approved rebate days separately from meal scans to avoid counting meal transactions as billing events.
7. Migrate historical data in dry-run batches with row counts, duplicate checks, allocation/rebate overlap reports, immutable source batch IDs, and signed reconciliation. Retain source records until approved validation completes.

## Approval gates before integration

Institution/unit/student ID mapping, auth and role mapping, database migration plans, student photo storage/retention, contractual rate source, billing ownership, and historical backfill each require explicit review. No integration or migration has been performed.

## Gaps to close

The MVP has standalone Alembic migrations but no later schema revisions yet. It lacks production SMS delivery, full staff account/role management, UI forms for imports/rebate/billing, PDF statements, rebate corrections, billing adjustments, and automated photo deletion. The local demo passwords must never be reused in an integrated or deployed environment.

