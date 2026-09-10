"""Auth routes: signup, login, refresh, logout."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from liftcam.api.deps import DbSession
from liftcam.api.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from liftcam.core.identity import find_user_by_verified_identity
from liftcam.core.models import RefreshToken, User
from liftcam.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    mint_refresh_token,
    refresh_expiry,
    verify_password,
)
from liftcam.core.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_token_pair(session: AsyncSession, user: User) -> TokenPair:
    raw_refresh = mint_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_expiry(),
        )
    )
    await session.commit()
    return TokenPair(access_token=create_access_token(user.id), refresh_token=raw_refresh)


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, session: DbSession) -> TokenPair:
    settings = get_settings()
    user = User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
        auth_provider="email",
        dob=body.dob,
        height=body.height,
        height_unit=body.height_unit,
        weight=body.weight,
        weight_unit=body.weight_unit,
        sex=body.sex,
        squat_max=body.squat_max,
        bench_max=body.bench_max,
        deadlift_max=body.deadlift_max,
        profile_picture_url=body.profile_picture_url or settings.default_profile_picture_url,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already in use",
        ) from exc
    return await _issue_token_pair(session, user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, session: DbSession) -> TokenPair:
    user = await find_user_by_verified_identity(session, email=body.email)
    if (
        user is None
        or user.password_hash is None
        or not verify_password(user.password_hash, body.password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return await _issue_token_pair(session, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: DbSession) -> TokenPair:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if stored is None or stored.expires_at <= now:
        if stored is not None:
            await session.delete(stored)
            await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user = await session.get(User, stored.user_id)
    await session.delete(stored)
    if user is None:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return await _issue_token_pair(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, session: DbSession) -> None:
    token_hash = hash_refresh_token(body.refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored is not None:
        await session.delete(stored)
        await session.commit()
