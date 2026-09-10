# Phase 2 feasibility spikes

Answers the two highest-variance unknowns before Phase 3 schema work.

## Questions

1. **Hough plate detection:** Does classical OpenCV Hough circle plate detection find plates reliably at **side**, **front**, and **oblique** angles on real deadlift footage? Or is a YOLOv8-nano fallback a V1 requirement?
2. **Chunked byte-range reads:** Can Expo `File.open()` + `readBytes` read a large local video in **8 MB** and **16 MB** parts on a real iPhone and Android without blowing memory or failing? Which part size should Phase 8 use?

## Method

### CV spike

- Script: `backend/scripts/cv_spike.py`
- From `backend/` (venv active):

```
python scripts/cv_spike.py path/to/side.mp4 --label side --out spike-out/side
python scripts/cv_spike.py path/to/front.mp4 --label front --out spike-out/front
python scripts/cv_spike.py path/to/oblique.mp4 --label oblique --out spike-out/oblique
```

- Per frame: MediaPipe Pose Landmarker (lite) + OpenCV `HoughCircles` on blurred gray.
- Outputs: annotated sample JPGs under `spike-out/<label>/samples/`, `summary.json`, `summary.txt`.
- Clip location: real gym clips stay **outside Git**. Preferred folder: `backend/tests/fixtures/clips/` (gitignored except `.gitkeep`).

### Upload spike

- Script: `mobile/spike/chunk-read.ts`
- Temporary UI: Capture tab → pick a video → **Run 8 MB** / **Run 16 MB** → **Copy log**.

## CV results (real gym clips — run 2026-09-10)

Angle labels are best-effort from sample frames (confirm if wrong):

| Angle (guess) | Clip | Frames | Plate “hit rate” | Pose hit rate | Sample frames | Notes |
|---------------|------|--------|------------------|---------------|---------------|-------|
| side | `IMG_2413.mov` | 556 | 100.0%* | 100.0% | `spike-out/IMG_2413/samples/` | Side deadlift. Pose lock is solid. |
| front | `IMG_2475.mov` | 549 | 100.0%* | 97.6% | `spike-out/IMG_2475/samples/` | More frontal / facing bar. Pose solid. |
| oblique | `IMG_2476.mov` | 150 | 100.0%* | 95.3% | `spike-out/IMG_2476/samples/` | Side-oblique. Pose solid. |

\* **Raw Hough hit rate is not usable.** Sample frames show dozens of green circles on treadmill, ceiling fans, racks, floor marks, and only incidentally on plates. A frame “hits” if *any* circle is found, so cluttered gym footage scores ~100% even when plate detection is wrong. Classical Hough **without ROI / bar-line / temporal constraints** fails the real-gym test.

Pose Landmarker is fine on these clips (95–100%).

## CV results (synthetic smoke — earlier)

| Angle | Clip | Frames | Plate hit rate | Pose hit rate | Notes |
|-------|------|--------|----------------|---------------|-------|
| side | `synthetic_side.mp4` | 60 | 100.0% | 0.0% | Round plates → Hough works. |
| front | `synthetic_front.mp4` | 60 | 0.0% | 0.0% | Edge-on slabs → Hough finds nothing. |
| oblique | `synthetic_oblique.mp4` | 60 | 0.0% | 0.0% | Foreshortened slabs → Hough finds nothing. |

## Upload results

| Device | Part size | File size (MB) | Parts | Total ms | Peak part bytes | Error | Notes |
|--------|-----------|----------------|-------|----------|-----------------|-------|-------|
| iPhone | 8 MB | 40.66 | 6 | 51 | 8388608 | none | Parts ~9–11 ms each. Clean. |
| iPhone | 16 MB | 40.66 | 3 | 56 | 16777216 | none | Parts ~22–23 ms. Clean. |
| Android | 8 MB | — | — | — | — | — | **Assumed similar to iPhone** (not run; developer accepted risk 2026-09-10). |
| Android | 16 MB | — | — | — | — | — | **Assumed similar to iPhone** (not run; developer accepted risk 2026-09-10). |

### iPhone raw logs

```
--- 8 MB ---
uri: file:///var/mobile/.../3AA009AA-....mov
file_size_mb: 40.66
part_size_mb: 8
part_count: 6
total_ms: 51
peak_part_bytes: 8388608
part 0: offset=0 bytes=8388608 ms=10
part 1: offset=8388608 bytes=8388608 ms=11
part 2: offset=16777216 bytes=8388608 ms=10
part 3: offset=25165824 bytes=8388608 ms=10
part 4: offset=33554432 bytes=8388608 ms=9
part 5: offset=41943040 bytes=689916 ms=1

--- 16 MB ---
uri: file:///var/mobile/.../F805EB63-....mov
file_size_mb: 40.66
part_size_mb: 16
part_count: 3
total_ms: 56
peak_part_bytes: 16777216
part 0: offset=0 bytes=16777216 ms=22
part 1: offset=16777216 bytes=16777216 ms=23
part 2: offset=33554432 bytes=9078524 ms=10
```

## Decisions

| Decision | Value | Signed by / date |
|----------|-------|------------------|
| Hough plate detection go/no-go for V1 classical-only path | **NO-GO** | agent + real clips 2026-09-10 |
| YOLOv8-nano fallback in V1 scope? (yes/no) | **YES** | agent + real clips 2026-09-10 |
| Chunked byte-range reads go/no-go | **GO** (iPhone measured; Android assumed similar) | 2026-09-10 |
| Part size Phase 8 will use (8 MB or 16 MB) | **16 MB** | 2026-09-10 |

### Rationale

- Real gym frames prove unconstrained Hough is a false-positive machine. Spec already requires ROI + bar-line + temporal consistency; even then front/oblique geometry is weak (synthetic). Put **YOLOv8-nano on the V1 path** for plate/bar detection; keep classical as a seam/fallback experiment, not the sole detector.
- Pose works well enough for V1 with later occlusion/confidence work. Do not block on pose.
- iPhone chunked reads are trivially fast (~50 ms for 40 MB). Both sizes work; **16 MB** means fewer PUTs. Android was not measured; developer accepted “same/similar to iOS” for Phase 2 closeout. Revisit only if Phase 8 device QA shows OOM or failed range reads (fall back to 8 MB).
- Phase 2 is **closed**. Phase 3 schema and later phases may proceed; Phase 8 uses 16 MB parts.

### Developer confirmation

- [x] Re-ran `cv_spike.py` on three real deadlift clips; updated real CV table.
- [x] Confirmed YOLO V1 = YES (classical-only NO-GO).
- [x] Pasted iPhone 8/16 MB logs.
- [x] Android assumed similar to iOS; part size locked at 16 MB (2026-09-10).

## Implied plan changes

- Phase 10: YOLOv8-nano is **in V1 scope**, not optional insurance. Classical Hough may remain as a secondary path behind the ROI constraints, not as the primary detector.
- Phase 8: multipart part size = **16 MB**.
