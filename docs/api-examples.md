# API examples

All service dates and meal times use `Asia/Kolkata`. Student and staff sign-in share `/api/v1/auth/login`; role and user details determine the portal. In local development only, the OTP request response includes a `development_code` because no SMS provider is connected.

## Student password sign-in

```http
POST /api/v1/auth/login
Content-Type: application/json

{"identifier":"+910000000001","password":"demo-student"}
```

Students can identify with a registered phone number, roll/student ID, or email. Admin staff use their account email and their own password on the same endpoint.

## First student sign-in by OTP

```http
POST /api/v1/auth/otp/request
Content-Type: application/json

{"identifier":"B23CS000"}
```

Pass the returned `challenge_id` and local `development_code` to `/api/v1/auth/otp/verify`. A first-login student also supplies `new_password` (minimum eight characters). OTPs expire in five minutes and allow at most five tries. The demo code is not sent by SMS.

## Selfie and meals

Use the login access token as a bearer token. `POST /api/v1/student/selfie` accepts the captured selfie as multipart field `file`. `GET /api/v1/student/meals` returns current eligibility and meal windows. During a valid window, request a numbered reference:

```http
POST /api/v1/student/tokens
Authorization: Bearer <access_token>
Content-Type: application/json

{"meal":"Breakfast"}
```

The response includes the reference, student and meal details, server timestamp, expiry, and photo-registration status. After the student collects the plate, confirm using `POST /api/v1/student/tokens/{reference}/collect` with the same bearer token. No counter authentication or counter scan is part of this flow.

## Allocation, rebate, and billing

Admin staff send their access token in `X-Admin-Key`; finance staff send theirs in `X-Finance-Key`. Allocation CSV columns are `name,email,phone,roll_number,start_date,end_date`; rebate CSV columns are `roll_number,start_date,end_date`. The portal includes rebate upload/preview/history and finance review/approval. Preview endpoints return a `batch_id`, validation issues, and a summary; confirmation/approval is a separate call.

Billing preview accepts a month and caller-supplied `daily_rate_paise`. It counts allocated days less unique approved rebate days, independently of meal collections. Only an approved immutable snapshot can be exported to CSV.

