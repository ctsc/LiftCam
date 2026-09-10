"""Pydantic read schemas mirroring the ORM tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    auth_provider: str
    apple_user_id: str | None
    dob: date
    height: float
    height_unit: str
    weight: float
    weight_unit: str
    sex: str
    squat_max: float
    bench_max: float
    deadlift_max: float
    favorite_lift: str | None
    profile_picture_url: str
    tier: str
    expo_push_token: str | None
    created_at: datetime


class UploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    r2_original_key: str | None
    r2_overlay_key: str | None
    multipart_upload_id: str | None
    weight: float
    weight_unit: str
    user_reps: int
    failed_stage: str | None
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    claimed_at: datetime | None
    finished_at: datetime | None
    duration_s: float | None
    fps: float | None
    width: int | None
    height: int | None
    rotation_deg: int | None


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    upload_id: uuid.UUID
    ord: int
    start_s: float
    end_s: float
    camera_angle_deg: float | None
    angle_confidence: float | None
    px_per_m: float | None
    calibration_confidence: float | None


class RepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    segment_id: uuid.UUID
    ord: int
    start_s: float
    end_s: float
    velocity: float | None
    faults: Any | None
    confidence: float | None
    force_estimate: float | None
    work_estimate: float | None
    lockout_ratio: float | None
    series: Any | None


class RefreshTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
