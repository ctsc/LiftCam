# LiftCam V1 Implementation Plan (Deadlift Only)

Source spec: `v1.md` (read-only reference). Scope covers every section of `v1.md` from Scope through Legal / Compliance. Everything under "Deferred to V2+" is out of scope and is not planned here.

This plan is an execution roadmap for an autonomous coding agent. It contains no implementation code. All Git write operations belong to the human developer.

Plan revisions folded in: feasibility spikes inserted as Phase 2; Google/Apple sign-in moved to the final phase (engineered for from Phase 3 on, built last); worker sends push directly; `reps.series` pulled into the schema phase; presence gate relaxed; overlay render capped at 720p; benchmarking marked deferrable; explicit MVP cut; per-phase Success Criteria checklists.

---

## 1. Repository Review

### Existing Architecture Observations

The repository is in the design phase. There is no application code, no package manifest, no build tooling, and no tests. Current contents:

- `v1.md`: the locked product and architecture spec (Decisions 1 through 55, design grilling closed).
- `copy.md`: an earlier copy of the same spec. Not a planning input.
- `diagrams/*.md`: five Mermaid diagrams that are the design closeout (component, capture/upload activity, process-job sequence, ER data model, job state machine).
- `.cursor/rules/coding-standards.mdc` and `.cursor/rules/git-safety.mdc`: always-on agent rules.
- Git: `main` tracks `origin/main` (github.com/ctsc/LiftCam), two commits, uncommitted edits to `v1.md`, untracked `.cursor/`, `copy.md`, `diagrams/`.

Because no code exists, "existing architecture" is the locked spec plus diagrams. The plan treats those as binding:

- Mobile: Expo (React Native, TypeScript), EAS Build, `expo-camera`, `expo-file-system`, `expo-notifications`, video playback via Expo.
- Backend: two Python processes on one machine. FastAPI for HTTP; a separate worker for MediaPipe Pose Landmarker (BlazePose 33 landmark), OpenCV classical bar/plate detection, scoring, and overlay render.
- Database: Neon Postgres. `uploads` row is both History item and job. Worker claims with `FOR UPDATE SKIP LOCKED` over a direct (non-pooler) connection.
- Storage: Cloudflare R2, exactly two objects per upload (`original`, `overlay`). Postgres stores keys only. Presigned GET (~10 min) and presigned multipart part PUTs.
- Auth: FastAPI-issued JWT access + refresh tokens. Email/password ships first; Google/Apple verify-then-issue is the last phase of V1. No hosted auth.
- Push: Expo Push only, one ping per finished job, requested after the first completed upload. The worker sends it directly.
- Queue: Postgres only. No Redis, Celery, SQS, websockets.
- Client status: poll `GET /uploads/:id` every 2 to 3 seconds while in flight.
- Hosting: VPS or small PaaS chosen at first deploy. Not AWS.

### Relevant Files and Directories

| Path | Why it matters |
|------|----------------|
| `v1.md` | Source of every product and architecture decision. Every phase below cites it. |
| `diagrams/er-data-model.md` | Column-level schema for `users`, `uploads`, `segments`, `reps`. Phase 3 implements this directly. |
| `diagrams/state-job.md` | The `uploads.status` machine and legal transitions. Drives API guards and worker writes. |
| `diagrams/sequence-process-job.md` | Multipart handshake, claim, stage outcomes, push path. Phase 6 updates the push path to worker-direct. |
| `diagrams/activity-capture-upload.md` | Record vs camera roll, confirm/retake, shared multipart path. Drives the mobile capture flow. |
| `diagrams/component.md` | Process boundaries: app talks to API and R2 directly; worker talks to Postgres, R2, and Expo Push. |
| `.cursor/rules/*.mdc` | Coding and Git constraints every phase must honor. |

### Existing Coding Conventions

No code conventions exist yet. The following are established by this plan and must be followed from Phase 1 onward:

- Database and JSON field naming: `snake_case`, matching the ER diagram (`r2_original_key`, `failed_stage`, `user_reps`).
- Status and code values are lowercase string enums exactly as spec'd: `uploading | queued | processing | ready | failed | no_lift`; `failed_stage` in `claim | download | probe | presence | pose | track | segment | score | render | overlay_upload`; `failure_code` in `timeout | crash | corrupt | no_bar | no_person | no_motion`.
- Python: `ruff` (lint + format), `mypy` strict on `liftcam/`, `pytest`. Type hints everywhere. Pydantic models for request/response schemas.
- TypeScript: `strict: true`, ESLint with the Expo config, Prettier. `expo-router` file-based routes.
- Worker stages are pure functions over in-memory frame/landmark data and return typed results. No stage touches Postgres or R2 except `claim`, `download`, `overlay_upload`, and the final commit.
- Comments: max 3 lines, intent only, no em dashes.
- Documentation: Markdown in `docs/`, diagrams stay Mermaid in `diagrams/`.

### Existing Patterns To Follow

None in code. Architectural patterns to follow come from the diagrams: thin client, API never touches video bytes, worker never serves HTTP, one row per job, keys-only media references, fail-cheap staged pipeline that commits once.

### Potential Reuse Opportunities

None exist. There is no prior code to reuse. Within this plan, reuse is designed in: a single Python package (`backend/liftcam/`) with a shared `core/` (settings, DB models, R2 client, push client) consumed by both the `api/` and `worker/` entrypoints, so models and clients are written once.

### Potential Conflicts

1. Push token cardinality. `v1.md` says "store an Expo push token per user/device"; the ER diagram has a single `users.expo_push_token`. The plan follows the ER diagram (one token per user, last device wins). Multi-device push is a V2 concern. Flagged so the developer can override before Phase 3.
2. Push path. The sequence and component diagrams route push through the API. The plan takes the simpler path: the worker calls Expo Push directly from shared `core/push.py`. No internal endpoint, no service token. Phase 6 updates both diagrams so they stay truthful. Resolved.
3. Pre-record "lightweight live check" (Capture section) says "angle detected + basic bar/plate/lifter presence." Any live detection needs on-device inference, which the same section forbids for the full overlay and the Architecture section forbids in general (thin client, all CV server-side). The plan implements the pre-record screen as a static framing guide plus the side-view tip, with no on-device inference. Live presence detection is listed under Missing Context.
4. Playback library. `v1.md` names `expo-av`. Expo has deprecated `expo-av`'s `Video` in favor of `expo-video`. The plan uses `expo-video` for playback and `expo-camera` for capture, and records the substitution in the Phase 7 ADR. Functionally identical for the spec's needs (play, seek, frame-accurate scrub).
5. ER diagram lacks operational columns needed by the spec: `created_at` (History sort order), `claimed_at` (timeout detection), probe metadata (`duration_s`, `fps`, `width`, `height`) needed for low-confidence gating, a `reps.series` JSONB for Graphs time series, a place to persist refresh tokens for revocation, and per-segment camera angle / calibration values needed for per-fault confidence gating. Phase 3 adds these and updates `diagrams/er-data-model.md`.
6. Video codecs. Phone uploads are usually HEVC in `.mov`. `pip` OpenCV builds may not decode HEVC reliably and cannot write H.264. The worker host needs system `ffmpeg`; the probe stage normalizes the original to an H.264 working copy on local disk (not stored in R2, so the two-object rule holds) and the render stage encodes the overlay with `ffmpeg` (`faststart`) for mobile playback.
7. Multipart chunking on device. Reading byte ranges of a local video for S3 part PUTs without a native module is the main mobile technical risk. Phase 2 spikes this on real devices before Phase 8 builds on it. If chunked reads prove impractical, that is a spec-level decision (spec forbids single-PUT full restart) and is escalated, not silently changed.
8. OAuth ordering. `v1.md` Accounts lists Google/Apple alongside email/password. The plan builds email/password first and Google/Apple as the final phase of V1. Schema, dedup logic, and auth screens are shaped for providers from Phase 3 on so the last phase is additive. Still inside V1 scope; only the order changes.

### Missing Context

- Which VPS/PaaS hosts API + worker (spec: decide at first deploy). Affects Phase 16 only.
- Population strength standards data source and its license (Benchmarking). Required for Phase 15.
- Whether the pre-record "live check" is meant to include any on-device detection (see Conflict 3).
- Apple Developer and Google Play accounts and bundle identifiers (Phase 16). Sign in with Apple and Google OAuth client IDs (Phase 19).
- Whether account deletion must ship in V1. App Store Review Guideline 5.1.1(v) requires in-app account deletion for apps with account creation. `v1.md` does not mention it. Listed under Major Caveats and Manual Developer Tasks.
- Three real clips (side, front, oblique) for the Phase 2 CV spike, and later the full ground-truth set for Phase 17.
- Exact plate diameter assumptions for calibration (45 lb / 20 kg IPF plates are 450 mm; bumper and iron plates vary). Spec says "standard 45/55lb plate"; the plan assumes 450 mm nominal and treats it as a provisional threshold.

---

## 2. Overall Summary

LiftCam V1 is a deadlift-only mobile app where a user records or uploads a clip, the backend asynchronously runs pose and bar tracking, counts reps, flags form faults, estimates bar velocity and force, renders a single overlay video, and the app plays back results per rep and shares the overlay file. It is needed to validate the CV pipeline and data model end to end on one lift before expanding. The architecture is a thin Expo client, a FastAPI process for auth and handshakes, a separate Python worker that claims jobs from Postgres with `SKIP LOCKED`, Neon Postgres for structured data, Cloudflare R2 for two video objects per upload, and Expo Push for completion notices.

---

## 3. Estimated Total LOC

Estimated Total LOC:
Approximately 15,000 to 22,000 lines

- Added lines: 15,000 to 22,000 (all greenfield)
  - Mobile app (TypeScript): 5,000 to 7,000
  - Backend API + shared core (Python): 2,500 to 3,500
  - Worker + CV pipeline (Python): 4,000 to 6,000
  - Tests (both stacks): 2,500 to 4,000
  - Config, migrations, CI, docs: 800 to 1,500
  - Feasibility spike scripts (throwaway dev tools): 150 to 300
- Modified lines: under 300 (diagram updates, README growth across phases)
- Deleted lines: 0 (nothing to delete; `copy.md` is left alone, see Manual Developer Tasks)

---

## 4. Assumptions

- The developer will provision Neon, R2, Expo/EAS, Apple, and Google accounts and supply credentials via environment variables. The agent never creates or stores secrets.
- Single worker process in V1. The claim query and timeout reaper are written to stay correct with multiple workers, but only one runs.
- Python 3.11 (pinned in Phase 1: the dev machine has no 3.12, and MediaPipe/OpenCV wheels cover 3.11 but not 3.13+), Node 20 or newer, Expo SDK 57 with `expo-router`.
- Tests that need Postgres run against the local Docker Postgres from `infra/compose.yml` (or a Neon branch). SQLite is never used because `SKIP LOCKED` and JSONB must be exercised for real.
- System `ffmpeg` is available on the worker host and in the worker container.
- Google/Apple sign-in, when built in Phase 19, is verified server-side from ID tokens the mobile app obtains natively; no OAuth redirect flow runs on the backend.
- Presigned GET TTL is 10 minutes; presigned part PUT TTL is 60 minutes; multipart uploads that never complete are cleaned by an R2 lifecycle rule (abort incomplete multipart after 1 day), configured by the developer.
- Per-job worker timeout is 10 minutes (provisional, like every threshold in the spec).
- Weight and reps entered by the user are required at upload time; units (`lb`/`kg`) are stored with the value.
- Fault codes for V1 are exactly: `bar_drift`, `early_hip_rise`, `incomplete_lockout`, `knee_valgus`. Each is reported as `pass | flagged | unavailable` with a confidence value.
- Expo Go is sufficient for the Phase 2 upload spike and for on-device testing of capture, upload, History, and results on iOS. A dev build (and therefore an Apple Developer account) is first needed for push on device and for Phase 19.

---

## 5. Existing Code To Reuse

There is no existing code. Reuse inside the plan:

- `backend/liftcam/core/` is the single home for settings, SQLAlchemy models, R2 client, Expo Push client, JWT helpers. API and worker import it; nothing is duplicated between the two processes.
- One `Upload` response schema serves History list items, the status poll, and the results page; the results payload is nested and only populated when `status = ready`.
- The mobile `api/` client wraps `fetch` with JWT attach, single-flight refresh, and typed endpoints; every screen uses it.
- One `StatusBadge` component maps the six statuses to the four UI labels (`processing`, `ready`, `failed`, `no lift`).
- One `useUploadPolling` hook implements the 2 to 3 second poll and stop condition, used by both History and the upload detail screen.
- Worker stages share a small set of typed dataclasses (`FrameMeta`, `PoseTrack`, `BarTrack`, `Segment`, `Rep`) defined once in `worker/types.py`.
- The Phase 2 CV spike script becomes the seed of the Phase 17 single-stage runner rather than being thrown away.

---

## 6. Files Likely Touched

All new. Proposed layout:

```
/mobile                       Expo app (TypeScript)
  app/                        expo-router routes: (auth)/, (tabs)/capture, history, profile, upload/[id]
  src/api                     typed client, auth token storage, refresh
  src/theme                   colors, typography, spacing
  src/components              StatusBadge, SkeletonRow, StatCard, Chart
  src/features/capture        record, pick, confirm, upload
  src/features/results        overview, video, graphs
  src/features/auth           signup, login (oauth added in Phase 19)
  spike/                      Phase 2 chunk-read spike (deleted after Phase 8)
/backend                      one Python package, two entrypoints
  pyproject.toml
  alembic/                    migrations
  liftcam/core                settings, db, models, r2, push, security
  liftcam/api                 FastAPI app, routers: auth, users, uploads
  liftcam/worker              claim loop, run_job subprocess, stages/, cv/
  scripts/                    cv_spike.py, ground_truth_report.py
  tests/                      api, worker, fixtures/clips
/diagrams                     existing Mermaid; ER, sequence, component updated in Phases 3 and 6
/docs                         setup, env, architecture, deployment, spikes, adr/
/infra                        compose.yml (local Postgres from Phase 1), Dockerfile
README.md
.gitignore
```

---

## 7. AI Execution Order

Execute the phases below in order. Each phase is sized for one agent session (the largest may take two), ends at a stable and reviewable state, and requires no Git action between phases. Spikes run before anything depends on their answers. Backend contracts are built before mobile screens that consume them. CV phases come after the mobile shell so an end-to-end flow (upload, queue, stubbed result, poll, push) is testable early, and the results UI is built last against real rep data. OAuth is last so its console setup never blocks the pipeline.

1. Repository scaffold and tooling
2. Feasibility spikes: CV plate detection and on-device chunked reads
3. Database schema and migrations
4. Auth (email/password) and profile API
5. Upload handshake, History, and media presign API
6. Worker runtime: claim, stage runner, failure persistence, direct push
7. Mobile foundation: theme, API client, email auth screens, Profile tab
8. Mobile capture and upload flow
9. Mobile History tab, polling, status states, retry
10. CV stage: presence, pose, bar and plate detection, subject lock
11. CV stage: camera angle, calibration, segmentation, rep counting
12. CV stage: form faults, VBT, force/work, confidence gating
13. Overlay render and result commit
14. Mobile results page (Overview / Video / Graphs) and share
15. Benchmarking (deferrable for MVP)
16. Deployment and operations
17. Validation fixture suite and ground truth
18. Pre-launch compliance engineering
19. Google and Apple sign-in

**MVP cut.** Minimum to ship a usable build: Phases 1 through 14, then 16, 17, 18. Phase 15 (benchmarking) and Phase 19 (OAuth) complete V1 but do not gate the first shippable build. Within Phase 12, any fault or estimate that fails the Phase 17 ground-truth bar ships as `unavailable`, not skipped; the pipeline and schema already support that.

---

## 8. Sequential Implementation Phases

Standard AI Completion Criteria apply to every phase and are not repeated in full: implementation complete, tests pass, type checking passes (`mypy`, `tsc`), linting passes (`ruff`, `eslint`), documentation updated, temporary code removed, repository stable (both processes start, app builds).

Each phase ends with a **Success Criteria** checklist. A phase is done only when the standard criteria hold and every box is checked. Each item is a single observable outcome (a command that succeeds, a test that passes, a screen that behaves a stated way). Items tagged `(developer)` need a human action or decision and are checked off by the developer, not the agent; the agent stops at the end of the phase and reports which developer items remain open.

---

### Phase 1: Repository Scaffold and Tooling

#### Goal
Create the monorepo skeleton, toolchains, local Postgres, and runnable no-op entrypoints for API, worker, and mobile so every later phase has a place to land and a green baseline.

#### High Level Summary
Set up `backend/` as one Python project with `liftcam.core`, `liftcam.api` (FastAPI app with `/health`), and `liftcam.worker` (loop that logs and sleeps). Set up `mobile/` as an Expo app with `expo-router` and three empty tabs (Capture, History, Profile). Add `infra/compose.yml` with a Postgres service so Phase 3 tests have a real database from day one. Add lint, format, type check, and test runners for both stacks, `.env.example` files, `.gitignore`, and a root README that points to `docs/`. No business logic.

#### Implementation Areas
- Build tooling: `pyproject.toml` (ruff, mypy, pytest, uvicorn), `package.json`, `tsconfig.json`, ESLint/Prettier, `infra/compose.yml`
- Routes: `/health` only
- Services: settings loader via pydantic-settings reading env
- Documentation: README, `docs/setup.md`, `docs/env.md`

#### Estimated LOC
Approximately 450 to 750 lines.

#### Files Expected To Change
`backend/pyproject.toml`, `backend/liftcam/core/settings.py`, `backend/liftcam/api/main.py`, `backend/liftcam/worker/main.py`, `backend/tests/test_health.py`, `mobile/app/_layout.tsx`, `mobile/app/(tabs)/*`, `mobile/package.json`, `mobile/tsconfig.json`, `mobile/app.json`, `mobile/eas.json`, `infra/compose.yml`, `.gitignore`, `README.md`, `docs/setup.md`, `docs/env.md`, `.env.example` files.

#### Dependencies
None.

#### Can AI Complete Independently?
Yes. Expo project identifiers (bundle ID, EAS project ID) are placeholders; the developer fills them in Phase 16.

#### Risk
Low. Standard scaffolding.

#### Complexity
1/5

#### Success Criteria
- [x] In `backend/`: `ruff check .`, `ruff format --check .`, `mypy liftcam`, and `pytest` all exit 0.
- [x] In `mobile/`: `npx tsc --noEmit` and `npx eslint .` exit 0.
- [x] `uvicorn liftcam.api.main:app` starts and `GET /health` returns 200 with a JSON body; `tests/test_health.py` covers it.
- [x] `python -m liftcam.worker.main` starts, logs a heartbeat on each loop, and exits 0 on SIGINT (and SIGBREAK on Windows).
- [x] `docker compose -f infra/compose.yml up` starts Postgres (host port 5433, avoiding the machine's own Postgres 18 on 5432) and `tests/test_db_connection.py` opens a connection using the URL from settings.
- [ ] `npx expo start` renders Capture, History, and Profile tabs in Expo Go with no red-box errors. `(developer)` Agent verified `npx expo export` bundles cleanly; the on-phone check is yours.
- [x] `settings.py` reads every variable listed in `backend/.env.example`, and `docs/env.md` lists the same set.
- [x] `docs/setup.md` takes a fresh clone from zero to all of the above without undocumented steps.
- [x] `.gitignore` excludes `.env`, `node_modules/`, `__pycache__/`, `*.egg-info/`, and build outputs.

---

### Phase 2: Feasibility Spikes

#### Goal
Answer the two highest-variance unknowns before any product code depends on them: whether classical plate detection holds across camera angles, and whether chunked byte-range reads are viable on real phones.

#### High Level Summary
Two throwaway scripts, no product code. **CV spike:** `backend/scripts/cv_spike.py` takes a clip path, runs MediaPipe Pose Landmarker and OpenCV Hough circle plate detection frame by frame, writes annotated sample frames and a per-frame hit rate to a local output folder. Run on three developer-supplied clips (side, front, oblique). Exit question: does Hough plate detection find plates reliably at front and oblique angles, or is the YOLOv8-nano fallback a V1 requirement? **Upload spike:** `mobile/spike/chunk-read.ts`, runnable in Expo Go, reads a large local video in 8 to 16 MB parts using `expo-file-system` byte-range reads, logs part timings and peak memory, on one iPhone and one Android. Exit question: chunked reads are viable at that part size, or the spec's no-single-PUT rule must be revisited. Both answers are written to `docs/spikes.md` with a go/no-go and any threshold or design change they imply.

#### Implementation Areas
- Scripts: CV spike, chunk-read spike
- Documentation: `docs/spikes.md`

#### Estimated LOC
Approximately 150 to 300 lines.

#### Files Expected To Change
`backend/scripts/cv_spike.py`, `mobile/spike/chunk-read.ts`, `docs/spikes.md`, `backend/pyproject.toml` (mediapipe, opencv deps added early).

#### Dependencies
Phase 1.

#### Can AI Complete Independently?
No. The agent writes both scripts and can run the CV spike on any clips present. The developer supplies the three clips and runs the upload spike on physical devices via Expo Go.

#### Risk
Low for the phase itself. Its results decide the risk level of Phases 8, 10, and 11.

#### Complexity
2/5

#### Success Criteria
- [ ] `python scripts/cv_spike.py <clip>` writes annotated sample frames and a per-frame plate hit-rate summary to a local output folder for each of the three clips.
- [ ] `docs/spikes.md` records plate hit rate for side, front, and oblique separately, with sample frames referenced.
- [ ] `mobile/spike/chunk-read.ts` runs in Expo Go and logs per-part read time and peak memory at 8 MB and 16 MB part sizes.
- [ ] `docs/spikes.md` contains the logged numbers from one iPhone and one Android. `(developer)`
- [ ] `docs/spikes.md` states an explicit go/no-go for each question, the part size Phase 8 will use, and whether the YOLOv8-nano fallback is in V1 scope.
- [ ] Developer has read `docs/spikes.md` and recorded both decisions before Phase 3 begins. `(developer)`
- [ ] Both scripts lint and type-check; no product code was added under `liftcam/` or `mobile/src/`.

---

### Phase 3: Database Schema and Migrations

#### Goal
Implement the ER diagram as SQLAlchemy models plus Alembic migrations, including the operational columns the spec needs but the diagram omits.

#### High Level Summary
Create `users`, `uploads`, `segments`, `reps`, and `refresh_tokens`. `users` carries email, username, password hash (nullable for provider-only accounts later), `auth_provider`, `apple_user_id` (nullable unique), profile fields, `tier` defaulting to `free`, and `expo_push_token`. `uploads` carries status, both R2 keys, multipart id, user weight and unit, user reps, failure fields, `created_at`, `claimed_at`, `finished_at`, and probe metadata. `segments` adds `camera_angle_deg`, `angle_confidence`, `px_per_m`, `calibration_confidence`. `reps` stores times, velocity, `faults` JSONB, confidence, `force_estimate`, `work_estimate`, internal `lockout_ratio`, and a `series` JSONB holding the compact per-rep joint and bar time series the Graphs section needs; Graphs cannot be built from scalar rep columns, so this is decided now rather than as a later migration. Add indexes for History (`uploads(user_id, created_at desc)`) and the claim query (partial index on `uploads(status) where status = 'queued'`). Unique constraints on `users.email` and `users.username`. Provide an async engine for the API (pooled URL) and a sync engine for the worker (direct URL). Update `diagrams/er-data-model.md` to reflect added columns and the new table.

#### Implementation Areas
- Database: models, migrations, indexes, enums as constrained strings
- Models: Pydantic read schemas mirroring the tables
- Testing: migration up/down against Postgres, constraint tests
- Documentation: ER diagram update, `docs/architecture.md` data model section, ADR for `refresh_tokens`, operational columns, and `reps.series`

#### Estimated LOC
Approximately 550 to 850 lines.

#### Files Expected To Change
`backend/liftcam/core/db.py`, `backend/liftcam/core/models.py`, `backend/liftcam/core/schemas.py`, `backend/alembic/**`, `backend/tests/test_models.py`, `backend/tests/conftest.py` (Postgres fixture), `diagrams/er-data-model.md`, `docs/architecture.md`, `docs/adr/0001-schema-additions.md`.

#### Dependencies
Phase 1 (local Postgres). Phase 2 results reviewed.

#### Can AI Complete Independently?
Yes. Column additions beyond the ER diagram are listed in the ADR for developer review.

#### Risk
Medium. Schema decisions here are the hardest to change later (spec: "presentation is far easier to revise later than the pipeline/data-model decisions").

#### Complexity
2/5

#### Success Criteria
- [ ] `alembic upgrade head` on an empty Postgres creates `users`, `uploads`, `segments`, `reps`, `refresh_tokens` with all indexes and constraints; `alembic downgrade base` returns the database to empty. Both are exercised by a test.
- [ ] Two concurrent sessions run the claim query against one `queued` row and exactly one receives it.
- [ ] Duplicate `users.email` and duplicate `users.username` inserts are rejected.
- [ ] `uploads.status`, `failed_stage`, and `failure_code` reject any value outside the spec'd enum lists.
- [ ] A sample `reps.series` payload round-trips through insert and select unchanged.
- [ ] The API async engine and the worker sync engine each connect using their own URL from settings.
- [ ] `diagrams/er-data-model.md` matches `models.py` column for column, including the new table.
- [ ] `docs/adr/0001-schema-additions.md` lists every column and table added beyond the original ER diagram, with the reason for each.
- [ ] Push token cardinality decision recorded before the migration is final. `(developer)`

---

### Phase 4: Auth (Email/Password) and Profile API

#### Goal
Implement signup, login, token issuance and refresh, and profile read/update per the Accounts section, with the provider hooks in place for Phase 19.

#### High Level Summary
Email/password signup with argon2 hashing collects username, optional profile picture (default URL if skipped), DOB, height, weight, sex, and SBD maxes with units. Enforce age 13+ from DOB and reject under-13 at creation. Issue a short-lived JWT access token and an opaque refresh token stored hashed in `refresh_tokens`, rotated on use (old token deleted, unknown token rejected). No token-family tracking; reuse detection can be added later if needed. Provide `GET/PATCH /me` (all signup fields plus optional `favorite_lift`), `POST /me/push-token`, and logout (revoke refresh token). Single `lifter` role; no role column beyond `tier`. Account lookup is written as "find user by verified identity" so Phase 19 adds Google/Apple identities without touching the token or profile code.

#### Implementation Areas
- APIs: `/auth/signup`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/me`, `/me/push-token`
- Services: password hashing, JWT sign/verify, user lookup by identity
- Middleware: bearer auth dependency
- Testing: unit tests for the age gate and lookup, integration tests for each endpoint, refresh rotation
- Documentation: `docs/api.md` auth section, env vars for JWT secret

#### Estimated LOC
Approximately 500 to 750 lines.

#### Files Expected To Change
`backend/liftcam/core/security.py`, `backend/liftcam/api/deps.py`, `backend/liftcam/api/routers/auth.py`, `backend/liftcam/api/routers/users.py`, `backend/liftcam/api/schemas/*`, `backend/tests/api/test_auth.py`, `backend/tests/api/test_users.py`, `docs/api.md`, `docs/env.md`.

#### Dependencies
Phase 3.

#### Can AI Complete Independently?
Yes.

#### Risk
Medium. Auth bugs are security bugs.

#### Complexity
2/5

#### Success Criteria
- [ ] `POST /auth/signup` with valid fields returns 201 with an access and refresh token; the stored password is an argon2 hash.
- [ ] A DOB under 13 years is rejected with 422 and a readable message; a DOB of exactly 13 years today is accepted.
- [ ] `POST /auth/login` returns 401 on a wrong password and tokens on a correct one.
- [ ] `POST /auth/refresh` returns a new pair and the previous refresh token is rejected on reuse; an unknown token is rejected.
- [ ] `POST /auth/logout` revokes the refresh token; a later refresh with it fails.
- [ ] `GET /me` returns every signup field plus `favorite_lift`; a test asserts the password hash is absent from the body.
- [ ] `PATCH /me` updates profile fields with unit validation; `POST /me/push-token` stores the token on the user row.
- [ ] Any protected route without a bearer token, or with an expired one, returns 401.
- [ ] `docs/api.md` documents every auth and profile endpoint; `docs/env.md` lists the JWT secret and token TTL variables.

---

### Phase 5: Upload Handshake, History, and Media Presign API

#### Goal
Implement the multipart upload handshake, the status/History endpoints, retry, and presigned media access exactly as the sequence and state diagrams describe.

#### High Level Summary
`POST /uploads` validates weight, unit, reps, declared duration (reject over 45 s), file size, and part count; inserts an `uploading` row; creates an R2 multipart upload; stores its id; returns presigned part PUT URLs. `POST /uploads/:id/complete` accepts part ETags, completes the multipart on R2, and transitions the row to `queued`. `GET /uploads` returns the user's History newest first with the badge-mapped status. `GET /uploads/:id` returns status and, when `ready`, nested segments and reps (including `series`). `POST /uploads/:id/retry` is allowed only from `failed`, clears failure fields, and sets `queued`. `GET /uploads/:id/media?kind=overlay|original` returns a fresh 10 minute presigned GET. Internal failure fields are never serialized to clients. The API never reads or writes video bytes.

#### Implementation Areas
- APIs: uploads router, media presign
- Services: R2 client (boto3 S3 API against R2 endpoint), status transition guards
- Models: response schemas for History item, detail, results
- Testing: transition guard tests, presign shape tests with a mocked S3 client, ownership checks (user cannot read another user's upload)
- Documentation: `docs/api.md` uploads section, R2 bucket setup notes

#### Estimated LOC
Approximately 600 to 900 lines.

#### Files Expected To Change
`backend/liftcam/core/r2.py`, `backend/liftcam/api/routers/uploads.py`, `backend/liftcam/api/schemas/uploads.py`, `backend/liftcam/core/status.py` (allowed transitions), `backend/tests/api/test_uploads.py`, `docs/api.md`, `docs/r2.md`.

#### Dependencies
Phases 3 and 4.

#### Can AI Complete Independently?
Yes. R2 is mocked in tests; a live smoke test against a dev bucket is a developer step.

#### Risk
Medium. Presign correctness against R2 (region `auto`, path-style, checksum headers) is a common integration snag.

#### Complexity
3/5

#### Success Criteria
- [ ] `POST /uploads` with a valid body creates an `uploading` row, stores the R2 multipart id, and returns one presigned PUT URL per part.
- [ ] Declared duration over 45 s, zero reps, negative weight, unsupported unit, and out-of-range part count are each rejected with 422 and no row is created.
- [ ] `POST /uploads/:id/complete` with part ETags calls R2 complete (mocked) and transitions the row to `queued`.
- [ ] `GET /uploads` returns only the caller's uploads ordered by `created_at desc`; a test with several hundred rows uses the `(user_id, created_at)` index (`EXPLAIN` check).
- [ ] Requesting another user's upload on any uploads route returns 404.
- [ ] `GET /uploads/:id` returns nested segments and reps (with `series`) only when `status = ready`.
- [ ] `POST /uploads/:id/retry` succeeds only from `failed`, clears failure fields, and sets `queued`; from every other status it returns 409.
- [ ] Illegal transitions (`ready -> queued`, `processing -> retry`) return 409.
- [ ] A test asserts `failed_stage`, `failure_code`, and `failure_message` are absent from every uploads response body.
- [ ] `GET /uploads/:id/media?kind=overlay|original` returns a presigned GET with a 10 minute expiry; any other `kind` returns 422.
- [ ] The R2 client exposes only create-multipart, complete, abort, and presign; no API route reads or writes object bodies.

---

### Phase 6: Worker Runtime: Claim, Stage Runner, Failure Persistence, Direct Push

#### Goal
Build the worker process around the job lifecycle with a stubbed CV pipeline so the full async loop works before any CV exists.

#### High Level Summary
The worker loop claims one `queued` row with `FOR UPDATE SKIP LOCKED` on the direct Neon connection, sets `processing` and `claimed_at`, and runs the job in a child process with a hard timeout so crashes and hangs are isolated. The stage runner executes the ordered stage list, maps any exception or timeout to `failed` with `failed_stage`, `failure_code`, and a short internal message, and maps detection misses to `no_lift` with `failure_code` only. On startup it reaps rows stuck in `processing` past the timeout into `failed/timeout`. Stages implemented for real in this phase: `claim`, `download` (original from R2 to a temp dir), `probe` (ffprobe: duration, fps, resolution, rotation; reject corrupt; if duration exceeds 45 s, trim to the first 45 s and continue rather than failing), `overlay_upload`, and the final commit. CV stages are stubs that return fixed results so the pipeline reaches `ready`. After any terminal status the worker sends one Expo Push message directly to the user's stored token via `core/push.py`; there is no API hop. Update `diagrams/sequence-process-job.md` and `diagrams/component.md` to show the worker talking to Expo Push. Structured JSON logs keyed by `upload_id` and stage.

#### Implementation Areas
- Services: claim loop, subprocess job runner, stage runner, reaper, ffprobe wrapper, temp dir lifecycle, push client
- Database: status writes, failure field writes, `finished_at`
- Testing: claim concurrency test, stage failure mapping table test, timeout test with a sleeping stub stage, reaper test, push client test with a mocked Expo endpoint, 46 s fixture trimmed not failed
- Documentation: `docs/worker.md` (stages, codes, timeout), ADR for subprocess isolation and direct push, diagram updates

#### Estimated LOC
Approximately 650 to 950 lines.

#### Files Expected To Change
`backend/liftcam/worker/main.py`, `backend/liftcam/worker/run_job.py`, `backend/liftcam/worker/runner.py`, `backend/liftcam/worker/stages/{download,probe,overlay_upload,commit}.py`, `backend/liftcam/worker/stages/stubs.py` (removed in Phase 13), `backend/liftcam/worker/types.py`, `backend/liftcam/core/push.py`, `backend/tests/worker/*`, `diagrams/sequence-process-job.md`, `diagrams/component.md`, `docs/worker.md`, `docs/adr/0002-worker-runtime.md`.

#### Dependencies
Phases 3 and 5.

#### Can AI Complete Independently?
Yes.

#### Risk
Medium. Correct handling of crash, timeout, and partial writes determines whether `failed` rows are ever left inconsistent.

#### Complexity
3/5

#### Success Criteria
- [ ] The worker claims a `queued` row, sets `processing` and `claimed_at`, and with stubbed CV stages reaches `ready` with `finished_at` set and both R2 keys populated.
- [ ] Killing the child process mid-job yields `failed` with `failure_code = crash`.
- [ ] A stub stage that sleeps past the job timeout yields `failed` with `failure_code = timeout`.
- [ ] A corrupt fixture yields `failed`, `failed_stage = probe`, `failure_code = corrupt`.
- [ ] A 50 s fixture is trimmed to 45 s, its probe metadata (`duration_s`, `fps`, `width`, `height`) is stored, and the job reaches `ready`.
- [ ] On startup the reaper moves rows stuck in `processing` past the timeout to `failed/timeout`.
- [ ] The push client is called exactly once per terminal status against a mocked Expo endpoint; a missing or invalid token does not change the job outcome.
- [ ] No `segments` or `reps` rows exist for any non-`ready` upload after the failure tests.
- [ ] SIGTERM lets the current job finish, then the loop exits 0.
- [ ] Every log line is JSON and carries `upload_id` and `stage`.
- [ ] `diagrams/sequence-process-job.md` and `diagrams/component.md` show worker -> Expo Push with no API hop; `docs/worker.md` lists stage order, failure mapping, and timeout.

---

### Phase 7: Mobile Foundation: Theme, API Client, Email Auth Screens, Profile Tab

#### Goal
Establish the visual system, typed API client with token handling, and the email/password auth and profile experience, with the auth screens laid out to accept provider buttons in Phase 19.

#### High Level Summary
Implement theme tokens from Branding: cream background, near-black primary text, muted gray secondary text, forest green primary accent, ochre warning tone, one sans family with tabular figures for numbers, rounded corners with thin borders, no shadows, light mode only. Build the API client with secure token storage (`expo-secure-store`), automatic access token attach, and single-flight refresh on 401. Build signup (all required fields, unit toggles, DOB picker with 13+ validation mirrored client-side), login, and the Profile tab (view and edit all fields, optional favorite lift, logout). Leave a clearly bounded slot on signup and login for provider buttons; do not build them. New users land on Capture after signup, with a brief first-time overlay explaining the framing guide and the async notify flow.

#### Implementation Areas
- Components: theme provider, text and number primitives, form inputs, buttons, skeleton placeholder
- State management: auth session context only; no global store
- Routes: `(auth)/signup`, `(auth)/login`, `(tabs)/profile`
- Testing: unit tests for the API client refresh path and form validation
- Documentation: `docs/mobile.md` (structure, theme tokens), ADR for `expo-video`

#### Estimated LOC
Approximately 1,000 to 1,400 lines.

#### Files Expected To Change
`mobile/src/theme/*`, `mobile/src/api/*`, `mobile/src/features/auth/*`, `mobile/app/(auth)/*`, `mobile/app/(tabs)/profile.tsx`, `mobile/app/_layout.tsx` (auth gate), `mobile/src/components/*`, `mobile/__tests__/*`, `docs/mobile.md`, `docs/adr/0003-expo-video.md`.

#### Dependencies
Phase 4 (auth API). Phase 1 shell.

#### Can AI Complete Independently?
Yes. Everything here runs in Expo Go; no developer accounts needed.

#### Risk
Low to medium. Token refresh races are the usual source of bugs.

#### Complexity
3/5

#### Success Criteria
- [ ] All colors, type styles, spacing, and radii come from `src/theme`; a grep for hex literals outside `src/theme` returns nothing.
- [ ] Signup collects every required field with unit toggles and a DOB picker; an under-13 DOB is blocked client-side, and a server 422 is surfaced when bypassed.
- [ ] Login and logout round-trip against the Phase 4 API; tokens live in `expo-secure-store` and are cleared on logout.
- [ ] Cold start lands on login when signed out and on Capture when signed in.
- [ ] Concurrent requests that all hit 401 trigger exactly one refresh call (unit test on the API client).
- [ ] Profile tab shows and edits every profile field including `favorite_lift`.
- [ ] Both auth screens contain an empty, bounded slot where provider buttons will go; no provider code exists.
- [ ] New users land on Capture after signup and see the first-time overlay exactly once.
- [ ] Numeric stat text renders with tabular figures.
- [ ] `docs/mobile.md` documents routes and theme tokens; `docs/adr/0003-expo-video.md` records the substitution.

---

### Phase 8: Mobile Capture and Upload Flow

#### Goal
Deliver both primary capture paths and the shared multipart upload path per the activity diagram, using the part size validated in Phase 2.

#### High Level Summary
Capture tab offers Record and Camera Roll with equal weight. Pre-record screen shows a static framing guide and the side-view tip ("film from the side for the most accurate bar path, we'll still track most angles"); no live inference. Recording is plain, no overlay, capped at 45 s. Camera roll picks a video and rejects clips over 45 s. Both paths land on a "dumb" confirm/retake screen with playback and a weight, unit, and reps form. Upload creates the row via `POST /uploads`, reads the file in fixed-size parts (size from `docs/spikes.md`), PUTs each part to its presigned URL with per-part retry, tracks ETags, calls complete, then navigates to History where the item appears as `processing`. Upload state (upload id, multipart id, completed parts) is persisted locally so reopening the app after backgrounding resumes the same multipart. Foreground only. After the user's first upload reaches a terminal state, prompt for push permission and register the Expo token. Delete `mobile/spike/` at the end of this phase.

#### Implementation Areas
- Components: framing guide, confirm/retake, upload progress
- Services: part reader, uploader with retry and resume, local upload state persistence
- Routes: `(tabs)/capture`, `capture/record`, `capture/confirm`
- Testing: unit tests for part splitting, retry, resume from persisted state, duration validation
- Documentation: `docs/mobile.md` capture section, upload resume behavior

#### Estimated LOC
Approximately 900 to 1,300 lines.

#### Files Expected To Change
`mobile/src/features/capture/*`, `mobile/src/features/upload/*`, `mobile/app/(tabs)/capture.tsx`, `mobile/app/capture/*`, `mobile/src/notifications/*`, `mobile/__tests__/upload/*`, `mobile/spike/` (deleted), `docs/mobile.md`.

#### Dependencies
Phases 2 (go on chunked reads), 5, 7.

#### Can AI Complete Independently?
Yes for code. Physical device testing of camera and large file reads is a developer step (Expo Go is enough).

#### Risk
Medium after the spike (was High). If the spike said no-go, this phase does not start until the spec question is resolved.

#### Complexity
4/5

#### Success Criteria
- [ ] Record path stops at 45 s; the pre-record screen shows the static framing guide and side-view tip and runs no inference.
- [ ] Camera roll path rejects a 46 s clip before any network call; a 45 s clip is accepted.
- [ ] Confirm screen plays the clip, collects weight, unit, and reps, and Retake returns to the originating path.
- [ ] Upload reads the file in parts of the size recorded in `docs/spikes.md`, PUTs each to its presigned URL, tracks ETags, calls complete, and History shows the item as `processing`.
- [ ] A simulated failed part is retried alone; other parts are not re-sent (unit test).
- [ ] Killing and relaunching mid-upload resumes with the same upload and multipart id and skips completed parts (unit test on persisted state, device check by developer).
- [ ] Push permission is not requested on first open; it is requested after the first upload reaches a terminal status, and the token is posted to `/me/push-token`.
- [ ] `mobile/spike/` no longer exists and nothing imports from it.
- [ ] Record, upload, background, relaunch, and resume confirmed on a physical phone. `(developer)`

---

### Phase 9: Mobile History Tab, Polling, Status States, Retry

#### Goal
Make History the single source of truth for job state with live polling and correct per-status behavior.

#### High Level Summary
History lists uploads newest first with skeleton placeholders while loading and an empty state pointing back to Capture. Each row shows the badge (`processing`, `ready`, `failed`, `no lift`). A `useUploadPolling` hook polls every 2 to 3 s while any visible item is in flight and stops when none are. Tapping `processing` opens a status view; tapping `failed` offers "processing failed, tap to retry" which calls retry and returns the item to `processing`; tapping `no lift` shows a plain explanation that nothing was detected, with no results page; tapping `ready` opens the results route (built in Phase 14, stubbed here). Failure codes and stages never appear. A push notification tap deep-links to the upload's detail route.

#### Implementation Areas
- Components: History list, StatusBadge, empty state, detail status screen
- State management: polling hook with visibility-aware stop
- Routes: `(tabs)/history`, `upload/[id]`
- Testing: badge mapping test, polling start/stop test, retry flow test
- Documentation: `docs/mobile.md` History section

#### Estimated LOC
Approximately 500 to 800 lines.

#### Files Expected To Change
`mobile/app/(tabs)/history.tsx`, `mobile/app/upload/[id].tsx`, `mobile/src/features/history/*`, `mobile/src/components/StatusBadge.tsx`, `mobile/src/hooks/useUploadPolling.ts`, `mobile/__tests__/history/*`, `docs/mobile.md`.

#### Dependencies
Phases 5, 6 (stubbed pipeline reaches `ready`), 7, 8.

#### Can AI Complete Independently?
Yes. Push-tap deep link on a device needs a dev build; it can be verified in Phase 16.

#### Risk
Low.

#### Complexity
2/5

#### Success Criteria
- [ ] History lists uploads newest first, shows skeleton rows while loading, and shows an empty state that links to Capture when there are none.
- [ ] `StatusBadge` maps all six statuses to the four labels (`uploading` and `queued` render as `processing`); covered by a unit test.
- [ ] `useUploadPolling` polls every 2 to 3 s while any visible item is in flight and stops within one interval after the last one settles (unit test with fake timers).
- [ ] Tapping `processing` opens the status view; tapping `failed` shows "processing failed, tap to retry", calls retry, and the row returns to `processing`; tapping `no lift` shows a plain explanation with no results route; tapping `ready` opens `upload/[id]` (stubbed until Phase 14).
- [ ] No screen renders `failed_stage`, `failure_code`, or `failure_message`.
- [ ] A push notification payload deep-links to `upload/[id]` for the right id (route wiring test; device check in Phase 16).
- [ ] End to end against the Phase 6 stubbed worker, an upload goes `processing -> ready` in History without an app restart.

---

### Phase 10: CV Stage: Presence, Pose, Bar and Plate Detection, Subject Lock

#### Goal
Replace the first CV stubs with real `presence`, `pose`, and `track` stages that produce per-frame landmarks and a bar track tied to a locked subject.

#### High Level Summary
`presence` samples a sparse set of frames and checks only for a person (BlazePose detection) and for motion; missing a person returns `no_lift/no_person` and nothing further runs. Bar presence is **not** decided here: a strict early bar gate would turn weak plate detection into false "no lift" results on valid videos. `pose` runs MediaPipe Pose Landmarker on every frame and keeps per-landmark confidence. `track` detects plates and the bar per frame using three constraints from the spec: ROI limited to the candidate lifter's zone, bar-line anchoring, and temporal consistency with bar motion. If no bar track can be established across the clip with the full temporal evidence, `track` returns `no_lift/no_bar`. Subject lock uses size/centrality as the fast first pass, confirmed by hand-to-bar proximity over subsequent frames; when they disagree, hand-bar contact wins. Once locked for a segment the subject id persists so a spotter cannot hijack tracking. Bar selection follows the winning subject. All functions are pure over frame arrays and return typed tracks. If the Phase 2 spike showed classical detection failing at front/oblique angles, the plate finder is built behind a small interface and the developer decides whether the YOLOv8-nano fallback is built in this phase or after Phase 17; the agent does not decide that alone.

#### Implementation Areas
- Services: frame reader, presence sampler, pose runner, plate/bar detector, subject lock
- Models: `PoseTrack`, `BarTrack`, per-frame confidence
- Testing: fixture clips for `no_person`, `no_bar`, and a clean happy path; unit tests for anchoring and temporal filters on synthetic data
- Documentation: `docs/cv.md` (detection approach, constraints, known limits, spike findings)

#### Estimated LOC
Approximately 1,000 to 1,500 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/frames.py`, `backend/liftcam/worker/cv/pose.py`, `backend/liftcam/worker/cv/plates.py`, `backend/liftcam/worker/cv/subject.py`, `backend/liftcam/worker/stages/{presence,pose,track}.py`, `backend/tests/worker/cv/*`, `backend/tests/fixtures/clips/README.md`, `docs/cv.md`.

#### Dependencies
Phases 2 and 6.

#### Can AI Complete Independently?
Partially. Code and synthetic tests are independent. Real acceptance needs developer-supplied clips (Phase 17). The fallback-detector decision is the developer's.

#### Risk
High. Classical plate detection against gym clutter is the stated risk in the spec; plates are circles only from the side, so front and oblique views are where it is weakest.

#### Complexity
5/5

#### Success Criteria
- [ ] The `no_person` fixture terminates at `presence` with `no_lift/no_person` and the pose runner is never invoked (asserted via mock).
- [ ] The `no_bar` fixture runs `pose` and `track` over the full clip and terminates with `no_lift/no_bar`.
- [ ] The happy-path fixture yields a `PoseTrack` with per-landmark confidence for every frame and a `BarTrack` with no gap longer than the provisional threshold.
- [ ] A synthetic second bar outside the lifter ROI is ignored; a synthetic bar that fails temporal consistency is rejected.
- [ ] When size/centrality and hand-bar contact disagree on the subject, hand-bar contact wins, and the subject id stays fixed for the rest of the segment (synthetic spotter test).
- [ ] The plate finder sits behind a small interface with one classical implementation; the fallback-detector decision from Phase 2 is recorded in `docs/cv.md`.
- [ ] Nothing under `worker/cv/` imports the database or R2 modules (import test).
- [ ] `docs/cv.md` describes the three detection constraints, subject lock, and known limits.

---

### Phase 11: CV Stage: Camera Angle, Calibration, Segmentation, Rep Counting

#### Goal
Turn tracks into segments and counted reps with a per-segment angle estimate and pixel-to-meter calibration.

#### High Level Summary
Camera angle uses visible bar length between outer plate edges as the primary signal (full length is front/behind, near zero is side, sine relationship in between) with plate width:height ratio as fallback when both ends are not visible; front vs behind is disambiguated by pose face orientation; left/right oblique mirror ambiguity is accepted. Calibration uses the plate's vertical extent assuming a standard plate, cross-checked against plate-to-plate span; disagreement or non-standard/no plates marks calibration low-confidence. Angle and calibration are computed independently so an error in one does not affect the other. Segmentation finds windows of continuous "person + bar in motion"; none found returns `no_lift/no_motion`. Rep counting finds local maxima in bar vertical position with a minimum peak-to-trough displacement, and a hard lockout gate requiring hip and knee extension at the peak of at least about 90% of full extension; sub-90% attempts are recorded internally as `lockout_ratio` on a non-counted attempt list and never surfaced. The user's entered rep count is compared to the detected count and the mismatch is logged only.

#### Implementation Areas
- Services: angle estimator, calibrator, segmenter, rep counter, lockout gate
- Models: `Segment` with angle and calibration fields, `Rep` with `lockout_ratio`
- Testing: synthetic bar trajectories (standard, RDL-style no floor reset, jitter, partial lockout); `no_motion` fixture; angle estimates on labeled fixtures
- Documentation: `docs/cv.md` thresholds table marked provisional

#### Estimated LOC
Approximately 800 to 1,200 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/angle.py`, `backend/liftcam/worker/cv/calibration.py`, `backend/liftcam/worker/cv/segments.py`, `backend/liftcam/worker/cv/reps.py`, `backend/liftcam/worker/stages/segment.py`, `backend/liftcam/worker/stages/score.py` (partial), `backend/tests/worker/cv/*`, `docs/cv.md`.

#### Dependencies
Phase 10.

#### Can AI Complete Independently?
Yes for code and synthetic tests. Threshold validation is developer work in Phase 17.

#### Risk
High. Every threshold is provisional by the spec's own statement.

#### Complexity
4/5

#### Success Criteria
- [ ] Camera angle on the labeled side, front, and oblique fixtures falls within the provisional tolerance; front vs behind is resolved by face orientation in a synthetic test.
- [ ] With both plate ends visible, angle comes from bar length; with one end hidden, it falls back to plate width:height ratio (unit tests for each path).
- [ ] Standard-plate fixtures produce `px_per_m` with high `calibration_confidence`; a plate-span cross-check mismatch or non-standard plate marks it low-confidence.
- [ ] Changing the angle input does not change the calibration output and vice versa (independence test).
- [ ] The `no_motion` fixture terminates at `segment` with `no_lift/no_motion`.
- [ ] Synthetic trajectories: a standard set of N reps counts N; an RDL-style set with no floor reset counts correctly; jitter adds no reps; a peak at 80% extension is not counted and appears in the internal attempt list with its `lockout_ratio`.
- [ ] A mismatch between entered and detected reps is logged and changes neither status nor results.
- [ ] Every threshold lives in one config module and `docs/cv.md` has a thresholds table marked provisional.

---

### Phase 12: CV Stage: Form Faults, VBT, Force/Work, Confidence Gating

#### Goal
Complete the `score` stage with per-rep faults, bar velocity, force/work estimates, and per-feature confidence.

#### High Level Summary
Compute four faults per rep, each gated by camera-angle confidence individually: bar-over-midfoot drift (side view), hip rising faster than shoulders / early hip extension (side view), lockout completeness (any angle), knee valgus (front or 45 degrees). Each fault reports `pass | flagged | unavailable` with a one-line reason code and confidence. Spine rounding is not scored; the shoulder-hip line is only a geometric reference. Liftoff occlusion handling: interpolate landmarks from neighbors when per-landmark confidence dips, fall back to the brace/setup frame as a proxy, and mark the portion low-confidence if both are poor. VBT is calibrated plate height times frame-to-frame displacement over time, trusted only at 30 fps+ and 720p+ with standard-plate calibration, otherwise low-confidence. Force/work/energy estimates use user-entered bar mass, measured velocity/acceleration, and a rough bodyweight factor from profile height/weight, inheriting the lowest input confidence. Also compute set-level velocity loss percent. Scoring reads raw or lightly filtered data, never the display-smoothed series. This stage also writes the per-rep `series` payload (bar X/Y and hip, knee, shoulder, elbow, wrist position and velocity over time) consumed by Graphs.

**MVP scope note.** `bar_drift` and `early_hip_rise` ship as `unavailable` until they pass the Phase 17 ground-truth bar. Force/work is the first estimate to hide when calibration confidence is poor. No code branches for this; the confidence gates already produce it.

#### Implementation Areas
- Services: fault detectors, occlusion handling, velocity, force/work, confidence combiner, series builder
- Models: `faults` JSONB shape (code, result, reason, confidence), rep numeric fields, `series` shape
- Testing: synthetic pose sequences per fault, occlusion interpolation tests, low-fps and non-standard-plate confidence downgrades, series shape test
- Documentation: `docs/cv.md` fault definitions and confidence rules; `docs/api.md` faults and series schema

#### Estimated LOC
Approximately 850 to 1,250 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/faults.py`, `backend/liftcam/worker/cv/velocity.py`, `backend/liftcam/worker/cv/force.py`, `backend/liftcam/worker/cv/confidence.py`, `backend/liftcam/worker/cv/series.py`, `backend/liftcam/worker/stages/score.py`, `backend/tests/worker/cv/*`, `docs/cv.md`, `docs/api.md`.

#### Dependencies
Phase 11.

#### Can AI Complete Independently?
Yes for code. Biomechanical threshold validation is developer work.

#### Risk
High. Fault thresholds and occlusion handling directly shape user-facing results.

#### Complexity
4/5

#### Success Criteria
- [ ] Each of the four fault detectors has a synthetic `pass` case and a synthetic `flagged` case, and every result carries a reason code and confidence.
- [ ] A front-view fixture reports `bar_drift` and `early_hip_rise` as `unavailable` (never `pass`) and computes `knee_valgus`; a side-view fixture reports `knee_valgus` as `unavailable`.
- [ ] Dropped landmarks during liftoff are interpolated from neighbors; when neighbors are also poor, the brace frame proxy is used and that portion is marked low-confidence.
- [ ] A 24 fps clip, a sub-720p clip, and a non-standard-plate calibration each downgrade velocity to low confidence.
- [ ] Force and work confidence is never higher than the velocity confidence they derive from (property test).
- [ ] Set-level velocity loss percent is computed and stored.
- [ ] `series` for one rep decodes to bar X/Y plus hip, knee, shoulder, elbow, and wrist position and velocity over time; the shape is documented in `docs/api.md`.
- [ ] Scoring never imports the display smoothing module (import test).
- [ ] `docs/cv.md` defines each fault and its angle gate; the MVP `unavailable` defaults are listed.

---

### Phase 13: Overlay Render and Result Commit

#### Goal
Render the single overlay video, upload it, commit segments and reps atomically, and remove the last stubs.

#### High Level Summary
The `render` stage draws skeleton, detected plates/bar, and bar path onto every frame using a separately smoothed display series (two-pass rendering). Where confidence drops, the overlay and path for that portion are hidden rather than drawn from a smoothed guess. Bar path is full 2D from side-ish angles and vertical-only from front/behind. Output is capped at 720p (downscale larger sources before drawing); the overlay is viewed on a phone and 1080p drawing plus encode is the largest single CPU cost in the job. Frames are encoded with `ffmpeg` to H.264 MP4 with `faststart` for mobile playback, preserving source rotation. `overlay_upload` puts the file to R2 under the `overlay` key. The commit writes `segments` and `reps` (with `series`) in one transaction, sets `ready` and `finished_at`, and triggers push. No per-rep encodes. All stubs from Phase 6 are deleted.

#### Implementation Areas
- Services: smoothing filter, frame drawer, downscale, encoder wrapper, commit
- Database: transactional insert of segments and reps
- Testing: render a short fixture and assert output duration, resolution cap, and playable metadata; commit rollback test on a forced failure after overlay upload
- Documentation: `docs/worker.md` render section

#### Estimated LOC
Approximately 500 to 800 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/smooth.py`, `backend/liftcam/worker/cv/draw.py`, `backend/liftcam/worker/stages/render.py`, `backend/liftcam/worker/stages/commit.py`, `backend/liftcam/worker/stages/stubs.py` (deleted), `backend/tests/worker/test_render.py`, `docs/worker.md`.

#### Dependencies
Phases 10 through 12.

#### Can AI Complete Independently?
Yes.

#### Risk
Medium. Encoding and rotation handling are fiddly; render time dominates job duration.

#### Complexity
3/5

#### Success Criteria
- [ ] The happy-path fixture runs end to end to `ready` with exactly two R2 objects and `segments`/`reps` row counts equal to the detected counts.
- [ ] A 1080p source yields a 720p overlay; a 720p source keeps its resolution; a portrait source keeps its rotation (checked with `ffprobe`).
- [ ] The overlay is H.264 MP4 with `faststart` (moov atom before mdat) and its duration matches the working copy within one frame.
- [ ] Low-confidence portions draw no skeleton or bar path (unit test on the drawer with a synthetic confidence dip).
- [ ] Bar path is 2D for side-ish angles and vertical-only for front/behind (unit test).
- [ ] A failure injected after `overlay_upload` leaves no `segments`/`reps` rows and the status reflects the failing stage.
- [ ] A 45 s 1080p fixture finishes inside the job timeout on the dev machine; wall time is recorded in `docs/worker.md`.
- [ ] `stages/stubs.py` is deleted and no reference to stubs remains in code, tests, or docs.

---

### Phase 14: Mobile Results Page (Overview / Video / Graphs) and Share

#### Goal
Build the `ready` experience: per-rep stats, seeked overlay playback, graphs, and overlay-only share/download.

#### High Level Summary
Results open from a `ready` History item with three sections. Overview: rep-by-rep stat cards (reps, average velocity, velocity loss percent, flagged faults summary, entered weight/reps, force/work estimate) with count-up on load, per-fault rows shown as pass / flagged / not available from this angle with a one-line explanation when flagged, and a short scannable stats summary with tooltips for terms like velocity loss. No blended score. Video: `expo-video` player on a fresh presigned overlay URL, rep selector that seeks to the rep's start and stops at its end, responsive frame-accurate scrubbing. Graphs: bar path X/Y, plus position and velocity over time for hip, knee, shoulder, elbow, wrist, selectable per rep, read from `reps.series`, using a lightweight SVG chart component. Share opens the OS share sheet with the downloaded overlay file (`expo-sharing`); download saves it to the camera roll (`expo-media-library`). The original is never shared. Skeleton placeholders while loading. Presigned URL expiry triggers a silent re-presign.

#### Implementation Areas
- Components: StatCard, FaultRow, RepSelector, VideoPlayer, LineChart, InfoTooltip
- Routes: `upload/[id]` results mode
- Services: media URL fetch with re-presign, file download for share
- Testing: fault row rendering per state, rep seek bounds, share uses overlay kind only
- Documentation: `docs/mobile.md` results section

#### Estimated LOC
Approximately 1,300 to 1,800 lines.

#### Files Expected To Change
`mobile/src/features/results/*`, `mobile/src/components/{StatCard,LineChart,InfoTooltip}.tsx`, `mobile/app/upload/[id].tsx`, `mobile/__tests__/results/*`, `docs/mobile.md`.

#### Dependencies
Phases 9 and 13.

#### Can AI Complete Independently?
Yes. Share sheet and save-to-camera-roll are verified on a device by the developer (Expo Go is enough).

#### Risk
Medium. Frame-accurate seek behavior varies across devices.

#### Complexity
4/5

#### Success Criteria
- [ ] Overview renders per-rep stat cards, a fault row per fault as pass / flagged / not available from this angle with a one-line explanation when flagged, and a stats summary with tooltips; no blended score appears anywhere.
- [ ] A fault marked `unavailable` never renders as pass (unit test per state).
- [ ] Video plays from a fresh presigned overlay URL; selecting rep 2 seeks to its `start_s` and pauses at its `end_s`.
- [ ] An expired presigned URL triggers a silent re-presign and playback continues.
- [ ] Graphs render bar path X/Y and position and velocity over time for hip, knee, shoulder, elbow, and wrist from `reps.series`, selectable per rep.
- [ ] Share hands the OS share sheet the overlay file only; download saves the overlay to the camera roll; the results screen never requests `kind=original` (unit test).
- [ ] Skeleton placeholders show while results load; all stat numbers use tabular figures.
- [ ] Share sheet and save-to-camera-roll confirmed on a physical phone. `(developer)`

---

### Phase 15: Benchmarking (Deferrable for MVP)

#### Goal
Show per-upload comparison against the user's own deadlift max and against population strength standards.

#### High Level Summary
Compute at read time in the API, not in the worker, since profile values can change. Personal benchmark: entered weight versus `deadlift_max`, and a hint when the upload exceeds the stored max. Population benchmark: bodyweight-relative percentile for deadlift by sex from a standards table shipped as a static data file in `core/`, with its source and license recorded. Returned as part of the results payload and shown in the Overview section. Deadlift only. This phase gates nothing else and is blocked on a human data-licensing decision, so it can run after the first shippable build.

#### Implementation Areas
- Services: benchmark calculator, standards table loader
- APIs: results payload extension
- Components: benchmark card in Overview
- Testing: interpolation and boundary tests (below lowest bracket, above highest, missing profile fields)
- Documentation: `docs/benchmarking.md` with data provenance

#### Estimated LOC
Approximately 300 to 500 lines.

#### Files Expected To Change
`backend/liftcam/core/benchmarks.py`, `backend/liftcam/core/data/deadlift_standards.json`, `backend/liftcam/api/routers/uploads.py`, `backend/tests/test_benchmarks.py`, `mobile/src/features/results/BenchmarkCard.tsx`, `docs/benchmarking.md`.

#### Dependencies
Phases 5 and 14.

#### Can AI Complete Independently?
No. The developer must choose and approve the strength standards data source and confirm its license before the table is committed.

#### Risk
Low technically; medium for data licensing.

#### Complexity
2/5

#### Success Criteria
- [ ] Standards data source and license are approved and recorded in `docs/benchmarking.md` before `deadlift_standards.json` is committed. `(developer)`
- [ ] Personal benchmark compares entered weight to `deadlift_max` and returns an exceeds-max hint when applicable.
- [ ] Percentile is monotonic across the whole table; below-lowest and above-highest brackets return the boundary value without error.
- [ ] Missing height, weight, sex, or max yields an explicit "add profile data" state in the payload, not an error.
- [ ] Benchmarks are computed in the API at read time; no worker file changes in this phase.
- [ ] The Overview section shows the benchmark card, including the "add profile data" state.

---

### Phase 16: Deployment and Operations

#### Goal
Make the API and worker deployable as two processes on one host, with mobile builds via EAS.

#### High Level Summary
Add a Dockerfile for the backend image (includes `ffmpeg` and MediaPipe runtime deps) with two commands (`api`, `worker`), extend `infra/compose.yml` (or the chosen PaaS manifest) to run both from the same image with health checks, log shipping to stdout, and an Alembic migrate step on deploy. Document Neon setup (pooled URL for API, direct URL for worker), R2 bucket creation with the incomplete-multipart lifecycle rule, environment variables, and EAS build profiles (development, preview, production) with the real bundle identifiers. No AWS. Hosting provider is chosen by the developer at this point per the spec. The first dev build here is also where push-on-device and the push-tap deep link are verified.

#### Implementation Areas
- Build tooling: Dockerfile, compose or manifest, `eas.json`, minimal CI running lint, types, and tests
- Documentation: `docs/deployment.md`, `docs/env.md` final pass

#### Estimated LOC
Approximately 300 to 500 lines.

#### Files Expected To Change
`infra/Dockerfile`, `infra/compose.yml`, `.github/workflows/ci.yml`, `mobile/eas.json`, `mobile/app.json`, `docs/deployment.md`, `docs/env.md`.

#### Dependencies
Phases 1 through 14 for a meaningful deploy.

#### Can AI Complete Independently?
No. Provider choice, account creation, DNS, secrets, bundle identifiers, and the first deploy are developer tasks. The agent produces the artifacts and instructions.

#### Risk
Medium. First deploy surfaces environment differences (ffmpeg, MediaPipe wheels, memory limits on a small VPS).

#### Complexity
2/5

#### Success Criteria
- [ ] `docker build -f infra/Dockerfile .` succeeds; `ffmpeg -version` and a MediaPipe import both work inside the container.
- [ ] The image's `api` and `worker` commands each start and pass their health checks in compose alongside Postgres; the Alembic migrate step runs before the API starts.
- [ ] `.github/workflows/ci.yml` runs lint, type check, and tests for both stacks and is green on the default branch.
- [ ] `mobile/eas.json` defines development, preview, and production profiles; `app.json` carries the real bundle identifier, package name, and EAS project ID. `(developer)` supplies the values.
- [ ] `docs/env.md` lists every variable read by API, worker, and mobile with the process that reads it; `docs/deployment.md` covers Neon (pooled and direct URLs), R2 bucket and lifecycle rule, host setup, and EAS.
- [ ] Developer completes the first deploy by following `docs/deployment.md` alone and reports any step that differed. `(developer)`
- [ ] Push arrives on a physical device from the deployed worker and tapping it opens the correct upload. `(developer)`

---

### Phase 17: Validation Fixture Suite and Ground Truth

#### Goal
Turn the Validation / QA section into an executable acceptance suite: one golden clip per `failure_code` and per happy-path stage, plus ground-truth comparisons.

#### High Level Summary
Create a fixture manifest listing each clip, its expected terminal status and code, and expected rep count, lockout calls, bar path extent, and velocity where measured. Grow `backend/scripts/cv_spike.py` from Phase 2 into the stage-level runner that executes any single stage on a clip without the rest of the worker, and add a full-pipeline test per fixture. Add a ground-truth comparison report that prints detected versus measured values with tolerances so thresholds from Phases 11 and 12 can be tuned against real data. Keep training footage (if a fallback detector is ever trained) separate from grading footage by directory convention. Large clips are stored outside Git (documented location) and downloaded by the test runner when present; tests skip cleanly when clips are absent. This phase is the acceptance gate for Phases 10 through 13 and for the MVP scope decisions in Phase 12.

#### Implementation Areas
- Testing: fixture manifest, stage-level runner, pipeline tests, report script
- Documentation: `docs/validation.md` (how to add a clip, how to measure ground truth, acceptance bar)

#### Estimated LOC
Approximately 400 to 700 lines.

#### Files Expected To Change
`backend/tests/fixtures/manifest.yaml`, `backend/tests/fixtures/clips/.gitkeep`, `backend/tests/worker/test_fixtures.py`, `backend/scripts/cv_spike.py` (renamed to `run_stage.py`), `backend/scripts/ground_truth_report.py`, `docs/validation.md`.

#### Dependencies
Phase 13.

#### Can AI Complete Independently?
No. The developer records the ground-truth clips (known bar, plates, camera setup, tape measure, frame counts, manual rep and lockout calls). The agent builds the harness and can seed it with synthetic or provisional clips.

#### Risk
Medium. Without real footage the CV phases cannot be accepted; this phase is the gate.

#### Complexity
3/5

#### Success Criteria
- [ ] `manifest.yaml` has an entry for each of the six `failure_code` values, a corrupt file, an over-length clip, and at least one happy-path clip per camera angle, each with expected terminal status and code.
- [ ] `python scripts/run_stage.py <stage> <clip>` runs any single stage from the CLI without the worker loop or database.
- [ ] `test_fixtures.py` runs the full pipeline per manifest entry and asserts terminal status and code; every test skips cleanly when its clip is absent.
- [ ] `ground_truth_report.py` prints detected versus measured rep count, lockout calls, bar path extent, and velocity with a tolerance pass/fail per metric.
- [ ] Training and grading footage live in separate directories and the test runner reads only the grading directory.
- [ ] `docs/validation.md` explains how to add a clip, how to measure ground truth, where large clips are stored, and the acceptance bar per metric.
- [ ] Ground-truth clips are recorded and their measured values filled into `manifest.yaml`. `(developer)`
- [ ] The ground-truth report is reviewed, threshold changes are accepted or rejected, and the MVP `unavailable` decisions for Phase 12 are recorded in `docs/cv.md`. `(developer)`

---

### Phase 18: Pre-Launch Compliance Engineering

#### Goal
Implement the engineering pieces of the Legal / Compliance checklist. Legal review itself is human work and a hard launch gate.

#### High Level Summary
Colorblind-safe fault signaling: every flagged or low-confidence state pairs the ochre color with an icon and text label so meaning never depends on hue alone; verify green/ochre contrast and simulate red-green deficiency. Legal hooks: Privacy Policy and Terms of Service links on signup and in Profile (URLs from config), a required acceptance checkbox at signup, and a one-time bystander attestation on first upload that the user has the right to record and share the footage, with acceptance timestamps stored on `users`. Data inventory: a `docs/privacy-data-inventory.md` listing every data type collected (video, pose/keypoint data, account info, DOB, height, weight, sex, self-reported maxes, push token), where it is stored, and retention (indefinite in V1), to feed the App Store privacy nutrition label and the policy drafts. Account deletion endpoint and Profile action are included only if the developer approves (see Manual Developer Tasks); if approved, deletion removes rows and both R2 objects.

#### Implementation Areas
- Components: fault iconography, accessibility labels, legal links, attestation modal
- APIs: `PATCH /me` fields for acceptance timestamps; optional `DELETE /me`
- Database: migration adding `tos_accepted_at`, `attestation_accepted_at`
- Testing: attestation gate blocks upload until accepted; badge renders icon and text in every state
- Documentation: `docs/privacy-data-inventory.md`, `docs/legal-checklist.md` mapping each spec item to owner and status

#### Estimated LOC
Approximately 300 to 500 lines.

#### Files Expected To Change
`mobile/src/components/StatusBadge.tsx`, `mobile/src/features/results/FaultRow.tsx`, `mobile/app/(auth)/signup.tsx`, `mobile/src/features/capture/AttestationModal.tsx`, `mobile/app/(tabs)/profile.tsx`, `backend/alembic/**`, `backend/liftcam/api/routers/users.py`, `docs/privacy-data-inventory.md`, `docs/legal-checklist.md`.

#### Dependencies
Phases 7, 8, 14.

#### Can AI Complete Independently?
Partially. Code is independent. Policy text, biometric law review (BIPA and similar), COPPA posture beyond the age gate, and the App Store label entries require counsel and the developer.

#### Risk
Medium. Non-engineering risk is high (biometric statutes); engineering risk is low.

#### Complexity
2/5

#### Success Criteria
- [ ] Every `StatusBadge` and `FaultRow` state renders an icon and a text label alongside its color (unit test per state); green/ochre contrast ratio is recorded in `docs/mobile.md`.
- [ ] Signup requires the Terms and Privacy acceptance checkbox, renders both links from config, and stores `tos_accepted_at`; Profile shows the same links.
- [ ] The attestation modal blocks the first upload until accepted, stores `attestation_accepted_at`, and never appears again for that user.
- [ ] The migration adding both timestamp columns upgrades and downgrades cleanly.
- [ ] `docs/privacy-data-inventory.md` lists every column and R2 object that holds personal data, where it lives, and its retention; a test cross-checks the column list against `models.py`.
- [ ] `docs/legal-checklist.md` maps each Legal / Compliance item in `v1.md` to an owner and a status.
- [ ] If account deletion is approved: `DELETE /me` removes the user's rows and both R2 objects per upload, and Profile exposes the action with confirmation. `(developer)` decides.
- [ ] Fault UI reviewed with a color-vision simulator and signed off. `(developer)`

---

### Phase 19: Google and Apple Sign-In

#### Goal
Add Google and Sign in with Apple as additional identities on the existing auth system, completing the Accounts section of `v1.md`.

#### High Level Summary
Backend: `POST /auth/oauth/google` and `POST /auth/oauth/apple` accept a native ID token, verify it against the provider's JWKS, and resolve to a user through the Phase 4 identity lookup. Dedup on verified email across providers; Apple relay emails fall back to `apple_user_id`. If a matching email/password account exists, link only after the user proves ownership by logging in with the password once (V1 has no email verification, so silent auto-merge would allow account takeover); otherwise create the account and collect the remaining required profile fields on first sign-in. Issue the same access and refresh tokens. Mobile: Sign in with Apple (`expo-apple-authentication`) and Google sign-in (`expo-auth-session`) buttons in the slot left in Phase 7, plus the first-sign-in profile completion step. Apple requires Sign in with Apple whenever any third-party login is offered on iOS, so both ship together.

#### Implementation Areas
- APIs: two OAuth endpoints, provider token verification, link flow
- Services: JWKS fetch and cache, dedup and link logic
- Components: provider buttons, profile completion screen
- Testing: recorded JWKS fixtures for both providers, dedup and relay-email tests, link-requires-password test
- Documentation: `docs/api.md` OAuth section, `docs/env.md` client IDs, ADR for link-on-password

#### Estimated LOC
Approximately 500 to 800 lines.

#### Files Expected To Change
`backend/liftcam/api/routers/auth.py`, `backend/liftcam/core/security.py`, `backend/liftcam/core/oauth.py`, `backend/tests/api/test_oauth.py`, `mobile/src/features/auth/*`, `mobile/app/(auth)/*`, `mobile/__tests__/auth/*`, `docs/api.md`, `docs/env.md`, `docs/adr/0004-oauth-link.md`.

#### Dependencies
Phases 4, 7, 16 (dev build on a device), 18 (signup screen final).

#### Can AI Complete Independently?
Mostly. Code and fixture tests are independent. Live sign-in needs developer-provisioned Apple and Google client IDs, bundle identifiers, and an EAS dev build on a physical device.

#### Risk
Medium. Provider verification and the link flow are security surfaces; ordering them last keeps their console setup off the critical path.

#### Complexity
3/5

#### Success Criteria
- [ ] `POST /auth/oauth/google` and `POST /auth/oauth/apple` verify ID tokens against recorded JWKS fixtures; a malformed, expired, or wrong-audience token returns 401.
- [ ] A first-time provider sign-in creates the user and the app collects the remaining required profile fields before landing on Capture.
- [ ] A provider sign-in whose verified email matches an existing email/password account returns a link-required response; the link completes only after a successful password login, after which both identities resolve to one user.
- [ ] An Apple relay email resolves to the existing user through `apple_user_id`.
- [ ] Provider sign-ins receive the same access and refresh tokens as email login, and refresh rotation works for them.
- [ ] Provider buttons render only when their client IDs are configured and are hidden otherwise (unit test for both states).
- [ ] `docs/api.md` documents both endpoints and the link flow; `docs/env.md` lists the client ID variables; `docs/adr/0004-oauth-link.md` records the link-on-password decision.
- [ ] Sign in with Google and with Apple, and the link-with-password flow, confirmed on an EAS dev build on a physical device. `(developer)`

---

## 9. Human Commit Plan

Suggested commits, one or two per phase. The AI never creates these.

- Commit 1: Monorepo scaffold, tooling, local Postgres, health endpoints (Phase 1)
- Commit 2: Feasibility spike scripts and findings (Phase 2)
- Commit 3: Database models, migrations, ER diagram update, ADR (Phase 3)
- Commit 4: Email/password auth, tokens, profile API (Phase 4)
- Commit 5: Upload handshake, History, presign API (Phase 5)
- Commit 6: Worker runtime with stubbed pipeline, direct push, diagram updates (Phase 6)
- Commit 7: Mobile theme, API client, email auth and Profile (Phase 7)
- Commit 8: Mobile capture and multipart upload (Phase 8)
- Commit 9: Mobile History, polling, retry (Phase 9)
- Commit 10: CV presence, pose, bar tracking, subject lock (Phase 10)
- Commit 11: CV angle, calibration, segmentation, rep counting (Phase 11)
- Commit 12: CV faults, VBT, force/work, confidence, series (Phase 12)
- Commit 13: Overlay render and result commit, remove stubs (Phase 13)
- Commit 14: Mobile results page and share (Phase 14)
- Commit 15: Benchmarking (Phase 15)
- Commit 16: Deployment artifacts and CI (Phase 16)
- Commit 17: Validation fixtures and ground-truth report (Phase 17)
- Commit 18: Compliance engineering and data inventory (Phase 18)
- Commit 19: Google and Apple sign-in (Phase 19)

Also recommended before Commit 1: commit the current `v1.md` edits and `diagrams/` so the plan's inputs are versioned, and decide whether `copy.md` should be removed (it duplicates `v1.md`).

---

## 10. Manual Developer Tasks

Every item here is something the agent cannot do: it needs a browser login to a third-party console, a paid account, a physical phone, a product or legal decision, or real-world footage. Anything the agent can do from the terminal (generate a random key, run Docker, run tests, write docs) is deliberately not listed.

### Before Phase 2
- Record three deadlift clips on your phone: one side view, one front view, one roughly 45 degree oblique. Any weight, standard plates. Put them where `docs/spikes.md` says.
- Install Expo Go on one iPhone and one Android (borrow one if needed) and run the chunk-read spike; paste the logged numbers into `docs/spikes.md`.
- Read `docs/spikes.md` and answer both go/no-go questions. If plate detection is weak at front/oblique, decide whether the YOLOv8-nano fallback is built in Phase 10 or after Phase 17 (fallback means you also label a few hundred frames later).

### Before Phase 3
- Decide push token cardinality: one token per user (ER diagram, plan default) or one per device.
- Confirm the pre-record screen is a static framing guide with no on-device detection (plan default).

### Before Phase 5 live smoke test (code can proceed without it)
- Create a Cloudflare account and an R2 bucket. Set it private. Add a lifecycle rule: abort incomplete multipart uploads after 1 day. Create an R2 API token and put its key/secret and the account endpoint in your local `.env`.

### During Phases 8, 9, 14 (device checks, Expo Go is enough)
- Record and upload from the app on a real phone; background it mid-upload, relaunch, confirm it resumes.
- Confirm camera and photo-library permission prompts, the 45 s reject, and the results share sheet delivering the overlay file.

### Before Phase 15
- Choose a population strength-standards data source for deadlift by sex and bodyweight, confirm its license allows redistribution in an app, and tell the agent the source URL and license so it can be recorded in `docs/benchmarking.md`. Do not let the agent commit a table without this.

### Phase 16
- Create a Neon project. Copy the pooled and direct connection strings into the host's environment.
- Pick the host (Hetzner, DigitalOcean, Fly, or Render; not AWS). Create the account, the machine or app, and DNS.
- Set every environment variable from `docs/env.md` in the host. The agent can generate the JWT signing key value for you; pasting it into the host is yours.
- Create an Expo account and EAS project; put the project ID and bundle identifiers in `app.json` / `eas.json` when prompted.
- Buy the Apple Developer membership ($99/yr). Needed for the first EAS iOS device build, push on device, TestFlight, and Phase 19.
- Create the Google Play developer account ($25 one-time) when you want an Android internal test track.
- Run the first deploy following `docs/deployment.md`; report anything that differs from the doc so the agent can fix it.
- Verify push arrives on a device and tapping it opens the correct upload.

### Phase 17
- Record the ground-truth set: known bar, known plates, known camera position. Measure bar path extent with a tape, time reps with frame counts or a stopwatch, and write manual rep and lockout calls per clip. Fill in `manifest.yaml` values the agent cannot know.
- Review the ground-truth report and approve or reject each threshold change it proposes. Decide which faults and estimates ship as `unavailable` for MVP.

### Phase 18
- Decide whether in-app account deletion ships in V1 (App Store guideline 5.1.1(v) makes it effectively required; plan recommends yes).
- Write or commission: Privacy Policy, Terms of Service, bystander attestation wording. Host them and put the URLs in config.
- Get a legal opinion on whether pose/keypoint data is biometric data under BIPA and similar statutes, and on COPPA posture beyond the age gate.
- Fill in the App Store privacy nutrition label and the Play Data Safety form from `docs/privacy-data-inventory.md`.
- Look at the fault UI with a color-vision simulator and sign off.

### Phase 19
- In the Apple Developer portal: enable Sign in with Apple on the app ID, create the Services ID and key, and give the agent the client ID (not the key file contents; put those in host env).
- In Google Cloud Console: create OAuth client IDs for iOS and Android, add the bundle ID / package name and SHA-1, and give the agent the client IDs.
- Sign in with both providers on a dev build and confirm the link-with-password flow.

### Every phase
- Review the diff, stage, commit, push, and open PRs. The agent never runs Git write commands.

---

## 11. Testing Checklist

### Existing Tests
None exist. Nothing to update.

### New Tests

Unit:
- Status transition guards; badge mapping; failure code and stage mapping table.
- JWT sign/verify, refresh rotation, age gate. Provider verification, dedup by email, Apple relay fallback, link-requires-password (Phase 19).
- Presign request shapes; part count and size validation; 45 s duration rejection at the API; trim-to-45 s at probe.
- Part splitter, per-part retry, resume from persisted upload state (mobile).
- Polling hook start/stop; single-flight token refresh (mobile).
- CV pure functions on synthetic data: bar-line anchoring, temporal consistency, angle from bar length and plate ratio, calibration cross-check, segmenter, peak detection with displacement floor, lockout gate, each fault detector, occlusion interpolation, velocity, force, confidence combiner, series builder, display smoothing.
- Benchmark interpolation and boundaries.

Integration:
- Claim concurrency with two sessions (`SKIP LOCKED`).
- Worker end to end on fixtures: each `failure_code`, corrupt file, over-length trim, timeout, crash, happy path to `ready` with two R2 objects (R2 mocked or dev bucket), push client called once per terminal status against a mocked Expo endpoint.
- API endpoints with a real Postgres: auth, uploads, media presign, ownership isolation.
- Migration up and down on a fresh database.

End to end (developer-run on device):
- Signup, record, confirm, upload, History shows processing, push arrives, results play and seek, share sheet receives overlay only.
- Background mid-upload, relaunch, upload resumes.
- Phase 19: sign in with Google and Apple, link to an existing email account via password.

### Edge Cases
- Invalid inputs: over 45 s at the API, zero reps, negative weight, unsupported unit, malformed ID token, under-13 DOB.
- Failure states: R2 complete fails after all parts uploaded; worker dies after overlay upload before commit; presigned URL expires mid-playback; push token invalid or missing (job still completes).
- Permission issues: camera or photo library denied; notifications denied (poll still reflects truth); one user requesting another's upload.
- Boundary conditions: exactly 45 s; 30 fps and 720p exactly at the floor; single-rep clip; lifter leaves frame between sets; two bars in frame; spotter enters mid-set; portrait video with rotation metadata; 1080p source downscaled to 720p overlay.

### Regression Testing
Each CV phase reruns the full fixture suite from Phase 17 (once it exists) so threshold changes in one stage are caught downstream. API contract tests protect the mobile client from payload drift.

### Performance Testing
Measure worker wall time for a 45 s 1080p30 clip on the target host; must finish inside the job timeout with headroom. Measure History list response time with several hundred uploads per user (index check). Measure mobile part upload throughput on cellular.

### Security Testing
Ownership checks on every upload route; presigned URLs are short-lived and never persisted; password hashes use argon2; rotated refresh tokens are rejected; no internal failure fields leak to clients; secrets absent from repo (CI grep); Phase 19 link flow requires password proof before merging identities.

---

## 12. Documentation Checklist

- README: project overview, repo layout, quick start for backend and mobile, link to `v1.md` and `docs/`.
- `docs/setup.md`: local development for both stacks, Docker Postgres, ffmpeg requirement.
- `docs/spikes.md`: Phase 2 questions, method, numbers, go/no-go, implied changes.
- `docs/env.md`: every environment variable for API, worker, and mobile, with which process reads it.
- `docs/api.md`: endpoints, request/response schemas, status and code enums, faults and series JSONB shapes, OAuth (Phase 19).
- `docs/architecture.md`: two-process design, Postgres-as-queue, R2 objects, presign policy, worker-direct push, links to the five Mermaid diagrams.
- `docs/worker.md`: stage order, failure mapping, timeout and reaper, trim rule, render pipeline and 720p cap.
- `docs/cv.md`: detection approach, spike findings, angle and calibration methods, thresholds table marked provisional, known limits (mirror ambiguity, no hitch detection, no spine scoring).
- `docs/mobile.md`: routes, theme tokens, upload resume, polling, results.
- `docs/deployment.md`: image, processes, Neon and R2 setup, EAS profiles.
- `docs/validation.md`: fixture manifest, ground-truth procedure, acceptance bar.
- `docs/benchmarking.md`: standards data provenance and license.
- `docs/privacy-data-inventory.md` and `docs/legal-checklist.md`.
- ADRs in `docs/adr/`: schema additions beyond the ER diagram (including `reps.series`), worker subprocess isolation and direct push, `expo-video` substitution, OAuth link-on-password.
- Update `diagrams/er-data-model.md` in Phase 3 and `diagrams/sequence-process-job.md` plus `diagrams/component.md` in Phase 6 so the diagrams match the build.
- Remove stale comments and any references to stubs when Phase 13 deletes them; delete `mobile/spike/` in Phase 8.

---

## 13. Migration Notes

Migration Required:
Yes

- Database migrations: Phase 3 creates all tables including `reps.series` and `refresh_tokens`; Phase 18 adds acceptance timestamps. Phase 19 needs no schema change (provider columns exist from Phase 3). All are additive. Alembic is the single mechanism.
- API changes: none are breaking during V1 because there are no prior clients. Contract tests guard the mobile client from Phase 9 onward.
- Configuration changes: environment variables are introduced per phase and recorded in `docs/env.md` in the same phase.
- Rollout strategy: single environment in V1. Deploy migrates then restarts API and worker. Worker drains the current job before restart (SIGTERM handling from Phase 6).
- Rollback strategy: redeploy previous image; Alembic downgrade scripts are written and tested for every migration. Rows in `processing` at rollback are reaped to `failed/timeout` and are user-retryable.
- Compatibility concerns: none for external consumers. Internal concern is the worker and API sharing one models module; they must be deployed from the same image tag.

---

## 14. Major Caveats

- Breaking changes: none externally. Internally, changing `uploads` or `reps` shape after Phase 3 is expensive; review the Phase 3 ADR carefully.
- Hough plate detection is side-view biased. Plates are circles only from the side; front and oblique views give ellipses, and that is exactly where the angle estimator needs plate edges most. The YOLOv8-nano fallback may be a V1 requirement rather than insurance. Phase 2 answers this before Phase 10 is built.
- Scalability: single worker and Postgres-as-queue are correct for V1 volume. Do not add a second worker or a broker until the Phase 17 report shows render time is the bottleneck. Indefinite retention grows R2 cost linearly; known and deferred by the spec.
- Security: JWT and refresh token handling and presign TTLs are the sensitive surfaces; Phase 19 adds provider verification and the link flow. Body pose data may be regulated biometric data in some jurisdictions; this is a legal determination, not an engineering one.
- Performance: MediaPipe on CPU for a 45 s clip at full frame rate plus rendering may approach the job timeout on a small VPS; frame stride for pose and the 720p render cap are the levers, both configurable.
- Third party limitations: Expo Push rate limit (600/s) is far above V1 needs. `pip` OpenCV codec support requires system `ffmpeg`. Chunked file reads in Expo are spiked in Phase 2 before anything depends on them.
- Deployment risks: MediaPipe wheel availability for the container base image; memory on the smallest instances; missing `ffmpeg` in the image.
- Rollback concerns: additive migrations only, so downgrade is safe; the only state to reconcile is `processing` rows, handled by the reaper.
- Spec deviations recorded in ADRs: operational schema columns and `reps.series`, `refresh_tokens` table, subprocess job isolation, worker-direct push (diagrams updated), `expo-video` in place of `expo-av`, OAuth built last with link-on-password.
- OAuth is the largest human-setup cost in V1 (Apple portal, Google Cloud console, bundle IDs, device dev build). Placing it last keeps it off the critical path; it remains required before public iOS release because Apple mandates Sign in with Apple whenever any third-party login is offered.
- App Store: in-app account deletion is likely required for submission and is not in the spec.

---

## 15. Confidence and Unknowns

Confidence:
70% for the full V1 spec, about 80% for the MVP cut (Phases 1 through 14, 16, 17, 18).

Backend, data model, and API phases are high confidence (the spec and diagrams are precise). Mobile capture/upload is medium confidence pending the Phase 2 chunk-read result. CV phases are the lowest confidence because every threshold is provisional and classical plate detection against real gym footage is unproven; the spec anticipates this with a fallback detector. The Phase 2 CV spike is the single biggest input to this number: a clean result at front and oblique angles moves full-spec confidence toward 80%; a poor one means the fallback detector and its labeling effort join the V1 critical path.

Unknowns:

- Phase 2 result: reliability of Hough-based plate detection at front and oblique angles; whether the YOLOv8-nano fallback becomes necessary.
- Phase 2 result: feasibility and memory cost of byte-range reads for multipart parts on iOS and Android.
- CPU wall time for pose plus 720p render on the chosen host; whether frame stride is needed to stay under the timeout.
- HEVC decode support in the worker image and the cost of the H.264 normalization step.
- Population strength standards source and license.
- Push token cardinality and account deletion decisions.
- Whether the pre-record live check may include any on-device detection.
- Legal status of pose/keypoint data under biometric statutes; outcome of counsel review.
- Availability and timing of ground-truth footage for acceptance.
