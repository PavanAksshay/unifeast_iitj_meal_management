# API examples

All service dates and meal times use `Asia/Kolkata`. Student and staff sign-in share `/api/v1/auth/login`; role and user details determine the portal. Registration codes are emailed through configured SMTP. The response contains a challenge ID. Configure SMTP before requesting a code.

## Student password sign-in

```http
POST /api/v1/auth/login
Content-Type: application/json

{"identifier":"student@iitj.ac.in","password":"demo-student"}
```

The portal uses email and password. The API also accepts registered student phone numbers and IDs for existing clients. Admin staff use their account email and their own password on the same endpoint.

## First student sign-in by OTP

```http
POST /api/v1/auth/otp/request
Content-Type: application/json

{"identifier":"firstlogin@iitj.ac.in"}
```

Submit the returned `challenge_id` and the code received by email.

```http
POST /api/v1/auth/otp/verify
Content-Type: application/json

{"challenge_id":"<challenge_id>","code":"123456"}
```

Codes expire in five minutes and allow five attempts. A new code invalidates the
previous one and requires a one-minute wait. Verification returns a
`registration_token`, which permits password setup for ten minutes.

```http
POST /api/v1/auth/password/setup
Content-Type: application/json

{"registration_token":"<registration_token>","password":"a-new-password","confirm_password":"a-new-password"}
```

Both passwords must match and contain 8–128 characters. Successful setup signs
the student in. Already registered users sign in using email and password.

Password sign-in and successful password setup also set a 30-day HttpOnly,
SameSite cookie. Browsers restore their sign-in through `GET /api/v1/auth/session`
and revoke it with `POST /api/v1/auth/logout`. API clients can continue using the
returned access token. All authentication responses use `Cache-Control: no-store`.

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

Admin staff send their access token in `X-Admin-Key`; finance staff send theirs in `X-Finance-Key`. Allocation CSV columns are `name,email,phone,roll_number,start_date,end_date`; rebate CSV columns are `roll_number,start_date,end_date`. Admin and finance staff can review pending rebate batches and approve or reject the entire upload. Preview endpoints return a `batch_id`, validation issues, and a summary; confirmation/approval is a separate call.

Billing preview accepts a month and caller-supplied `daily_rate_paise`. It counts allocated days less unique approved rebate days, independently of meal collections. Only an approved immutable snapshot can be exported to CSV.
