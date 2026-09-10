#!/usr/bin/env python3
"""Phase 2 CV spike: MediaPipe pose + OpenCV Hough plate circles on one clip.

Throwaway / seed for Phase 17 stage runner. No imports from liftcam product code.

Usage (from backend/ with venv active):
  python scripts/cv_spike.py path/to/clip.mp4
  python scripts/cv_spike.py path/to/clip.mp4 --out ../spike-out/side --label side
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core import base_options as mp_base
from mediapipe.tasks.python.vision import pose_landmarker

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
MODEL_NAME = "pose_landmarker_lite.task"
SAMPLE_EVERY_N = 5
MAX_SAMPLE_FRAMES = 12


@dataclass
class FrameResult:
    frame_index: int
    t_s: float
    plate_hits: int
    pose_detected: bool


def _ensure_model(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / MODEL_NAME
    if model_path.is_file() and model_path.stat().st_size > 0:
        return model_path
    # Prefer urllib so we do not add a network dep beyond stdlib.
    import urllib.request

    print(f"downloading pose model to {model_path} ...", file=sys.stderr)
    urllib.request.urlretrieve(MODEL_URL, model_path)
    return model_path


def _transcode_if_needed(clip: Path, work_dir: Path) -> Path:
    """OpenCV often fails on phone HEVC; normalize to H.264 when open fails."""
    cap = cv2.VideoCapture(str(clip))
    ok, _ = cap.read()
    cap.release()
    if ok:
        return clip

    out = work_dir / f"{clip.stem}_h264.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(clip),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out),
    ]
    print(f"opencv could not decode {clip.name}; running ffmpeg normalize", file=sys.stderr)
    subprocess.run(cmd, check=True, capture_output=True)
    return out


# BlazePose topology for drawing a readable stick figure (landmark index pairs).
POSE_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (24, 26),
    (25, 27),
    (26, 28),
    (27, 29),
    (28, 30),
    (29, 31),
    (30, 32),
    (27, 31),
    (28, 32),
)


def _hough_plates(gray: np.ndarray) -> list[tuple[int, int, int]]:
    """Classical plate candidates: Hough circles on a blurred gray frame."""
    blurred = cv2.GaussianBlur(gray, (9, 9), 1.5)
    h, w = gray.shape[:2]
    min_r = max(20, int(min(h, w) * 0.035))
    max_r = max(min_r + 1, int(min(h, w) * 0.16))
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(40, min_r * 2),
        param1=120,
        param2=35,
        minRadius=min_r,
        maxRadius=max_r,
    )
    if circles is None:
        return []
    return [(int(x), int(y), int(r)) for x, y, r in circles[0]]


def _draw_overlay(
    bgr: np.ndarray,
    circles: list[tuple[int, int, int]],
    landmarks: list[tuple[float, float]] | None,
) -> np.ndarray:
    """Draw Hough faintly, then a thick pose skeleton on top so it is visible."""
    out = bgr.copy()
    h, w = out.shape[:2]

    # Dim green Hough candidates (easy to see the spam without burying the person).
    overlay = out.copy()
    for x, y, r in circles:
        cv2.circle(overlay, (x, y), r, (0, 180, 0), 1)
    cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)

    if landmarks:
        pts = [(int(lx * w), int(ly * h)) for lx, ly in landmarks]
        for a, b in POSE_CONNECTIONS:
            if a < len(pts) and b < len(pts):
                cv2.line(out, pts[a], pts[b], (0, 0, 255), 3)  # red bones
        for x, y in pts:
            cv2.circle(out, (x, y), 5, (255, 255, 0), -1)  # cyan joints
            cv2.circle(out, (x, y), 5, (0, 0, 0), 1)
    return out


def _landmark_xy(result: vision.PoseLandmarkerResult) -> list[tuple[float, float]] | None:
    if not result.pose_landmarks:
        return None
    return [(lm.x, lm.y) for lm in result.pose_landmarks[0]]


def run_spike(
    clip: Path,
    out_dir: Path,
    label: str,
    model_path: Path,
    *,
    max_frames: int | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = out_dir / "samples"
    samples_dir.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="liftcam_cv_spike_") as tmp:
        work = Path(tmp)
        video_path = _transcode_if_needed(clip, work)

        options = pose_landmarker.PoseLandmarkerOptions(
            base_options=mp_base.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.4,
            min_pose_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        )
        landmarker = pose_landmarker.PoseLandmarker.create_from_options(options)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise SystemExit(f"failed to open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_results: list[FrameResult] = []
        sample_paths: list[str] = []
        frame_index = 0
        plate_positive = 0
        pose_positive = 0

        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if max_frames is not None and frame_index >= max_frames:
                break
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            circles = _hough_plates(gray)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int(frame_index * 1000.0 / fps)
            pose = landmarker.detect_for_video(mp_image, ts_ms)
            landmarks = _landmark_xy(pose)
            pose_ok = landmarks is not None
            plate_ok = len(circles) > 0
            if plate_ok:
                plate_positive += 1
            if pose_ok:
                pose_positive += 1

            fr = FrameResult(
                frame_index=frame_index,
                t_s=round(frame_index / fps, 3),
                plate_hits=len(circles),
                pose_detected=pose_ok,
            )
            frame_results.append(fr)

            if frame_index % SAMPLE_EVERY_N == 0 and len(sample_paths) < MAX_SAMPLE_FRAMES:
                annotated = _draw_overlay(bgr, circles, landmarks)
                sample_name = f"frame_{frame_index:05d}.jpg"
                sample_path = samples_dir / sample_name
                cv2.imwrite(str(sample_path), annotated)
                sample_paths.append(str(sample_path.as_posix()))

            frame_index += 1

        cap.release()
        landmarker.close()

    total = max(1, len(frame_results))
    summary = {
        "label": label,
        "clip": str(clip.resolve()),
        "frames": len(frame_results),
        "fps": round(float(fps), 3),
        "plate_hit_rate": round(plate_positive / total, 4),
        "pose_hit_rate": round(pose_positive / total, 4),
        "plate_positive_frames": plate_positive,
        "pose_positive_frames": pose_positive,
        "sample_frames": sample_paths,
        "notes": _notes(label, plate_positive / total),
        "per_frame": [asdict(r) for r in frame_results],
    }

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report = out_dir / "summary.txt"
    report.write_text(
        "\n".join(
            [
                f"label: {label}",
                f"clip: {clip}",
                f"frames: {summary['frames']}",
                f"plate_hit_rate: {summary['plate_hit_rate']:.1%}",
                f"pose_hit_rate: {summary['pose_hit_rate']:.1%}",
                f"samples: {len(sample_paths)} under {samples_dir}",
                f"notes: {summary['notes']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"))
    return summary


def _notes(label: str, plate_rate: float) -> str:
    if plate_rate >= 0.5:
        return (
            f"{label}: Hough found circles on most frames — inspect samples; "
            "cluttered gyms often mean false positives, not true plates."
        )
    if plate_rate >= 0.15:
        return (
            f"{label}: intermittent Hough hits; may need ROI/bar-line "
            "constraints or a learned detector."
        )
    return (
        f"{label}: weak Hough circle rate. Front/oblique plates look like "
        "ellipses; classical Hough is expected to struggle here."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="LiftCam Phase 2 CV plate/pose spike")
    parser.add_argument("clip", type=Path, help="Path to a video clip")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: spike-out/<clip-stem>)",
    )
    parser.add_argument("--label", default="", help="Angle label: side|front|oblique")
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=Path(__file__).resolve().parent / ".models",
        help="Directory for the downloaded Pose Landmarker model",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Stop after N frames (faster re-renders for sample JPGs)",
    )
    args = parser.parse_args()
    clip = args.clip
    if not clip.is_file():
        raise SystemExit(f"clip not found: {clip}")

    label = args.label or clip.stem
    out_dir = args.out or (Path("spike-out") / clip.stem)
    model_path = _ensure_model(args.model_cache)
    run_spike(clip, out_dir, label, model_path, max_frames=args.max_frames)


if __name__ == "__main__":
    main()
