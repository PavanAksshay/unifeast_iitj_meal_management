# UniFeast IIT Jodhpur Meal Management

Standalone local pilot MVP for student allocations, first-login OTP/password setup, selfie registration, meal references, plate-collection confirmation, rebate approval, and student-level billing. Synthetic data only; no existing UniFeast service or database is connected.

## Start

Requirements: Docker Compose.

```sh
docker compose up --build --detach --wait
```

- Shared student/admin sign-in portal: http://localhost:3100
- FastAPI / OpenAPI: http://localhost:8100/docs
- Health: http://localhost:8100/health

Stop with `docker compose down`. Persistent data is in isolated `iitj_meals_db` and `iitj_meals_photos` volumes. `docker compose down -v` removes those demo volumes. Copy `.env.example` to `.env` to configure credentials. Do not expose this demo beyond localhost. The API applies Alembic migrations before starting. Compose publishes both HTTP ports on loopback. The frontend proxies browser API requests through port 3100.

## Demo sign-in

The student and admin use the same login page.

- Returning student email `student@iitj.ac.in`, password `demo-student`.
- First-login student email `firstlogin@iitj.ac.in`. Choose **First-time registration**, request an email code, verify it, then enter and confirm a new password.
- Admin: email `admin@unifeast.local`, password `demo-admin`.
- Finance API account: email `finance@unifeast.local`, password `demo-finance`.

Configure SMTP in `.env` before requesting registration codes. The backend sends codes only to the student email already recorded by the mess administrator. Registration displays a configuration message until email delivery is configured. Codes expire after five minutes, allow five attempts, and can be resent after one minute. Successful verification grants ten minutes to set and confirm the password. Returning accounts sign in directly with email and password. First-time eligible students must take a selfie with the browser's front camera before the meal dashboard unlocks. Meal times are illustrative; an admin can set a window to the current Asia/Kolkata time for a live demo. Imported students complete OTP/password setup at first sign-in.

For a larger test, download the fictional [40-student allocation file](frontend/sample-data/students.csv) and [10-request rebate file](frontend/sample-data/rebates.csv). The [mess testing guide](docs/mess-testing.md) explains how to set capacity, import the files, approve rebates, and try student sign-in. Run `python scripts/generate_sample_data.py` to refresh their dates.

## Email delivery setup

Copy `.env.example` to `.env` and fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
`SMTP_USERNAME`, and `SMTP_PASSWORD`. Set `SMTP_SECURITY=starttls` for STARTTLS
(usually port 587), or `ssl` for implicit TLS (usually port 465). The sender
must be permitted by your email provider. Recreate the API after changing settings
with `docker compose up --detach --build --wait`. Credentials belong in the
ignored `.env` file. Automated tests mock delivery and use synthetic records.

## Student flow

1. Returning users sign in with their registered email and password.
2. First-time students verify an email OTP, create and confirm a password, and enter the student home page. The home page asks for a front-camera selfie before meal collection becomes available.
3. During an available meal window, request the numbered meal reference. It displays the student's name, ID, mess, meal, date, server timestamp, and photo.
4. Collect the plate, then slide to confirm. The server records the meal once. The number is a reference only; no counter login or scan is involved.

## Implemented workflows

- Shared role-aware email sign-in, separate email verification and password setup for first-time students, and seeded admin and finance accounts.
- An HttpOnly, SameSite cookie remembers the browser until sign-out. The server session has no automatic expiry, and the cookie is renewed on restoration. The cookie uses a rolling 400-day lifetime within browser retention limits. Clearing cookies requires a new sign-in. Only a random session secret is stored in the cookie, with its hash persisted in the database. Passwords remain salted password hashes on the server. Access tokens stay in browser memory. Sign-out revokes the remembered session.
- Allocation eligibility checked by the API; protected selfie storage and access; server-authoritative meal timing.
- Numbered meal references expire after 15 minutes. Student-authenticated slider confirmation creates the unique served-meal record; duplicate collection is rejected.
- The admin portal includes rebate CSV upload, validation preview, and import history. Admin or finance staff can review each batch and approve or reject it.
- The admin portal also includes searchable student allocation records, meal/rebate activity analytics, daily meal windows on the dashboard, and date/meal-filtered presence reports with CSV export. Presence is based on student-confirmed meal collection.
- The admin UI includes a mess capacity and occupancy dashboard, MIS CSV downloads, student gender/course/branch breakdowns, individual student entry, metadata-aware bulk imports, admin/finance account creation and activation, weekly menu plans, rebate reason/frequency analytics, and a report builder with date presets and printable PDF output.
- Allocation CSV preview/confirmation/history; rebate CSV preview and admin or finance approval; billing snapshots computed from allocated days minus approved rebate days; approved CSV export. Meal scans are not billing inputs.
- Audit rows for sensitive MVP actions, meal timing configuration, student selfie, and meal collection.

With Python 3.12, install `backend/requirements-dev.txt` and run `python -m unittest discover -s tests -v` from `backend`.

## API notes

OpenAPI is at `/docs`. Students use `Authorization: Bearer <access_token>`. Admin endpoints use the logged-in admin session in `X-Admin-Key`; finance endpoints use the finance session in `X-Finance-Key`.

- `POST /api/v1/auth/login`, `POST /api/v1/auth/otp/request`, `POST /api/v1/auth/otp/verify`, `POST /api/v1/auth/password/setup`
- `GET /api/v1/auth/session`, `POST /api/v1/auth/logout`
- `GET /api/v1/student/me`, `POST /api/v1/student/selfie`, `GET /api/v1/student/meals`
- `POST /api/v1/student/tokens`, `POST /api/v1/student/tokens/{reference}/collect`, `GET /api/v1/student/tokens/{reference}`
- `POST /api/v1/admin/allocations/preview`, `POST /api/v1/admin/allocations/{batch_id}/confirm`, `GET /api/v1/admin/allocations/history`
- `POST /api/v1/admin/rebates/preview`, `POST /api/v1/admin/rebates/{batch_id}/approve`
- `POST /api/v1/admin/billing/{YYYY-MM}/preview?daily_rate_paise=...`, `POST /api/v1/admin/billing/{cycle_id}/approve`, `GET /api/v1/admin/billing/{cycle_id}/export.csv`
- Admin portal additions: `GET /api/v1/admin/analytics`, `GET /api/v1/admin/students`, `POST /api/v1/admin/students`, `GET /api/v1/admin/units`, `PUT /api/v1/admin/units/{unit_id}/capacity`, `GET/PUT /api/v1/admin/meal-plans`, `GET/POST/PATCH /api/v1/admin/users`, `GET /api/v1/admin/presence.csv`, and `GET /api/v1/admin/mis.csv`.

Allocation CSV required columns: `name,email,phone,roll_number,start_date,end_date`; optional student metadata columns: `gender,course,branch`. Rebate CSV required columns: `roll_number,start_date,end_date`; `reason` is optional. Import previews show validation issues and require explicit confirmation/approval.

## MVP limits

This is not deployment-ready. SMTP email delivery requires provider credentials in the private `.env`. Set `COOKIE_SECURE=true` when serving the site over HTTPS. Mess occupancy is calculated from active allocations and configured mess capacity. Report PDFs use the browser print dialog; report history is stored in the current browser. Institution/site/UniFeast role hierarchies, rebate revisions, billing adjustments, and automated photo retention/deletion are incomplete. No facial recognition is used. Future schema changes require explicit Alembic revisions.

Existing repositories were inspected read-only. See [integration readiness](docs/integration-readiness.md) and [API examples](docs/api-examples.md).
