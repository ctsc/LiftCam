"""Integration tests for /me and push token."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import signup_payload


async def _auth_header(client: AsyncClient) -> dict[str, str]:
    resp = await client.post("/auth/signup", json=signup_payload())
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_me_returns_profile_without_password_hash(client: AsyncClient) -> None:
    headers = await _auth_header(client)
    resp = await client.get("/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "lifter@example.com"
    assert body["username"] == "lifter1"
    assert body["favorite_lift"] is None
    assert "password_hash" not in body
    assert "password" not in body


@pytest.mark.asyncio
async def test_patch_me_updates_units_and_favorite(client: AsyncClient) -> None:
    headers = await _auth_header(client)
    resp = await client.patch(
        "/me",
        headers=headers,
        json={
            "favorite_lift": "deadlift",
            "weight_unit": "kg",
            "weight": 82.0,
            "height_unit": "cm",
            "height": 178.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["favorite_lift"] == "deadlift"
    assert body["weight_unit"] == "kg"
    assert body["height_unit"] == "cm"


@pytest.mark.asyncio
async def test_patch_me_rejects_bad_unit(client: AsyncClient) -> None:
    headers = await _auth_header(client)
    resp = await client.patch("/me", headers=headers, json={"weight_unit": "stone"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_push_token_stored(client: AsyncClient, migrated_database: str) -> None:
    headers = await _auth_header(client)
    resp = await client.post(
        "/me/push-token",
        headers=headers,
        json={"token": "ExponentPushToken[abc123]"},
    )
    assert resp.status_code == 204

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from liftcam.core.models import User

    engine = create_engine(migrated_database)
    with sessionmaker(bind=engine)() as session:
        user = session.scalar(select(User).where(User.email == "lifter@example.com"))
        assert user is not None
        assert user.expo_push_token == "ExponentPushToken[abc123]"
    engine.dispose()


@pytest.mark.asyncio
async def test_protected_route_requires_bearer(client: AsyncClient) -> None:
    missing = await client.get("/me")
    assert missing.status_code == 401

    bad = await client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401
