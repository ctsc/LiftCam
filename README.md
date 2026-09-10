# LiftCam

Deadlift form and bar-speed analysis from a phone video. The app records or uploads a clip; a backend worker runs pose and bar tracking, counts reps, flags faults, estimates velocity, and renders an overlay video the user can play back per rep and share.

V1 is deadlift only. Product and architecture decisions live in [`v1.md`](v1.md); the phased build plan is [`plan.md`](plan.md); design diagrams are in [`diagrams/`](diagrams/).

## Layout

```
backend/   one Python package, two entrypoints (liftcam.api, liftcam.worker)
mobile/    Expo (React Native, TypeScript) app
infra/     local Postgres via Docker Compose; deploy artifacts land here later
diagrams/  Mermaid design diagrams
docs/      setup, environment, and per-area documentation
```

## Quick start

See [`docs/setup.md`](docs/setup.md) for the full walkthrough.

```
docker compose -f infra/compose.yml up -d

cd backend
py -3.11 -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn liftcam.api.main:app --reload        # http://127.0.0.1:8000/health
python -m liftcam.worker.main                # idle loop, Ctrl-C to stop

cd ../mobile
npm install
npx expo start
```

## Checks

Backend: `ruff check .`, `ruff format --check .`, `mypy`, `pytest`
Mobile: `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`
