"""API fixtures for auth and profile integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from liftcam.api.main import app
from liftcam.core.db import get_async_sessionmaker


@pytest.fixture
def clean_db(migrated_database: str) -> Iterator[None]:
    engine = create_engine(migrated_database)
    with engine.begin() as conn:
        for table in ("reps", "segments", "uploads", "refresh_tokens", "users"):
            conn.execute(text(f"TRUNCATE {table} CASCADE"))
    engine.dispose()
    # Drop cached engines/sessionmakers so they reconnect cleanly after truncate.
    get_async_sessionmaker.cache_clear()
    from liftcam.core.db import get_async_engine

    get_async_engine.cache_clear()
    yield
    get_async_sessionmaker.cache_clear()
    get_async_engine.cache_clear()


@pytest.fixture
async def client(clean_db: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def adult_dob() -> date:
    return date.today() - timedelta(days=365 * 20)


def exactly_thirteen_dob() -> date:
    today = date.today()
    try:
        return today.replace(year=today.year - 13)
    except ValueError:
        return date(today.year - 13, 3, 1)


def under_thirteen_dob() -> date:
    return exactly_thirteen_dob() + timedelta(days=1)


def signup_payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "email": "lifter@example.com",
        "username": "lifter1",
        "password": "password123",
        "dob": adult_dob().isoformat(),
        "height": 70.0,
        "height_unit": "in",
        "weight": 180.0,
        "weight_unit": "lb",
        "sex": "male",
        "squat_max": 315.0,
        "bench_max": 225.0,
        "deadlift_max": 405.0,
    }
    body.update(overrides)
    return body
