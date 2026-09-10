# Environment variables

Each variable lists which process reads it. Local values come from `backend/.env` and `mobile/.env` (copied from the `.env.example` files, never committed). Production values are set on the host.

New variables are added here in the same phase that introduces them.

## Backend

| Variable | Read by | Default | Purpose |
|----------|---------|---------|---------|
| `ENV` | API, worker | `development` | Environment name for logging and behavior toggles. |
| `LOG_LEVEL` | API, worker | `INFO` | Python logging level. |
| `DATABASE_URL` | API | `postgresql://liftcam:liftcam@localhost:5433/liftcam` | Pooled connection string. In production, the Neon pooler URL. |
| `DATABASE_DIRECT_URL` | worker | `postgresql://liftcam:liftcam@localhost:5433/liftcam` | Direct (non-pooler) connection string. Required for `FOR UPDATE SKIP LOCKED` job claims. |
| `WORKER_POLL_INTERVAL_S` | worker | `2` | Seconds between queue polls when idle. |

## Mobile

Expo only exposes variables prefixed `EXPO_PUBLIC_` to app code. They are baked into the build and are not secrets.

| Variable | Default | Purpose |
|----------|---------|---------|
| `EXPO_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the LiftCam API. Use your machine's LAN IP when testing in Expo Go on a phone. |
