#!/usr/bin/env python3
"""Generate three synthetic deadlift-ish clips for CV spike smoke tests.

Not a substitute for real gym footage. Side = round plates; front = thin ellipses;
oblique = tilted ellipses. Writes under the given directory.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np


def _write_clip(
    path: Path,
    *,
    kind: str,
    frames: int = 60,
    fps: int = 30,
    size: tuple[int, int] = (720, 1280),
) -> None:
    h, w = size
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (w, h),
    )
    for i in range(frames):
        img = np.full((h, w, 3), 40, dtype=np.uint8)
        cv2.line(img, (0, int(h * 0.85)), (w, int(h * 0.85)), (70, 70, 70), 2)
        cx = w // 2
        base_y = int(h * 0.72)
        lift = int(40 * abs(math.sin(i / frames * math.pi * 2)))
        bar_y = base_y - lift
        # No round head blob — that would create false Hough hits on front/oblique.
        cv2.rectangle(img, (cx - 12, bar_y - 100), (cx + 12, bar_y - 20), (200, 180, 160), -1)
        cv2.line(img, (cx - 50, bar_y), (cx + 50, bar_y), (180, 180, 180), 4)

        if kind == "side":
            r = 56
            for x in (cx - 50, cx + 50):
                cv2.circle(img, (x, bar_y), r, (25, 25, 25), -1)
                cv2.circle(img, (x, bar_y), r, (110, 110, 110), 4)
        elif kind == "front":
            # Edge-on plates: vertical slabs, not ellipses (ellipses still fool Hough).
            for x in (cx - 50, cx + 50):
                cv2.rectangle(
                    img,
                    (x - 3, bar_y - 56),
                    (x + 3, bar_y + 56),
                    (25, 25, 25),
                    -1,
                )
        else:
            # Strong foreshortening: short thick slabs, not round.
            for x, skew in ((cx - 55, 18), (cx + 55, -18)):
                pts = np.array(
                    [
                        [x - 6 + skew, bar_y - 50],
                        [x + 6 + skew, bar_y - 50],
                        [x + 6, bar_y + 50],
                        [x - 6, bar_y + 50],
                    ],
                    dtype=np.int32,
                )
                cv2.fillPoly(img, [pts], (25, 25, 25))

        writer.write(img)
    writer.release()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "clips",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for kind in ("side", "front", "oblique"):
        path = args.out / f"synthetic_{kind}.mp4"
        _write_clip(path, kind=kind)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
