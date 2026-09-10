"""Shared fixtures for schema tests. Require local compose Postgres on :5433."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from liftcam.core.db import _to_sync_url
from liftcam.core.models import User
from liftcam.core.settings import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _public_tables(engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                )
            )
        }


@pytest.fixture(scope="session")
def database_url() -> str:
    return _to_sync_url(get_settings().database_direct_url)


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> Iterator[str]:
    """Leave the DB at head after tests so local/dev keep a usable schema."""
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — skip when Docker/Postgres is down
        pytest.skip(f"Postgres not reachable: {exc}")

    cfg = _alembic_config()
    # Prove upgrade/downgrade once, then stay migrated for the rest of the session.
    command.downgrade(cfg, "base")
    assert _public_tables(engine) == set()
    command.upgrade(cfg, "head")
    assert _public_tables(engine) == {
        "users",
        "uploads",
        "segments",
        "reps",
        "refresh_tokens",
    }
    yield database_url
    # Do not downgrade on teardown — keeps compose DB ready for Phase 4+.
    engine.dispose()


@pytest.fixture
def db_session(migrated_database: str) -> Iterator[Session]:
    engine = create_engine(migrated_database)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        # Wipe rows between tests while keeping schema.
        for table in ("reps", "segments", "uploads", "refresh_tokens", "users"):
            session.execute(text(f"TRUNCATE {table} CASCADE"))
        session.commit()
        yield session
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def make_user(session: Session, *, email: str = "a@example.com", username: str = "alice") -> User:
    user = User(
        email=email,
        username=username,
        password_hash="hash",
        auth_provider="email",
        dob=date.today() - timedelta(days=365 * 20),
        height=70.0,
        height_unit="in",
        weight=180.0,
        weight_unit="lb",
        sex="male",
        squat_max=315.0,
        bench_max=225.0,
        deadlift_max=405.0,
    )
    session.add(user)
    session.flush()
    return user
