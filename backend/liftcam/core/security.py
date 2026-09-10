"""Password hashing, JWT access tokens, and opaque refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from liftcam.core.settings import Settings, get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> str:
    cfg = settings or get_settings()
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=cfg.access_token_ttl_s)).timestamp()),
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings | None = None) -> uuid.UUID:
    cfg = settings or get_settings()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise ValueError("invalid or expired access token") from exc
    if payload.get("typ") != "access":
        raise ValueError("invalid or expired access token")
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid or expired access token") from exc


def mint_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def refresh_expiry(*, settings: Settings | None = None, now: datetime | None = None) -> datetime:
    cfg = settings or get_settings()
    issued = now or datetime.now(UTC)
    return issued + timedelta(seconds=cfg.refresh_token_ttl_s)
