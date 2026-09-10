"""phase3 initial schema

Revision ID: 0001_phase3
Revises:
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase3"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("auth_provider", sa.String(length=16), nullable=False, server_default="email"),
        sa.Column("apple_user_id", sa.String(length=255), nullable=True),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("height_unit", sa.String(length=8), nullable=False, server_default="in"),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("weight_unit", sa.String(length=8), nullable=False, server_default="lb"),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("squat_max", sa.Float(), nullable=False),
        sa.Column("bench_max", sa.Float(), nullable=False),
        sa.Column("deadlift_max", sa.Float(), nullable=False),
        sa.Column("favorite_lift", sa.String(length=32), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=False, server_default="free"),
        sa.Column("expo_push_token", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("apple_user_id"),
        sa.CheckConstraint(
            "auth_provider IN ('email', 'google', 'apple')",
            name="ck_users_auth_provider",
        ),
        sa.CheckConstraint("sex IN ('male', 'female')", name="ck_users_sex"),
        sa.CheckConstraint("tier IN ('free')", name="ck_users_tier"),
        sa.CheckConstraint("height_unit IN ('in', 'cm')", name="ck_users_height_unit"),
        sa.CheckConstraint("weight_unit IN ('lb', 'kg')", name="ck_users_weight_unit"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("r2_original_key", sa.String(length=512), nullable=True),
        sa.Column("r2_overlay_key", sa.String(length=512), nullable=True),
        sa.Column("multipart_upload_id", sa.String(length=128), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("weight_unit", sa.String(length=8), nullable=False, server_default="lb"),
        sa.Column("user_reps", sa.Integer(), nullable=False),
        sa.Column("failed_stage", sa.String(length=32), nullable=True),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("rotation_deg", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('uploading', 'queued', 'processing', 'ready', 'failed', 'no_lift')",
            name="ck_uploads_status",
        ),
        sa.CheckConstraint(
            "failed_stage IS NULL OR failed_stage IN ("
            "'claim', 'download', 'probe', 'presence', 'pose', 'track', "
            "'segment', 'score', 'render', 'overlay_upload')",
            name="ck_uploads_failed_stage",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN ("
            "'timeout', 'crash', 'corrupt', 'no_bar', 'no_person', 'no_motion')",
            name="ck_uploads_failure_code",
        ),
        sa.CheckConstraint("weight_unit IN ('lb', 'kg')", name="ck_uploads_weight_unit"),
    )
    op.create_index(
        "ix_uploads_user_created",
        "uploads",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_uploads_queued",
        "uploads",
        ["status"],
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("camera_angle_deg", sa.Float(), nullable=True),
        sa.Column("angle_confidence", sa.Float(), nullable=True),
        sa.Column("px_per_m", sa.Float(), nullable=True),
        sa.Column("calibration_confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("upload_id", "ord", name="uq_segments_upload_ord"),
    )

    op.create_table(
        "reps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("velocity", sa.Float(), nullable=True),
        sa.Column("faults", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("force_estimate", sa.Float(), nullable=True),
        sa.Column("work_estimate", sa.Float(), nullable=True),
        sa.Column("lockout_ratio", sa.Float(), nullable=True),
        sa.Column("series", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("segment_id", "ord", name="uq_reps_segment_ord"),
    )


def downgrade() -> None:
    op.drop_table("reps")
    op.drop_table("segments")
    op.drop_index("ix_uploads_queued", table_name="uploads")
    op.drop_index("ix_uploads_user_created", table_name="uploads")
    op.drop_table("uploads")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
