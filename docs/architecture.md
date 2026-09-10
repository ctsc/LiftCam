# Architecture

## Processes

- **API (FastAPI):** HTTP only. Auth, multipart handshake, History, presigned URLs. Never runs CV and never proxies video bytes.
- **Worker:** Claims jobs from Postgres (`FOR UPDATE SKIP LOCKED` on the direct URL), runs staged CV, writes results, uploads overlay to R2.
- **Mobile (Expo):** Thin client. Capture/upload/playback; polls History while jobs are in flight.

## Data model

Source of truth: `diagrams/er-data-model.md` and `liftcam/core/models.py` (must match column for column).

| Table | Role |
|-------|------|
| `users` | Account + profile. One `expo_push_token` per user (last device wins). Default `profile_picture_url` when signup skips pfp. |
| `refresh_tokens` | Opaque refresh token hashes for revocation/rotation. |
| `uploads` | History item **and** job row. Status machine + R2 keys + failure fields + probe metadata. |
| `segments` | Auto-detected lift windows within one upload, plus angle/calibration. |
| `reps` | Counted reps with faults, VBT, force/work, and `series` JSONB for Graphs. |

Migrations: Alembic under `backend/alembic/`. API uses `DATABASE_URL` (async/asyncpg); worker uses `DATABASE_DIRECT_URL` (sync/psycopg) so `SKIP LOCKED` is reliable on Neon.

See `docs/adr/0001-schema-additions.md` for columns added beyond the original design-phase ER sketch.
