"""Allowed string values for constrained columns (Postgres CHECK + app validation)."""

from __future__ import annotations

UPLOAD_STATUSES = (
    "uploading",
    "queued",
    "processing",
    "ready",
    "failed",
    "no_lift",
)

FAILED_STAGES = (
    "claim",
    "download",
    "probe",
    "presence",
    "pose",
    "track",
    "segment",
    "score",
    "render",
    "overlay_upload",
)

FAILURE_CODES = (
    "timeout",
    "crash",
    "corrupt",
    "no_bar",
    "no_person",
    "no_motion",
)

AUTH_PROVIDERS = ("email", "google", "apple")
SEX_VALUES = ("male", "female")
WEIGHT_UNITS = ("lb", "kg")
HEIGHT_UNITS = ("in", "cm")
TIER_VALUES = ("free",)
