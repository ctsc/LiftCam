"""Phase 3 schema: migrations, constraints, claim, series round-trip."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from liftcam.core.claim import claim_next_queued_upload
from liftcam.core.db import _to_async_url, _to_sync_url, get_async_engine, get_sync_engine
from liftcam.core.models import Rep, Segment, Upload
from liftcam.core.settings import get_settings
from tests.conftest import make_user


def test_migration_creates_expected_tables(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
        )
    ).all()
    assert {r[0] for r in rows} == {"users", "uploads", "segments", "reps", "refresh_tokens"}

    checks = {
        r[0]
        for r in db_session.execute(
            text("SELECT conname FROM pg_constraint WHERE contype = 'c' AND conname LIKE 'ck_%'")
        )
    }
    assert "ck_uploads_status" in checks
    assert "ck_uploads_failed_stage" in checks
    assert "ck_uploads_failure_code" in checks


def test_duplicate_email_and_username_rejected(db_session: Session) -> None:
    make_user(db_session, email="one@example.com", username="one")
    db_session.commit()

    with pytest.raises(IntegrityError):
        make_user(db_session, email="one@example.com", username="two")
        db_session.commit()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        make_user(db_session, email="two@example.com", username="one")
        db_session.commit()
    db_session.rollback()


def test_upload_status_and_failure_enums_rejected(db_session: Session) -> None:
    user = make_user(db_session)
    bad_status = Upload(
        user_id=user.id,
        status="not_a_status",
        weight=225.0,
        weight_unit="lb",
        user_reps=3,
    )
    db_session.add(bad_status)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    bad_stage = Upload(
        user_id=user.id,
        status="failed",
        weight=225.0,
        weight_unit="lb",
        user_reps=3,
        failed_stage="not_a_stage",
        failure_code="crash",
    )
    db_session.add(bad_stage)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    bad_code = Upload(
        user_id=user.id,
        status="failed",
        weight=225.0,
        weight_unit="lb",
        user_reps=3,
        failed_stage="probe",
        failure_code="not_a_code",
    )
    db_session.add(bad_code)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_reps_series_round_trip(db_session: Session) -> None:
    user = make_user(db_session)
    upload = Upload(
        user_id=user.id,
        status="ready",
        weight=315.0,
        weight_unit="lb",
        user_reps=2,
    )
    db_session.add(upload)
    db_session.flush()
    segment = Segment(upload_id=upload.id, ord=0, start_s=0.0, end_s=8.0)
    db_session.add(segment)
    db_session.flush()

    series = {
        "t": [0.0, 0.033, 0.066],
        "bar_xy": [[0.1, 0.2], [0.11, 0.25], [0.12, 0.3]],
        "hip": [0.5, 0.51, 0.52],
    }
    rep = Rep(
        segment_id=segment.id,
        ord=0,
        start_s=0.5,
        end_s=2.0,
        velocity=0.42,
        faults={"bar_drift": "flagged"},
        confidence=0.9,
        force_estimate=1200.0,
        work_estimate=300.0,
        lockout_ratio=0.95,
        series=series,
    )
    db_session.add(rep)
    db_session.commit()

    loaded = db_session.execute(select(Rep).where(Rep.id == rep.id)).scalar_one()
    assert loaded.series == series


def test_claim_skip_locked_only_one_wins(db_session: Session, migrated_database: str) -> None:
    user = make_user(db_session)
    upload = Upload(
        user_id=user.id,
        status="queued",
        weight=225.0,
        weight_unit="lb",
        user_reps=1,
    )
    db_session.add(upload)
    db_session.commit()
    upload_id = upload.id

    results: list[uuid.UUID | None] = []
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        engine = create_engine(migrated_database)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            claimed = claim_next_queued_upload(session)
            session.commit()
            results.append(claimed.id if claimed else None)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            session.rollback()
        finally:
            session.close()
            engine.dispose()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors
    assert results.count(upload_id) == 1
    assert results.count(None) == 1

    db_session.expire_all()
    refreshed = db_session.get(Upload, upload_id)
    assert refreshed is not None
    assert refreshed.status == "processing"
    assert refreshed.claimed_at is not None


def test_async_and_sync_engines_use_distinct_settings_urls() -> None:
    settings = get_settings()
    assert _to_async_url(settings.database_url).startswith("postgresql+asyncpg://")
    assert _to_sync_url(settings.database_direct_url).startswith("postgresql+psycopg://")

    # Engines construct without connecting; connection is covered by migrated tests.
    async_engine = get_async_engine()
    sync_engine = get_sync_engine()
    assert async_engine is not sync_engine


def test_refresh_token_table_exists(db_session: Session) -> None:
    from liftcam.core.models import RefreshToken

    user = make_user(db_session)
    token = RefreshToken(
        user_id=user.id,
        token_hash="abc123",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(token)
    db_session.commit()
    assert db_session.get(RefreshToken, token.id) is not None
