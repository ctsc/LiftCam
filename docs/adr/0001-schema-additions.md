# ADR 0001 — Schema additions beyond the original ER diagram

## Status

Accepted (Phase 3).

## Context

The design-phase ER diagram in `diagrams/er-data-model.md` (pre-Phase 3) listed `users`, `uploads`, `segments`, and `reps` with the core product columns. The implementation plan and `v1.md` require additional operational fields that were not on that sketch. Push-token cardinality was also unresolved between “per user/device” (spec prose) and a single column (ER).

## Decision

### Push token cardinality

**One `users.expo_push_token` per user (last device wins).** Multi-device push is V2. Matches the ER diagram and avoids a device table in V1.

### New table: `refresh_tokens`

| Column | Reason |
|--------|--------|
| `id` | PK |
| `user_id` | Owner; cascade delete with user |
| `token_hash` | Store only a hash of the opaque refresh token |
| `created_at` | Audit / rotation |
| `expires_at` | Absolute expiry |

Needed so logout and refresh rotation can revoke tokens. Not on the original ER (JWT-only sketch).

### `users` additions

| Column | Reason |
|--------|--------|
| `auth_provider` | `email` / `google` / `apple` — prepare Phase 19 without a later migration |
| `password_hash` nullable | Provider-only accounts have no password |
| `height_unit`, `weight_unit` | Profile values need units (`in`/`cm`, `lb`/`kg`) |
| `created_at` | Account chronology |

### `uploads` additions

| Column | Reason |
|--------|--------|
| `weight_unit` | Entered lift weight needs `lb`/`kg` |
| `created_at` | History sort (`user_id, created_at DESC`) |
| `claimed_at` | Worker timeout / stuck `processing` detection |
| `finished_at` | Terminal timestamp |
| `duration_s`, `fps`, `width`, `height`, `rotation_deg` | Probe metadata for confidence gating and overlay encode |

### `segments` additions

| Column | Reason |
|--------|--------|
| `camera_angle_deg` | Continuous angle estimate for per-fault gating |
| `angle_confidence` | Confidence of that estimate |
| `px_per_m` | Calibration scale |
| `calibration_confidence` | Confidence of calibration |

### `reps` additions

| Column | Reason |
|--------|--------|
| `force_estimate`, `work_estimate` | Force/work section of results |
| `lockout_ratio` | Internal lockout gate evidence |
| `series` (JSONB) | Compact joint/bar time series for Graphs; cannot be rebuilt from scalar columns alone |

## Consequences

- `diagrams/er-data-model.md` is updated to match `models.py`.
- Phase 19 Google/Apple sign-in should not need a users-table migration for provider identity beyond using `auth_provider` / `apple_user_id`.
- Graphs (Phase 14) read `reps.series` written at commit time.
