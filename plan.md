# LiftCam V1 Implementation Plan (Deadlift Only)

Source spec: `v1.md` (read-only reference). Scope covers every section of `v1.md` from Scope through Legal / Compliance. Everything under "Deferred to V2+" is out of scope and is not planned here.

This plan is an execution roadmap for an autonomous coding agent. It contains no implementation code. All Git write operations belong to the human developer.

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
- Auth: FastAPI-issued JWT access + refresh tokens; email/password and Google/Apple verify-then-issue. No hosted auth.
- Push: Expo Push only, one ping per finished job, requested after the first completed upload.
- Queue: Postgres only. No Redis, Celery, SQS, websockets.
- Client status: poll `GET /uploads/:id` every 2 to 3 seconds while in flight.
- Hosting: VPS or small PaaS chosen at first deploy. Not AWS.

### Relevant Files and Directories

| Path | Why it matters |
|------|----------------|
| `v1.md` | Source of every product and architecture decision. Every phase below cites it. |
| `diagrams/er-data-model.md` | Column-level schema for `users`, `uploads`, `segments`, `reps`. Phase 2 implements this directly. |
| `diagrams/state-job.md` | The `uploads.status` machine and legal transitions. Drives API guards and worker writes. |
| `diagrams/sequence-process-job.md` | Multipart handshake, claim, stage outcomes, push path (worker asks API, API sends to Expo). |
| `diagrams/activity-capture-upload.md` | Record vs camera roll, confirm/retake, shared multipart path. Drives the mobile capture flow. |
| `diagrams/component.md` | Process boundaries: app talks to API and R2 directly; worker talks to Postgres and R2; only API talks to Expo Push. |
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

1. Push token cardinality. `v1.md` says "store an Expo push token per user/device"; the ER diagram has a single `users.expo_push_token`. The plan follows the ER diagram (one token per user, last device wins). Multi-device push is a V2 concern. Flagged so the developer can override before Phase 2.
2. Worker to Push path. The sequence diagram routes push through the API (`W -> API -> Expo Push`); the component diagram also shows only the API talking to Expo Push. The plan follows this with a small internal endpoint on the API protected by a shared service token. A simpler alternative (worker calls Expo Push directly from shared `core/push.py`) is noted in the ADR for Phase 5; the diagram wins unless the developer chooses otherwise.
3. Pre-record "lightweight live check" (Capture section) says "angle detected + basic bar/plate/lifter presence." Any live detection needs on-device inference, which the same section forbids for the full overlay and the Architecture section forbids in general (thin client, all CV server-side). The plan implements the pre-record screen as a static framing guide plus the side-view tip, with no on-device inference. Live presence detection is listed under Missing Context.
4. Playback library. `v1.md` names `expo-av`. Expo has deprecated `expo-av`'s `Video` in favor of `expo-video`. The plan uses `expo-video` for playback and `expo-camera` for capture, and records the substitution in the Phase 6 ADR. Functionally identical for the spec's needs (play, seek, frame-accurate scrub).
5. ER diagram lacks operational columns needed by the spec: `created_at` (History sort order), `claimed_at` (timeout detection), and probe metadata (`duration_s`, `fps`, `width`, `height`) needed for low-confidence gating. Also lacks a place to persist refresh tokens for revocation, and per-segment camera angle / calibration values needed for per-fault confidence gating. Phase 2 adds these; Phase 2 also updates `diagrams/er-data-model.md` so the diagram stays truthful.
6. Video codecs. Phone uploads are usually HEVC in `.mov`. `pip` OpenCV builds may not decode HEVC reliably and cannot write H.264. The worker host needs system `ffmpeg`; the probe stage normalizes the original to an H.264 working copy on local disk (not stored in R2, so the two-object rule holds) and the render stage encodes the overlay with `ffmpeg` (`faststart`) for mobile playback.
7. Multipart chunking on device. Reading byte ranges of a local video for S3 part PUTs without a native module is the main mobile technical risk. The plan uses `expo-file-system`'s file byte access with a fixed part size (8 to 16 MB). If chunked reads prove impractical on a target OS, that is a spec-level decision (spec forbids single-PUT full restart) and is escalated, not silently changed.

### Missing Context

- Which VPS/PaaS hosts API + worker (spec: decide at first deploy). Affects Phase 15 only.
- Population strength standards data source and its license (Benchmarking). Required for Phase 14.
- Whether the pre-record "live check" is meant to include any on-device detection (see Conflict 3).
- Apple Developer and Google Play accounts, bundle identifiers, Sign in with Apple and Google OAuth client IDs.
- Whether account deletion must ship in V1. App Store Review Guideline 5.1.1(v) requires in-app account deletion for apps with account creation. `v1.md` does not mention it. Listed under Major Caveats and Manual Developer Tasks.
- Ground-truth footage availability (Validation/QA). CV phases can be built against a small provisional clip set, but acceptance requires the developer's real uploads.
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
- Modified lines: under 300 (diagram updates, README growth across phases)
- Deleted lines: 0 (nothing to delete; `copy.md` is left alone, see Manual Developer Tasks)

---

## 4. Assumptions

- The developer will provision Neon, R2, Expo/EAS, Apple, and Google accounts and supply credentials via environment variables. The agent never creates or stores secrets.
- Single worker process in V1. The claim query and timeout reaper are written to stay correct with multiple workers, but only one runs.
- Python 3.12, Node 20 LTS, current Expo SDK with `expo-router`. Versions are pinned in Phase 1.
- Tests that need Postgres run against a local Docker Postgres or a Neon branch. SQLite is never used because `SKIP LOCKED` and JSONB must be exercised for real.
- System `ffmpeg` is available on the worker host and in the worker container.
- Google/Apple sign-in is verified server-side from ID tokens the mobile app obtains natively; no OAuth redirect flow runs on the backend.
- Presigned GET TTL is 10 minutes; presigned part PUT TTL is 60 minutes; multipart uploads that never complete are cleaned by an R2 lifecycle rule (abort incomplete multipart after 1 day), configured by the developer.
- Per-job worker timeout is 10 minutes (provisional, like every threshold in the spec).
- Weight and reps entered by the user are required at upload time; units (`lb`/`kg`) are stored with the value.
- Fault codes for V1 are exactly: `bar_drift`, `early_hip_rise`, `incomplete_lockout`, `knee_valgus`. Each is reported as `pass | flagged | unavailable` with a confidence value.

---

## 5. Existing Code To Reuse

There is no existing code. Reuse inside the plan:

- `backend/liftcam/core/` is the single home for settings, SQLAlchemy models, R2 client, Expo Push client, JWT helpers. API and worker import it; nothing is duplicated between the two processes.
- One `Upload` response schema serves History list items, the status poll, and the results page; the results payload is nested and only populated when `status = ready`.
- The mobile `api/` client wraps `fetch` with JWT attach, single-flight refresh, and typed endpoints; every screen uses it.
- One `StatusBadge` component maps the six statuses to the four UI labels (`processing`, `ready`, `failed`, `no lift`).
- One `useUploadPolling` hook implements the 2 to 3 second poll and stop condition, used by both History and the upload detail screen.
- Worker stages share a small set of typed dataclasses (`FrameMeta`, `PoseTrack`, `BarTrack`, `Segment`, `Rep`) defined once in `worker/types.py`.

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
  src/features/auth           signup, login, oauth
/backend                      one Python package, two entrypoints
  pyproject.toml
  alembic/                    migrations
  liftcam/core                settings, db, models, r2, push, security
  liftcam/api                 FastAPI app, routers: auth, users, uploads, internal
  liftcam/worker              claim loop, run_job subprocess, stages/, cv/
  tests/                      api, worker, fixtures/clips
/diagrams                     existing Mermaid; ER diagram updated in Phase 2
/docs                         setup, env, architecture, deployment, adr/
/infra                        Dockerfiles, process definitions, eas.json lives in /mobile
README.md
.gitignore
```

---

## 7. AI Execution Order

Execute the phases below in order. Each phase is sized for one agent session, ends at a stable and reviewable state, and requires no Git action between phases. Backend contracts are built before mobile screens that consume them. CV phases come after the mobile shell so an end-to-end flow (upload, queue, stubbed result, poll, push) is testable early, and the results UI is built last against real rep data.

1. Repository scaffold and tooling
2. Database schema and migrations
3. Auth and profile API
4. Upload handshake, History, and media presign API
5. Worker runtime: claim, stage runner, failure persistence, push
6. Mobile foundation: theme, API client, auth screens, Profile tab
7. Mobile capture and upload flow
8. Mobile History tab, polling, status states, retry
9. CV stage: presence, pose, bar and plate detection, subject lock
10. CV stage: camera angle, calibration, segmentation, rep counting
11. CV stage: form faults, VBT, force/work, confidence gating
12. Overlay render and result commit
13. Mobile results page (Overview / Video / Graphs) and share
14. Benchmarking
15. Deployment and operations
16. Validation fixture suite and ground truth
17. Pre-launch compliance engineering

---

## 8. Sequential Implementation Phases

Standard AI Completion Criteria apply to every phase and are not repeated in full: implementation complete, tests pass, type checking passes (`mypy`, `tsc`), linting passes (`ruff`, `eslint`), documentation updated, temporary code removed, repository stable (both processes start, app builds). Phase-specific criteria are listed under each phase.

---

### Phase 1: Repository Scaffold and Tooling

#### Goal
Create the monorepo skeleton, toolchains, and runnable no-op entrypoints for API, worker, and mobile so every later phase has a place to land and a green baseline.

#### High Level Summary
Set up `backend/` as one Python project with `liftcam.core`, `liftcam.api` (FastAPI app with `/health`), and `liftcam.worker` (loop that logs and sleeps). Set up `mobile/` as an Expo app with `expo-router` and three empty tabs (Capture, History, Profile). Add lint, format, type check, and test runners for both stacks, `.env.example` files, `.gitignore`, and a root README that points to `docs/`. No business logic.

#### Implementation Areas
- Build tooling: `pyproject.toml` (ruff, mypy, pytest, uvicorn), `package.json`, `tsconfig.json`, ESLint/Prettier
- Routes: `/health` only
- Services: settings loader via pydantic-settings reading env
- Documentation: README, `docs/setup.md`, `docs/env.md`

#### Estimated LOC
Approximately 400 to 700 lines.

#### Files Expected To Change
`backend/pyproject.toml`, `backend/liftcam/core/settings.py`, `backend/liftcam/api/main.py`, `backend/liftcam/worker/main.py`, `backend/tests/test_health.py`, `mobile/app/_layout.tsx`, `mobile/app/(tabs)/*`, `mobile/package.json`, `mobile/tsconfig.json`, `mobile/app.json`, `mobile/eas.json`, `.gitignore`, `README.md`, `docs/setup.md`, `docs/env.md`, `.env.example` files.

#### Dependencies
None.

#### Can AI Complete Independently?
Yes. Expo project identifiers (bundle ID, EAS project ID) can be placeholders; the developer fills them in Phase 15.

#### Risk
Low. Standard scaffolding.

#### Complexity
1/5

#### AI Completion Criteria
Standard criteria, plus: `uvicorn liftcam.api.main:app` serves `/health`; `python -m liftcam.worker.main` runs and exits cleanly on SIGINT; `npx expo start` renders three tabs; `ruff`, `mypy`, `pytest`, `tsc`, `eslint` all pass.

---

### Phase 2: Database Schema and Migrations

#### Goal
Implement the ER diagram as SQLAlchemy models plus Alembic migrations, including the operational columns the spec needs but the diagram omits.

#### High Level Summary
Create `users`, `uploads`, `segments`, `reps`, and `refresh_tokens`. `uploads` carries status, both R2 keys, multipart id, user weight and unit, user reps, failure fields, `created_at`, `claimed_at`, `finished_at`, and probe metadata. `segments` adds `camera_angle_deg`, `angle_confidence`, `px_per_m`, `calibration_confidence`. `reps` stores times, velocity, `faults` JSONB, confidence, plus `force_estimate`, `work_estimate`, and internal `lockout_ratio`. Add indexes for History (`uploads(user_id, created_at desc)`) and the claim query (partial index on `uploads(status) where status = 'queued'`). Add unique constraints on `users.email` and `users.username`, and `users.apple_user_id` nullable unique. `tier` defaults to `free`. Provide an async engine for the API (pooled URL) and a sync engine for the worker (direct URL). Update `diagrams/er-data-model.md` to reflect added columns and the new table.

#### Implementation Areas
- Database: models, migrations, indexes, enums as constrained strings
- Models: Pydantic read schemas mirroring the tables
- Testing: migration up/down against Postgres, constraint tests
- Documentation: ER diagram update, `docs/architecture.md` data model section, ADR for `refresh_tokens` and operational columns

#### Estimated LOC
Approximately 500 to 800 lines.

#### Files Expected To Change
`backend/liftcam/core/db.py`, `backend/liftcam/core/models.py`, `backend/liftcam/core/schemas.py`, `backend/alembic/**`, `backend/tests/test_models.py`, `backend/tests/conftest.py` (Postgres fixture), `diagrams/er-data-model.md`, `docs/architecture.md`, `docs/adr/0001-schema-additions.md`.

#### Dependencies
Phase 1.

#### Can AI Complete Independently?
Yes, given a reachable Postgres for tests. Column additions beyond the ER diagram are listed in the ADR for developer review.

#### Risk
Medium. Schema decisions here are the hardest to change later (spec: "presentation is far easier to revise later than the pipeline/data-model decisions").

#### Complexity
2/5

#### AI Completion Criteria
Standard criteria, plus: `alembic upgrade head` and `downgrade base` both succeed on a fresh database; a `queued` row can be claimed with `FOR UPDATE SKIP LOCKED` in a test with two concurrent sessions and only one wins.

---

### Phase 3: Auth and Profile API

#### Goal
Implement signup, login, OAuth verification, token issuance and refresh, and profile read/update per the Accounts section.

#### High Level Summary
Email/password signup with argon2 hashing collects username, optional profile picture (default URL if skipped), DOB, height, weight, sex, and SBD maxes with units. Enforce age 13+ from DOB and reject under-13 at creation. Google and Apple sign-in accept a native ID token, verify it against provider JWKS, dedupe on verified email across providers, and fall back to `apple_user_id` for Apple relay emails. Issue a short-lived JWT access token and an opaque refresh token stored hashed in `refresh_tokens` with rotation on use. Provide `GET/PATCH /me` (all signup fields plus optional `favorite_lift`), `POST /me/push-token`, and logout (revoke refresh token). Single `lifter` role; no role column beyond `tier`.

#### Implementation Areas
- APIs: `/auth/signup`, `/auth/login`, `/auth/oauth/google`, `/auth/oauth/apple`, `/auth/refresh`, `/auth/logout`, `/me`, `/me/push-token`
- Services: password hashing, JWT sign/verify, provider token verification, dedup logic
- Middleware: bearer auth dependency
- Testing: unit tests for dedup and age gate, integration tests for each endpoint, refresh rotation and reuse detection
- Documentation: `docs/api.md` auth section, env vars for JWT secret and OAuth client IDs

#### Estimated LOC
Approximately 700 to 1,000 lines.

#### Files Expected To Change
`backend/liftcam/core/security.py`, `backend/liftcam/api/deps.py`, `backend/liftcam/api/routers/auth.py`, `backend/liftcam/api/routers/users.py`, `backend/liftcam/api/schemas/*`, `backend/tests/api/test_auth.py`, `backend/tests/api/test_users.py`, `docs/api.md`, `docs/env.md`.

#### Dependencies
Phase 2.

#### Can AI Complete Independently?
Yes. Provider verification is tested with recorded JWKS fixtures; live OAuth requires developer-supplied client IDs and is verified in Phase 6.

#### Risk
Medium. Auth bugs are security bugs. Dedup-by-email plus Apple relay handling has edge cases.

#### Complexity
3/5

#### AI Completion Criteria
Standard criteria, plus: an under-13 DOB is rejected with a clear error; signing up with Google then logging in with email for the same verified address resolves to one user; a reused rotated refresh token is rejected and revokes the family.

---

### Phase 4: Upload Handshake, History, and Media Presign API

#### Goal
Implement the multipart upload handshake, the status/History endpoints, retry, and presigned media access exactly as the sequence and state diagrams describe.

#### High Level Summary
`POST /uploads` validates weight, unit, reps, declared duration (reject over 45 s), file size, and part count; inserts an `uploading` row; creates an R2 multipart upload; stores its id; returns presigned part PUT URLs. `POST /uploads/:id/complete` accepts part ETags, completes the multipart on R2, and transitions the row to `queued`. `GET /uploads` returns the user's History newest first with the badge-mapped status. `GET /uploads/:id` returns status and, when `ready`, nested segments and reps. `POST /uploads/:id/retry` is allowed only from `failed`, clears failure fields, and sets `queued`. `GET /uploads/:id/media?kind=overlay|original` returns a fresh 10 minute presigned GET. Internal failure fields are never serialized to clients. The API never reads or writes video bytes.

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
Phases 2 and 3.

#### Can AI Complete Independently?
Yes. R2 is mocked in tests; a live smoke test against a dev bucket is a developer step.

#### Risk
Medium. Presign correctness against R2 (region `auto`, path-style, checksum headers) is a common integration snag.

#### Complexity
3/5

#### AI Completion Criteria
Standard criteria, plus: illegal transitions (`ready -> queued`, `processing -> retry`) return 409; `failed_stage`, `failure_code`, and `failure_message` never appear in any response body; History ordering is by `created_at desc`.

---

### Phase 5: Worker Runtime: Claim, Stage Runner, Failure Persistence, Push

#### Goal
Build the worker process around the job lifecycle with a stubbed CV pipeline so the full async loop works before any CV exists.

#### High Level Summary
The worker loop claims one `queued` row with `FOR UPDATE SKIP LOCKED` on the direct Neon connection, sets `processing` and `claimed_at`, and runs the job in a child process with a hard timeout so crashes and hangs are isolated. The stage runner executes the ordered stage list, maps any exception or timeout to `failed` with `failed_stage`, `failure_code`, and a short internal message, and maps detection misses to `no_lift` with `failure_code` only. On startup it reaps rows stuck in `processing` past the timeout into `failed/timeout`. Stages implemented for real in this phase: `claim`, `download` (original from R2 to a temp dir), `probe` (ffprobe: duration, fps, resolution, rotation; reject corrupt), `overlay_upload`, and the final commit. CV stages are stubs that return fixed results so the pipeline reaches `ready`. After any terminal status the worker calls the API's internal push endpoint; the API sends one Expo Push message to the user's stored token. Structured JSON logs keyed by `upload_id` and stage.

#### Implementation Areas
- Services: claim loop, subprocess job runner, stage runner, reaper, ffprobe wrapper, temp dir lifecycle
- APIs: `POST /internal/push` guarded by a service token
- Database: status writes, failure field writes, `finished_at`
- Testing: claim concurrency test, stage failure mapping table test, timeout test with a sleeping stub stage, reaper test, push endpoint auth test
- Documentation: `docs/worker.md` (stages, codes, timeout), ADR for subprocess isolation and API-routed push

#### Estimated LOC
Approximately 700 to 1,000 lines.

#### Files Expected To Change
`backend/liftcam/worker/main.py`, `backend/liftcam/worker/run_job.py`, `backend/liftcam/worker/runner.py`, `backend/liftcam/worker/stages/{download,probe,overlay_upload,commit}.py`, `backend/liftcam/worker/stages/stubs.py` (removed in Phase 12), `backend/liftcam/worker/types.py`, `backend/liftcam/core/push.py`, `backend/liftcam/api/routers/internal.py`, `backend/tests/worker/*`, `docs/worker.md`, `docs/adr/0002-worker-runtime.md`.

#### Dependencies
Phases 2 and 4.

#### Can AI Complete Independently?
Yes.

#### Risk
Medium. Correct handling of crash, timeout, and partial writes determines whether `failed` rows are ever left inconsistent.

#### Complexity
3/5

#### AI Completion Criteria
Standard criteria, plus: killing the child process mid-job yields `failed` with `failure_code = crash`; a stage exceeding the timeout yields `failed/timeout`; a corrupt fixture file yields `failed/probe/corrupt`; no `segments` or `reps` rows exist for any non-`ready` upload.

---

### Phase 6: Mobile Foundation: Theme, API Client, Auth Screens, Profile Tab

#### Goal
Establish the visual system, typed API client with token handling, and the full auth and profile experience.

#### High Level Summary
Implement theme tokens from Branding: cream background, near-black primary text, muted gray secondary text, forest green primary accent, ochre warning tone, one sans family with tabular figures for numbers, rounded corners with thin borders, no shadows, light mode only. Build the API client with secure token storage (`expo-secure-store`), automatic access token attach, and single-flight refresh on 401. Build signup (all required fields, unit toggles, DOB picker with 13+ validation mirrored client-side), login, Sign in with Apple (`expo-apple-authentication`), Google sign-in (`expo-auth-session`), and the Profile tab (view and edit all fields, optional favorite lift, logout). New users land on Capture after signup, with a brief first-time overlay explaining the framing guide and the async notify flow.

#### Implementation Areas
- Components: theme provider, text and number primitives, form inputs, buttons, skeleton placeholder
- State management: auth session context only; no global store
- Routes: `(auth)/signup`, `(auth)/login`, `(tabs)/profile`
- Testing: unit tests for the API client refresh path and form validation
- Documentation: `docs/mobile.md` (structure, theme tokens), ADR for `expo-video`

#### Estimated LOC
Approximately 1,200 to 1,700 lines.

#### Files Expected To Change
`mobile/src/theme/*`, `mobile/src/api/*`, `mobile/src/features/auth/*`, `mobile/app/(auth)/*`, `mobile/app/(tabs)/profile.tsx`, `mobile/app/_layout.tsx` (auth gate), `mobile/src/components/*`, `mobile/__tests__/*`, `docs/mobile.md`, `docs/adr/0003-expo-video.md`.

#### Dependencies
Phase 3 (auth API). Phase 1 shell.

#### Can AI Complete Independently?
Mostly. Live Apple/Google sign-in needs developer-provisioned client IDs and an EAS dev build on a physical device; the agent wires the code and documents the setup.

#### Risk
Medium. OAuth on device and token refresh races are the usual sources of bugs.

#### Complexity
3/5

#### AI Completion Criteria
Standard criteria, plus: expired access token triggers exactly one refresh even with concurrent requests; signup rejects under-13 client-side and surfaces the server error if bypassed; numeric stat text renders with tabular figures.

---

### Phase 7: Mobile Capture and Upload Flow

#### Goal
Deliver both primary capture paths and the shared multipart upload path per the activity diagram.

#### High Level Summary
Capture tab offers Record and Camera Roll with equal weight. Pre-record screen shows a static framing guide and the side-view tip ("film from the side for the most accurate bar path, we'll still track most angles"); no live inference. Recording is plain, no overlay, capped at 45 s. Camera roll picks a video and rejects clips over 45 s. Both paths land on a "dumb" confirm/retake screen with playback and a weight, unit, and reps form. Upload creates the row via `POST /uploads`, reads the file in fixed-size parts, PUTs each part to its presigned URL with per-part retry, tracks ETags, calls complete, then navigates to History where the item appears as `processing`. Upload state (upload id, multipart id, completed parts) is persisted locally so reopening the app after backgrounding resumes the same multipart. Foreground only. After the user's first upload reaches a terminal state, prompt for push permission and register the Expo token.

#### Implementation Areas
- Components: framing guide, confirm/retake, upload progress
- Services: part reader, uploader with retry and resume, local upload state persistence
- Routes: `(tabs)/capture`, `capture/record`, `capture/confirm`
- Testing: unit tests for part splitting, retry, resume from persisted state, duration validation
- Documentation: `docs/mobile.md` capture section, upload resume behavior

#### Estimated LOC
Approximately 900 to 1,300 lines.

#### Files Expected To Change
`mobile/src/features/capture/*`, `mobile/src/features/upload/*`, `mobile/app/(tabs)/capture.tsx`, `mobile/app/capture/*`, `mobile/src/notifications/*`, `mobile/__tests__/upload/*`, `docs/mobile.md`.

#### Dependencies
Phases 4 and 6.

#### Can AI Complete Independently?
Yes for code. Physical device testing of camera and large file reads is a developer step. If byte-range reads are not achievable on a target OS with the chosen Expo APIs, stop and escalate (see Conflict 7).

#### Risk
High. Chunked reads of large local videos and multipart correctness on device are the biggest mobile unknown.

#### Complexity
4/5

#### AI Completion Criteria
Standard criteria, plus: a simulated failed part is retried without restarting other parts; killing and relaunching mid-upload resumes with the same multipart id; a 46 s clip is rejected before any network call; push permission is not requested on first open.

---

### Phase 8: Mobile History Tab, Polling, Status States, Retry

#### Goal
Make History the single source of truth for job state with live polling and correct per-status behavior.

#### High Level Summary
History lists uploads newest first with skeleton placeholders while loading and an empty state pointing back to Capture. Each row shows the badge (`processing`, `ready`, `failed`, `no lift`). A `useUploadPolling` hook polls every 2 to 3 s while any visible item is in flight and stops when none are. Tapping `processing` opens a status view; tapping `failed` offers "processing failed, tap to retry" which calls retry and returns the item to `processing`; tapping `no lift` shows a plain explanation that nothing was detected, with no results page; tapping `ready` opens the results route (built in Phase 13, stubbed here). Failure codes and stages never appear. A push notification tap deep-links to the upload's detail route.

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
Phases 4, 5 (stubbed pipeline reaches `ready`), 6, 7.

#### Can AI Complete Independently?
Yes.

#### Risk
Low.

#### Complexity
2/5

#### AI Completion Criteria
Standard criteria, plus: polling stops within one interval after the last in-flight item settles; end-to-end against the stubbed worker, an upload goes `processing -> ready` in History without app restart; push tap opens the correct upload.

---

### Phase 9: CV Stage: Presence, Pose, Bar and Plate Detection, Subject Lock

#### Goal
Replace the first CV stubs with real `presence`, `pose`, and `track` stages that produce per-frame landmarks and a bar track tied to a locked subject.

#### High Level Summary
`presence` samples a sparse set of frames and checks for a person (BlazePose detection) and a bar/plate candidate (OpenCV Hough circles anchored to a detected bar line); missing either returns `no_lift` with `no_bar` or `no_person` and nothing further runs. `pose` runs MediaPipe Pose Landmarker on every frame and keeps per-landmark confidence. `track` detects plates and the bar per frame using three constraints from the spec: ROI limited to the candidate lifter's zone, bar-line anchoring, and temporal consistency with bar motion. Subject lock uses size/centrality as the fast first pass, confirmed by hand-to-bar proximity over subsequent frames; when they disagree, hand-bar contact wins. Once locked for a segment the subject id persists so a spotter cannot hijack tracking. Bar selection follows the winning subject. All functions are pure over frame arrays and return typed tracks. The YOLOv8-nano fallback is not built; a seam is left so a detector can replace the classical plate finder behind the same interface if Phase 16 shows it is needed.

#### Implementation Areas
- Services: frame reader, presence sampler, pose runner, plate/bar detector, subject lock
- Models: `PoseTrack`, `BarTrack`, per-frame confidence
- Testing: fixture clips for `no_bar`, `no_person`, and a clean happy path; unit tests for anchoring and temporal filters on synthetic data
- Documentation: `docs/cv.md` (detection approach, constraints, known limits)

#### Estimated LOC
Approximately 1,000 to 1,500 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/frames.py`, `backend/liftcam/worker/cv/pose.py`, `backend/liftcam/worker/cv/plates.py`, `backend/liftcam/worker/cv/subject.py`, `backend/liftcam/worker/stages/{presence,pose,track}.py`, `backend/tests/worker/cv/*`, `backend/tests/fixtures/clips/README.md`, `docs/cv.md`.

#### Dependencies
Phase 5.

#### Can AI Complete Independently?
Partially. Code and synthetic tests are independent. Real acceptance needs developer-supplied clips (see Phase 16).

#### Risk
High. Classical plate detection against gym clutter is the stated risk in the spec and the reason a fallback detector is reserved.

#### Complexity
5/5

#### AI Completion Criteria
Standard criteria, plus: `no_bar` and `no_person` fixtures terminate at `presence` with no pose run; happy-path fixture produces a bar track with no gaps longer than a provisional threshold; a synthetic second bar outside the ROI is ignored.

---

### Phase 10: CV Stage: Camera Angle, Calibration, Segmentation, Rep Counting

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
Phase 9.

#### Can AI Complete Independently?
Yes for code and synthetic tests. Threshold validation is developer work in Phase 16.

#### Risk
High. Every threshold is provisional by the spec's own statement.

#### Complexity
4/5

#### AI Completion Criteria
Standard criteria, plus: a synthetic RDL trajectory with no floor reset counts the right number of reps; a peak with 80% extension is not counted and appears in the internal attempt list; `no_motion` fixture terminates at `segment`; all thresholds live in one config module.

---

### Phase 11: CV Stage: Form Faults, VBT, Force/Work, Confidence Gating

#### Goal
Complete the `score` stage with per-rep faults, bar velocity, force/work estimates, and per-feature confidence.

#### High Level Summary
Compute four faults per rep, each gated by camera-angle confidence individually: bar-over-midfoot drift (side view), hip rising faster than shoulders / early hip extension (side view), lockout completeness (any angle), knee valgus (front or 45 degrees). Each fault reports `pass | flagged | unavailable` with a one-line reason code and confidence. Spine rounding is not scored; the shoulder-hip line is only a geometric reference. Liftoff occlusion handling: interpolate landmarks from neighbors when per-landmark confidence dips, fall back to the brace/setup frame as a proxy, and mark the portion low-confidence if both are poor. VBT is calibrated plate height times frame-to-frame displacement over time, trusted only at 30 fps+ and 720p+ with standard-plate calibration, otherwise low-confidence. Force/work/energy estimates use user-entered bar mass, measured velocity/acceleration, and a rough bodyweight factor from profile height/weight, inheriting the lowest input confidence. Also compute set-level velocity loss percent. Scoring reads raw or lightly filtered data, never the display-smoothed series.

#### Implementation Areas
- Services: fault detectors, occlusion handling, velocity, force/work, confidence combiner
- Models: `faults` JSONB shape (code, result, reason, confidence), rep numeric fields
- Testing: synthetic pose sequences per fault, occlusion interpolation tests, low-fps and non-standard-plate confidence downgrades
- Documentation: `docs/cv.md` fault definitions and confidence rules; `docs/api.md` faults schema

#### Estimated LOC
Approximately 800 to 1,200 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/faults.py`, `backend/liftcam/worker/cv/velocity.py`, `backend/liftcam/worker/cv/force.py`, `backend/liftcam/worker/cv/confidence.py`, `backend/liftcam/worker/stages/score.py`, `backend/tests/worker/cv/*`, `docs/cv.md`, `docs/api.md`.

#### Dependencies
Phase 10.

#### Can AI Complete Independently?
Yes for code. Biomechanical threshold validation is developer work.

#### Risk
High. Fault thresholds and occlusion handling directly shape user-facing results.

#### Complexity
4/5

#### AI Completion Criteria
Standard criteria, plus: a front-view fixture reports `bar_drift` and `early_hip_rise` as `unavailable`, not `pass`; a 24 fps clip yields low-confidence velocity and force; force is never higher confidence than the velocity it derives from.

---

### Phase 12: Overlay Render and Result Commit

#### Goal
Render the single overlay video, upload it, commit segments and reps atomically, and remove the last stubs.

#### High Level Summary
The `render` stage draws skeleton, detected plates/bar, and bar path onto every frame using a separately smoothed display series (two-pass rendering). Where confidence drops, the overlay and path for that portion are hidden rather than drawn from a smoothed guess. Bar path is full 2D from side-ish angles and vertical-only from front/behind. Frames are encoded with `ffmpeg` to H.264 MP4 with `faststart` for mobile playback, preserving source rotation. `overlay_upload` puts the file to R2 under the `overlay` key. The commit writes `segments` and `reps` in one transaction, sets `ready` and `finished_at`, and triggers push. No per-rep encodes. All stubs from Phase 5 are deleted.

#### Implementation Areas
- Services: smoothing filter, frame drawer, encoder wrapper, commit
- Database: transactional insert of segments and reps
- Testing: render a short fixture and assert output duration, resolution, and playable metadata; commit rollback test on a forced failure after overlay upload
- Documentation: `docs/worker.md` render section

#### Estimated LOC
Approximately 500 to 800 lines.

#### Files Expected To Change
`backend/liftcam/worker/cv/smooth.py`, `backend/liftcam/worker/cv/draw.py`, `backend/liftcam/worker/stages/render.py`, `backend/liftcam/worker/stages/commit.py`, `backend/liftcam/worker/stages/stubs.py` (deleted), `backend/tests/worker/test_render.py`, `docs/worker.md`.

#### Dependencies
Phases 9 through 11.

#### Can AI Complete Independently?
Yes.

#### Risk
Medium. Encoding and rotation handling are fiddly; render time dominates job duration.

#### Complexity
3/5

#### AI Completion Criteria
Standard criteria, plus: happy-path fixture goes end to end to `ready` with two R2 objects and correct row counts; a failure injected after `overlay_upload` leaves no `segments`/`reps` rows and status `failed/render` or `failed/overlay_upload` as appropriate; a 45 s 1080p fixture finishes within the job timeout on the dev machine.

---

### Phase 13: Mobile Results Page (Overview / Video / Graphs) and Share

#### Goal
Build the `ready` experience: per-rep stats, seeked overlay playback, graphs, and overlay-only share/download.

#### High Level Summary
Results open from a `ready` History item with three sections. Overview: rep-by-rep stat cards (reps, average velocity, velocity loss percent, flagged faults summary, entered weight/reps, force/work estimate) with count-up on load, per-fault rows shown as pass / flagged / not available from this angle with a one-line explanation when flagged, and a short scannable stats summary with tooltips for terms like velocity loss. No blended score. Video: `expo-video` player on a fresh presigned overlay URL, rep selector that seeks to the rep's start and stops at its end, responsive frame-accurate scrubbing. Graphs: bar path X/Y, plus position and velocity over time for hip, knee, shoulder, elbow, wrist, selectable per rep, using a lightweight SVG chart component. Share opens the OS share sheet with the downloaded overlay file (`expo-sharing`); download saves it to the camera roll (`expo-media-library`). The original is never shared. Skeleton placeholders while loading. Presigned URL expiry triggers a silent re-presign.

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
Phases 8 and 12. Requires the API to return the per-frame series needed for graphs; if `reps` rows alone are insufficient for joint time series, Phase 13 adds a compact per-rep `series` JSONB to `reps` via a migration and the worker writes it in the commit stage. This is the one place the schema may grow after Phase 2, and it is noted in the Phase 2 ADR.

#### Can AI Complete Independently?
Yes.

#### Risk
Medium. Frame-accurate seek behavior varies across devices.

#### Complexity
4/5

#### AI Completion Criteria
Standard criteria, plus: selecting rep 2 seeks to its `start_s` and pauses at `end_s`; a fault marked `unavailable` never renders as pass; share sheet receives only the overlay file; tabular figures used for all stat numbers.

---

### Phase 14: Benchmarking

#### Goal
Show per-upload comparison against the user's own deadlift max and against population strength standards.

#### High Level Summary
Compute at read time in the API, not in the worker, since profile values can change. Personal benchmark: entered weight versus `deadlift_max`, and a hint when the upload exceeds the stored max. Population benchmark: bodyweight-relative percentile for deadlift by sex from a standards table shipped as a static data file in `core/`, with its source and license recorded. Returned as part of the results payload and shown in the Overview section. Deadlift only.

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
Phases 4 and 13.

#### Can AI Complete Independently?
No. The developer must choose and approve the strength standards data source and confirm its license before the table is committed.

#### Risk
Low technically; medium for data licensing.

#### Complexity
2/5

#### AI Completion Criteria
Standard criteria, plus: missing height, weight, sex, or max yields a clear "add profile data" state rather than an error; percentile is monotonic across the table.

---

### Phase 15: Deployment and Operations

#### Goal
Make the API and worker deployable as two processes on one host, with mobile builds via EAS.

#### High Level Summary
Add a Dockerfile for the backend image (includes `ffmpeg` and MediaPipe runtime deps) with two commands (`api`, `worker`), a process definition (Compose file or the chosen PaaS manifest) running both from the same image, health checks, log shipping to stdout, and an Alembic migrate step on deploy. Document Neon setup (pooled URL for API, direct URL for worker), R2 bucket creation with the incomplete-multipart lifecycle rule, environment variables, and EAS build profiles (development, preview, production) with the real bundle identifiers. No AWS. Hosting provider is chosen by the developer at this point per the spec.

#### Implementation Areas
- Build tooling: Dockerfile, compose or manifest, `eas.json`, minimal CI running lint, types, and tests
- Documentation: `docs/deployment.md`, `docs/env.md` final pass

#### Estimated LOC
Approximately 300 to 500 lines.

#### Files Expected To Change
`infra/Dockerfile`, `infra/compose.yml` (or provider manifest), `.github/workflows/ci.yml`, `mobile/eas.json`, `mobile/app.json`, `docs/deployment.md`, `docs/env.md`.

#### Dependencies
Phases 1 through 12 for a meaningful deploy.

#### Can AI Complete Independently?
No. Provider choice, account creation, DNS, secrets, and the first deploy are developer tasks. The agent produces the artifacts and instructions.

#### Risk
Medium. First deploy surfaces environment differences (ffmpeg, MediaPipe wheels, memory limits on a small VPS).

#### Complexity
2/5

#### AI Completion Criteria
Standard criteria, plus: the image builds locally and both commands start; `docs/deployment.md` walks from empty accounts to a running stack; CI passes on the default branch.

---

### Phase 16: Validation Fixture Suite and Ground Truth

#### Goal
Turn the Validation / QA section into an executable acceptance suite: one golden clip per `failure_code` and per happy-path stage, plus ground-truth comparisons.

#### High Level Summary
Create a fixture manifest listing each clip, its expected terminal status and code, and expected rep count, lockout calls, bar path extent, and velocity where measured. Add a test runner that executes any single stage on a clip without the rest of the worker, and a full-pipeline test per fixture. Add a ground-truth comparison report that prints detected versus measured values with tolerances so thresholds from Phases 10 and 11 can be tuned against real data. Keep training footage (if a fallback detector is ever trained) separate from grading footage by directory convention. Large clips are stored outside Git (documented location) and downloaded by the test runner when present; tests skip cleanly when clips are absent.

#### Implementation Areas
- Testing: fixture manifest, stage-level runner, pipeline tests, report script
- Documentation: `docs/validation.md` (how to add a clip, how to measure ground truth, acceptance bar)

#### Estimated LOC
Approximately 400 to 700 lines.

#### Files Expected To Change
`backend/tests/fixtures/manifest.yaml`, `backend/tests/fixtures/clips/.gitkeep`, `backend/tests/worker/test_fixtures.py`, `backend/scripts/ground_truth_report.py`, `docs/validation.md`.

#### Dependencies
Phase 12.

#### Can AI Complete Independently?
No. The developer records the ground-truth clips (known bar, plates, camera setup, tape measure, frame counts, manual rep and lockout calls). The agent builds the harness and can seed it with synthetic or provisional clips.

#### Risk
Medium. Without real footage the CV phases cannot be accepted; this phase is the gate.

#### Complexity
3/5

#### AI Completion Criteria
Standard criteria, plus: every `failure_code` has a manifest entry; running a single stage on a clip works from the CLI; the report lists tolerance pass/fail per metric.

---

### Phase 17: Pre-Launch Compliance Engineering

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
Phases 6, 7, 13.

#### Can AI Complete Independently?
Partially. Code is independent. Policy text, biometric law review (BIPA and similar), COPPA posture beyond the age gate, and the App Store label entries require counsel and the developer.

#### Risk
Medium. Non-engineering risk is high (biometric statutes); engineering risk is low.

#### Complexity
2/5

#### AI Completion Criteria
Standard criteria, plus: no UI state conveys fault status by color alone; upload is blocked until attestation is accepted once; the data inventory lists every column that holds personal data.

---

## 9. Human Commit Plan

Suggested commits, one or two per phase. The AI never creates these.

- Commit 1: Monorepo scaffold, tooling, health endpoints (Phase 1)
- Commit 2: Database models, migrations, ER diagram update, ADR (Phase 2)
- Commit 3: Auth, tokens, profile API (Phase 3)
- Commit 4: Upload handshake, History, presign API (Phase 4)
- Commit 5: Worker runtime with stubbed pipeline and push (Phase 5)
- Commit 6: Mobile theme, API client, auth and Profile (Phase 6)
- Commit 7: Mobile capture and multipart upload (Phase 7)
- Commit 8: Mobile History, polling, retry (Phase 8)
- Commit 9: CV presence, pose, bar tracking, subject lock (Phase 9)
- Commit 10: CV angle, calibration, segmentation, rep counting (Phase 10)
- Commit 11: CV faults, VBT, force/work, confidence (Phase 11)
- Commit 12: Overlay render and result commit, remove stubs (Phase 12)
- Commit 13: Mobile results page and share (Phase 13)
- Commit 14: Benchmarking (Phase 14)
- Commit 15: Deployment artifacts and CI (Phase 15)
- Commit 16: Validation fixtures and ground-truth report (Phase 16)
- Commit 17: Compliance engineering and data inventory (Phase 17)

Also recommended before Commit 1: commit the current `v1.md` edits and `diagrams/` so the plan's inputs are versioned, and decide whether `copy.md` should be removed (it duplicates `v1.md`).

---

## 10. Manual Developer Tasks

- Create and fund accounts: Neon, Cloudflare R2, Expo/EAS, Apple Developer ($99/yr), Google Play ($25).
- Provision secrets: JWT signing key, service token for `/internal/push`, R2 access keys, database URLs (pooled and direct), OAuth client IDs. Never commit them.
- Configure R2 bucket: private, incomplete multipart abort lifecycle rule.
- Choose the VPS/PaaS at Phase 15 and perform the first deploy and DNS.
- Configure Sign in with Apple and Google OAuth in the respective consoles; set bundle identifiers.
- Record ground-truth footage and take independent measurements for Phase 16.
- Choose and license the population strength standards data source (Phase 14).
- Decide on account deletion in V1 (App Store guideline 5.1.1(v)). Recommended: include it in Phase 17.
- Decide push token cardinality (one per user per ER diagram, or per device) before Phase 2.
- Confirm whether the pre-record screen should attempt any on-device detection (plan assumes no).
- Legal: Privacy Policy, Terms of Service, bystander attestation language, biometric data law review, COPPA posture, App Store privacy nutrition label. Hard launch gate.
- Colorblind accessibility sign-off after Phase 17.
- Approve every threshold change proposed by the ground-truth report.
- Review each phase's diff, stage, commit, push, and open PRs.

---

## 11. Testing Checklist

### Existing Tests
None exist. Nothing to update.

### New Tests

Unit:
- Status transition guards; badge mapping; failure code and stage mapping table.
- JWT sign/verify, refresh rotation and reuse detection, dedup by email, Apple relay fallback, age gate.
- Presign request shapes; part count and size validation; 45 s duration rejection.
- Part splitter, per-part retry, resume from persisted upload state (mobile).
- Polling hook start/stop; single-flight token refresh (mobile).
- CV pure functions on synthetic data: bar-line anchoring, temporal consistency, angle from bar length and plate ratio, calibration cross-check, segmenter, peak detection with displacement floor, lockout gate, each fault detector, occlusion interpolation, velocity, force, confidence combiner, display smoothing.
- Benchmark interpolation and boundaries.

Integration:
- Claim concurrency with two sessions (`SKIP LOCKED`).
- Worker end to end on fixtures: each `failure_code`, corrupt file, timeout, crash, happy path to `ready` with two R2 objects (R2 mocked or dev bucket).
- API endpoints with a real Postgres: auth, uploads, media presign, ownership isolation, internal push auth.
- Migration up and down on a fresh database.

End to end (developer-run on device):
- Signup, record, confirm, upload, History shows processing, push arrives, results play and seek, share sheet receives overlay only.
- Background mid-upload, relaunch, upload resumes.

### Edge Cases
- Invalid inputs: over 45 s, zero reps, negative weight, unsupported unit, malformed ID token, under-13 DOB.
- Failure states: R2 complete fails after all parts uploaded; worker dies after overlay upload before commit; presigned URL expires mid-playback; push token invalid.
- Permission issues: camera or photo library denied; notifications denied (poll still reflects truth); one user requesting another's upload.
- Boundary conditions: exactly 45 s; 30 fps and 720p exactly at the floor; single-rep clip; lifter leaves frame between sets; two bars in frame; spotter enters mid-set; portrait video with rotation metadata.

### Regression Testing
Each CV phase reruns the full fixture suite from Phase 16 (once it exists) so threshold changes in one stage are caught downstream. API contract tests protect the mobile client from payload drift.

### Performance Testing
Measure worker wall time for a 45 s 1080p30 clip on the target host; must finish inside the job timeout with headroom. Measure History list response time with several hundred uploads per user (index check). Measure mobile part upload throughput on cellular.

### Security Testing
Ownership checks on every upload route; internal push endpoint rejects missing or wrong service token; presigned URLs are short-lived and never persisted; password hashes use argon2; refresh token reuse is detected; no internal failure fields leak to clients; secrets absent from repo (CI grep).

---

## 12. Documentation Checklist

- README: project overview, repo layout, quick start for backend and mobile, link to `v1.md` and `docs/`.
- `docs/setup.md`: local development for both stacks, Postgres for tests, ffmpeg requirement.
- `docs/env.md`: every environment variable for API, worker, and mobile, with which process reads it.
- `docs/api.md`: endpoints, request/response schemas, status and code enums, faults JSONB shape.
- `docs/architecture.md`: two-process design, Postgres-as-queue, R2 objects, presign policy, links to the five Mermaid diagrams.
- `docs/worker.md`: stage order, failure mapping, timeout and reaper, render pipeline.
- `docs/cv.md`: detection approach, angle and calibration methods, thresholds table marked provisional, known limits (mirror ambiguity, no hitch detection, no spine scoring).
- `docs/mobile.md`: routes, theme tokens, upload resume, polling, results.
- `docs/deployment.md`: image, processes, Neon and R2 setup, EAS profiles.
- `docs/validation.md`: fixture manifest, ground-truth procedure, acceptance bar.
- `docs/benchmarking.md`: standards data provenance and license.
- `docs/privacy-data-inventory.md` and `docs/legal-checklist.md`.
- ADRs in `docs/adr/`: schema additions beyond the ER diagram, worker subprocess isolation and API-routed push, `expo-video` substitution.
- Update `diagrams/er-data-model.md` in Phase 2 so the diagram matches the schema.
- Remove stale comments and any references to stubs when Phase 12 deletes them.

---

## 13. Migration Notes

Migration Required:
Yes

- Database migrations: Phase 2 creates all tables; Phase 13 may add `reps.series`; Phase 17 adds acceptance timestamps and, if approved, nothing else (deletion needs no schema change). All are additive. Alembic is the single mechanism.
- API changes: none are breaking during V1 because there are no prior clients. Contract tests guard the mobile client from Phase 8 onward.
- Configuration changes: environment variables are introduced per phase and recorded in `docs/env.md` in the same phase.
- Rollout strategy: single environment in V1. Deploy migrates then restarts API and worker. Worker drains the current job before restart (SIGTERM handling from Phase 5).
- Rollback strategy: redeploy previous image; Alembic downgrade scripts are written and tested for every migration. Rows in `processing` at rollback are reaped to `failed/timeout` and are user-retryable.
- Compatibility concerns: none for external consumers. Internal concern is the worker and API sharing one models module; they must be deployed from the same image tag.

---

## 14. Major Caveats

- Breaking changes: none externally. Internally, changing `uploads` shape after Phase 2 is expensive; review the Phase 2 ADR carefully.
- Scalability: single worker and Postgres-as-queue are correct for V1 volume. Render time bounds throughput; indefinite retention grows R2 cost linearly. Both are known and deferred by the spec.
- Security: JWT and refresh token handling, presign TTLs, and the internal push endpoint are the sensitive surfaces. Body pose data may be regulated biometric data in some jurisdictions; this is a legal determination, not an engineering one.
- Performance: MediaPipe on CPU for a 45 s clip at full frame rate plus rendering may approach the job timeout on a small VPS; frame stride for pose and a smaller render resolution are the levers, both configurable.
- Third party limitations: Expo Push rate limit (600/s) is far above V1 needs. `pip` OpenCV codec support requires system `ffmpeg`. Chunked file reads in Expo without a native module are the primary mobile risk.
- Deployment risks: MediaPipe wheel availability for the container base image; memory on the smallest instances; missing `ffmpeg` in the image.
- Rollback concerns: additive migrations only, so downgrade is safe; the only state to reconcile is `processing` rows, handled by the reaper.
- Spec deviations recorded in ADRs: operational schema columns, `refresh_tokens` table, subprocess job isolation, `expo-video` in place of `expo-av`.
- App Store: in-app account deletion is likely required for submission and is not in the spec.

---

## 15. Confidence and Unknowns

Confidence:
70%

Backend, data model, and API phases are high confidence (the spec and diagrams are precise). Mobile capture/upload is medium confidence pending on-device chunked reads. CV phases are the lowest confidence because every threshold is provisional and classical plate detection against real gym footage is unproven; the spec anticipates this with a fallback detector.

Unknowns:

- Feasibility and performance of byte-range reads for multipart parts with current Expo file APIs on iOS and Android.
- Reliability of Hough-based plate detection in cluttered gyms; whether the YOLOv8-nano fallback becomes necessary.
- CPU wall time for pose plus render on the chosen host; whether frame stride is needed to stay under the timeout.
- HEVC decode support in the worker image and the cost of the H.264 normalization step.
- Whether `reps` rows suffice for Graphs or a per-rep `series` column is needed (decided in Phase 13).
- Population strength standards source and license.
- Push token cardinality and account deletion decisions.
- Whether the pre-record live check may include any on-device detection.
- Legal status of pose/keypoint data under biometric statutes; outcome of counsel review.
- Availability and timing of ground-truth footage for acceptance.
