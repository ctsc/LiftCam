# API

Base URL is the FastAPI process (local default `http://127.0.0.1:8000`). JSON request and response bodies unless noted. Access tokens are sent as `Authorization: Bearer <access_token>`.

## Health

### `GET /health`

Unauthenticated. Returns `{"status":"ok","version":"<semver>"}`.

## Auth

### `POST /auth/signup`

Creates an email/password account. Password is stored as an argon2 hash. Optional `profile_picture_url`; if omitted, the configured default avatar URL is stored. DOB must be age 13+ (exactly 13 on the signup date is allowed).

**Body**

| Field | Type | Notes |
|-------|------|--------|
| `email` | string | Unique; stored lowercased |
| `username` | string | Unique; 3–64 chars |
| `password` | string | Min 8 chars |
| `dob` | date (`YYYY-MM-DD`) | Age gate 13+ |
| `height` | number | `> 0` |
| `height_unit` | `"in"` \| `"cm"` | Default `"in"` |
| `weight` | number | `> 0` |
| `weight_unit` | `"lb"` \| `"kg"` | Default `"lb"`; also applies to SBD maxes |
| `sex` | `"male"` \| `"female"` | |
| `squat_max` | number | `> 0` |
| `bench_max` | number | `> 0` |
| `deadlift_max` | number | `> 0` |
| `profile_picture_url` | string \| null | Optional |

**Responses**

- `201` — `TokenPair` (`access_token`, `refresh_token`, `token_type: "bearer"`)
- `422` — validation (including under-13 DOB)
- `409` — email or username already in use

### `POST /auth/login`

**Body:** `{ "email", "password" }`

- `200` — `TokenPair`
- `401` — unknown email or wrong password

### `POST /auth/refresh`

Rotates the refresh token: the previous opaque token is deleted and a new pair is issued. Reuse of the old token returns `401`. Unknown tokens return `401`.

**Body:** `{ "refresh_token" }` → `200` `TokenPair`

### `POST /auth/logout`

Revokes the given refresh token (idempotent if already unknown).

**Body:** `{ "refresh_token" }` → `204`

## Profile

All `/me` routes require a valid bearer access token (`401` if missing or expired).

### `GET /me`

Returns the signed-in profile: signup fields plus `favorite_lift`, `profile_picture_url`, `tier`, `auth_provider`, `id`, and `created_at`. Never includes `password` or `password_hash`.

### `PATCH /me`

Partial update. Allowed fields: `username`, `dob`, `height`, `height_unit`, `weight`, `weight_unit`, `sex`, `squat_max`, `bench_max`, `deadlift_max`, `favorite_lift`, `profile_picture_url`. Unit fields must be the same enums as signup.

- `200` — updated `MeOut`
- `409` — username conflict
- `422` — invalid units or under-13 DOB

### `POST /me/push-token`

Stores one Expo push token on the user row (last write wins).

**Body:** `{ "token" }` → `204`
