# Local development setup

## Prerequisites

- Python 3.11 (MediaPipe and OpenCV ship wheels for 3.11; 3.13+ do not yet). On Windows, `py -3.11` selects it.
- Node 20 LTS or newer, npm.
- Docker Desktop (local Postgres).
- `ffmpeg` on PATH. Not needed until the worker's probe and render stages exist (Phase 6+), but install it now.
- Expo Go on a phone for on-device testing. No Apple or Google developer account is needed until deployment.

## Postgres

```
docker compose -f infra/compose.yml up -d
docker compose -f infra/compose.yml ps        # wait for "healthy"
```

Credentials are `liftcam` / `liftcam`, database `liftcam`, exposed on host port **5433** (not 5432, so a Postgres already installed on the machine is left alone). Data persists in the `pgdata` volume; `docker compose -f infra/compose.yml down -v` wipes it.

## Backend

```
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate            # PowerShell; use source .venv/bin/activate elsewhere
pip install -e ".[dev]"
copy .env.example .env
```

Run the two processes in separate terminals:

```
uvicorn liftcam.api.main:app --reload
python -m liftcam.worker.main
```

`GET http://127.0.0.1:8000/health` returns `{"status":"ok","version":"..."}`. The worker logs an idle heartbeat at DEBUG and stops cleanly on Ctrl-C.

Checks:

```
ruff check .
ruff format --check .
mypy
pytest
```

Migrations (Phase 3+):

```
alembic upgrade head
alembic downgrade base
```

## Mobile

```
cd mobile
npm install
copy .env.example .env
npx expo start
```

Scan the QR code with Expo Go. Three tabs render: Capture, History, Profile.

Checks:

```
npm run typecheck
npm run lint
npm run format:check
npm test
```

## Environment variables

See [env.md](env.md).

## Phase 2 spikes

See [spikes.md](spikes.md). Short version:

```
cd backend
.\.venv\Scripts\activate
python scripts/make_synthetic_clips.py
python scripts/cv_spike.py tests/fixtures/clips/synthetic_side.mp4 --label side --out spike-out/side
```

On phone (Expo Go): Capture tab → Run 8 MB / Run 16 MB → paste logs into `docs/spikes.md`.
