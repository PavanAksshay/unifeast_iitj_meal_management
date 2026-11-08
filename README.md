# UniFeast IIT Jodhpur Meal Management

Standalone local pilot MVP for student allocations, first-login OTP/password setup, selfie registration, meal references, plate-collection confirmation, rebate approval, and student-level billing. Synthetic data only; no existing UniFeast service or database is connected.

## Start

Requirements: Docker Compose.

```sh
docker compose up --build
```

- Shared student/admin sign-in portal: http://localhost:3100
- FastAPI / OpenAPI: http://localhost:8100/docs
- Health: http://localhost:8100/health

Stop with `docker compose down`. Persistent data is in isolated `iitj_meals_db` and `iitj_meals_photos` volumes. `docker compose down -v` removes those demo volumes. Copy `.env.example` to `.env` to configure credentials. Do not expose this demo beyond localhost. The API applies Alembic migrations before starting.

## Demo sign-in

The student and admin use the same login page.

- Returning student: phone `+910000000001` or ID `B23CS001`, password `demo-student`.
- First-login student: phone `+910000000003` or ID `B23CS000`. Choose **Get a student OTP**, enter the local demo code shown on screen, and create a password.
- Admin: email `admin@unifeast.local`, password `demo-admin`.
- Finance API account: email `finance@unifeast.local`, password `demo-finance`.

The OTP is displayed only in local development mode; no SMS provider is connected. First-time eligible students must take a selfie with the browser's front camera before the meal dashboard unlocks. Meal times are illustrative; an admin can set a window to the current Asia/Kolkata time for a live demo. Imported students complete OTP/password setup at first sign-in.

For a larger test, download the fictional [40-student allocation file](frontend/sample-data/students.csv) and [10-request rebate file](frontend/sample-data/rebates.csv). The [mess testing guide](docs/mess-testing.md) explains how to set capacity, import the files, approve rebates, and try student sign-in. Run `python scripts/generate_sample_data.py` to refresh their dates.

## Student flow

1. Sign in with registered phone/ID and OTP or an existing password.
2. On first sign-in, choose a password after OTP verification and take a selfie using the front camera.
3. During an available meal window, request the numbered meal reference. It displays the student's name, ID, mess, meal, date, server timestamp, and photo.
4. Collect the plate, then slide to confirm. The server records the meal once. The number is a reference only; no counter login or scan is involved.

## Implemented workflows

- Shared role-aware login screen; student OTP challenge with five-minute expiry and attempt limit; seeded admin and finance password accounts.
- Allocation eligibility checked by the API; protected selfie storage and access; server-authoritative meal timing.
- Numbered meal references expire after 15 minutes. Student-authenticated slider confirmation creates the unique served-meal record; duplicate collection is rejected.
- The admin portal includes rebate CSV upload, validation preview, and import history. Admin or finance staff can review each batch and approve or reject it.
- The admin portal also includes searchable student allocation records, meal/rebate activity analytics, daily meal windows on the dashboard, and date/meal-filtered presence reports with CSV export. Presence is based on student-confirmed meal collection.
- The admin UI includes a mess capacity and occupancy dashboard, MIS CSV downloads, student gender/course/branch breakdowns, individual student entry, metadata-aware bulk imports, admin/finance account creation and activation, weekly menu plans, rebate reason/frequency analytics, and a report builder with date presets and printable PDF output.
- Allocation CSV preview/confirmation/history; rebate CSV preview and admin or finance approval; billing snapshots computed from allocated days minus approved rebate days; approved CSV export. Meal scans are not billing inputs.
- Audit rows for sensitive MVP actions, meal timing configuration, student selfie, and meal collection.

Run API tests from `backend` with `python -m unittest discover -s tests -v`.

## API notes

OpenAPI is at `/docs`. Students use `Authorization: Bearer <access_token>`. Admin endpoints use the logged-in admin session in `X-Admin-Key`; finance endpoints use the finance session in `X-Finance-Key`.

- `POST /api/v1/auth/login`, `POST /api/v1/auth/otp/request`, `POST /api/v1/auth/otp/verify`
- `GET /api/v1/student/me`, `POST /api/v1/student/selfie`, `GET /api/v1/student/meals`
- `POST /api/v1/student/tokens`, `POST /api/v1/student/tokens/{reference}/collect`, `GET /api/v1/student/tokens/{reference}`
- `POST /api/v1/admin/allocations/preview`, `POST /api/v1/admin/allocations/{batch_id}/confirm`, `GET /api/v1/admin/allocations/history`
- `POST /api/v1/admin/rebates/preview`, `POST /api/v1/admin/rebates/{batch_id}/approve`
- `POST /api/v1/admin/billing/{YYYY-MM}/preview?daily_rate_paise=...`, `POST /api/v1/admin/billing/{cycle_id}/approve`, `GET /api/v1/admin/billing/{cycle_id}/export.csv`
- Admin portal additions: `GET /api/v1/admin/analytics`, `GET /api/v1/admin/students`, `POST /api/v1/admin/students`, `GET /api/v1/admin/units`, `PUT /api/v1/admin/units/{unit_id}/capacity`, `GET/PUT /api/v1/admin/meal-plans`, `GET/POST/PATCH /api/v1/admin/users`, `GET /api/v1/admin/presence.csv`, and `GET /api/v1/admin/mis.csv`.

Allocation CSV required columns: `name,email,phone,roll_number,start_date,end_date`; optional student metadata columns: `gender,course,branch`. Rebate CSV required columns: `roll_number,start_date,end_date`; `reason` is optional. Import previews show validation issues and require explicit confirmation/approval.

## MVP limits

This is not deployment-ready. OTP delivery is a development adapter; connect an approved SMS provider before a pilot. Mess occupancy is calculated from active allocations and configured mess capacity. Report PDFs use the browser print dialog; report history is stored in the current browser. Institution/site/UniFeast role hierarchies, rebate revisions, billing adjustments, and automated photo retention/deletion are incomplete. No facial recognition is used. Future schema changes require explicit Alembic revisions.

Existing repositories were inspected read-only. See [integration readiness](docs/integration-readiness.md) and [API examples](docs/api-examples.md).
