"""Claim one queued upload with FOR UPDATE SKIP LOCKED (worker path)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from liftcam.core.models import Upload


def claim_next_queued_upload(session: Session) -> Upload | None:
    """Atomically claim the oldest queued job. Safe under concurrent workers."""
    stmt = (
        select(Upload)
        .where(Upload.status == "queued")
        .order_by(Upload.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    upload = session.execute(stmt).scalar_one_or_none()
    if upload is None:
        return None
    upload.status = "processing"
    upload.claimed_at = datetime.now(UTC)
    session.flush()
    return upload


def claim_next_queued_upload_raw(session: Session) -> uuid.UUID | None:
    """Same claim using raw SQL (documents the partial-index query shape)."""
    row = session.execute(
        text(
            """
            UPDATE uploads
            SET status = 'processing', claimed_at = NOW()
            WHERE id = (
                SELECT id FROM uploads
                WHERE status = 'queued'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id
            """
        )
    ).first()
    return row[0] if row else None
