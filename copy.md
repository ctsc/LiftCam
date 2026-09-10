# LiftCam — V1 Plan (Deadlift Only)

## Scope
- V1 supports **deadlift only**. Squat/bench planned for later, after the pipeline is validated.

## Architecture & Stack
- Processing happens **server-side**, not on-device — the app stays thin (capture/upload/playback), all CV runs on a backend. No Mac needed anywhere in the pipeline.
- **Mobile:** Expo (React Native, TypeScript), `expo-camera`/`expo-av`/`expo-file-system` for capture and playback, `expo-notifications` for push, **EAS Build** for cloud iOS/Android builds (solves the no-Mac constraint, still fully App Store/Play Store publishable).
- **Backend is two processes, not one:** FastAPI handles HTTP (auth, multipart upload handshake, job status, History, presigned URLs). A **separate worker process** runs MediaPipe / OpenCV / scoring / overlay render. Same machine is fine for v1; they must not share a process. A 45s pose/bar pipeline would stall HTTP if it ran in-process, and the user can already close the app while a job keeps running. FastAPI never proxies video bytes.
- **CV:** **MediaPipe Pose Landmarker (BlazePose, 33-landmark, 3D)** for skeleton/joint angles. **OpenCV (classical CV — Hough Circle/edge-based)** for plate/bar detection in v1, with a small custom-trained detector (YOLOv8-nano) held as fallback if classical CV proves unreliable.
- **Queue:** no Redis, Celery, SQS, or websockets. The `uploads` row in Postgres *is* the queue. API sets `queued` after multipart complete; the worker claims with `FOR UPDATE SKIP LOCKED`.
- **Storage:** Cloudflare **R2** for video bytes (S3-compatible, no AWS required). **Neon Postgres** for all structured data (users, uploads/jobs, segments, reps). Video is never stored in Postgres — only object keys. The worker uses a direct (non-pooler) Neon connection for claim if the pooler breaks `SKIP LOCKED`.
- **Hosting:** not AWS for v1 (no EC2/ECS/Lambda/RDS). **Neon** for Postgres. API+worker on a cheap VPS or small PaaS (Hetzner, DigitalOcean, Fly, Render) — pick at first deploy; same machine, two processes. Revisit AWS later if GPU workers, multi-region, or company procurement require it.
- **Push:** **Expo Push Notifications** only. No OneSignal, no direct FCM/APNs. Free (no per-notification fee); hard limit is 600 notifications/sec/project, not cost. One transactional ping per finished job. Store an Expo push token per user/device.
- **Licensing:** MediaPipe (Apache 2.0), OpenCV (BSD/Apache 2.0), Expo/React Native (MIT) — all explicitly permit commercial/monetized use, no royalties, no restrictions on app store publishing.
- **iOS testing without a Mac:** confirmed non-issue — EAS-built binaries install and test directly on a physical iPhone, no Mac/simulator required.
- **Realistic cost range:** dev/testing phase ~$10-40/month (EAS free tier, small backend instance, R2). Pre-launch beta ~$50-100/month plus one-time/annual dev accounts (Apple $99/yr, Google Play $25 one-time). At real scale, the actual cost driver isn't the frameworks (all free/open-source), it's CV processing compute + storage, since v1 retains everything indefinitely — this is exactly why server-side expiration/archival is already flagged in Deferred to V2+.

## Runtime, Data & Auth
- **History item = one `uploads` row.** That row is both the History item and the job. It owns the R2 keys, multipart `uploadId` (while `uploading`), user-entered weight/reps, status, and internal failure fields. Do not split Upload and Job into two tables. Retry reuses the same row and the same original video; it does not spawn a second job.
- **First-class `segments` and `reps`.** One `segments` row per auto-detected lift window (start/end, order). One `reps` row per counted rep (times, velocity, faults, confidence). Fault lists may be JSONB *on* a rep; they are not a substitute for a rep row. Results UI still rolls up to one upload. V2 progress tracking stays possible without a refactor.
- **`uploads.status` machine:** `uploading` → `queued` → `processing` → `ready` | `failed` | `no_lift`.
  - `failed` = pipeline crash/timeout/corrupt file. Tap to retry. Original video kept. Persist `failed_stage` + `failure_code` + short internal message (see Processing Flow). UI still only says "processing failed, tap to retry."
  - `no_lift` = worker finished with a detection miss. Own terminal status, not `failed` and not `ready`. Results page never opens. Persist `failure_code` only: `no_bar` | `no_person` | `no_motion`.
  - History badges: map `uploading` / `queued` / `processing` → **processing**; `ready` → **ready**; `failed` → **failed**; `no_lift` → **no lift**.
- **R2 objects:** exactly two files per upload — `original` (the uploaded clip) and `overlay` (one full render: skeleton, bar, path). Each rep stores start/end (optional thumbnail). The app plays `overlay` and seeks to the rep range. No per-rep encodes. No on-the-fly overlay at playback.
- **Media URLs:** API issues **short-lived presigned GETs** (~10 min) after a valid JWT. Postgres stores R2 object keys only — never a public bucket, never a persisted URL. Playback and share-file download both go through a fresh presign.
- **Auth tokens:** FastAPI issues a short-lived **JWT access token** and a longer **refresh token** after email/password or Google/Apple. OAuth is verify-then-issue-our-tokens. No cookie sessions. No hosted auth product (Supabase Auth, Clerk) in v1.

## App Navigation
- **Three tabs, nothing more:** Capture/Upload (home), History, Profile.
- New users land directly on Capture/Upload right after signup, not an empty dashboard/history list. A brief first-time overlay introduces the framing guide and the async "we'll notify you" flow.
- No separate processing screen or notifications inbox — an in-progress upload just shows up in History as an item with a status badge, one source of truth for job state (`uploads.status`).
- **Live status while the app is open:** poll `GET /uploads/:id` (or the History list) every **~2–3s** while status is `uploading` | `queued` | `processing`, then stop. Expo push covers the background case. No websocket.
- **History tab:** sorted most-recent-upload-first, no other sort/filter options in v1 (nothing to filter by yet with only one lift type). Empty state points back to Capture/Upload ("no lifts yet — record or upload your first set") rather than a blank list. Each list item shows its status badge; tapping **ready** opens per-rep overlay playback + stats, tapping **processing** shows job status, tapping **failed** offers retry, tapping **no lift** explains that nothing was detected (no results page). Failure codes and stages are never shown in the UI.

## Branding & Visual Design
*Everything in this section is v1's starting point, not permanent — presentation is far easier to revise later than the pipeline/data-model decisions above.*
- **App name: LiftCam.** Icon is a placeholder for now.
- **Aesthetic direction: warm-neutral, restrained.** Cream/off-white background, near-black text for primary content, muted grays for secondary/metadata text. No gradients, no heavy shadows, flat and content-forward, generous spacing — similar spirit to Claude's own interface (warm parchment background, minimal chrome), not a direct copy.
- **Two functional colors, not one:** a calm primary accent (proposed: deep forest green, ~#3D5C42) for primary actions, navigation, and "working correctly" states; a separate muted warning tone (proposed: warm ochre/amber, ~#B8823D) reserved only for flagged faults and low-confidence badges. True red avoided — fault flags are informational, not punitive.
- **Light mode only in v1.** No dark mode — doubles the design/QA surface for limited payoff right now; deferred.
- **Typography: all-sans, no serif**, one type family varying by weight/size for both headers and body. Numbers use tabular (fixed-width) figures so stat cards/velocity numbers don't jitter as values update between reps.
- **Motion: minimal and purposeful only, no decorative animation.** Skeleton-placeholder loading states (not blank screens or spinners) given how much of the app is async waiting. Frame-accurate, responsive video scrubbing on the results screen. Brief count-up/fade-in for numbers as data loads, rather than popping into place.
- **Component shape language:** rounded corners + thin, subtle borders for cards/rows/buttons, no shadows anywhere — consistent with the flat aesthetic above.

## Capture & Recording Flow
- **Both camera-roll upload and in-app recording are primary, equal-weight paths.** Most people will upload from camera roll, but in-app recording (with a live framing guide) also works as a standalone "check my angle" tool even for people who'll ultimately shoot on their native camera app.
- **Pre-record screen:** lightweight live check only — angle detected + basic bar/plate/lifter presence. Not the full technical overlay (that would require on-device/native real-time inference, which breaks the "thin mobile client" architecture principle).
- **During active recording:** no overlay at all, plain recording.
- **After stopping recording:** the clip enters the **exact same async pipeline as a camera-roll upload** — no special treatment, no separate quick-preview pass. One pipeline regardless of source.
- **Confirm/retake screen** shown before anything enters the upload queue (applies to both recording and camera-roll picks) — playback + Upload/Retake choice. Kept intentionally "dumb," no pre-check run here; a bad take just goes through the normal async flow and comes back as "no lift detected" or low-confidence, same as any other edge case. The model's own detection *is* the precheck, it just runs after upload instead of before.

## Upload & Segmentation
- One upload = one video. Can contain a full set, multiple sets (with gaps where the lifter leaves frame), or a single rep.
- Backend auto-segments the video into distinct lift windows based on continuous "person + bar in motion" detection.
- Max upload length: **45 seconds** (v1/free tier).
- Min quality floor: **30fps, 720p**. Below this, video is still processed for what it supports (rep count, form score), but fps/resolution-dependent numbers (VBT) are flagged low-confidence rather than trusted.

## Camera Angle Handling
- No hard angle requirement — confidence is computed per feature based on detected angle, not gated as a single pass/fail.
- **Angle detection primary signal: bar length.** Full visible length between outer plate edges = front/behind view. Near-zero = side view (looking down the bar's axis). In-between follows a sine relationship, giving a continuous angle estimate, not just buckets.
- **Plate width:height ratio** used as a secondary/fallback signal when both bar ends aren't visible in frame (tight crops, close framing).
- Front vs. behind (identical apparent bar length) disambiguated via pose-based face-orientation check.
- Left-oblique vs. right-oblique mirror ambiguity is an accepted v1 limitation — doesn't affect fault-confidence math, just self-occlusion awareness (not solved in v1).
- Before upload, UI shows a tip: "film from the side for the most accurate bar path — we'll still track most angles." A recommendation, not a requirement. Angle-quality text ("good for xyz") is never shown live during or after recording — only as this static pre-upload tip.

## Calibration (pixel → real-world distance)
- Assumes a **standard 45/55lb plate**.
- Primary measurement: **plate's vertical extent** (top rim to ground) — this stays accurate regardless of camera angle, unlike horizontal width which compresses depending on viewing angle.
- Cross-referenced against plate-to-plate span as a secondary check. Disagreement between the two = flagged low-confidence.
- Non-standard plate size (25s, 10s, etc.) or no plates detected → VBT marked low-confidence/unavailable. Rep count and form score are unaffected (they don't need calibration).
- This calibration system is fully decoupled from bar-length-based angle detection — an error in one doesn't corrupt the other.

## Subject & Equipment Detection
- Lifter identified by **hand-to-bar proximity/contact**, not size or position in frame. Once locked in for a segment, subject ID persists through it so a spotter stepping in briefly doesn't hijack tracking.
- **Bar/plate detection: classical CV for v1** (Hough Circle / edge-based), not a trained model yet. Made robust against background clutter (racked plates, other lifters) via three constraints:
  - Region-of-interest limited to the identified lifter's zone
  - Bar-line anchoring (a circular blob only counts if it sits at the end of the detected bar line)
  - Temporal consistency (must move in sync with the bar's own motion)
- Small custom-trained detector (e.g. YOLOv8-nano) held as a fallback if classical CV proves unreliable against ground-truth testing.
- **Multi-bar resolution (crowded gym):** size/centrality in frame is the fast first-pass candidate for the lifter (self-recorded footage almost always frames the lifter as biggest/most-central). This is then confirmed against hand-to-bar contact over the next few frames. If they agree, confident lock. If they disagree (e.g. a spotter or closer bystander reads as more central), hand-bar contact wins as the more direct behavioral signal. Bar selection follows from whichever subject wins this check, not chosen independently.

## Rep Counting
- Reps counted by **local maxima in bar vertical position** (peak = direction reversal from ascending to descending) — not return-to-floor, so this works for both standard deadlifts and RDL-style variants that don't reset to the ground.
- Minimum vertical displacement between a peak and its preceding trough required, to filter out jitter/noise as a false rep.
- **Lockout gate is a hard requirement:** a rep only counts if hip/knee extension at the peak is ≥ ~90% of full extension. Below that, it does NOT increment rep count.
- Sub-90% attempts are logged internally for dev/validation purposes only — never surfaced in the UI.
- Hitch detection (down-up-down mid-rep) is explicitly **out of v1** — noted as a possible v2 feature.
- User manually enters completed rep count + weight lifted (lbs/kg) on upload.
- User-entered rep count is cross-checked silently against the CV's auto-detected count. Mismatches are logged internally only, never shown to the user.

## Form Scoring (Deadlift, v1 fault checklist)
- Generic biomechanical joint-angle thresholds — not personalized to height/weight.
- **Spine/lumbar rounding is NOT scored.** Shoulder-hip line is still used as a geometric reference for other checks (e.g. hip-rise timing), but "roundness" itself isn't flagged — left to the user's own judgment.
- V1 fault checklist, each gated by camera-angle confidence individually (not one gate for the whole score):
  - Bar-over-midfoot drift (side view)
  - Hip rising faster than shoulders / early hip extension (side view)
  - Lockout completeness / full hip-knee extension (any angle)
  - Knee valgus / inward cave (front or 45°)
- Occlusion handling at the bottom/liftoff position (most occluded, most important moment):
  - Per-landmark confidence from BlazePose; interpolate from neighboring frames when confidence dips
  - Fallback to the brace/setup position (fully visible just before the pull starts) as a proxy when live-frame confidence is too low
  - If both are low-confidence, that portion of the score is flagged low-confidence rather than guessed

## VBT / Bar Velocity
- Computed from calibrated plate-height measurement × frame-to-frame displacement over time.
- Requires 30fps+ video and standard-plate detection to be trusted; otherwise flagged low-confidence.
- Vertical velocity stays fairly reliable across most horizontal angles (vertical motion is roughly in-plane regardless of camera position) — confidence only drops meaningfully at steep oblique angles.

## Bar Path
- Full-fidelity 2D path (including front-back drift) shown from side-ish angles.
- Simplified vertical-only trajectory shown from front/behind, since front-back drift isn't measurable from that angle.

## Force / Work / Energy Estimate
- Included in v1, explicitly labeled as an **estimate**, not a lab-grade biomechanical measurement — a single external camera can't observe true ground-reaction/segment-mass biomechanics.
- Computed from bar mass (user-entered weight) × measured velocity/acceleration, with a rough bodyweight factor from profile height/weight.
- Inherits the same confidence gating as everything else — if velocity/calibration confidence is low for a rep, the derived force/work number is flagged low-confidence too, never presented as a clean number off shaky inputs.

## Results Page Structure
- Three sections per uploaded video: **Overview / Video / Graphs** (deliberately not a copy of any reference app's section naming).
  - **Overview:** rep-by-rep stat cards — reps, avg velocity, velocity loss % across the set, flagged faults summary, weight/reps entered, force/work estimate.
  - **Video:** per-rep playback of the single overlay file (skeleton, detected plates/bar, bar path line), seeked to that rep's start/end, rendered per Display/Rendering rules below.
  - **Graphs:** bar path X/Y, plus position and velocity over time for hip/knee/shoulder/elbow/wrist, selectable per rep.
- Per-fault form results shown as pass / flagged / not-available-from-this-angle, each with a one-line explanation when flagged — no single blended "78/100" score, since that would falsely imply uniform precision across faults with different confidence levels.
- A **separate short stats summary** (not a text/markdown document — an in-app page) sits alongside the video: velocity per rep as a trend, velocity loss %, fault frequency (e.g. "knee valgus flagged on 2 of 3 reps"), weight/reps, rolled-up confidence notes. Kept short and scannable — a handful of glanceable numbers, not paragraphs. Extra explanation (e.g. what "velocity loss" means) lives behind a tooltip/info icon, not inline.
- **Share/download is the overlay video file only** — OS share sheet (Messages, Instagram, etc.) and download/save. No unlisted result link, no public web page, no share of the original clip (that's already on their camera roll or playable in History).

## Benchmarking
- Per-upload comparison against the user's own profile max for that lift (personal benchmark).
- Per-upload comparison against **population strength standards** (bodyweight-relative percentile ranking, e.g. "stronger than X% of lifters at your bodyweight/sex") — v1 scope limited to deadlift, matching overall app scope.
- Requires profile data to function: height, weight, sex, DOB, and SBD maxes (see Accounts).

## Display / Rendering
- **Two-pass rendering:** raw/lightly-filtered data drives the scoring math; a separately-smoothed version drives the on-screen overlay so it looks stable even though underlying detection always has some natural jitter.
- When confidence genuinely drops on a frame/segment, the overlay/bar-path line is **hidden** for that portion rather than rendering a smoothed guess. Confident-but-incomplete beats looks-wrong.

## Processing Flow
- Fully **async** — user confirms upload, row is `uploading` then `queued`, worker claims it, status becomes `processing`. User can back out or close the app without losing the job, notified when done.
- API never runs CV. Worker writes segments/reps, stores the overlay object, then sets `ready`, `failed`, or `no_lift`.
- **Upload bytes:** client uploads **directly to R2** with S3 multipart. API only creates the multipart upload, hands out short-lived presigned part URLs, and completes it — then sets `queued`. Resume = retry the failed part, not the whole file. The multipart `uploadId` is stored on that `uploads` row; on reopen after background, continue the same upload. Foreground-only in v1, no native background-session module. No tus, no API-proxied chunks, no single-PUT full restart.
- **Worker stages (fail cheap, commit once).** Each stage is a pure function (fixture-testable). Crash/timeout anywhere after claim → `failed`, original kept. Do not pose or render until presence clears; do not write `segments`/`reps` until the overlay object exists.
  1. Claim job → download `original` from R2 → probe (duration / fps / resolution)
  2. Fast presence on a sparse frame sample (bar + person) — miss either → `no_lift` (`no_bar` or `no_person`), no pose, no render
  3. Full-frame pose + bar track
  4. Segment on “person + bar in motion” — no moving bar / no windows → `no_lift` (`no_motion`)
  5. Per segment: subject lock → reps → faults → VBT
  6. Smoothed overlay render → upload overlay to R2 → write `segments`/`reps` → `ready` → Expo push
- **Root cause (internal only).** Structured logs keyed by `upload_id` + stage. Persist on the `uploads` row:
  - `failed` → `failed_stage` (`claim` / `download` / `probe` / `presence` / `pose` / `track` / `segment` / `score` / `render` / `overlay_upload`) + `failure_code` (`timeout` / `crash` / `corrupt` / …) + short internal message
  - `no_lift` → `failure_code` only (`no_bar` / `no_person` / `no_motion`)
  - Retry clears failure fields and resets the same row to `queued`
  - No per-frame debug dumps in R2 in v1 (indefinite retention)
- **Push notification timing:** Expo Push, not requested on first app open. Asked right after the user's first upload completes. If denied, in-app poll still reflects reality — the notification is a convenience, not the source of truth.

## Accounts
- Lightweight auth: email/password OR Google/Apple OAuth, then FastAPI JWTs (access + refresh) as described in Runtime, Data & Auth.
- Deduplication keyed on verified email across all signup methods, regardless of provider. Apple's relay-email case uses Apple's stable user ID as the fallback dedup key.
- **Signup requires:** username, optional pfp (default provided if skipped), password (if not OAuth), date of birth, height, weight, sex (male/female — for strength-standard accuracy only), and SBD max lifts (lbs/kg).
- **Favorite lift is profile-only**, not collected at signup — optional, editable anytime.
- All signup fields (height, weight, maxes, favorite lift) remain editable later in Profile.
- Single **"lifter" role** for all users — no separate coach/athlete roles. V1 has no in-app recipient; if they share, they share a video file through the OS.
- **Minimum age 13+** (from DOB above, COPPA line). Under-13 blocked from account creation entirely.
- Account includes a **`tier` field, defaulting to `free`** for every user in v1 — placeholder only, avoids a schema migration later. No paid tier, billing, or upgrade flow built in v1.

## Sharing
- V1 share is **not a link**. No unlisted URL, no public `/s/:token` page, no `share_links` table.
- From a **ready** result: native OS share sheet and/or download, **overlay video only** (the rendered result, not the original).
- Unlisted full-result links and any structured send-to-another-user flow are V2 (with the Dropbox-style messaging upgrade).

## Storage & Retention
- No personal media library or storage quotas in v1 — results history is just a list of past `uploads` with original + overlay in R2 and segments/reps in Postgres.
- Downloadable artifact is the overlay video.
- All videos and results retained indefinitely in v1, no auto-expiration.
- No retention/expiration messaging shown to the user, since nothing is actually being deleted yet.
- Real server-side expiration/archival for storage-cost management is a planned v2+ backend feature, not built now.

## Validation / QA
- Ground-truth test set built from the user's own uploads — known bar, known plates, known camera setup — cross-checked against independent measurement (tape measure for bar path, frame-count/stopwatch for velocity, manual rep/lockout calls).
- This test set is the actual acceptance bar for shipping a feature, not a subjective "looks right" check.
- **In-depth fixture suite after the pipeline runs:** one golden clip per `failure_code` and per happy-path stage. The persisted code list *is* the test matrix. Stages stay pure so a clip can be run at a single stage without the rest of the worker.
- All thresholds in this plan (90% lockout cutoff, noise displacement minimum, 30fps/720p floors, etc.) are provisional until validated against real ground-truth data.
- Footage used to train the fallback custom detector (if/when needed) must stay separate from footage used to grade it.

## Legal / Compliance — Pre-Launch Checklist (not a v1 build task)
- **Privacy Policy + Terms of Service** — required for App Store/Play Store submission regardless of tier; must disclose what's collected (video, pose/keypoint data, account info, DOB, height, weight, sex, self-reported maxes), storage, that the user can download/share the overlay file off-platform, and retention.
- **Biometric data law review** — body pose/keypoint data may fall under state biometric statutes (e.g. Illinois BIPA and similar laws elsewhere), which have driven real litigation. Whether this app's data qualifies is a genuine legal question requiring actual counsel, not something resolved in this doc.
- **COPPA, beyond the v1 age gate** — broader requirement around not knowingly collecting data from children without verifiable parental consent.
- **Bystander footage** — gym videos will incidentally capture other people. Needs explicit ToS language having the uploading user attest they have the right to record/share.
- **App Store privacy nutrition label** — must accurately disclose data types collected in App Store Connect.
- **Colorblind accessibility review** — the two-color fault-flag system (green accent / amber warning, Decision 50) needs a pass for colorblind-safe distinction (e.g. red-green colorblindness) before launch, not built into v1 design.
- This entire section is a hard pre-launch gate requiring real legal review, not engineering work.

## Deferred to V2+
- Progress tracking over time (charts, PR history, per-rep-count trend graphs) — data model already supports this without refactor, just not built as a UI in v1
- Leaderboard/social feed
- Height/weight-personalized form scoring
- Hitch detection (down-up-down mid-rep)
- Unlisted full-result share links and a public result page
- Dropbox-style two-way video messaging system between exactly two users (structured, access-controlled)
- Squat and bench support (including per-lift benchmarking and lift-type detection/selection once multiple lifts exist)
- Server-side expiration/archival for storage cost management
- Dark mode
- AWS as a platform (GPU workers, multi-region, or procurement)

## Design-phase diagrams
Diagrams live in `/diagrams` as **Mermaid** in `*.md`. V1 design closeout is these five, nothing else (no separate deployment diagram, no UI wireframes, no PlantUML/Excalidraw):

- `diagrams/component.md` — `flowchart` — Expo app, FastAPI, worker, Neon, R2, Expo Push
- `diagrams/activity-capture-upload.md` — `flowchart` — record vs camera-roll, confirm/retake, shared multipart → queue path
- `diagrams/sequence-process-job.md` — `sequenceDiagram` — multipart → complete → claim → stages → push → poll
- `diagrams/er-data-model.md` — `erDiagram` — User, Upload (incl. R2 keys, multipart id, failure fields), Segment, Rep (no ShareLink)
- `diagrams/state-job.md` — `stateDiagram-v2` — `uploading` / `queued` / `processing` / `ready` / `failed` / `no_lift`

---

Product decisions resolved through Decision 55. Design-phase grilling is **closed**. Locked: two-process backend, Postgres-as-queue, no AWS, R2 + **Neon**, `uploads` as History+job, first-class segments/reps, `no_lift` as its own status, two R2 objects, overlay-only OS share/download, JWT access+refresh, **presigned GET/PUT (keys only in Postgres)**, **Expo Push**, **S3 multipart client→R2**, **fail-cheap worker stages**, **`failed_stage` + `failure_code`**, **History poll ~2–3s**, **Mermaid diagrams** as above. Still open at first deploy only: which VPS hosts API+worker.