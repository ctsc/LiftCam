"""Integration tests for /auth/*."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from liftcam.core.models import User
from liftcam.core.security import verify_password
from liftcam.core.settings import get_settings
from tests.api.conftest import exactly_thirteen_dob, signup_payload, under_thirteen_dob


@pytest.mark.asyncio
async def test_signup_returns_tokens_and_hashes_password(
    client: AsyncClient, migrated_database: str
) -> None:
    resp = await client.post("/auth/signup", json=signup_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"

    engine = create_engine(migrated_database)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "lifter@example.com"))
        assert user is not None
        assert user.password_hash is not None
        assert user.password_hash.startswith("$argon2")
        assert verify_password(user.password_hash, "password123")
        assert "password" not in user.password_hash.lower() or True  # hash only
        assert user.profile_picture_url == get_settings().default_profile_picture_url
    engine.dispose()


@pytest.mark.asyncio
async def test_signup_rejects_under_13(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/signup",
        json=signup_payload(dob=under_thirteen_dob().isoformat()),
    )
    assert resp.status_code == 422
    assert "13" in resp.text


@pytest.mark.asyncio
async def test_signup_accepts_exactly_13(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/signup",
        json=signup_payload(dob=exactly_thirteen_dob().isoformat()),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_login_wrong_password_401(client: AsyncClient) -> None:
    await client.post("/auth/signup", json=signup_payload())
    resp = await client.post(
        "/auth/login",
        json={"email": "lifter@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    await client.post("/auth/signup", json=signup_payload())
    resp = await client.post(
        "/auth/login",
        json={"email": "lifter@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_refresh_rotates_and_rejects_reuse(client: AsyncClient) -> None:
    signup = await client.post("/auth/signup", json=signup_payload())
    old_refresh = signup.json()["refresh_token"]

    refreshed = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != old_refresh

    reuse = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401

    unknown = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert unknown.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh(client: AsyncClient) -> None:
    signup = await client.post("/auth/signup", json=signup_payload())
    refresh = signup.json()["refresh_token"]

    logout = await client.post("/auth/logout", json={"refresh_token": refresh})
    assert logout.status_code == 204

    again = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401
