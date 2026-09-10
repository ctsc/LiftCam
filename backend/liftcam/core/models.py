"""ORM tables for LiftCam V1. Column set matches diagrams/er-data-model.md."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from liftcam.core.db import Base
from liftcam.core.enums import (
    AUTH_PROVIDERS,
    FAILED_STAGES,
    FAILURE_CODES,
    HEIGHT_UNITS,
    SEX_VALUES,
    TIER_VALUES,
    UPLOAD_STATUSES,
    WEIGHT_UNITS,
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in_list("auth_provider", AUTH_PROVIDERS), name="ck_users_auth_provider"),
        CheckConstraint(_in_list("sex", SEX_VALUES), name="ck_users_sex"),
        CheckConstraint(_in_list("tier", TIER_VALUES), name="ck_users_tier"),
        CheckConstraint(_in_list("height_unit", HEIGHT_UNITS), name="ck_users_height_unit"),
        CheckConstraint(_in_list("weight_unit", WEIGHT_UNITS), name="ck_users_weight_unit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    apple_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    height_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="in")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weight_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="lb")
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    squat_max: Mapped[float] = mapped_column(Float, nullable=False)
    bench_max: Mapped[float] = mapped_column(Float, nullable=False)
    deadlift_max: Mapped[float] = mapped_column(Float, nullable=False)
    favorite_lift: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tier: Mapped[str] = mapped_column(
        String(16), nullable=False, default="free", server_default="free"
    )
    # One Expo push token per user (last device wins). Multi-device is V2.
    expo_push_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    uploads: Mapped[list[Upload]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (
        CheckConstraint(_in_list("status", UPLOAD_STATUSES), name="ck_uploads_status"),
        CheckConstraint(
            f"failed_stage IS NULL OR {_in_list('failed_stage', FAILED_STAGES)}",
            name="ck_uploads_failed_stage",
        ),
        CheckConstraint(
            f"failure_code IS NULL OR {_in_list('failure_code', FAILURE_CODES)}",
            name="ck_uploads_failure_code",
        ),
        CheckConstraint(_in_list("weight_unit", WEIGHT_UNITS), name="ck_uploads_weight_unit"),
        Index(
            "ix_uploads_user_created",
            "user_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_uploads_queued",
            "status",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploading")
    r2_original_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    r2_overlay_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    multipart_upload_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weight_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="lb")
    user_reps: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Probe metadata (ffprobe) for confidence gating.
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotation_deg: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped[User] = relationship(back_populates="uploads")
    segments: Mapped[list[Segment]] = relationship(back_populates="upload")


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (UniqueConstraint("upload_id", "ord", name="uq_segments_upload_ord"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    camera_angle_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    angle_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    px_per_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    upload: Mapped[Upload] = relationship(back_populates="segments")
    reps: Mapped[list[Rep]] = relationship(back_populates="segment")


class Rep(Base):
    __tablename__ = "reps"
    __table_args__ = (UniqueConstraint("segment_id", "ord", name="uq_reps_segment_ord"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    faults: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    force_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    work_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    lockout_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Compact per-rep joint/bar time series for Graphs (Phase 14).
    series: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    segment: Mapped[Segment] = relationship(back_populates="reps")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
